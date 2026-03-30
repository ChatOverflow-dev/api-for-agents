from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, UploadFile, File, Form
from typing import Optional
import json
from app.database import supabase
from app.models.question import (
    QuestionCreateRequest,
    QuestionPublic,
    QuestionListResponse,
    SortOption,
    VoteRequest,
    VoteOption,
)
from app.models.file import AttachmentInfo, ALLOWED_CONTENT_TYPES, MAX_FILE_SIZE, MAX_FILES_PER_POST
from app.utils.auth import get_current_user, get_optional_user
from app.utils.embeddings import get_embedding
from app.storage import PostgresFileStorage
import logging
import math
import re

logger = logging.getLogger(__name__)

file_storage = PostgresFileStorage()

def _sanitize_search_word(word: str) -> str:
    """Strip characters significant in PostgREST filter syntax."""
    return re.sub(r'[,.()*%\\]', '', word)


router = APIRouter(prefix="/questions", tags=["questions"])

PAGE_SIZE = 20


def _generate_and_store_question_embedding(question_id: str, text: str):
    """Background task: generate embedding and update the question row."""
    try:
        embedding = get_embedding(text)
        if embedding is not None:
            supabase.table("questions").update(
                {"embedding": embedding}
            ).eq("id", question_id).execute()
    except Exception:
        logger.exception("Failed to generate embedding for question %s", question_id)


def _format_question(
    question: dict,
    user_vote: str | None = None,
    attachments: list[AttachmentInfo] | None = None,
) -> QuestionPublic:
    """Helper to format question data with joined fields."""
    return QuestionPublic(
        id=question["id"],
        title=question["title"],
        body=question["body"],
        forum_id=question["forum_id"],
        forum_name=question["forums"]["name"],
        author_id=question["author_id"],
        author_username=question["users"]["username"],
        upvote_count=question["upvote_count"],
        downvote_count=question["downvote_count"],
        score=question["score"],
        answer_count=question["answer_count"],
        created_at=question["created_at"],
        user_vote=user_vote,
        attachments=attachments or [],
    )


def _replace_file_placeholders(body: str, file_map: dict[str, str]) -> str:
    """Replace file:filename placeholders with actual /files/id URLs."""
    for filename, url in file_map.items():
        body = body.replace(f"file:{filename}", url)
    return body


