from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, UploadFile, File, Form
import json
from app.database import supabase
from app.models.answer import (
    AnswerCreateRequest,
    AnswerPublic,
    AnswerListResponse,
)
from app.models.question import SortOption, VoteRequest, VoteOption
from app.models.file import AttachmentInfo, ALLOWED_CONTENT_TYPES, MAX_FILE_SIZE, MAX_FILES_PER_POST
from app.utils.auth import get_current_user, get_optional_user
from app.utils.embeddings import get_embedding
from app.storage import PostgresFileStorage
import logging
import math

logger = logging.getLogger(__name__)

file_storage = PostgresFileStorage()

router = APIRouter(tags=["answers"])

PAGE_SIZE = 20


def _generate_and_store_answer_embedding(answer_id: str, text: str):
    """Background task: generate embedding and update the answer row."""
    try:
        embedding = get_embedding(text)
        if embedding is not None:
            supabase.table("answers").update(
                {"embedding": embedding}
            ).eq("id", answer_id).execute()
    except Exception:
        logger.exception("Failed to generate embedding for answer %s", answer_id)


def _format_answer(
    answer: dict,
    user_vote: str | None = None,
    attachments: list[AttachmentInfo] | None = None,
) -> AnswerPublic:
    """Helper to format answer data with joined fields."""
    return AnswerPublic(
        id=answer["id"],
        body=answer["body"],
        question_id=answer["question_id"],
        author_id=answer["author_id"],
        author_username=answer["users"]["username"],
        status=answer["status"],
        upvote_count=answer["upvote_count"],
        downvote_count=answer["downvote_count"],
        score=answer["score"],
        created_at=answer["created_at"],
        user_vote=user_vote,
        attachments=attachments or [],
    )


# ============ Nested under /questions/{question_id} ============

def _replace_file_placeholders(body: str, file_map: dict[str, str]) -> str:
    """Replace file:filename placeholders with actual /files/id URLs."""
    for filename, url in file_map.items():
        body = body.replace(f"file:{filename}", url)
    return body


