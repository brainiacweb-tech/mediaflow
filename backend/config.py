from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./downloader.db"
    download_dir: str = "./downloads"
    max_concurrent_downloads: int = 3
    file_expiry_minutes: int = 60
    max_playlist_size: int = 50
    rate_limit_per_minute: int = 30
    secret_key: str = "change-this-to-a-random-secret"
    isbndb_api_key: str = ""
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def download_path(self) -> Path:
        p = Path(self.download_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
