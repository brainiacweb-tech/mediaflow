from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.models import DownloadTask, TaskType, TaskStatus
from backend.schemas import PlaylistInfoRequest, PlaylistInfo, YouTubeDownloadRequest, TaskResponse
from backend.services import youtube_service, download_manager

router = APIRouter(prefix="/api/youtube", tags=["YouTube"])


@router.post("/info", response_model=PlaylistInfo)
async def get_info(req: PlaylistInfoRequest):
    try:
        info = await youtube_service.get_playlist_info(req.url)
        return info
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/download", response_model=list[TaskResponse])
async def start_download(req: YouTubeDownloadRequest, db: AsyncSession = Depends(get_db)):
    try:
        info = await youtube_service.get_playlist_info(req.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    videos = info["videos"]
    if req.video_ids:
        videos = [v for v in videos if v["id"] in req.video_ids]

    if not videos:
        raise HTTPException(status_code=400, detail="No videos selected")

    task_type = TaskType.YOUTUBE_AUDIO if req.format == "mp3" else TaskType.YOUTUBE_VIDEO

    tasks = []
    for video in videos:
        task = DownloadTask(
            task_type=task_type,
            title=video["title"],
            url=video["url"],
            thumbnail=video.get("thumbnail"),
            quality=req.quality,
            format=req.format,
            duration=video.get("duration"),
        )
        db.add(task)
        tasks.append(task)

    await db.commit()

    for task in tasks:
        await db.refresh(task)
        download_manager.queue_download(task.id)

    return tasks
