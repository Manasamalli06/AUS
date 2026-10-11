import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.models.schemas import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import generate_token, user_manager, verify_token

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Dependency to extract authenticated user from Authorization: Bearer <token> header."""
    if not authorization:
        return None
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            return None
        token_data = verify_token(token)
        if not token_data:
            return None
        user = user_manager.get_user_by_id(token_data["user_id"])
        return user
    except Exception:
        return None


def require_auth(current_user: Optional[dict] = Depends(get_current_user)) -> dict:
    """Dependency that strictly requires an authenticated user."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


@auth_router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Creates a new user account with hashed password and returns an authentication bearer token.",
)
async def register(payload: UserRegisterRequest):
    try:
        user = user_manager.create_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
        )
        token = generate_token(user["id"], user["username"])
        return TokenResponse(
            access_token=token,
            user=UserResponse(
                id=user["id"],
                username=user["username"],
                email=user["email"],
                full_name=user["full_name"],
                created_at=user["created_at"],
            ),
            message="User registration successful",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error registering user: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again.",
        )


@auth_router.post(
    "/login",
    response_model=TokenResponse,
    summary="User login",
    description="Authenticates with username/email and password, returning an access token.",
)
async def login(payload: UserLoginRequest):
    user = user_manager.authenticate_user(
        username_or_email=payload.username_or_email, password=payload.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password.",
        )

    token = generate_token(user["id"], user["username"])
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            full_name=user["full_name"],
            created_at=user["created_at"],
        ),
        message="Login successful",
    )


@auth_router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Returns profile information for the authenticated token.",
)
async def get_me(current_user: dict = Depends(require_auth)):
    return UserResponse(
        id=current_user["id"],
        username=current_user["username"],
        email=current_user["email"],
        full_name=current_user.get("full_name"),
        created_at=current_user["created_at"],
    )
