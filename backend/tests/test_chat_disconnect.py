"""Tests for issue #50: the Claude turn must complete and persist the
assistant message even when the client disconnects mid-stream.

Note on test shape: httpx's `ASGITransport` buffers the full response body
before delivering any chunks to the client, so a naive "read one chunk,
break out of the stream" pattern does NOT actually reproduce a mid-stream
disconnect at the server — the server-side task has already finished by
the time the client receives anything. To test the real disconnect
behaviour we drive `_run_turn_task` directly (the HTTP-level tests would
accidentally pass even without the detached-task fix)."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import claude_runner
from app.api.routes import sessions as sessions_route
from app.claude_runner import StreamEvent
from app.db import Base, get_db, get_session_factory
from app.main import app
from app.models import Message, MessageRole, User
from app.models import Session as ChatSession

ALICE = {"email": "alice@example.com", "username": "alice", "password": "pw-alice-123"}


@pytest.fixture
def _engine() -> Generator[Engine, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(_engine: Engine) -> Generator[Session, None, None]:
    TestingSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    s = TestingSession()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
async def async_client(_engine: Engine) -> AsyncGenerator[httpx.AsyncClient, None]:
    TestingSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: TestingSession
    sessions_route._active_turns.clear()
    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_session_factory, None)


async def _signup_alice(client: httpx.AsyncClient) -> None:
    resp = await client.post("/auth/signup", json=ALICE)
    assert resp.status_code == 201, resp.text


async def _create_session(client: httpx.AsyncClient) -> int:
    resp = await client.post("/sessions")
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _patch_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pre_delta_delay: float = 0.0,
    pre_done_delay: float = 0.0,
) -> None:
    """Patch claude_runner so every turn emits one delta then done, with
    configurable delays for disconnect-timing scenarios."""

    async def fake_start(system_prompt: str | None = None, **_: Any) -> str:
        return "claude-sid"

    async def fake_send(session_id: str, prompt: str, **_: Any):
        if pre_delta_delay:
            await asyncio.sleep(pre_delta_delay)
        yield StreamEvent(type="text_delta", text=f"reply to {prompt}")
        if pre_done_delay:
            await asyncio.sleep(pre_done_delay)
        yield StreamEvent(type="message_done")

    monkeypatch.setattr(claude_runner, "start_session", fake_start)
    monkeypatch.setattr(claude_runner, "send_message", fake_send)


async def _wait_for_turn_to_finish(session_id: int, timeout: float = 2.0) -> None:
    """Poll the module registry until the turn for `session_id` is gone
    (task finished and unregistered itself)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while session_id in sessions_route._active_turns:
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(
                f"turn for session {session_id} did not finish within {timeout}s"
            )
        await asyncio.sleep(0.02)


# -------- disconnect-survival --------------------------------------------


