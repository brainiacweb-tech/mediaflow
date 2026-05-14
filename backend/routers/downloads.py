from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from urllib.parse import quote
from backend.database import get_db
from backend.models import DownloadTask, TaskStatus
from backend.schemas import TaskResponse
from backend.services import download_manager, file_manager

router = APIRouter(prefix="/api/downloads", tags=["Downloads"])


@router.get("/", response_model=list[TaskResponse])
async def list_downloads(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    q = select(DownloadTask).order_by(desc(DownloadTask.created_at)).offset(offset).limit(limit)
    if status:
        q = q.where(DownloadTask.status == status)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{task_id}", response_model=TaskResponse)
async def get_download(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await db.get(DownloadTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/file")
async def download_file(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await db.get(DownloadTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != TaskStatus.COMPLETED or not task.file_path:
        raise HTTPException(status_code=400, detail="File not available")

    fp = Path(task.file_path)
    if not fp.exists():
        raise HTTPException(status_code=404, detail="File has been deleted")

    safe_name = quote(fp.name)
    return FileResponse(
        path=str(fp),
        filename=fp.name,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"{safe_name}\"; filename*=UTF-8''{safe_name}",
            "Cache-Control": "no-cache",
        },
    )


@router.post("/{task_id}/cancel")
async def cancel_download(task_id: str, db: AsyncSession = Depends(get_db)):
    ok = await download_manager.cancel_download(task_id, db)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "cancelled"}


@router.delete("/{task_id}")
async def delete_download(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await db.get(DownloadTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.file_path:
        p = Path(task.file_path)
        if p.exists():
            p.unlink()
    await db.delete(task)
    await db.commit()
    return {"status": "deleted"}


@router.post("/bulk-zip")
async def create_bulk_zip(task_ids: list[str], db: AsyncSession = Depends(get_db)):
    zip_path = await file_manager.create_zip(task_ids)
    if not zip_path:
        raise HTTPException(status_code=400, detail="No completed files found")
    return FileResponse(
        path=zip_path,
        filename=Path(zip_path).name,
        media_type="application/zip",
    )
