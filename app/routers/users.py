from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from app.database import supabase
from app.models.user import UserPublic
from app.models.question import QuestionPublic, QuestionListResponse, SortOption
from app.models.answer import AnswerPublic, AnswerListResponse
from app.utils.auth import get_current_user
import math

router = APIRouter(prefix="/users", tags=["users"])

PAGE_SIZE = 20

USER_PUBLIC_FIELDS = "id, username, question_count, answer_count, reputation, created_at"


class UserUsageStats(BaseModel):
    id: str
    username: str
    activity_score: int
    feedback_score: int
    contribution_score: int
    question_count: int
    answer_count: int
    created_at: str


def _format_user(user: dict) -> UserPublic:
    """Helper to format user data."""
    return UserPublic(
        id=user["id"],
        username=user["username"],
        question_count=user["question_count"],
        answer_count=user["answer_count"],
        reputation=user["reputation"],
        created_at=user["created_at"],
    )


@router.get("/me", response_model=UserPublic)
async def get_my_profile(user: dict = Depends(get_current_user)):
    """
    Get the currently authenticated user's profile.

    Requires a valid API key in the Authorization header.
    """
    return _format_user(user)


@router.get("/top", response_model=list[UserPublic])
async def get_top_users(
    limit: int = Query(10, ge=1, le=50, description="Number of top users to return (max 50)"),
):
    """
    Get top users ranked by reputation.

    Public endpoint - no authentication required.
    """
    result = (
        supabase.table("users")
        .select(USER_PUBLIC_FIELDS)
        .order("reputation", desc=True)
        .limit(limit)
        .execute()
    )

    return [_format_user(u) for u in result.data]


@router.get("/usage", response_model=list[UserUsageStats])
async def get_usage_stats(
    limit: int = Query(50, ge=1, le=100, description="Number of users to return (max 100)"),
):
    """
    Get usage statistics for top users.

    Returns three scores per user:
    - activity_score: total questions + answers posted
    - feedback_score: sum of (upvotes - downvotes) on all questions and answers they authored
    - contribution_score: total votes (up + down) they have cast on others' content

    Public endpoint - no authentication required.
    """
    # 1. Get top users
    users_result = (
        supabase.table("users")
        .select("id, username, question_count, answer_count, created_at")
        .order("reputation", desc=True)
        .limit(limit)
        .execute()
    )
    user_list = users_result.data or []

    if not user_list:
        return []

    user_ids = [u["id"] for u in user_list]

    # 2. Batch fetch all question scores for these users (single query)
    q_result = (
        supabase.table("questions")
        .select("author_id, score")
        .in_("author_id", user_ids)
        .execute()
    )
    q_scores: dict[str, int] = {}
    for row in (q_result.data or []):
        q_scores[row["author_id"]] = q_scores.get(row["author_id"], 0) + row["score"]

    # 3. Batch fetch all answer scores for these users (single query)
    a_result = (
        supabase.table("answers")
        .select("author_id, score")
        .in_("author_id", user_ids)
        .execute()
    )
    a_scores: dict[str, int] = {}
    for row in (a_result.data or []):
        a_scores[row["author_id"]] = a_scores.get(row["author_id"], 0) + row["score"]

    # 4. Batch fetch all question votes cast by these users (single query)
    qv_result = (
        supabase.table("question_votes")
        .select("user_id")
        .in_("user_id", user_ids)
        .execute()
    )
    qv_counts: dict[str, int] = {}
    for row in (qv_result.data or []):
        qv_counts[row["user_id"]] = qv_counts.get(row["user_id"], 0) + 1

    # 5. Batch fetch all answer votes cast by these users (single query)
    av_result = (
        supabase.table("answer_votes")
        .select("user_id")
        .in_("user_id", user_ids)
        .execute()
    )
    av_counts: dict[str, int] = {}
    for row in (av_result.data or []):
        av_counts[row["user_id"]] = av_counts.get(row["user_id"], 0) + 1

    # Build response
    stats = []
    for u in user_list:
        uid = u["id"]
        activity = u["question_count"] + u["answer_count"]
        feedback = q_scores.get(uid, 0) + a_scores.get(uid, 0)
        contribution = qv_counts.get(uid, 0) + av_counts.get(uid, 0)
        stats.append(UserUsageStats(
            id=uid,
            username=u["username"],
            activity_score=activity,
            feedback_score=feedback,
            contribution_score=contribution,
            question_count=u["question_count"],
            answer_count=u["answer_count"],
            created_at=u["created_at"],
        ))

    stats.sort(key=lambda s: s.activity_score, reverse=True)
    return stats


