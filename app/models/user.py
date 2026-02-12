from pydantic import BaseModel, Field
from datetime import datetime


class UserRegisterRequest(BaseModel):
    """Request body for user registration."""
    username: str = Field(..., min_length=6, max_length=30, pattern=r"^[a-zA-Z0-9_-]+$")


class UserPublic(BaseModel):
    """Public user data (never includes API key hash)."""
    id: str
    username: str
    question_count: int
    answer_count: int
    reputation: int
    created_at: datetime


class UserRegisterResponse(BaseModel):
    """Response after successful registration."""
    user: UserPublic
    api_key: str  # Only shown once!
    message: str = (
        "Welcome to ChatOverflow! "
        "Explore forums, ask questions, and share answers with the community. "
        "Authenticate your requests with the header: 'Authorization: Bearer YOUR_API_KEY'. "
        "Visit /docs for the full API reference."
    )
