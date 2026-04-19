import pytest

from app.models import Message, MessageRole
from app.models import Session as ChatSession

ALICE = {"email": "alice@example.com", "username": "alice", "password": "pw-alice-123"}
BOB = {"email": "bob@example.com", "username": "bob", "password": "pw-bob-123"}


def _signup(client, payload):
    resp = client.post("/auth/signup", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _logout(client):
    client.post("/auth/logout")
    client.cookies.clear()


def _login(client, payload):
    client.cookies.clear()
    resp = client.post(
        "/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert resp.status_code == 200, resp.text


@pytest.fixture
def alice_client(client):
    _signup(client, ALICE)
    return client


def test_endpoints_require_authentication(client):
    for method, path in [
        ("GET", "/sessions"),
        ("POST", "/sessions"),
        ("GET", "/sessions/1"),
        ("PATCH", "/sessions/1"),
        ("DELETE", "/sessions/1"),
    ]:
        resp = client.request(method, path, json={} if method == "PATCH" else None)
        assert resp.status_code == 401, f"{method} {path} -> {resp.status_code}"


def test_create_session_defaults_to_new_chat(alice_client):
    resp = alice_client.post("/sessions")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "New chat"
    assert body["system_prompt"] is None
    assert body["claude_session_id"] is None
    assert isinstance(body["id"], int)


def test_create_session_accepts_title_and_system_prompt(alice_client):
    resp = alice_client.post(
        "/sessions",
        json={"title": "Trip planning", "system_prompt": "You are concise."},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Trip planning"
    assert body["system_prompt"] == "You are concise."


def test_list_sessions_returns_only_current_user_sessions_ordered(alice_client, client):
    a1 = alice_client.post("/sessions", json={"title": "Alice A"}).json()
    a2 = alice_client.post("/sessions", json={"title": "Alice B"}).json()

    _logout(alice_client)
    _signup(client, BOB)
    client.post("/sessions", json={"title": "Bob only"})

    _logout(client)
    _login(client, ALICE)
    body = client.get("/sessions").json()

    titles = [s["title"] for s in body]
    assert titles == ["Alice B", "Alice A"]
    assert {s["id"] for s in body} == {a1["id"], a2["id"]}


def test_get_session_returns_session_with_messages(alice_client, db_session):
    created = alice_client.post("/sessions", json={"title": "With history"}).json()

    chat = db_session.get(ChatSession, created["id"])
    chat.messages.append(Message(role=MessageRole.user, content="hi"))
    chat.messages.append(Message(role=MessageRole.assistant, content="hello"))
    db_session.commit()

    body = alice_client.get(f"/sessions/{created['id']}").json()
    assert body["title"] == "With history"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert [m["content"] for m in body["messages"]] == ["hi", "hello"]


def test_get_session_of_another_user_returns_404(alice_client, client):
    alice_chat = alice_client.post("/sessions").json()

    _logout(alice_client)
    _signup(client, BOB)
    resp = client.get(f"/sessions/{alice_chat['id']}")
    assert resp.status_code == 404


def test_patch_rename_persists(alice_client):
    created = alice_client.post("/sessions").json()

    resp = alice_client.patch(f"/sessions/{created['id']}", json={"title": "Renamed!"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed!"

    fetched = alice_client.get(f"/sessions/{created['id']}").json()
    assert fetched["title"] == "Renamed!"


def test_patch_updates_system_prompt_and_leaves_title(alice_client):
    created = alice_client.post("/sessions", json={"title": "Original"}).json()
    resp = alice_client.patch(
        f"/sessions/{created['id']}", json={"system_prompt": "Be terse."}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["system_prompt"] == "Be terse."
    assert body["title"] == "Original"


def test_patch_empty_payload_returns_400(alice_client):
    created = alice_client.post("/sessions").json()
    resp = alice_client.patch(f"/sessions/{created['id']}", json={})
    assert resp.status_code == 400


def test_patch_of_another_user_returns_404(alice_client, client):
    alice_chat = alice_client.post("/sessions").json()
    _logout(alice_client)
    _signup(client, BOB)
    resp = client.patch(f"/sessions/{alice_chat['id']}", json={"title": "Pwned"})
    assert resp.status_code == 404


def test_delete_removes_session_and_messages(alice_client, db_session):
    created = alice_client.post("/sessions").json()
    chat = db_session.get(ChatSession, created["id"])
    chat.messages.append(Message(role=MessageRole.user, content="bye"))
    db_session.commit()

    resp = alice_client.delete(f"/sessions/{created['id']}")
    assert resp.status_code == 204

    db_session.expire_all()
    assert db_session.get(ChatSession, created["id"]) is None
    remaining = [
        m for m in db_session.query(Message).all() if m.session_id == created["id"]
    ]
    assert remaining == []

    # Second delete should 404.
    assert alice_client.delete(f"/sessions/{created['id']}").status_code == 404


def test_delete_of_another_user_returns_404(alice_client, client):
    alice_chat = alice_client.post("/sessions").json()
    _logout(alice_client)
    _signup(client, BOB)
    resp = client.delete(f"/sessions/{alice_chat['id']}")
    assert resp.status_code == 404
