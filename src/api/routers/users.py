"""User endpoints for testing authentication."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import get_current_user
from models.user import User


router = APIRouter(prefix="/users", tags=["users"])


class UserResponse(BaseModel):
    """Response model for user info."""

    id: int
    auth0_id: str
    email: str | None

    model_config = {"from_attributes": True}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Get the current authenticated user's info."""
    return current_user
