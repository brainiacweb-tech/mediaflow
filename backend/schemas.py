from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
from backend.models import TaskStatus, TaskType


class PlaylistInfoRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=2000)


class VideoInfo(BaseModel):
    id: str
    title: str
    thumbnail: str | None = None
    duration: str | None = None
    duration_seconds: int | None = None
    url: str
    file_size_estimate: str | None = None


class PlaylistInfo(BaseModel):
    title: str
    thumbnail: str | None = None
    video_count: int
    videos: list[VideoInfo]


class YouTubeDownloadRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=2000)
    quality: str = Field(default="best", pattern="^(144|360|480|720|1080|best)$")
    format: str = Field(default="mp4", pattern="^(mp4|mp3)$")
    video_ids: list[str] | None = None


class BookSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    search_type: str = Field(default="title", pattern="^(title|author|isbn)$")


class BookInfo(BaseModel):
    id: str
    title: str
    author: str | None = None
    cover_url: str | None = None
    description: str | None = None
    formats: list[str] = []
    file_size: str | None = None
    year: str | None = None
    isbn: str | None = None
    ia_id: str | None = None
    ext: str | None = None
    mirror: str | None = None


class BookDownloadRequest(BaseModel):
    book_id: str
    title: str
    author: str | None = None
    download_url: str
    format: str = "pdf"
    cover_url: str | None = None


class TaskResponse(BaseModel):
    id: str
    task_type: TaskType
    status: TaskStatus
    title: str
    url: str
    thumbnail: str | None = None
    quality: str | None = None
    format: str | None = None
    file_size: int | None = None
    progress: float
    error_message: str | None = None
    duration: str | None = None
    parent_task_id: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    expires_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProgressUpdate(BaseModel):
    task_id: str
    progress: float
    status: TaskStatus
    speed: str | None = None
    eta: str | None = None
    file_size: int | None = None
