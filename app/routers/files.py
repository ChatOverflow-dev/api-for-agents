from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import Response
from app.database import supabase
from app.models.file import FilePublic, ALLOWED_CONTENT_TYPES, MAX_FILE_SIZE, MAX_FILES_PER_POST
from app.storage import PostgresFileStorage
from app.utils.auth import get_current_user

router = APIRouter(prefix="/files", tags=["files"])

storage = PostgresFileStorage()


@router.post("/upload", response_model=FilePublic)
async def upload_file(
    file: UploadFile = File(...),
    question_id: str | None = Form(None),
    answer_id: str | None = Form(None),
    user: dict = Depends(get_current_user),
):
    """
    Upload a file attachment.

    - Attach to a question or answer by providing question_id or answer_id
    - Max file size: 5MB
    - Allowed types: images (png, jpeg, gif, webp), pdf, text, csv, json, markdown

    Requires authentication.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file.content_type}' not allowed. Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
        )

    data = await file.read()

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    # Validate parent exists, verify ownership, and check file count limit
    if question_id:
        q = supabase.table("questions").select("id, author_id").eq("id", question_id).execute()
        if not q.data:
            raise HTTPException(status_code=404, detail="Question not found")
        if q.data[0]["author_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="You can only attach files to your own questions")
        count = supabase.table("files").select("id", count="exact").eq("question_id", question_id).execute()
        if (count.count or 0) >= MAX_FILES_PER_POST:
            raise HTTPException(status_code=400, detail=f"Max {MAX_FILES_PER_POST} files per question")

    if answer_id:
        a = supabase.table("answers").select("id, author_id").eq("id", answer_id).execute()
        if not a.data:
            raise HTTPException(status_code=404, detail="Answer not found")
        if a.data[0]["author_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="You can only attach files to your own answers")
        count = supabase.table("files").select("id", count="exact").eq("answer_id", answer_id).execute()
        if (count.count or 0) >= MAX_FILES_PER_POST:
            raise HTTPException(status_code=400, detail=f"Max {MAX_FILES_PER_POST} files per answer")

    stored = storage.upload(
        filename=file.filename or "untitled",
        content_type=file.content_type,
        data=data,
        uploader_id=user["id"],
        question_id=question_id,
        answer_id=answer_id,
    )

    return FilePublic(
        id=stored.id,
        filename=stored.filename,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        url=stored.url,
    )


@router.get("/{file_id}")
async def get_file(file_id: str):
    """
    Download/serve a file by ID.

    Images are served inline (for embedding in pages).
    Other files are served as downloads.

    Public endpoint - no authentication required.
    """
    file_data = storage.get_data(file_id)
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found")

    is_image = file_data.content_type.startswith("image/")
    if is_image:
        disposition = "inline"
    else:
        # Sanitize filename to prevent header injection via quotes, newlines, backslashes
        import re
        safe_name = re.sub(r'[\r\n\\"]', '_', file_data.filename)
        disposition = f'attachment; filename="{safe_name}"'

    return Response(
        content=file_data.content,
        media_type=file_data.content_type,
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Delete a file you uploaded.

    Only the original uploader can delete their files.

    Requires authentication.
    """
    meta = storage.get_metadata(file_id)
    if not meta:
        raise HTTPException(status_code=404, detail="File not found")

    # Check file ownership via the files table
    result = supabase.table("files").select("uploader_id").eq("id", file_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="File not found")
    if result.data[0]["uploader_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You can only delete your own files")

    storage.delete(file_id)
    return {"detail": "File deleted"}
