from fastapi import APIRouter, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request
from app.database import supabase
from app.models.user import UserRegisterRequest, UserRegisterResponse, UserPublic
from app.utils.api_key import generate_api_key

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRegisterResponse)
@limiter.limit("5/minute")
async def register(request: Request, body: UserRegisterRequest):
    """
    Register a new user and receive an API key.

    The API key is only shown once - store it securely!
    """
    # Generate API key
    full_api_key, prefix, hashed_key = generate_api_key()

    # Insert user into database
    try:
        result = supabase.table("users").insert({
            "username": body.username,
            "api_key_prefix": prefix,
            "api_key_hash": hashed_key,
        }).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create user")

        user_data = result.data[0]

        return UserRegisterResponse(
            user=UserPublic(
                id=user_data["id"],
                username=user_data["username"],
                question_count=user_data.get("question_count", 0),
                answer_count=user_data.get("answer_count", 0),
                reputation=user_data.get("reputation", 0),
                created_at=user_data["created_at"],
            ),
            api_key=full_api_key,
        )

    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e)
        # Check for unique constraint violation (username already taken)
        if "duplicate key" in error_message or "unique constraint" in error_message.lower():
            raise HTTPException(status_code=409, detail="Username already taken. Please try a different username.")
        raise HTTPException(status_code=500, detail="Registration failed")
