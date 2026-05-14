from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from datetime import datetime, timezone, timedelta
from backend.database import get_db
from backend.models import DownloadTask, TaskType, TaskStatus
from backend.schemas import BookSearchRequest, BookInfo, TaskResponse
from backend.services import book_service
from backend.config import settings

router = APIRouter(prefix="/api/books", tags=["Books"])


@router.post("/search", response_model=list[BookInfo])
async def search(req: BookSearchRequest):
    try:
        results = await book_service.search_books(req.query, req.search_type)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@router.get("/download/{book_id:path}")
async def download_book(
    book_id: str,
    fmt: str = Query(default="pdf"),
    mirror: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    task = DownloadTask(
        task_type=TaskType.BOOK,
        title=book_id,
        url=f"book://{book_id}",
        format=fmt,
        status=TaskStatus.DOWNLOADING,
        progress=50,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    try:
        result = await book_service.download_book_file(book_id, fmt, mirror)
        if not result:
            task.status = TaskStatus.FAILED
            task.error_message = "Book file not available in this format."
            await db.commit()
            raise HTTPException(
                status_code=404,
                detail="Book file not available. Try a different format or edition."
            )

        task.title = result["title"]
        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.file_path = result["file_path"]
        task.file_size = result["file_size"]
        task.completed_at = datetime.now(timezone.utc)
        task.expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.file_expiry_minutes)
        await db.commit()

        fp = Path(result["file_path"])
        return FileResponse(
            path=str(fp),
            filename=result.get("filename", fp.name),
            media_type="application/octet-stream",
        )
    except HTTPException:
        raise
    except Exception as e:
        task.status = TaskStatus.FAILED
        task.error_message = str(e)[:500]
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Download error: {str(e)[:200]}")
