from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user
from app.db import get_db
from app.models import Message, User
from app.models import Session as ChatSession
from app.schemas.search import SearchHit

router = APIRouter(prefix="/search", tags=["search"])

SEARCH_LIMIT = 50
SNIPPET_CONTEXT = 30


def _make_snippet(content: str, query: str) -> str:
    """Return ~SNIPPET_CONTEXT chars of context on each side of the first
    case-insensitive occurrence of `query` in `content`. An ellipsis marker
    is prepended/appended when the snippet is clipped from the original."""
    idx = content.lower().find(query.lower())
    if idx == -1:
        # Shouldn't happen given the caller matched via LIKE, but guard
        # against it so we never return an empty snippet.
        return content[: SNIPPET_CONTEXT * 2 + len(query)]
    start = max(0, idx - SNIPPET_CONTEXT)
    end = min(len(content), idx + len(query) + SNIPPET_CONTEXT)
    snippet = content[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(content):
        snippet = snippet + "…"
    return snippet


@router.get("", response_model=list[SearchHit])
def search_sessions(
    q: str | None = Query(default=None),
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> list[SearchHit]:
    """Search the current user's sessions by title or message content.

    Matches are case-insensitive substring; results are capped at
    SEARCH_LIMIT sessions, ordered by session recency (updated_at desc).
    When both a message and the title match in a session, the message hit
    wins — its role is returned as `matched_role`, and the snippet is
    extracted from the message content with ~SNIPPET_CONTEXT chars of
    context on each side of the match. Title-only matches return the
    title as the snippet and `matched_role=null`.

    Future: upgrade to SQLite FTS5 for relevance ranking and faster queries
    once message volumes outgrow `LIKE`.
    """
    query = (q or "").strip()
    if not query:
        # Explicit 400 (rather than letting Query(..., min_length=1) 422)
        # because the plan's acceptance test asserts 400 on empty q.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'q' is required",
        )

    pattern = f"%{query}%"
    hits: dict[int, SearchHit] = {}

    # Pass 1: sessions with at least one matching message. We fetch
    # (message, session) rows in recency order and dedupe in Python —
    # cheap for v1 dataset sizes; break as soon as we've collected
    # SEARCH_LIMIT distinct sessions.
    msg_stmt = (
        select(Message, ChatSession)
        .join(ChatSession, ChatSession.id == Message.session_id)
        .where(ChatSession.user_id == user.id)
        .where(Message.content.ilike(pattern))
        .order_by(ChatSession.updated_at.desc(), Message.created_at.asc())
    )
    for msg, chat in db.execute(msg_stmt):
        if chat.id in hits:
            continue
        hits[chat.id] = SearchHit(
            session_id=chat.id,
            title=chat.title,
            snippet=_make_snippet(msg.content, query),
            matched_role=msg.role,
        )
        if len(hits) >= SEARCH_LIMIT:
            break

    # Pass 2: sessions whose title matches but weren't already hit.
    if len(hits) < SEARCH_LIMIT:
        title_stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user.id)
            .where(ChatSession.title.ilike(pattern))
            .order_by(ChatSession.updated_at.desc())
        )
        for chat in db.execute(title_stmt).scalars():
            if chat.id in hits:
                continue
            hits[chat.id] = SearchHit(
                session_id=chat.id,
                title=chat.title,
                snippet=_make_snippet(chat.title, query),
                matched_role=None,
            )
            if len(hits) >= SEARCH_LIMIT:
                break

    return list(hits.values())
