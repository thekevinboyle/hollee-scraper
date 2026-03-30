"""Application configuration via pydantic-settings.

Settings are loaded from environment variables with sensible defaults
for local development. In Docker, these are set via docker-compose.yml.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://ogdocs:ogdocs_dev@localhost:5432/ogdocs"
    sync_database_url: str = "postgresql://ogdocs:ogdocs_dev@localhost:5432/ogdocs"

    # Huey task queue
    huey_db_path: str = "data/huey.db"

    # File storage
    data_dir: str = "data"
    documents_dir: str = "data/documents"

    # Server
    environment: str = "development"
    log_level: str = "debug"
    debug: bool = True

    # CORS
    frontend_url: str = "http://localhost:3000"

    # OCR
    ocr_confidence_threshold: float = 0.80

    # API
    api_v1_prefix: str = "/api/v1"
    app_version: str = "0.1.0"
    app_title: str = "Oil & Gas Document Scraper API"

    @property
    def huey_db_dir(self) -> Path:
        """Ensure parent directory for Huey SQLite DB exists."""
        path = Path(self.huey_db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


def get_settings() -> Settings:
    """Create and return Settings instance."""
    return Settings()
