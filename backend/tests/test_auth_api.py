from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import verify_password
from app.db import Base, get_db
from app.main import app
from app.models import User

VALID_PAYLOAD = {
    "email": "alice@example.com",
    "username": "alice",
    "password": "correct-horse-battery",
}


def test_signup_sets_cookie_and_me_returns_user(client):
    resp = client.post("/auth/signup", json=VALID_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == VALID_PAYLOAD["email"]
    assert body["username"] == VALID_PAYLOAD["username"]
    assert "password" not in body
    assert "password_hash" not in body
    assert "auth_token" in resp.cookies

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == VALID_PAYLOAD["email"]


def test_signup_cookie_flags_httponly_and_samesite_lax(client):
    resp = client.post("/auth/signup", json=VALID_PAYLOAD)
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


def test_signup_duplicate_email_returns_409(client):
    assert client.post("/auth/signup", json=VALID_PAYLOAD).status_code == 201
    dup = {**VALID_PAYLOAD, "username": "alice2"}
    assert client.post("/auth/signup", json=dup).status_code == 409


def test_signup_duplicate_username_returns_409(client):
    assert client.post("/auth/signup", json=VALID_PAYLOAD).status_code == 201
    dup = {**VALID_PAYLOAD, "email": "other@example.com"}
    assert client.post("/auth/signup", json=dup).status_code == 409


def test_signup_invalid_email_returns_422(client):
    resp = client.post("/auth/signup", json={**VALID_PAYLOAD, "email": "nope"})
    assert resp.status_code == 422


def test_signup_short_password_returns_422(client):
    resp = client.post("/auth/signup", json={**VALID_PAYLOAD, "password": "short"})
    assert resp.status_code == 422


def test_login_success_sets_cookie(client):
    client.post("/auth/signup", json=VALID_PAYLOAD)
    client.cookies.clear()

    resp = client.post(
        "/auth/login",
        json={"email": VALID_PAYLOAD["email"], "password": VALID_PAYLOAD["password"]},
    )
    assert resp.status_code == 200
    assert "auth_token" in resp.cookies


def test_login_wrong_password_returns_401(client):
    client.post("/auth/signup", json=VALID_PAYLOAD)
    client.cookies.clear()

    resp = client.post(
        "/auth/login",
        json={"email": VALID_PAYLOAD["email"], "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert "auth_token" not in resp.cookies


def test_login_unknown_email_returns_401(client):
    resp = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "whatever-123"},
    )
    assert resp.status_code == 401


def test_me_without_cookie_returns_401(client):
    assert client.get("/auth/me").status_code == 401


def test_me_with_invalid_cookie_returns_401(client):
    client.cookies.set("auth_token", "not-a-real-jwt")
    assert client.get("/auth/me").status_code == 401


def test_logout_clears_cookie(client):
    client.post("/auth/signup", json=VALID_PAYLOAD)
    assert client.get("/auth/me").status_code == 200

    assert client.post("/auth/logout").status_code == 204
    client.cookies.clear()
    assert client.get("/auth/me").status_code == 401


def test_signup_persists_bcrypt_hash_not_plaintext(tmp_path):
    """Drive signup through the HTTP layer, then inspect the row directly:
    the stored hash must not equal the plaintext and must verify via bcrypt."""
    db_file = tmp_path / "app.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override() -> Generator[Session, None, None]:
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as c:
            assert c.post("/auth/signup", json=VALID_PAYLOAD).status_code == 201

        with TestingSession() as inspect:
            user = inspect.execute(
                select(User).filter_by(email=VALID_PAYLOAD["email"])
            ).scalar_one()
            assert user.password_hash != VALID_PAYLOAD["password"]
            assert user.password_hash.startswith("$2")
            assert verify_password(VALID_PAYLOAD["password"], user.password_hash)
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
