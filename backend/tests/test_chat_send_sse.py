import json
from typing import Any

import pytest

from app import claude_runner
from app.claude_runner import StreamEvent
from app.models import Message, MessageRole
from app.models import Session as ChatSession

ALICE = {"email": "alice@example.com", "username": "alice", "password": "pw-alice-123"}
BOB = {"email": "bob@example.com", "username": "bob", "password": "pw-bob-123"}


def _signup(client, payload):
    resp = client.post("/auth/signup", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def alice_client(client):
    _signup(client, ALICE)
    return client


def _fake_runner(
    monkeypatch,
    *,
    events: list[StreamEvent],
    start_session_id: str = "claude-session-xyz",
    start_calls: list[str | None] | None = None,
    send_calls: list[tuple[str, str]] | None = None,
) -> None:
    async def fake_start(system_prompt: str | None = None, **_: Any) -> str:
        if start_calls is not None:
            start_calls.append(system_prompt)
        return start_session_id

    async def fake_send(session_id: str, prompt: str, **_: Any):
        if send_calls is not None:
            send_calls.append((session_id, prompt))
        for ev in events:
            yield ev

    monkeypatch.setattr(claude_runner, "start_session", fake_start)
    monkeypatch.setattr(claude_runner, "send_message", fake_send)


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    """Return [(event, parsed_data)] from a full SSE body."""
    out: list[tuple[str, dict]] = []
    for chunk in body.split("\n\n"):
        if not chunk.strip():
            continue
        event = None
        data_lines: list[str] = []
        for line in chunk.splitlines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        assert event is not None, f"event missing in chunk: {chunk!r}"
        data = json.loads("\n".join(data_lines)) if data_lines else {}
        out.append((event, data))
    return out


def _post_and_collect(client, session_id: int, content: str) -> tuple[int, list]:
    with client.stream(
        "POST",
        f"/sessions/{session_id}/messages",
        json={"content": content},
    ) as resp:
        body = b"".join(resp.iter_bytes()).decode()
    return resp.status_code, _parse_sse(body) if resp.status_code == 200 else []


# -------- basic auth / ownership ------------------------------------------


def test_send_message_requires_authentication(client):
    resp = client.post("/sessions/1/messages", json={"content": "hi"})
    assert resp.status_code == 401


def test_send_message_of_another_user_returns_404(alice_client, client, monkeypatch):
    chat = alice_client.post("/sessions").json()
    _fake_runner(monkeypatch, events=[])

    alice_client.post("/auth/logout")
    alice_client.cookies.clear()
    _signup(client, BOB)

    resp = client.post(f"/sessions/{chat['id']}/messages", json={"content": "hi"})
    assert resp.status_code == 404


# -------- streaming happy path --------------------------------------------


def test_stream_yields_delta_then_done_and_persists_messages(
    alice_client, db_session, monkeypatch
):
    chat = alice_client.post("/sessions").json()
    _fake_runner(
        monkeypatch,
        events=[
            StreamEvent(type="text_delta", text="Hello"),
            StreamEvent(type="text_delta", text=" world"),
            StreamEvent(type="message_done"),
        ],
    )

    status, events = _post_and_collect(alice_client, chat["id"], "What's up?")
    assert status == 200
    assert [e for e, _ in events] == ["delta", "delta", "done"]
    assert events[0][1] == {"text": "Hello"}
    assert events[1][1] == {"text": " world"}
    assert events[2][1] == {"text": "Hello world"}

    # User message persisted BEFORE assistant; assistant persisted on done.
    messages = (
        db_session.query(Message)
        .filter_by(session_id=chat["id"])
        .order_by(Message.id)
        .all()
    )
    assert [m.role for m in messages] == [MessageRole.user, MessageRole.assistant]
    assert [m.content for m in messages] == ["What's up?", "Hello world"]


def test_first_user_message_autotitles_session(alice_client, db_session, monkeypatch):
    chat = alice_client.post("/sessions").json()
    assert chat["title"] == "New chat"

    _fake_runner(
        monkeypatch,
        events=[
            StreamEvent(type="text_delta", text="ok"),
            StreamEvent(type="message_done"),
        ],
    )
    long_prompt = "Plan a three-day trip to Kyoto in autumn " * 3
    status, _ = _post_and_collect(alice_client, chat["id"], long_prompt)
    assert status == 200

    db_session.expire_all()
    refreshed = db_session.get(ChatSession, chat["id"])
    assert refreshed.title != "New chat"
    assert len(refreshed.title) <= 60
    assert refreshed.title == long_prompt.strip()[:60]


def test_existing_title_is_preserved(alice_client, db_session, monkeypatch):
    chat = alice_client.post("/sessions", json={"title": "Kept title"}).json()

    _fake_runner(
        monkeypatch,
        events=[
            StreamEvent(type="text_delta", text="ok"),
            StreamEvent(type="message_done"),
        ],
    )
    _post_and_collect(alice_client, chat["id"], "anything")

    db_session.expire_all()
    refreshed = db_session.get(ChatSession, chat["id"])
    assert refreshed.title == "Kept title"


# -------- claude_session_id lifecycle -------------------------------------


def test_claude_session_id_set_on_first_call_and_reused(
    alice_client, db_session, monkeypatch
):
    chat = alice_client.post("/sessions").json()
    start_calls: list[str | None] = []
    send_calls: list[tuple[str, str]] = []
    _fake_runner(
        monkeypatch,
        events=[
            StreamEvent(type="text_delta", text="a"),
            StreamEvent(type="message_done"),
        ],
        start_session_id="sid-first",
        start_calls=start_calls,
        send_calls=send_calls,
    )

    # First turn: start_session runs, id is persisted.
    _post_and_collect(alice_client, chat["id"], "turn one")
    db_session.expire_all()
    assert db_session.get(ChatSession, chat["id"]).claude_session_id == "sid-first"
    assert len(start_calls) == 1
    assert send_calls[-1] == ("sid-first", "turn one")

    # Second turn: start_session must NOT be called again; send_message reuses id.
    _post_and_collect(alice_client, chat["id"], "turn two")
    assert len(start_calls) == 1, "start_session should only run on first turn"
    assert send_calls[-1] == ("sid-first", "turn two")


# -------- error path ------------------------------------------------------


def test_error_event_is_emitted_and_assistant_not_persisted(
    alice_client, db_session, monkeypatch
):
    chat = alice_client.post("/sessions").json()
    _fake_runner(
        monkeypatch,
        events=[
            StreamEvent(type="text_delta", text="partial"),
            StreamEvent(type="error", error="boom"),
        ],
    )

    status, events = _post_and_collect(alice_client, chat["id"], "trigger error")
    assert status == 200
    assert [e for e, _ in events] == ["delta", "error"]
    assert events[-1][1] == {"error": "boom"}

    # Assistant message NOT persisted on error; user message IS.
    messages = (
        db_session.query(Message)
        .filter_by(session_id=chat["id"])
        .order_by(Message.id)
        .all()
    )
    assert [m.role for m in messages] == [MessageRole.user]
