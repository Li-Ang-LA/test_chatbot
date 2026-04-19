import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from app import claude_runner
from app.api.deps import current_user
from app.db import get_db
from app.models import Message, MessageRole, User
from app.models import Session as ChatSession
from app.schemas.session import (
    MessageCreate,
    SessionCreate,
    SessionDetail,
    SessionOut,
    SessionUpdate,
)

DEFAULT_TITLE = "New chat"
MAX_AUTO_TITLE_LEN = 60

router = APIRouter(prefix="/sessions", tags=["sessions"])

# Per-session locks prevent two overlapping Claude turns from interleaving
# on the same session. Parallel turns on *different* sessions stay fully
# independent because each session gets its own lock.
_session_locks: dict[int, asyncio.Lock] = {}


def _get_session_lock(session_id: int) -> asyncio.Lock:
    lock = _session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock
    return lock


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


@router.post("/{session_id}/messages")
async def send_session_message(
    session_id: int,
    payload: MessageCreate,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> StreamingResponse:
    """Persist the user message, kick off a Claude turn, and stream deltas as SSE.

    SSE events:
      event: delta → {"text": "<chunk>"}   (zero or more)
      event: done  → {"text": "<full assembled assistant message>"}
      event: error → {"error": "<message>"}  (only on failure)

    On `done`, the assembled assistant message is persisted. On `error`, no
    assistant message is persisted; the user message and (if just created)
    the Claude session id are left in place so the client can retry.
    """
    chat = _get_owned_session(db, session_id, user.id)

    # Reject a second concurrent turn on the *same* session with 409.
    # On a single asyncio event loop, checking `lock.locked()` then calling
    # `lock.acquire()` on the unlocked fast path is atomic (no yield point
    # between them), so no request can slip past the check.
    lock = _get_session_lock(chat.id)
    if lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A message is already streaming for this session",
        )
    await lock.acquire()

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
        chat_id = chat.id
        prompt = payload.content
    except BaseException:
        lock.release()
        raise

    async def stream():
        buffer: list[str] = []
        try:
            async for ev in claude_runner.send_message(claude_session_id, prompt):
                if ev.type == "text_delta" and ev.text:
                    buffer.append(ev.text)
                    yield _sse("delta", {"text": ev.text})
                elif ev.type == "message_done":
                    assembled = "".join(buffer)
                    db.add(
                        Message(
                            session_id=chat_id,
                            role=MessageRole.assistant,
                            content=assembled,
                        )
                    )
                    # Force an UPDATE so session.updated_at reflects the new activity.
                    db.get(ChatSession, chat_id).updated_at = datetime.now(timezone.utc)
                    db.commit()
                    yield _sse("done", {"text": assembled})
                    return
                elif ev.type == "error":
                    yield _sse("error", {"error": ev.error or "unknown claude error"})
                    return
        except Exception as e:  # defensive: any unexpected runner failure
            yield _sse("error", {"error": f"internal error: {e}"})
            return
        finally:
            lock.release()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
