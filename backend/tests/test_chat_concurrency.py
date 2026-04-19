"""Concurrency tests for POST /sessions/:id/messages.

Covers issue #16:
 - Two turns on *different* sessions stream in parallel (not serialized).
 - A second turn on the *same* session while one is in flight returns 409.
 - Assistant replies land in the right session's message list after parallel run.
"""

import asyncio
import time
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
from app.db import Base, get_db
from app.main import app
from app.models import Message, MessageRole

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
    # Clear the module-level session-lock registry between tests so state
    # from an earlier test can't leak into this one.
    sessions_route._session_locks.clear()
    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


async def _signup_alice(client: httpx.AsyncClient) -> None:
    resp = await client.post("/auth/signup", json=ALICE)
    assert resp.status_code == 201, resp.text


async def _create_session(client: httpx.AsyncClient) -> int:
    resp = await client.post("/sessions")
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _patch_runner(monkeypatch: pytest.MonkeyPatch, *, send_delay: float) -> None:
    """Patch claude_runner with a fake that sleeps for `send_delay` seconds
    before emitting a single delta and a done event. start_session is instant.
    """

    async def fake_start(system_prompt: str | None = None, **_: Any) -> str:
        return "claude-sid"

    async def fake_send(session_id: str, prompt: str, **_: Any):
        await asyncio.sleep(send_delay)
        yield StreamEvent(type="text_delta", text=f"reply to {prompt}")
        yield StreamEvent(type="message_done")

    monkeypatch.setattr(claude_runner, "start_session", fake_start)
    monkeypatch.setattr(claude_runner, "send_message", fake_send)


async def _consume_post(
    client: httpx.AsyncClient, session_id: int, content: str
) -> tuple[int, bytes]:
    async with client.stream(
        "POST", f"/sessions/{session_id}/messages", json={"content": content}
    ) as r:
        body = b""
        async for chunk in r.aiter_bytes():
            body += chunk
        return r.status_code, body


# -------- parallel across different sessions ------------------------------


async def test_parallel_sends_to_different_sessions_dont_serialize(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _signup_alice(async_client)
    sid_a = await _create_session(async_client)
    sid_b = await _create_session(async_client)

    send_delay = 0.3
    _patch_runner(monkeypatch, send_delay=send_delay)

    start = time.perf_counter()
    (status_a, _), (status_b, _) = await asyncio.gather(
        _consume_post(async_client, sid_a, "hi A"),
        _consume_post(async_client, sid_b, "hi B"),
    )
    elapsed = time.perf_counter() - start

    assert status_a == 200
    assert status_b == 200
    # Serial would be ~2 * send_delay; parallel should be ~send_delay.
    # Allow generous headroom for scheduler jitter.
    assert elapsed < 2 * send_delay * 0.85, (
        f"expected parallel execution, got elapsed={elapsed:.3f}s "
        f"(serial baseline would be ~{2 * send_delay:.3f}s)"
    )


# -------- same-session 409 -----------------------------------------------


async def test_second_concurrent_send_to_same_session_returns_409(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _signup_alice(async_client)
    sid = await _create_session(async_client)

    _patch_runner(monkeypatch, send_delay=0.3)

    first = asyncio.create_task(_consume_post(async_client, sid, "first"))
    # Give the first task long enough to enter the handler and acquire the lock.
    await asyncio.sleep(0.05)

    resp = await async_client.post(
        f"/sessions/{sid}/messages", json={"content": "second"}
    )
    assert resp.status_code == 409, resp.text

    # First request finishes normally.
    status_first, _ = await first
    assert status_first == 200

    # After the first request fully completes the lock is released, so a
    # follow-up send succeeds.
    status_retry, _ = await _consume_post(async_client, sid, "retry")
    assert status_retry == 200


# -------- no crosstalk between sessions ----------------------------------


async def test_parallel_runs_write_assistant_to_correct_session(
    async_client: httpx.AsyncClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _signup_alice(async_client)
    sid_a = await _create_session(async_client)
    sid_b = await _create_session(async_client)

    _patch_runner(monkeypatch, send_delay=0.2)

    await asyncio.gather(
        _consume_post(async_client, sid_a, "question A"),
        _consume_post(async_client, sid_b, "question B"),
    )

    msgs_a = (
        db_session.query(Message).filter_by(session_id=sid_a).order_by(Message.id).all()
    )
    msgs_b = (
        db_session.query(Message).filter_by(session_id=sid_b).order_by(Message.id).all()
    )

    assert [(m.role, m.content) for m in msgs_a] == [
        (MessageRole.user, "question A"),
        (MessageRole.assistant, "reply to question A"),
    ]
    assert [(m.role, m.content) for m in msgs_b] == [
        (MessageRole.user, "question B"),
        (MessageRole.assistant, "reply to question B"),
    ]
