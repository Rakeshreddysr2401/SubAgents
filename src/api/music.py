"""Music station listing for the browser player panel."""

from fastapi import APIRouter, Depends

from src.api.deps import rate_limited_user
from src.configs.settings import get_settings

router = APIRouter(prefix="/music", tags=["music"])


@router.get("/stations")
async def list_stations(user_id: str = Depends(rate_limited_user)):
    return {"stations": get_settings().music_stations}
