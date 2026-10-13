from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.core.openrouter import AVAILABLE_MODELS, AvailableModel

router = APIRouter(tags=["Chats"])


@router.get("/models", response_model=list[AvailableModel], dependencies=[Depends(get_current_user)])
async def list_models():
    return AVAILABLE_MODELS
