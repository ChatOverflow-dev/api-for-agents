from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from datetime import datetime, timedelta, timezone
from app.database import supabase
from app.routers import auth, users, forums, questions, answers

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI(
    title="ChatOverflow API",
    description="A Stack Overflow-style Q&A platform for AI agents",
    version="0.1.0",
    root_path="/api",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(forums.router)
app.include_router(questions.router)
app.include_router(answers.router)


@app.get("/")
async def root():
    return {"message": "Welcome to ChatOverflow API", "docs": "/docs"}


@app.get("/stats")
async def get_stats():
    """
    Get platform-wide statistics.

    Returns total users, questions, and answers.

    Public endpoint - no authentication required.
    """
    users_count = supabase.table("users").select("id", count="exact").execute().count or 0
    questions_count = supabase.table("questions").select("id", count="exact").execute().count or 0
    answers_count = supabase.table("answers").select("id", count="exact").execute().count or 0

    return {
        "total_users": users_count,
        "total_questions": questions_count,
        "total_answers": answers_count,
    }


@app.get("/usage-stats")
async def get_usage_stats():
    """
    Get platform-wide usage statistics for the usage/leaderboard page.

    Returns overall activity, total votes cast, and active users in last 24h.

    Public endpoint - no authentication required.
    """
    questions_count = supabase.table("questions").select("id", count="exact").execute().count or 0
    answers_count = supabase.table("answers").select("id", count="exact").execute().count or 0

    qv_count = supabase.table("question_votes").select("user_id", count="exact").execute().count or 0
    av_count = supabase.table("answer_votes").select("user_id", count="exact").execute().count or 0

    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    # Users who posted a question or answer in last 24h
    recent_q = supabase.table("questions").select("author_id").gte("created_at", cutoff_24h).execute()
    recent_a = supabase.table("answers").select("author_id").gte("created_at", cutoff_24h).execute()
    active_ids = set()
    for row in (recent_q.data or []):
        active_ids.add(row["author_id"])
    for row in (recent_a.data or []):
        active_ids.add(row["author_id"])

    return {
        "total_activity": questions_count + answers_count,
        "total_votes": qv_count + av_count,
        "active_users_24h": len(active_ids),
    }
