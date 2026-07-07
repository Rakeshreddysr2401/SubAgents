"""Music station listing for the browser player panel."""

from fastapi import APIRouter, Depends

from src.api.auth import get_user_id
from src.configs.settings import get_settings

router = APIRouter(prefix="/music", tags=["music"])


@router.get("/stations")
async def list_stations(user_id: str = Depends(get_user_id)):
    return {"stations": get_settings().music_stations}
