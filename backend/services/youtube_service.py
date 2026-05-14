import asyncio
import re
from pathlib import Path
from backend.config import settings

QUALITY_MAP = {
    "144": "bestvideo[height<=144]+bestaudio/best[height<=144]",
    "360": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "480": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "720": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "best": "bestvideo+bestaudio/best",
}


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name)[:200]


def _format_duration(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _estimate_size(duration: int | None, quality: str) -> str | None:
    if duration is None:
        return None
    bitrate_map = {"144": 0.2, "360": 0.7, "480": 1.2, "720": 2.5, "1080": 5.0, "best": 5.0}
    mbps = bitrate_map.get(quality, 2.5)
    size_mb = (mbps * duration) / 8
    if size_mb > 1024:
        return f"{size_mb / 1024:.1f} GB"
    return f"{size_mb:.0f} MB"


async def get_playlist_info(url: str) -> dict:
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "ignoreerrors": True,
        "no_check_certificates": True,
    }

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _extract)

    if info is None:
        raise ValueError("Could not extract info from URL. Check the URL is valid.")

    entries = info.get("entries", [])
    if not entries:
        entries = [info]
        is_playlist = False
    else:
        entries = [e for e in entries if e is not None]
        entries = entries[:settings.max_playlist_size]
        is_playlist = True

    if not entries:
        raise ValueError("No videos found in the playlist.")

    videos = []
    for entry in entries:
        vid_id = entry.get("id", "")
        vid_url = entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={vid_id}"
        thumb = None
        if entry.get("thumbnail"):
            thumb = entry["thumbnail"]
        elif entry.get("thumbnails"):
            thumb = entry["thumbnails"][0].get("url") if entry["thumbnails"] else None
        if not thumb and vid_id:
            thumb = f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"

        videos.append({
            "id": vid_id,
            "title": entry.get("title", "Unknown"),
            "thumbnail": thumb,
            "duration": _format_duration(entry.get("duration")),
            "duration_seconds": entry.get("duration"),
            "url": vid_url,
            "file_size_estimate": _estimate_size(entry.get("duration"), "720"),
        })

    return {
        "title": info.get("title", "Single Video") if is_playlist else info.get("title", "Video"),
        "thumbnail": info.get("thumbnail"),
        "video_count": len(videos),
        "videos": videos,
    }


async def download_video(
    url: str,
    quality: str,
    fmt: str,
    output_dir: Path,
    progress_callback=None,
) -> dict:
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "restrictfilenames": False,
        "windowsfilenames": True,
        "ignoreerrors": False,
        "no_check_certificates": True,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 3,
    }

    if fmt == "mp3":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        format_str = QUALITY_MAP.get(quality, QUALITY_MAP["best"])
        ydl_opts["format"] = format_str
        ydl_opts["merge_output_format"] = "mp4"

    result = {"title": "", "file_path": "", "file_size": 0}

    def _progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0 and progress_callback:
                pct = min((downloaded / total) * 100, 99)
                try:
                    progress_callback(pct, d.get("speed"), d.get("eta"))
                except Exception:
                    pass
        elif d["status"] == "finished":
            result["file_path"] = d.get("filename", "")
            result["file_size"] = d.get("total_bytes", 0) or d.get("downloaded_bytes", 0)
            if progress_callback:
                try:
                    progress_callback(100, None, None)
                except Exception:
                    pass

    ydl_opts["progress_hooks"] = [_progress_hook]

    def _download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise ValueError("Failed to download video. The video may be unavailable or restricted.")
            result["title"] = info.get("title", "Unknown")
            prepared = ydl.prepare_filename(info)
            if fmt == "mp3":
                prepared = str(Path(prepared).with_suffix(".mp3"))
            elif fmt == "mp4":
                prepared = str(Path(prepared).with_suffix(".mp4"))
            result["file_path"] = prepared

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _download)

    fp = Path(result["file_path"])
    if not fp.exists():
        safe_title = _sanitize_filename(result["title"])
        search_patterns = [
            f"*{result['title']}*.mp4",
            f"*{result['title']}*.mp3",
            f"*{result['title']}*.webm",
            f"*{safe_title}*.mp4",
            f"*{safe_title}*.mp3",
        ]
        for pattern in search_patterns:
            try:
                matches = list(output_dir.glob(pattern))
                if matches:
                    newest = max(matches, key=lambda p: p.stat().st_mtime)
                    result["file_path"] = str(newest)
                    result["file_size"] = newest.stat().st_size
                    break
            except Exception:
                continue
        else:
            all_recent = sorted(output_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            for f in all_recent[:5]:
                if f.suffix in ('.mp4', '.mp3', '.webm', '.mkv') and f.stat().st_size > 1000:
                    result["file_path"] = str(f)
                    result["file_size"] = f.stat().st_size
                    break
            else:
                raise FileNotFoundError(f"Downloaded file not found. Check ffmpeg is installed for video merging.")

    fp = Path(result["file_path"])
    if fp.exists() and result["file_size"] == 0:
        result["file_size"] = fp.stat().st_size

    return result
