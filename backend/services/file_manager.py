import zipfile
import os
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from backend.config import settings
from backend.database import async_session
from backend.models import DownloadTask, TaskStatus


async def create_zip(task_ids: list[str]) -> str | None:
    async with async_session() as db:
        result = await db.execute(
            select(DownloadTask).where(
                DownloadTask.id.in_(task_ids),
                DownloadTask.status == TaskStatus.COMPLETED,
            )
        )
        tasks = result.scalars().all()

    if not tasks:
        return None

    zip_name = f"bulk_download_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = settings.download_path / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for task in tasks:
            if task.file_path and Path(task.file_path).exists():
                zf.write(task.file_path, Path(task.file_path).name)

    return str(zip_path)


async def cleanup_expired_files():
    now = datetime.now(timezone.utc)
    async with async_session() as db:
        result = await db.execute(
            select(DownloadTask).where(
                DownloadTask.expires_at != None,
                DownloadTask.expires_at < now,
            )
        )
        expired = result.scalars().all()

        for task in expired:
            if task.file_path:
                try:
                    p = Path(task.file_path)
                    if p.exists():
                        p.unlink()
                except OSError:
                    pass
            task.file_path = None
            task.status = TaskStatus.FAILED
            task.error_message = "File expired"

        await db.commit()

    for f in settings.download_path.iterdir():
        if f.is_file():
            age_minutes = (datetime.now(timezone.utc).timestamp() - f.stat().st_mtime) / 60
            if age_minutes > settings.file_expiry_minutes * 2:
                try:
                    f.unlink()
                except OSError:
                    pass
