import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload, sessionmaker

from app import claude_runner
from app.api.deps import current_user
from app.db import get_db, get_session_factory
from app.models import Message, MessageRole, User
from app.models import Session as ChatSession
from app.schemas.session import (
    MessageCreate,
    SessionCreate,
    SessionDetail,
    SessionOut,
    SessionUpdate,
)

log = logging.getLogger(__name__)

DEFAULT_TITLE = "New chat"
MAX_AUTO_TITLE_LEN = 60

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ---------- active-turn registry ------------------------------------------
#
# Each session can have at most one in-flight Claude turn. The turn runs as
# a detached `asyncio.Task` that is **not** tied to the originating HTTP
# request, so a client disconnect no longer cancels generation — the task
# completes and persists the assistant message regardless. A new request to
# the same session while a turn is running returns 409.

TurnStatus = Literal["pending", "done", "error"]


@dataclass
class _ActiveTurn:
    # Appended to on every delta, so late subscribers (future reattach flow)
    # could replay what they missed; for now it's also the source of the
    # assembled assistant message we persist on `done`.
    buffer: list[str] = field(default_factory=list)
    # Each HTTP stream attaches one queue; the task broadcasts events to all
    # live subscribers. A None on the queue is the end-of-stream sentinel.
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    status: TurnStatus = "pending"
    task: asyncio.Task | None = None


_active_turns: dict[int, _ActiveTurn] = {}


def _broadcast(turn: _ActiveTurn, event: str, data: dict) -> None:
    for queue in turn.subscribers:
        # Unbounded queue, so put_nowait never blocks; it can only fail if
        # the queue has been closed, which we don't do.
        queue.put_nowait((event, data))


def _signal_end(turn: _ActiveTurn) -> None:
    for queue in turn.subscribers:
        queue.put_nowait(None)


def _get_owned_session(db: DbSession, session_id: int, user_id: int) -> ChatSession:
    chat = db.get(ChatSession, session_id)
    if chat is None or chat.user_id != user_id:
        # 404 (not 403) so we don't leak existence of other users' sessions.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    return chat


@router.get("", response_model=list[SessionOut])
def list_sessions(
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> list[ChatSession]:
    rows = db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
    ).scalars()
    return list(rows)


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate | None = None,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> ChatSession:
    title = (payload.title if payload else None) or DEFAULT_TITLE
    system_prompt = payload.system_prompt if payload else None
    chat = ChatSession(user_id=user.id, title=title, system_prompt=system_prompt)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: int,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> ChatSession:
    chat = db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.messages))
    ).scalar_one_or_none()
    if chat is None or chat.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    return chat


@router.patch("/{session_id}", response_model=SessionOut)
def update_session(
    session_id: int,
    payload: SessionUpdate,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> ChatSession:
    chat = _get_owned_session(db, session_id, user.id)

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update"
        )

    if "title" in data:
        chat.title = data["title"]
    if "system_prompt" in data:
        chat.system_prompt = data["system_prompt"]

    db.commit()
    db.refresh(chat)
    return chat


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> None:
    chat = _get_owned_session(db, session_id, user.id)
    db.delete(chat)
    db.commit()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _run_turn_task(
    session_id: int,
    claude_session_id: str,
    prompt: str,
    turn: _ActiveTurn,
    session_factory: sessionmaker,
) -> None:
    """Drive one Claude turn to completion, independent of any HTTP request.

    Feeds deltas into `turn.buffer` and broadcasts to any attached
    subscribers. On `message_done`, persists the assistant `Message` using
    a fresh DB session (the request's session may already be closed if the
    client disconnected). On error, marks the turn as failed and emits a
    terminal error event.
    """
    try:
        async for ev in claude_runner.send_message(claude_session_id, prompt):
            if ev.type == "text_delta" and ev.text:
                turn.buffer.append(ev.text)
                _broadcast(turn, "delta", {"text": ev.text})
            elif ev.type == "message_done":
                assembled = "".join(turn.buffer)
                try:
                    with session_factory() as db:
                        db.add(
                            Message(
                                session_id=session_id,
                                role=MessageRole.assistant,
                                content=assembled,
                            )
                        )
                        chat = db.get(ChatSession, session_id)
                        if chat is not None:
                            chat.updated_at = datetime.now(timezone.utc)
                        db.commit()
                except Exception:
                    log.exception(
                        "failed to persist assistant message for session %s",
                        session_id,
                    )
                turn.status = "done"
                _broadcast(turn, "done", {"text": assembled})
                return
            elif ev.type == "error":
                turn.status = "error"
                _broadcast(turn, "error", {"error": ev.error or "unknown claude error"})
                return
    except Exception as e:  # defensive: any unexpected runner failure
        turn.status = "error"
        _broadcast(turn, "error", {"error": f"internal error: {e}"})
    finally:
        _signal_end(turn)
        # Clear the slot so the next POST can start a new turn. Do this last
        # so a concurrent request observing `in _active_turns` up until this
        # point still gets 409.
        _active_turns.pop(session_id, None)


