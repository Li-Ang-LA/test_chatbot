from sqlalchemy import select

from app.models import Message, MessageRole, User
from app.models import Session as ChatSession


def _make_user(db, email: str, username: str) -> User:
    user = User(email=email, username=username, password_hash="hashed")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_session_roundtrip_with_messages(db_session):
    user = _make_user(db_session, "alice@example.com", "alice")

    chat = ChatSession(user_id=user.id, title="First chat")
    chat.messages.append(Message(role=MessageRole.user, content="hi"))
    chat.messages.append(Message(role=MessageRole.assistant, content="hello"))
    db_session.add(chat)
    db_session.commit()

    fetched = db_session.execute(select(ChatSession)).scalar_one()
    assert fetched.title == "First chat"
    assert fetched.user_id == user.id
    assert fetched.claude_session_id is None
    assert fetched.system_prompt is None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert [m.role for m in fetched.messages] == [
        MessageRole.user,
        MessageRole.assistant,
    ]
    assert [m.content for m in fetched.messages] == ["hi", "hello"]


def test_deleting_session_cascades_to_messages(db_session):
    user = _make_user(db_session, "alice@example.com", "alice")
    chat = ChatSession(user_id=user.id, title="Chat")
    chat.messages.append(Message(role=MessageRole.user, content="hey"))
    chat.messages.append(Message(role=MessageRole.assistant, content="yo"))
    db_session.add(chat)
    db_session.commit()

    assert db_session.execute(select(Message)).scalars().all()

    db_session.delete(chat)
    db_session.commit()

    assert db_session.execute(select(ChatSession)).scalars().all() == []
    assert db_session.execute(select(Message)).scalars().all() == []


def test_deleting_user_cascades_to_sessions_and_messages(db_session):
    user = _make_user(db_session, "alice@example.com", "alice")
    chat = ChatSession(user_id=user.id, title="Chat")
    chat.messages.append(Message(role=MessageRole.user, content="hey"))
    db_session.add(chat)
    db_session.commit()

    db_session.delete(user)
    db_session.commit()

    assert db_session.execute(select(ChatSession)).scalars().all() == []
    assert db_session.execute(select(Message)).scalars().all() == []


def test_cross_user_isolation(db_session):
    alice = _make_user(db_session, "alice@example.com", "alice")
    bob = _make_user(db_session, "bob@example.com", "bob")

    db_session.add(ChatSession(user_id=alice.id, title="Alice chat"))
    db_session.add(ChatSession(user_id=bob.id, title="Bob chat"))
    db_session.commit()

    alice_sessions = (
        db_session.execute(select(ChatSession).where(ChatSession.user_id == alice.id))
        .scalars()
        .all()
    )
    assert [s.title for s in alice_sessions] == ["Alice chat"]

    bob_sessions = (
        db_session.execute(select(ChatSession).where(ChatSession.user_id == bob.id))
        .scalars()
        .all()
    )
    assert [s.title for s in bob_sessions] == ["Bob chat"]
