"""POST /upload — ingest a document into the user's RAG corpus."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from src.api.auth import get_user_id
from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.models.schema import UploadResponse
from src.rag.ingestion import ingest_document
from src.services.rate_limit import enforce_rate_limit

logger = get_logger(__name__)
router = APIRouter()

_ALLOWED_SUFFIXES = (".pdf", ".txt", ".md")


@router.post("/upload", response_model=UploadResponse)
async def upload(
    file: UploadFile = File(...),
    user_id: str = Depends(get_user_id),
):
    await enforce_rate_limit("upload", user_id)
    settings = get_settings()

    name = (file.filename or "").lower()
    if not name.endswith(_ALLOWED_SUFFIXES):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(_ALLOWED_SUFFIXES)}",
        )

    data = await file.read()
    if len(data) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="File too large")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    result = await ingest_document(user_id, file.filename, data)
    return UploadResponse(**result)
