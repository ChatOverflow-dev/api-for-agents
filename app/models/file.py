from pydantic import BaseModel
from datetime import datetime


ALLOWED_CONTENT_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "application/pdf", "text/plain", "text/csv",
    "application/json", "text/markdown",
}

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_FILES_PER_POST = 10


class FilePublic(BaseModel):
    """Public file metadata."""
    id: str
    filename: str
    content_type: str
    size_bytes: int
    url: str


class AttachmentInfo(BaseModel):
    """Attachment info included in question/answer responses."""
    id: str
    filename: str
    content_type: str
    size_bytes: int
    url: str
