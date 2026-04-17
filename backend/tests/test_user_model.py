import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import User


def test_user_roundtrip_by_email(db_session):
    user = User(
        email="alice@example.com",
        username="alice",
        password_hash="hashed",
    )
    db_session.add(user)
    db_session.commit()

    fetched = db_session.execute(
        select(User).filter_by(email="alice@example.com")
    ).scalar_one()
    assert fetched.id == user.id
    assert fetched.email == "alice@example.com"
    assert fetched.username == "alice"
    assert fetched.created_at is not None


def test_duplicate_email_raises_integrity_error(db_session):
    db_session.add(User(email="dup@example.com", username="first", password_hash="h1"))
    db_session.commit()

    db_session.add(User(email="dup@example.com", username="second", password_hash="h2"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_duplicate_username_raises_integrity_error(db_session):
    db_session.add(User(email="a@example.com", username="samename", password_hash="h1"))
    db_session.commit()

    db_session.add(User(email="b@example.com", username="samename", password_hash="h2"))
    with pytest.raises(IntegrityError):
        db_session.commit()
