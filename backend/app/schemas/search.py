from pydantic import BaseModel

from app.models import MessageRole


class SearchHit(BaseModel):
    session_id: int
    title: str
    snippet: str
    matched_role: MessageRole | None