async def test_assistant_message_persists_after_client_disconnect(
    async_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client reads the first delta, then bails. The detached task must
    still reach `message_done` and persist the assistant message."""
    await _signup_alice(async_client)
    sid = await _create_session(async_client)
    # Delay `done` so we can disconnect between the delta and the final
    # persistence.
    _patch_runner(monkeypatch, pre_done_delay=0.3)

    async with async_client.stream(
        "POST", f"/sessions/{sid}/messages", json={"content": "hi"}
    ) as r:
        assert r.status_code == 200
        # Read one SSE event (the delta) then break to simulate client going away.
        async for _ in r.aiter_bytes():
            break
    # Exiting the `async with` aborts the underlying HTTP stream.

    await _wait_for_turn_to_finish(sid)

    msgs = (
        db_session.query(Message).filter_by(session_id=sid).order_by(Message.id).all()
    )
    assert [(m.role, m.content) for m in msgs] == [
        (MessageRole.user, "hi"),
        (MessageRole.assistant, "reply to hi"),
    ]


async def test_get_session_after_disconnect_includes_assistant_reply(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate the UI flow: user sends, navigates away mid-stream, then
    refetches the session. The assistant reply must be there."""
    await _signup_alice(async_client)
    sid = await _create_session(async_client)
    _patch_runner(monkeypatch, pre_done_delay=0.2)

    async with async_client.stream(
        "POST", f"/sessions/{sid}/messages", json={"content": "status?"}
    ) as r:
        assert r.status_code == 200
        async for _ in r.aiter_bytes():
            break  # disconnect after first event

    await _wait_for_turn_to_finish(sid)

    resp = await async_client.get(f"/sessions/{sid}")
    assert resp.status_code == 200
    roles = [m["role"] for m in resp.json()["messages"]]
    contents = [m["content"] for m in resp.json()["messages"]]
    assert roles == ["user", "assistant"]
    assert contents == ["status?", "reply to status?"]


# -------- direct unit test of subscriber-independence -------------------
#
# This is the only place we can *genuinely* simulate "subscriber goes away
# mid-stream" without the ASGITransport buffering issue — we drive
# _run_turn_task directly and remove the subscriber from the live list
# after one delta.


async def test_run_turn_task_keeps_running_after_subscriber_leaves(
    _engine: Engine,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    TestingSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    # Seed a user + session directly so we don't go through HTTP auth.
    user = User(email="bob@example.com", username="bob", password_hash="h")
    db_session.add(user)
    db_session.commit()
    chat = ChatSession(user_id=user.id, title="T", claude_session_id="claude-sid")
    db_session.add(chat)
    db_session.commit()
    sid = chat.id

    # Gate the task: delta is emitted, then we wait on an Event before done.
    gate = asyncio.Event()

    async def fake_send(session_id: str, prompt: str, **_: Any):
        yield StreamEvent(type="text_delta", text="hello ")
        await gate.wait()
        yield StreamEvent(type="text_delta", text="world")
        yield StreamEvent(type="message_done")

    monkeypatch.setattr(claude_runner, "send_message", fake_send)

    sessions_route._active_turns.clear()
    turn = sessions_route._ActiveTurn()
    sub: asyncio.Queue = asyncio.Queue()
    turn.subscribers.append(sub)
    sessions_route._active_turns[sid] = turn

    task = asyncio.create_task(
        sessions_route._run_turn_task(
            session_id=sid,
            claude_session_id="claude-sid",
            prompt="hi",
            turn=turn,
            session_factory=TestingSession,
        )
    )
    turn.task = task

    # Subscriber receives the first delta, then "disconnects" by removing
    # itself from the live-subscribers list.
    first = await asyncio.wait_for(sub.get(), timeout=1.0)
    assert first == ("delta", {"text": "hello "})
    turn.subscribers.remove(sub)

    # While the subscriber is gone, a re-POST would still see the turn and
    # get 409. Verify by inspecting the registry directly.
    assert sid in sessions_route._active_turns

    # Release the gate and let the task run to completion.
    gate.set()
    await asyncio.wait_for(task, timeout=2.0)

    # Task unregistered itself on exit.
    assert sid not in sessions_route._active_turns

    # Assistant message got persisted even though no subscriber was
    # watching when `done` fired.
    db_session.expire_all()
    msgs = (
        db_session.query(Message).filter_by(session_id=sid).order_by(Message.id).all()
    )
    assert [(m.role, m.content) for m in msgs] == [
        (MessageRole.assistant, "hello world"),
    ]


# -------- no crosstalk between detached tasks ----------------------------


async def test_parallel_detached_tasks_persist_to_correct_session(
    async_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two sessions, both clients disconnect mid-stream. Each session's
    assistant reply must still land in the right session."""
    await _signup_alice(async_client)
    sid_a = await _create_session(async_client)
    sid_b = await _create_session(async_client)
    _patch_runner(monkeypatch, pre_done_delay=0.2)

    async def start_and_disconnect(sid: int, content: str) -> None:
        async with async_client.stream(
            "POST", f"/sessions/{sid}/messages", json={"content": content}
        ) as r:
            assert r.status_code == 200
            async for _ in r.aiter_bytes():
                break

    await asyncio.gather(
        start_and_disconnect(sid_a, "question A"),
        start_and_disconnect(sid_b, "question B"),
    )

    await _wait_for_turn_to_finish(sid_a)
    await _wait_for_turn_to_finish(sid_b)

    msgs_a = [
        m.content
        for m in db_session.query(Message)
        .filter_by(session_id=sid_a)
        .order_by(Message.id)
        .all()
    ]
    msgs_b = [
        m.content
        for m in db_session.query(Message)
        .filter_by(session_id=sid_b)
        .order_by(Message.id)
        .all()
    ]
    assert msgs_a == ["question A", "reply to question A"]
    assert msgs_b == ["question B", "reply to question B"]
