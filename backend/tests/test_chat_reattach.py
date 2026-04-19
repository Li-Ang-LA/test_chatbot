"""Tests for GET /sessions/:id/messages/stream (issue #52).

The endpoint lets the frontend reattach to an in-flight Claude turn when
the user navigates back to a session whose POST has already been aborted.
We drive `_ActiveTurn` and `_run_turn_task` directly here because httpx's
`ASGITransport` buffers streaming responses — which masks the precise
event ordering we want to assert."""

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


async def _signup_alice(client: httpx.AsyncClient) -> int:
    resp = await client.post("/auth/signup", json=ALICE)
    assert resp.status_code == 201, resp.text
    resp = await client.post("/sessions")
    assert resp.status_code == 201
    return resp.json()["id"]


def _parse_sse(body: bytes) -> list[tuple[str, str]]:
    """Return [(event, raw_data)] pairs from a full SSE response body."""
    import json

    out: list[tuple[str, str]] = []
    for chunk in body.decode().split("\n\n"):
        if not chunk.strip():
            continue
        event = None
        data_lines: list[str] = []
        for line in chunk.splitlines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        assert event is not None
        out.append((event, json.loads("\n".join(data_lines)) if data_lines else {}))
    return out


def _seed_turn(
    session_id: int, buffer: list[str] | None = None
) -> sessions_route._ActiveTurn:
    turn = sessions_route._ActiveTurn()
    if buffer:
        turn.buffer.extend(buffer)
    sessions_route._active_turns[session_id] = turn
    return turn


# -------- HTTP: idle case -------------------------------------------------