async def _create_answer_impl(
    question_id: str, body: str, status_val: str,
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    user: dict,
) -> AnswerPublic:
    """Shared implementation for creating an answer with optional files."""
    if len(files) > MAX_FILES_PER_POST:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES_PER_POST} files per answer")

    question_result = supabase.table("questions").select("id").eq("id", question_id).execute()
    if not question_result.data:
        raise HTTPException(status_code=404, detail="Question not found")

    try:
        result = supabase.table("answers").insert({
            "body": body, "question_id": question_id, "author_id": user["id"], "status": status_val,
        }).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create answer")

        answer_data = result.data[0]
        answer_id = answer_data["id"]

        file_map: dict[str, str] = {}
        uploaded_attachments: list[AttachmentInfo] = []

        for f in files:
            if f.content_type not in ALLOWED_CONTENT_TYPES:
                raise HTTPException(status_code=400, detail=f"File '{f.filename}' type '{f.content_type}' not allowed")
            data = await f.read()
            if len(data) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail=f"File '{f.filename}' too large. Max {MAX_FILE_SIZE // (1024 * 1024)}MB")
            stored = file_storage.upload(
                filename=f.filename or "untitled", content_type=f.content_type,
                data=data, uploader_id=user["id"], answer_id=answer_id,
            )
            file_map[f.filename or "untitled"] = stored.url
            uploaded_attachments.append(
                AttachmentInfo(id=stored.id, filename=stored.filename, content_type=stored.content_type, size_bytes=stored.size_bytes, url=stored.url)
            )

        if file_map:
            final_body = _replace_file_placeholders(body, file_map)
            supabase.table("answers").update({"body": final_body}).eq("id", answer_id).execute()
            answer_data["body"] = final_body

        background_tasks.add_task(_generate_and_store_answer_embedding, answer_id, answer_data["body"])

        return AnswerPublic(
            id=answer_data["id"], body=answer_data["body"], question_id=answer_data["question_id"],
            author_id=answer_data["author_id"], author_username=user["username"],
            status=answer_data["status"], upvote_count=answer_data["upvote_count"],
            downvote_count=answer_data["downvote_count"], score=answer_data["score"],
            created_at=answer_data["created_at"], attachments=uploaded_attachments,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to create answer")


@router.post("/questions/{question_id}/answers", response_model=AnswerPublic)
async def create_answer(
    question_id: str,
    request: AnswerCreateRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """
    Create an answer (JSON, no files).

    Body: `{"body", "status"}`

    To attach files, use multipart form via POST /questions/{id}/answers/with-files.

    Requires authentication.
    """
    return await _create_answer_impl(question_id, request.body, request.status.value, [], background_tasks, user)


@router.post("/questions/{question_id}/answers/with-files", response_model=AnswerPublic)
async def create_answer_with_files(
    question_id: str,
    background_tasks: BackgroundTasks,
    metadata: str = Form(..., description='JSON string: {"body", "status"}'),
    files: list[UploadFile] = File(default=[]),
    user: dict = Depends(get_current_user),
):
    """
    Create an answer with file attachments (multipart form).

    Send `metadata` as JSON string + `files` as file uploads.
    Reference files in body using `file:filename` placeholders.

    Limits: max 5MB per file, max 10 files per answer.

    Requires authentication.
    """
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON")

    body = meta.get("body", "").strip()
    status_val = meta.get("status", "success").strip()
    if not body or len(body) > 50000:
        raise HTTPException(status_code=400, detail="Body required, max 50000 chars")
    if status_val not in ("success", "attempt", "failure"):
        raise HTTPException(status_code=400, detail="status must be success, attempt, or failure")

    return await _create_answer_impl(question_id, body, status_val, files, background_tasks, user)


@router.get("/questions/{question_id}/answers", response_model=AnswerListResponse)
async def list_answers(
    question_id: str,
    sort: SortOption = Query(SortOption.top, description="Sort order: 'top' (default) or 'newest'"),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    user: dict | None = Depends(get_optional_user),
):
    """
    List answers to a question.

    - Sort by 'top' (default, by score) or 'newest'
    - Secondary sort is always by newest (created_at)
    - Returns 20 answers per page
    - If authenticated, includes user_vote for each answer

    Public endpoint - authentication optional.
    """
    # Verify question exists
    question_check = supabase.table("questions").select("id").eq("id", question_id).execute()
    if not question_check.data:
        raise HTTPException(status_code=404, detail="Question not found")

    # Get total count for this question
    count_result = (
        supabase.table("answers")
        .select("id", count="exact")
        .eq("question_id", question_id)
        .execute()
    )
    total = count_result.count or 0
    total_pages = math.ceil(total / PAGE_SIZE) if total > 0 else 1

    # Check if page exists
    if page > total_pages:
        raise HTTPException(
            status_code=404,
            detail=f"Page {page} not found. Total pages: {total_pages}"
        )

    # Build query for results
    offset = (page - 1) * PAGE_SIZE
    query = (
        supabase.table("answers")
        .select("*, users!answers_author_id_fkey(username)")
        .eq("question_id", question_id)
    )

    # Apply sorting (always with secondary sort by newest)
    if sort == SortOption.top:
        query = query.order("score", desc=True).order("created_at", desc=True)
    else:  # newest
        query = query.order("created_at", desc=True)

    query = query.range(offset, offset + PAGE_SIZE - 1)
    result = query.execute()

    # Get user votes if authenticated
    user_votes = {}
    if user and result.data:
        answer_ids = [a["id"] for a in result.data]
        votes_result = (
            supabase.table("answer_votes")
            .select("answer_id, vote_type")
            .eq("user_id", user["id"])
            .in_("answer_id", answer_ids)
            .execute()
        )
        user_votes = {v["answer_id"]: v["vote_type"] for v in votes_result.data}

    # Batch-fetch attachments for all answers
    answer_ids = [a["id"] for a in result.data]
    attachments_by_answer = file_storage.list_for_answers(answer_ids)

    def _answer_attachments(answer_id: str) -> list[AttachmentInfo]:
        return [
            AttachmentInfo(id=f.id, filename=f.filename, content_type=f.content_type, size_bytes=f.size_bytes, url=f.url)
            for f in attachments_by_answer.get(answer_id, [])
        ]

    return AnswerListResponse(
        answers=[
            _format_answer(a, user_vote=user_votes.get(a["id"]), attachments=_answer_attachments(a["id"]))
            for a in result.data
        ],
        page=page,
        total_pages=total_pages,
    )


# ============ Top-level /answers endpoints ============

@router.get("/answers/{answer_id}", response_model=AnswerPublic)
async def get_answer(
    answer_id: str,
    user: dict | None = Depends(get_optional_user),
):
    """
    Get a specific answer by ID.

    If authenticated, includes user_vote field.

    Public endpoint - authentication optional.
    """
    result = (
        supabase.table("answers")
        .select("*, users!answers_author_id_fkey(username)")
        .eq("id", answer_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Answer not found")

    # Get user's vote if authenticated
    user_vote = None
    if user:
        vote_result = (
            supabase.table("answer_votes")
            .select("vote_type")
            .eq("user_id", user["id"])
            .eq("answer_id", answer_id)
            .execute()
        )
        if vote_result.data:
            user_vote = vote_result.data[0]["vote_type"]

    # Fetch attachments
    stored_files = file_storage.list_for_answer(answer_id)
    attachments = [
        AttachmentInfo(id=f.id, filename=f.filename, content_type=f.content_type, size_bytes=f.size_bytes, url=f.url)
        for f in stored_files
    ]

    return _format_answer(result.data[0], user_vote=user_vote, attachments=attachments)


@router.post("/answers/{answer_id}/vote", response_model=AnswerPublic)
async def vote_on_answer(
    answer_id: str,
    request: VoteRequest,
    user: dict = Depends(get_current_user),
):
    """
    Vote on an answer (upvote, downvote, or remove vote).

    - vote: "up" to upvote, "down" to downvote, "none" to remove vote
    - Returns 409 if already voted the same way
    - Returns 400 if trying to remove a vote that doesn't exist

    Requires authentication.
    """
    # Verify answer exists
    answer_result = (
        supabase.table("answers")
        .select("*, users!answers_author_id_fkey(username)")
        .eq("id", answer_id)
        .execute()
    )
    if not answer_result.data:
        raise HTTPException(status_code=404, detail="Answer not found")

    answer = answer_result.data[0]

    # Get existing vote
    existing_vote_result = (
        supabase.table("answer_votes")
        .select("vote_type")
        .eq("user_id", user["id"])
        .eq("answer_id", answer_id)
        .execute()
    )
    existing_vote = existing_vote_result.data[0]["vote_type"] if existing_vote_result.data else None

    # Determine what to do based on current state and requested vote
    requested_vote = request.vote.value if request.vote != VoteOption.none else None

    # Check for no-op cases
    if existing_vote == requested_vote:
        if requested_vote == "up":
            raise HTTPException(status_code=409, detail="Already upvoted")
        elif requested_vote == "down":
            raise HTTPException(status_code=409, detail="Already downvoted")
        else:  # both None
            raise HTTPException(status_code=400, detail="No vote to remove")

    # Calculate delta for upvote_count and downvote_count
    upvote_delta = 0
    downvote_delta = 0

    if existing_vote == "up":
        upvote_delta -= 1
    elif existing_vote == "down":
        downvote_delta -= 1

    if requested_vote == "up":
        upvote_delta += 1
    elif requested_vote == "down":
        downvote_delta += 1

    # Update or delete the vote record
    if requested_vote is None:
        # Remove vote
        supabase.table("answer_votes").delete().eq("user_id", user["id"]).eq("answer_id", answer_id).execute()
    elif existing_vote is None:
        # Insert new vote
        supabase.table("answer_votes").insert({
            "user_id": user["id"],
            "answer_id": answer_id,
            "vote_type": requested_vote,
        }).execute()
    else:
        # Update existing vote
        supabase.table("answer_votes").update({
            "vote_type": requested_vote,
        }).eq("user_id", user["id"]).eq("answer_id", answer_id).execute()

    # Update answer counts atomically
    supabase.rpc("update_answer_vote_counts", {
        "p_answer_id": answer_id,
        "p_upvote_delta": upvote_delta,
        "p_downvote_delta": downvote_delta,
    }).execute()

    new_upvote_count = answer["upvote_count"] + upvote_delta
    new_downvote_count = answer["downvote_count"] + downvote_delta
    new_score = new_upvote_count - new_downvote_count

    # Note: author reputation is updated automatically by the
    # trg_answer_score database trigger when score changes.

    # Return updated answer with user's vote
    answer["upvote_count"] = new_upvote_count
    answer["downvote_count"] = new_downvote_count
    answer["score"] = new_score

    return _format_answer(answer, user_vote=requested_vote)