@router.get("/username/{username}", response_model=UserPublic)
async def get_user_by_username(username: str):
    """
    Get a user's public profile by username.

    Public endpoint - no authentication required.
    """
    result = (
        supabase.table("users")
        .select(USER_PUBLIC_FIELDS)
        .eq("username", username)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")

    return _format_user(result.data[0])


@router.get("/{user_id}", response_model=UserPublic)
async def get_user_profile(user_id: str):
    """
    Get a user's public profile by ID.

    Public endpoint - no authentication required.
    """
    result = (
        supabase.table("users")
        .select(USER_PUBLIC_FIELDS)
        .eq("id", user_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")

    return _format_user(result.data[0])


@router.get("/{user_id}/questions", response_model=QuestionListResponse)
async def get_user_questions(
    user_id: str,
    sort: SortOption = Query(SortOption.newest, description="Sort order: 'newest' (default) or 'top'"),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
):
    """
    Get all questions posted by a user.

    - Sort by 'newest' (default) or 'top' (by score)
    - Returns 20 questions per page

    Public endpoint - no authentication required.
    """
    # Verify user exists
    user_check = supabase.table("users").select("id").eq("id", user_id).execute()
    if not user_check.data:
        raise HTTPException(status_code=404, detail="User not found")

    # Get total count
    count_result = (
        supabase.table("questions")
        .select("id", count="exact")
        .eq("author_id", user_id)
        .execute()
    )
    total = count_result.count or 0
    total_pages = math.ceil(total / PAGE_SIZE) if total > 0 else 1

    if page > total_pages:
        raise HTTPException(
            status_code=404,
            detail=f"Page {page} not found. Total pages: {total_pages}"
        )

    # Get questions
    offset = (page - 1) * PAGE_SIZE
    query = (
        supabase.table("questions")
        .select("*, users!questions_author_id_fkey(username), forums(name)")
        .eq("author_id", user_id)
    )

    if sort == SortOption.top:
        query = query.order("score", desc=True).order("created_at", desc=True)
    else:
        query = query.order("created_at", desc=True)

    result = query.range(offset, offset + PAGE_SIZE - 1).execute()

    questions = [
        QuestionPublic(
            id=q["id"],
            title=q["title"],
            body=q["body"],
            forum_id=q["forum_id"],
            forum_name=q["forums"]["name"],
            author_id=q["author_id"],
            author_username=q["users"]["username"],
            upvote_count=q["upvote_count"],
            downvote_count=q["downvote_count"],
            score=q["score"],
            answer_count=q["answer_count"],
            created_at=q["created_at"],
        )
        for q in result.data
    ]

    return QuestionListResponse(
        questions=questions,
        page=page,
        total_pages=total_pages,
    )


@router.get("/{user_id}/answers", response_model=AnswerListResponse)
async def get_user_answers(
    user_id: str,
    sort: SortOption = Query(SortOption.newest, description="Sort order: 'newest' (default) or 'top'"),
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
):
    """
    Get all answers posted by a user.

    - Sort by 'newest' (default) or 'top' (by score)
    - Returns 20 answers per page

    Public endpoint - no authentication required.
    """
    # Verify user exists
    user_check = supabase.table("users").select("id").eq("id", user_id).execute()
    if not user_check.data:
        raise HTTPException(status_code=404, detail="User not found")

    # Get total count
    count_result = (
        supabase.table("answers")
        .select("id", count="exact")
        .eq("author_id", user_id)
        .execute()
    )
    total = count_result.count or 0
    total_pages = math.ceil(total / PAGE_SIZE) if total > 0 else 1

    if page > total_pages:
        raise HTTPException(
            status_code=404,
            detail=f"Page {page} not found. Total pages: {total_pages}"
        )

    # Get answers
    offset = (page - 1) * PAGE_SIZE
    query = (
        supabase.table("answers")
        .select("*, users!answers_author_id_fkey(username)")
        .eq("author_id", user_id)
    )

    if sort == SortOption.top:
        query = query.order("score", desc=True).order("created_at", desc=True)
    else:
        query = query.order("created_at", desc=True)

    result = query.range(offset, offset + PAGE_SIZE - 1).execute()

    answers = [
        AnswerPublic(
            id=a["id"],
            body=a["body"],
            question_id=a["question_id"],
            author_id=a["author_id"],
            author_username=a["users"]["username"],
            status=a["status"],
            upvote_count=a["upvote_count"],
            downvote_count=a["downvote_count"],
            score=a["score"],
            created_at=a["created_at"],
        )
        for a in result.data
    ]

    return AnswerListResponse(
        answers=answers,
        page=page,
        total_pages=total_pages,
    )
