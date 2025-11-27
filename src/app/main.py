import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Header, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import Base, get_db, engine
from app.models import TrackedFile
from app.schemas import (
    FileCreate,
    FileResponse,
    FileResponseEnvelope,
    FileListResponseEnvelope,
)


LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
    force=True,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Code Tracker API")


def compress_content(raw: str) -> str:
    """Collapse whitespace (spaces, tabs, newlines) to single spaces."""
    return re.sub(r"\s+", " ", raw).strip()


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """Extract API key from header and enforce its presence."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing x-api-key header",
        )
    return x_api_key

def normalize_timestamp(dt: datetime) -> datetime:
    """Ensure timestamps are naive UTC (strip timezone info)."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


@app.on_event("startup")
def on_startup() -> None:
    """Create tables, retrying a few times until MySQL is ready."""
    max_attempts = 10
    delay_seconds = 3

    for attempt in range(1, max_attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database schema created successfully")
            break
        except OperationalError as exc:
            logger.warning(
                "Database not ready (attempt %s/%s): %s",
                attempt,
                max_attempts,
                exc,
            )
            if attempt == max_attempts:
                logger.error("Could not connect to database after retries")
                raise
            time.sleep(delay_seconds)


@app.post(
    "/api/v1/files",
    response_model=FileResponseEnvelope,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tracked file entry",
)
def create_tracked_file(
    payload: FileCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
):
    try:
        compressed_content = compress_content(payload.fullContent)
        normalized_ts = normalize_timestamp(payload.timestamp)

        window_start = normalized_ts - timedelta(seconds=5)
        window_end = normalized_ts + timedelta(seconds=5)

        existing = (
            db.query(TrackedFile)
            .filter(
                TrackedFile.fileName == payload.fileName,
                TrackedFile.filePath == payload.filePath,
                TrackedFile.timestamp.between(window_start, window_end),
            )
            .order_by(TrackedFile.timestamp.desc())
            .first()
        )
        logger.debug("Existing entry within window: %s", existing)
        if existing:
            delta_seconds = abs(
                (normalized_ts - existing.timestamp).total_seconds()
            )
            logger.info(
                "Existing snapshot detected for %s (Δ=%ss)",
                payload.fileName,
                delta_seconds,
            )
            existing_data = (
                FileResponse.model_validate(existing).model_dump(mode="json")
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "message": "File snapshot already stored",
                    "data": existing_data,
                },
            )

        tracked_file = TrackedFile(
            fileName=payload.fileName,
            filePath=payload.filePath,
            key=api_key,
            fullContent=compressed_content,
            timestamp=normalized_ts,
        )
        db.add(tracked_file)
        db.commit()
        db.refresh(tracked_file)
        created_data = (
            FileResponse.model_validate(tracked_file).model_dump(mode="json")
        )
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "message": "File snapshot created",
                "data": created_data,
            },
        )
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to save file")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {exc}",
        )


@app.get("/api/v1/health", summary="Health check")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get(
    "/api/v1/files",
    response_model=FileListResponseEnvelope,
    summary="List tracked files for the provided API key",
)
def list_tracked_files(
    db: Session = Depends(get_db),
    api_key: str = Depends(require_api_key),
):
    rows = (
        db.query(TrackedFile)
        .filter(TrackedFile.key == api_key)
        .order_by(TrackedFile.created_at.desc())
        .all()
    )
    data = [FileResponse.model_validate(row) for row in rows]
    return {
        "message": f"{len(data)} file snapshots found",
        "data": data,
    }


