import asyncio
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.config import settings
from backend.database import async_session
from backend.models import DownloadTask, TaskStatus, TaskType
from backend.services import youtube_service

_active_tasks: dict[str, asyncio.Task] = {}
_semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)
_ws_connections: dict[str, set] = {}


def register_ws(task_id: str, ws):
    _ws_connections.setdefault(task_id, set()).add(ws)


def unregister_ws(task_id: str, ws):
    if task_id in _ws_connections:
        _ws_connections[task_id].discard(ws)


async def _broadcast_progress(task_id: str, progress: float, status: str, speed=None, eta=None, file_size=None):
    msg = json.dumps({
        "task_id": task_id,
        "progress": round(progress, 1),
        "status": status,
        "speed": f"{speed / 1024 / 1024:.1f} MB/s" if speed else None,
        "eta": f"{int(eta)}s" if eta else None,
        "file_size": file_size,
    })
    for ws_set in [_ws_connections.get(task_id, set()), _ws_connections.get("__all__", set())]:
        dead = []
        for ws in ws_set:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_set.discard(ws)


async def start_youtube_download(task_id: str):
    async with _semaphore:
        async with async_session() as db:
            task = await db.get(DownloadTask, task_id)
            if not task or task.status == TaskStatus.CANCELLED:
                return

            task.status = TaskStatus.DOWNLOADING
            await db.commit()
            await _broadcast_progress(task_id, 0, TaskStatus.DOWNLOADING)

        try:
            loop = asyncio.get_event_loop()

            def progress_cb(pct, speed, eta):
                asyncio.run_coroutine_threadsafe(
                    _update_progress(task_id, pct, speed, eta), loop
                )

            result = await youtube_service.download_video(
                url=task.url,
                quality=task.quality or "best",
                fmt=task.format or "mp4",
                output_dir=settings.download_path,
                progress_callback=progress_cb,
            )

            async with async_session() as db:
                task = await db.get(DownloadTask, task_id)
                if task and task.status != TaskStatus.CANCELLED:
                    task.status = TaskStatus.COMPLETED
                    task.progress = 100
                    task.file_path = result["file_path"]
                    task.file_size = result.get("file_size", 0)
                    task.completed_at = datetime.now(timezone.utc)
                    task.expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.file_expiry_minutes)
                    await db.commit()
                    await _broadcast_progress(task_id, 100, TaskStatus.COMPLETED, file_size=task.file_size)

        except Exception as e:
            async with async_session() as db:
                task = await db.get(DownloadTask, task_id)
                if task:
                    task.status = TaskStatus.FAILED
                    task.error_message = str(e)[:500]
                    await db.commit()
                    await _broadcast_progress(task_id, task.progress, TaskStatus.FAILED)
        finally:
            _active_tasks.pop(task_id, None)


async def _update_progress(task_id: str, pct: float, speed, eta):
    async with async_session() as db:
        await db.execute(
            update(DownloadTask).where(DownloadTask.id == task_id).values(progress=pct)
        )
        await db.commit()
    await _broadcast_progress(task_id, pct, TaskStatus.DOWNLOADING, speed, eta)


def queue_download(task_id: str):
    loop = asyncio.get_event_loop()
    t = loop.create_task(start_youtube_download(task_id))
    _active_tasks[task_id] = t


async def cancel_download(task_id: str, db: AsyncSession):
    task = await db.get(DownloadTask, task_id)
    if not task:
        return False
    task.status = TaskStatus.CANCELLED
    await db.commit()

    if task_id in _active_tasks:
        _active_tasks[task_id].cancel()
        _active_tasks.pop(task_id, None)

    await _broadcast_progress(task_id, task.progress, TaskStatus.CANCELLED)
    return True