async def test_attach_with_no_active_turn_returns_empty_stream(
    async_client: httpx.AsyncClient,
) -> None:
    sid = await _signup_alice(async_client)

    resp = await async_client.get(f"/sessions/{sid}/messages/stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    # No active turn → no events, stream closed.
    assert resp.content == b""


# -------- HTTP: auth / ownership ------------------------------------------


async def test_attach_requires_auth(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.get("/sessions/1/messages/stream")
    assert resp.status_code == 401


async def test_attach_to_other_users_session_is_404(
    async_client: httpx.AsyncClient, db_session: Session
) -> None:
    await _signup_alice(async_client)
    # Bob's session, seeded directly.
    bob = User(email="bob@example.com", username="bob", password_hash="h")
    db_session.add(bob)
    db_session.commit()
    bob_chat = ChatSession(user_id=bob.id, title="B")
    db_session.add(bob_chat)
    db_session.commit()

    resp = await async_client.get(f"/sessions/{bob_chat.id}/messages/stream")
    assert resp.status_code == 404


# -------- direct: replay + tail ------------------------------------------


async def test_subscriber_receives_replay_then_live_deltas_then_done(
    _engine: Engine,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mid-stream subscriber must see (a) a replay delta with everything
    the task has already produced, (b) any further live deltas, and (c) the
    terminal done event."""
    TestingSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

    user = User(email="a@a.com", username="a", password_hash="h")
    db_session.add(user)
    db_session.commit()
    chat = ChatSession(user_id=user.id, title="T", claude_session_id="claude-sid")
    db_session.add(chat)
    db_session.commit()
    sid = chat.id

    gate = asyncio.Event()

    async def fake_send(session_id: str, prompt: str, **_: Any):
        # First batch of deltas emitted before the subscriber attaches.
        yield StreamEvent(type="text_delta", text="Hello")
        yield StreamEvent(type="text_delta", text=" ")
        yield StreamEvent(type="text_delta", text="world")
        await gate.wait()
        # Tail delta arriving after attach.
        yield StreamEvent(type="text_delta", text="!")
        yield StreamEvent(type="message_done")

    monkeypatch.setattr(claude_runner, "send_message", fake_send)

    sessions_route._active_turns.clear()
    turn = sessions_route._ActiveTurn()
    # First subscriber so the task has someone to broadcast to — but we
    # drain it separately so we don't interfere with the reattach subscriber.
    original_sub: asyncio.Queue = asyncio.Queue()
    turn.subscribers.append(original_sub)
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

    # Drain the three pre-gate deltas on the original subscriber so the
    # task can proceed to the gate.
    for _ in range(3):
        await asyncio.wait_for(original_sub.get(), timeout=1.0)

    # Now attach a reattach subscriber — mimics what the new GET handler does.
    late_sub: asyncio.Queue = asyncio.Queue()
    buffer_snapshot = "".join(turn.buffer)
    turn.subscribers.append(late_sub)
    if buffer_snapshot:
        late_sub.put_nowait(("delta", {"text": buffer_snapshot}))

    # Release the gate so the task emits the tail delta + done.
    gate.set()

    # Also drain the original subscriber through the end so the task
    # actually progresses (both subscribers must be read).
    async def drain(q: asyncio.Queue) -> list[tuple[str, dict] | None]:
        items = []
        while True:
            item = await asyncio.wait_for(q.get(), timeout=2.0)
            items.append(item)
            if item is None:
                return items
            ev, _ = item
            if ev in ("done", "error"):
                # Task will still push a None sentinel from _signal_end.
                pass

    late_items, _original_items = await asyncio.gather(
        drain(late_sub), drain(original_sub)
    )
    await asyncio.wait_for(task, timeout=2.0)

    # Expected on late subscriber: replay delta, live delta, done, None sentinel.
    non_sentinel = [i for i in late_items if i is not None]
    assert len(non_sentinel) == 3
    assert non_sentinel[0] == ("delta", {"text": "Hello world"})
    assert non_sentinel[1] == ("delta", {"text": "!"})
    assert non_sentinel[2] == ("done", {"text": "Hello world!"})


async def test_multiple_subscribers_see_same_live_events(
    _engine: Engine,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    TestingSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    user = User(email="a@a.com", username="a", password_hash="h")
    db_session.add(user)
    db_session.commit()
    chat = ChatSession(user_id=user.id, title="T", claude_session_id="claude-sid")
    db_session.add(chat)
    db_session.commit()
    sid = chat.id

    async def fake_send(session_id: str, prompt: str, **_: Any):
        yield StreamEvent(type="text_delta", text="a")
        yield StreamEvent(type="text_delta", text="b")
        yield StreamEvent(type="message_done")

    monkeypatch.setattr(claude_runner, "send_message", fake_send)

    sessions_route._active_turns.clear()
    turn = sessions_route._ActiveTurn()
    sub_a: asyncio.Queue = asyncio.Queue()
    sub_b: asyncio.Queue = asyncio.Queue()
    turn.subscribers.extend([sub_a, sub_b])
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

    async def collect(q: asyncio.Queue) -> list:
        out = []
        while True:
            item = await asyncio.wait_for(q.get(), timeout=1.0)
            if item is None:
                return out
            out.append(item)

    items_a, items_b = await asyncio.gather(collect(sub_a), collect(sub_b))
    await task

    assert items_a == items_b
    assert [ev for ev, _ in items_a] == ["delta", "delta", "done"]


async def test_subscriber_leaving_doesnt_stop_task(
    _engine: Engine,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies the underlying property #52 relies on: if a subscriber
    disappears mid-turn, the other subscribers still receive done and the
    assistant message still gets persisted."""
    TestingSession = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    user = User(email="a@a.com", username="a", password_hash="h")
    db_session.add(user)
    db_session.commit()
    chat = ChatSession(user_id=user.id, title="T", claude_session_id="claude-sid")
    db_session.add(chat)
    db_session.commit()
    sid = chat.id

    gate = asyncio.Event()

    async def fake_send(session_id: str, prompt: str, **_: Any):
        yield StreamEvent(type="text_delta", text="first ")
        await gate.wait()
        yield StreamEvent(type="text_delta", text="second")
        yield StreamEvent(type="message_done")

    monkeypatch.setattr(claude_runner, "send_message", fake_send)

    sessions_route._active_turns.clear()
    turn = sessions_route._ActiveTurn()
    leaving: asyncio.Queue = asyncio.Queue()
    staying: asyncio.Queue = asyncio.Queue()
    turn.subscribers.extend([leaving, staying])
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

    # Both see the first delta.
    assert await asyncio.wait_for(leaving.get(), timeout=1.0) == (
        "delta",
        {"text": "first "},
    )
    assert await asyncio.wait_for(staying.get(), timeout=1.0) == (
        "delta",
        {"text": "first "},
    )

    # `leaving` disconnects.
    turn.subscribers.remove(leaving)

    # Release the gate — task continues.
    gate.set()

    # `staying` receives everything remaining.
    items: list = []
    while True:
        item = await asyncio.wait_for(staying.get(), timeout=2.0)
        if item is None:
            break
        items.append(item)
    await asyncio.wait_for(task, timeout=2.0)

    assert items == [
        ("delta", {"text": "second"}),
        ("done", {"text": "first second"}),
    ]

    # And the assistant message was persisted.
    db_session.expire_all()
    msgs = db_session.query(Message).filter_by(session_id=sid).all()
    assert [(m.role, m.content) for m in msgs] == [
        (MessageRole.assistant, "first second"),
    ]


# -------- HTTP end-to-end: replay delivered when attaching to a seeded turn


async def test_http_attach_delivers_replay_from_seeded_buffer(
    async_client: httpx.AsyncClient,
) -> None:
    """Seed an _ActiveTurn with a non-empty buffer and a task that emits
    one more delta then done, so the GET handler must deliver:
    replay-delta + live-delta + done. Uses an in-memory fake task so we
    don't depend on claude_runner."""
    sid = await _signup_alice(async_client)

    sessions_route._active_turns.clear()
    turn = sessions_route._ActiveTurn()
    turn.buffer.extend(["Hel", "lo"])
    sessions_route._active_turns[sid] = turn

    async def fake_task():
        # Wait for at least one subscriber to attach before emitting so the
        # replay has a deterministic effect, then emit a live delta + done.
        while not turn.subscribers:
            await asyncio.sleep(0.01)
        turn.buffer.append("!")
        sessions_route._broadcast(turn, "delta", {"text": "!"})
        turn.status = "done"
        sessions_route._broadcast(turn, "done", {"text": "Hello!"})
        sessions_route._signal_end(turn)
        sessions_route._active_turns.pop(sid, None)

    turn.task = asyncio.create_task(fake_task())

    resp = await async_client.get(f"/sessions/{sid}/messages/stream")
    assert resp.status_code == 200
    events = _parse_sse(resp.content)

    assert [e for e, _ in events] == ["delta", "delta", "done"]
    assert events[0][1] == {"text": "Hello"}  # replay of the buffer
    assert events[1][1] == {"text": "!"}  # live delta
    assert events[2][1] == {"text": "Hello!"}  # done
    await turn.task
