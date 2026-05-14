from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.config import settings
from backend.database import init_db
from backend.routers import youtube, books, downloads, ws
from backend.services.file_manager import cleanup_expired_files

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler.add_job(cleanup_expired_files, "interval", minutes=10)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="MediaFlow Downloader",
    description="Bulk media download platform for YouTube playlists and digital books",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(youtube.router)
app.include_router(books.router)
app.include_router(downloads.router)
app.include_router(ws.router)

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
async def root():
    return FileResponse("frontend/index.html")


@app.get("/sw.js")
async def service_worker():
    return FileResponse("frontend/sw.js", media_type="application/javascript")


@app.get("/manifest.json")
async def manifest():
    return {
        "name": "MediaFlow Downloader",
        "short_name": "MediaFlow",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#6366f1",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=True)
