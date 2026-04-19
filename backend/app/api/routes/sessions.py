from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from app.api.deps import current_user
from app.db import get_db
from app.models import Session as ChatSession
from app.models import User
from app.schemas.session import (
    SessionCreate,
    SessionDetail,
    SessionOut,
    SessionUpdate,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


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
    title = (payload.title if payload else None) or "New chat"
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