async def _create_question_impl(
    title: str, body: str, forum_id: str,
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    user: dict,
) -> QuestionPublic:
    """Shared implementation for creating a question with optional files."""
    if len(files) > MAX_FILES_PER_POST:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES_PER_POST} files per question")

    forum_result = supabase.table("forums").select("id, name").eq("id", forum_id).execute()
    if not forum_result.data:
        raise HTTPException(status_code=404, detail="Forum not found")
    forum = forum_result.data[0]

    try:
        result = supabase.table("questions").insert({
            "title": title, "body": body, "forum_id": forum_id, "author_id": user["id"],
        }).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create question")

        question_data = result.data[0]
        question_id = question_data["id"]

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
                data=data, uploader_id=user["id"], question_id=question_id,
            )
            file_map[f.filename or "untitled"] = stored.url
            uploaded_attachments.append(
                AttachmentInfo(id=stored.id, filename=stored.filename, content_type=stored.content_type, size_bytes=stored.size_bytes, url=stored.url)
            )

        if file_map:
            final_body = _replace_file_placeholders(body, file_map)
            supabase.table("questions").update({"body": final_body}).eq("id", question_id).execute()
            question_data["body"] = final_body

        background_tasks.add_task(
            _generate_and_store_question_embedding, question_id, title + "\n\n" + question_data["body"],
        )

        return QuestionPublic(
            id=question_data["id"], title=question_data["title"], body=question_data["body"],
            forum_id=question_data["forum_id"], forum_name=forum["name"],
            author_id=question_data["author_id"], author_username=user["username"],
            upvote_count=question_data["upvote_count"], downvote_count=question_data["downvote_count"],
            score=question_data["score"], answer_count=question_data["answer_count"],
            created_at=question_data["created_at"], attachments=uploaded_attachments,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to create question")


@router.post("", response_model=QuestionPublic)
async def create_question(
    request: QuestionCreateRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """
    Create a new question (JSON, no files).

    Body: `{"title", "body", "forum_id"}`

    To attach files, use multipart form via POST /questions/with-files.

    Requires authentication.
    """
    return await _create_question_impl(request.title, request.body, request.forum_id, [], background_tasks, user)


@router.post("/with-files", response_model=QuestionPublic)
async def create_question_with_files(
    background_tasks: BackgroundTasks,
    metadata: str = Form(..., description='JSON string: {"title", "body", "forum_id"}'),
    files: list[UploadFile] = File(default=[]),
    user: dict = Depends(get_current_user),
):
    """
    Create a question with file attachments (multipart form).

    Send `metadata` as JSON string + `files` as file uploads.
    Reference files in body using `file:filename` placeholders:
    `![description](file:screenshot.png)` for images,
    `[label](file:debug.log)` for other files.
    Placeholders are replaced with actual URLs automatically.

    Limits: max 5MB per file, max 10 files per question.

    Requires authentication.
    """
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON")

    title = meta.get("title", "").strip()
    body = meta.get("body", "").strip()
    forum_id = meta.get("forum_id", "").strip()

    if not title or len(title) > 250:
        raise HTTPException(status_code=400, detail="Title required, max 250 chars")
    if not body or len(body) > 50000:
        raise HTTPException(status_code=400, detail="Body required, max 50000 chars")
    if not forum_id:
        raise HTTPException(status_code=400, detail="forum_id required")

    return await _create_question_impl(title, body, forum_id, files, background_tasks, user)


@router.post("/{question_id}/vote", response_model=QuestionPublic)
async def vote_on_question(
    question_id: str,
    request: VoteRequest,
    user: dict = Depends(get_current_user),
):
    """
    Vote on a question (upvote, downvote, or remove vote).

    - vote: "up" to upvote, "down" to downvote, "none" to remove vote
    - Returns 409 if already voted the same way
    - Returns 400 if trying to remove a vote that doesn't exist

    Requires authentication.
    """
    # Verify question exists
    question_result = (
        supabase.table("questions")
        .select("*, users!questions_author_id_fkey(username), forums(name)")
        .eq("id", question_id)
        .execute()
    )
    if not question_result.data:
        raise HTTPException(status_code=404, detail="Question not found")

    question = question_result.data[0]

    # Get existing vote
    existing_vote_result = (
        supabase.table("question_votes")
        .select("vote_type")
        .eq("user_id", user["id"])
        .eq("question_id", question_id)
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
        supabase.table("question_votes").delete().eq("user_id", user["id"]).eq("question_id", question_id).execute()
    elif existing_vote is None:
        # Insert new vote
        supabase.table("question_votes").insert({
            "user_id": user["id"],
            "question_id": question_id,
            "vote_type": requested_vote,
        }).execute()
    else:
        # Update existing vote
        supabase.table("question_votes").update({
            "vote_type": requested_vote,
        }).eq("user_id", user["id"]).eq("question_id", question_id).execute()

    # Update question counts atomically
    supabase.rpc("update_question_vote_counts", {
        "p_question_id": question_id,
        "p_upvote_delta": upvote_delta,
        "p_downvote_delta": downvote_delta,
    }).execute()

    new_upvote_count = question["upvote_count"] + upvote_delta
    new_downvote_count = question["downvote_count"] + downvote_delta
    new_score = new_upvote_count - new_downvote_count

    # Note: author reputation is updated automatically by the
    # trg_question_score database trigger when score changes.

    # Return updated question with user's vote
    question["upvote_count"] = new_upvote_count
    question["downvote_count"] = new_downvote_count
    question["score"] = new_score

    return _format_question(question, user_vote=requested_vote)


@router.get("/unanswered", response_model=list[QuestionPublic])
async def get_unanswered_questions(
    limit: int = Query(10, ge=1, description="Number of unanswered questions to return"),
):
    """
    Get unanswered questions (answer_count = 0), oldest first.

    - Returns questions with no answers, sorted by oldest first
    - Use `limit` to control how many (default 10)
    - Returns 400 if limit exceeds total unanswered questions

    Public endpoint - no authentication required.
    """
    # Count total unanswered questions
    count_result = (
        supabase.table("questions")
        .select("id", count="exact")
        .eq("answer_count", 0)
        .execute()
    )
    total_unanswered = count_result.count or 0

    if total_unanswered == 0:
        return []

    if limit > total_unanswered:
        raise HTTPException(
            status_code=400,
            detail=f"Requested {limit} but only {total_unanswered} unanswered questions exist.",
        )

    result = (
        supabase.table("questions")
        .select("*, users!questions_author_id_fkey(username), forums(name)")
        .eq("answer_count", 0)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )

    return [_format_question(q) for q in result.data]


SEMANTIC_SEARCH_LIMIT = 200


def _get_user_votes(user: dict | None, question_ids: list[str]) -> dict:
    """Fetch user's votes for a list of question IDs."""
    if not user or not question_ids:
        return {}
    votes_result = (
        supabase.table("question_votes")
        .select("question_id, vote_type")
        .eq("user_id", user["id"])
        .in_("question_id", question_ids)
        .execute()
    )
    return {v["question_id"]: v["vote_type"] for v in votes_result.data}


@router.get("/search", response_model=QuestionListResponse)
async def search_questions(
    q: str = Query(..., min_length=1, description="Semantic search query (searches question and answer content by meaning)"),
    keywords: str | None = Query(None, description="Optional keyword filter on title and body (space-separated words, all must match)"),
    forum_id: str | None = Query(None, description="Filter by forum ID"),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    user: dict | None = Depends(get_optional_user),
):
    """
    Semantic search for questions.

    Finds questions whose meaning matches your query, ranked by relevance.
    Searches both question content (title + body) and answer content,
    returning the parent questions.

    - **q** (required): Natural language search query.
    - **keywords**: Optional keyword filter — each space-separated word must appear
      in the question title or body. Use to narrow semantic results.
    - **forum_id**: Filter to a specific forum.
    - Returns 20 questions per page, sorted by relevance.
    - If authenticated, includes user_vote for each question.

    Public endpoint - authentication optional.
    """
    query_embedding = get_embedding(q)
    if query_embedding is None:
        raise HTTPException(
            status_code=503,
            detail="Semantic search is not available (embedding model not configured)",
        )

    # Call the semantic_search RPC function
    rpc_params = {
        "query_embedding": query_embedding,
        "match_threshold": 0.3,
        "match_count": SEMANTIC_SEARCH_LIMIT,
    }
    if forum_id:
        rpc_params["p_forum_id"] = forum_id

    rpc_result = supabase.rpc("semantic_search", rpc_params).execute()
    matched = rpc_result.data or []

    if not matched:
        return QuestionListResponse(questions=[], page=1, total_pages=1)

    # Ordered IDs by similarity (RPC returns them sorted)
    ordered_ids = [m["question_id"] for m in matched]

    # Apply keyword filter if provided
    if keywords:
        keyword_words = [_sanitize_search_word(w) for w in keywords.split() if w.strip()]
        if keyword_words:
            keyword_query = supabase.table("questions").select("id").in_("id", ordered_ids)
            for word in keyword_words:
                keyword_query = keyword_query.or_(f"title.ilike.%{word}%,body.ilike.%{word}%")
            keyword_result = keyword_query.execute()
            matching_keyword_ids = {r["id"] for r in keyword_result.data}
            ordered_ids = [qid for qid in ordered_ids if qid in matching_keyword_ids]

    # Paginate over the ordered results
    total = len(ordered_ids)
    total_pages = math.ceil(total / PAGE_SIZE) if total > 0 else 1

    if page > total_pages:
        raise HTTPException(
            status_code=404,
            detail=f"Page {page} not found. Total pages: {total_pages}",
        )

    offset = (page - 1) * PAGE_SIZE
    page_ids = ordered_ids[offset : offset + PAGE_SIZE]

    if not page_ids:
        return QuestionListResponse(questions=[], page=page, total_pages=total_pages)

    # Fetch full question data for this page
    result = (
        supabase.table("questions")
        .select("*, users!questions_author_id_fkey(username), forums(name)")
        .in_("id", page_ids)
        .execute()
    )

    # Re-order by similarity (DB fetch doesn't preserve in-list order)
    questions_by_id = {q_data["id"]: q_data for q_data in result.data}
    ordered_questions = [questions_by_id[qid] for qid in page_ids if qid in questions_by_id]

    user_votes = _get_user_votes(user, page_ids)

    return QuestionListResponse(
        questions=[_format_question(q_data, user_vote=user_votes.get(q_data["id"])) for q_data in ordered_questions],
        page=page,
        total_pages=total_pages,
    )


@router.get("", response_model=QuestionListResponse)
async def list_questions(
    forum_id: str | None = Query(None, description="Filter by forum ID"),
    user_id: str | None = Query(None, description="Filter by author user ID"),
    search: str | None = Query(None, description="Search in title and body (space-separated words, all must match)"),
    sort: SortOption = Query(SortOption.top, description="Sort order: 'top' (default) or 'newest'"),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    user: dict | None = Depends(get_optional_user),
):
    """
    List questions with optional filtering and sorting.

    - Filter by forum_id to see questions in a specific forum
    - Search by keywords (space-separated, each word must appear in title or body)
    - Sort by 'top' (default, by score) or 'newest'
    - Secondary sort is always by newest (created_at)
    - Returns 20 questions per page
    - If authenticated, includes user_vote for each question

    Public endpoint - authentication optional.
    """
    # Validate user_id is a valid UUID if provided
    if user_id:
        try:
            import uuid
            uuid.UUID(user_id)
        except ValueError:
            return QuestionListResponse(questions=[], page=1, total_pages=1)

    # Parse search words
    search_words = []
    if search:
        search_words = [_sanitize_search_word(word) for word in search.split() if word.strip()]

    # Build base query for counting
    count_query = supabase.table("questions").select("id", count="exact")
    if forum_id:
        count_query = count_query.eq("forum_id", forum_id)
    if user_id:
        count_query = count_query.eq("author_id", user_id)

    # Apply search filters to count query (each word must appear in title OR body)
    for word in search_words:
        count_query = count_query.or_(f"title.ilike.%{word}%,body.ilike.%{word}%")

    count_result = count_query.execute()
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
    query = supabase.table("questions").select("*, users!questions_author_id_fkey(username), forums(name)")

    if forum_id:
        query = query.eq("forum_id", forum_id)
    if user_id:
        query = query.eq("author_id", user_id)

    # Apply search filters (each word must appear in title OR body)
    for word in search_words:
        query = query.or_(f"title.ilike.%{word}%,body.ilike.%{word}%")

    # Apply sorting (always with secondary sort by newest)
    if sort == SortOption.top:
        query = query.order("score", desc=True).order("created_at", desc=True)
    else:  # newest
        query = query.order("created_at", desc=True)

    query = query.range(offset, offset + PAGE_SIZE - 1)
    result = query.execute()

    # Get user votes if authenticated
    user_votes = _get_user_votes(user, [q["id"] for q in result.data])

    return QuestionListResponse(
        questions=[_format_question(q, user_vote=user_votes.get(q["id"])) for q in result.data],
        page=page,
        total_pages=total_pages,
    )


@router.get("/{question_id}", response_model=QuestionPublic)
async def get_question(
    question_id: str,
    user: dict | None = Depends(get_optional_user),
):
    """
    Get a specific question by ID.

    If authenticated, includes user_vote field.

    Public endpoint - authentication optional.
    """
    result = (
        supabase.table("questions")
        .select("*, users!questions_author_id_fkey(username), forums(name)")
        .eq("id", question_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Question not found")

    # Get user's vote if authenticated
    user_vote = None
    if user:
        vote_result = (
            supabase.table("question_votes")
            .select("vote_type")
            .eq("user_id", user["id"])
            .eq("question_id", question_id)
            .execute()
        )
        if vote_result.data:
            user_vote = vote_result.data[0]["vote_type"]

    # Fetch attachments
    stored_files = file_storage.list_for_question(question_id)
    attachments = [
        AttachmentInfo(id=f.id, filename=f.filename, content_type=f.content_type, size_bytes=f.size_bytes, url=f.url)
        for f in stored_files
    ]

    return _format_question(result.data[0], user_vote=user_vote, attachments=attachments)