@router.post("/{session_id}/messages")
async def send_session_message(
    session_id: int,
    payload: MessageCreate,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
    session_factory: sessionmaker = Depends(get_session_factory),
) -> StreamingResponse:
    """Persist the user message, kick off a Claude turn as a detached task,
    and stream its events back to this client as SSE.

    SSE events:
      event: delta → {"text": "<chunk>"}   (zero or more)
      event: done  → {"text": "<full assembled assistant message>"}
      event: error → {"error": "<message>"}  (only on failure)

    The Claude turn runs as an `asyncio.Task` that outlives the HTTP request,
    so if this client disconnects mid-stream the task keeps running and
    persists the assistant message on `message_done`. A second POST to the
    same session while a turn is in flight returns 409.
    """
    chat = _get_owned_session(db, session_id, user.id)

    # Reject a second concurrent turn on the same session. On a single
    # asyncio loop, `in _active_turns` check and the subsequent insert are
    # atomic (no yield between them), so no request can slip past the check.
    if chat.id in _active_turns:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A message is already streaming for this session",
        )
    turn = _ActiveTurn()
    _active_turns[chat.id] = turn

    try:
        # 1) Persist the user message; bump title if still the default.
        user_message = Message(
            session_id=chat.id,
            role=MessageRole.user,
            content=payload.content,
        )
        db.add(user_message)
        if chat.title == DEFAULT_TITLE:
            auto_title = payload.content.strip()[:MAX_AUTO_TITLE_LEN]
            if auto_title:
                chat.title = auto_title
        db.commit()
        db.refresh(chat)

        # 2) Initialize the Claude session on the first turn.
        if chat.claude_session_id is None:
            try:
                claude_sid = await claude_runner.start_session(chat.system_prompt)
            except claude_runner.ClaudeRunnerError as e:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Could not start claude session: {e}",
                ) from e
            chat.claude_session_id = claude_sid
            db.commit()
            db.refresh(chat)

        claude_session_id = chat.claude_session_id
        assert claude_session_id is not None
    except BaseException:
        _active_turns.pop(chat.id, None)
        raise

    # 3) Attach this request as the first subscriber BEFORE spawning the
    # task, so no events can be lost between task start and subscribe.
    subscriber: asyncio.Queue = asyncio.Queue()
    turn.subscribers.append(subscriber)

    turn.task = asyncio.create_task(
        _run_turn_task(
            session_id=chat.id,
            claude_session_id=claude_session_id,
            prompt=payload.content,
            turn=turn,
            session_factory=session_factory,
        )
    )

    async def stream():
        try:
            while True:
                item = await subscriber.get()
                if item is None:  # end-of-stream sentinel
                    return
                event, data = item
                yield _sse(event, data)
                if event in ("done", "error"):
                    return
        finally:
            # Detach this subscriber; the task itself keeps running so the
            # assistant message still gets persisted even if the client went
            # away before `done`.
            try:
                turn.subscribers.remove(subscriber)
            except ValueError:
                pass

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
