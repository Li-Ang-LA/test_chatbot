from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import MessageRole


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    system_prompt: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    system_prompt: str | None = None


class SessionOut(BaseModel):
    id: int
    title: str
    claude_session_id: str | None
    system_prompt: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageOut(BaseModel):
    id: int
    role: MessageRole
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionDetail(SessionOut):
    messages: list[MessageOut]
