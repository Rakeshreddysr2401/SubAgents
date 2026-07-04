"""Document ingestion: extract text → chunk → embed → Qdrant `documents`."""

import io
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.rag.store import upsert_texts

logger = get_logger(__name__)


def _extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    # txt / md / anything else: decode as utf-8 (lossy)
    return data.decode("utf-8", errors="ignore")


async def ingest_document(user_id: str, filename: str, data: bytes) -> dict:
    """Ingest one uploaded document for a user. Returns {doc_id, filename, chunks}."""
    settings = get_settings()
    text = _extract_text(filename, data).strip()
    if not text:
        return {"doc_id": None, "filename": filename, "chunks": 0}

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )
    chunks = splitter.split_text(text)
    doc_id = str(uuid.uuid4())
    payloads = [
        {
            "user_id": user_id,
            "doc_id": doc_id,
            "filename": filename,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]
    await upsert_texts(settings.documents_collection, chunks, payloads)
    logger.info("Ingested '%s' for user=%s (%d chunks)", filename, user_id, len(chunks))
    return {"doc_id": doc_id, "filename": filename, "chunks": len(chunks)}
