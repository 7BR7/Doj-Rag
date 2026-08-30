"""
Pydantic request/response models shared across routes.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    document: str
    document_type: Optional[str] = None
    part: Optional[str] = None
    chapter: Optional[str] = None
    article: Optional[str] = None
    section: Optional[str] = None
    rule: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    language: str = "English"
    # user_id intentionally NOT accepted here - the authenticated user (see
    # app/routes/deps.py) always determines whose history this belongs to.


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    language: str
    sources: List[SourceRef] = Field(default_factory=list)
    needs_clarification: bool = False
    suggestions: List[str] = Field(default_factory=list)


class TranscribeResponse(BaseModel):
    text: str
    detected_language: str


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    updated_at: str
    message_count: int


class MessageOut(BaseModel):
    sender: Literal["user", "bot"]
    message: str
    language: str
    sources: List[SourceRef] = Field(default_factory=list)
    created_at: str


class ConversationDetail(BaseModel):
    conversation_id: str
    title: str
    messages: List[MessageOut]


class UserSettings(BaseModel):
    preferred_language: str = "English"
    voice_enabled: bool = True
    auto_speak: bool = False


class FeedbackRequest(BaseModel):
    conversation_id: str
    message_index: int
    rating: Literal["up", "down"]
    comment: Optional[str] = None


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: Optional[str] = None
    password: str = Field(min_length=6)


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    user_id: str
    username: str
    email: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
