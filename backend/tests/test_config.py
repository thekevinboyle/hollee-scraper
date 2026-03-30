"""Tests for application configuration."""

from og_scraper.config import Settings, get_settings


class TestSettings:
    def test_defaults(self):
        """Settings have sensible defaults."""
        settings = Settings()
        assert "asyncpg" in settings.database_url
        assert settings.environment == "development"
        assert settings.ocr_confidence_threshold == 0.80
        assert settings.api_v1_prefix == "/api/v1"

    def test_from_env(self, monkeypatch):
        """Settings can be loaded from environment variables."""
        monkeypatch.setenv(
            "DATABASE_URL", "postgresql+asyncpg://test:test@testdb:5432/testdb"
        )
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("LOG_LEVEL", "warning")

        settings = Settings()
        assert (
            settings.database_url
            == "postgresql+asyncpg://test:test@testdb:5432/testdb"
        )
        assert settings.environment == "production"
        assert settings.log_level == "warning"

    def test_ocr_threshold_from_env(self, monkeypatch):
        """OCR confidence threshold can be customized."""
        monkeypatch.setenv("OCR_CONFIDENCE_THRESHOLD", "0.90")
        settings = Settings()
        assert settings.ocr_confidence_threshold == 0.90

    def test_get_settings_returns_settings(self):
        """get_settings() returns a Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_huey_db_path_default(self):
        """Huey DB path has a sensible default."""
        settings = Settings()
        assert settings.huey_db_path == "data/huey.db"

    def test_app_version(self):
        """App version is set."""
        settings = Settings()
        assert settings.app_version == "0.1.0"

    def test_frontend_url_default(self):
        """Frontend URL defaults to localhost:3000."""
        settings = Settings()
        assert settings.frontend_url == "http://localhost:3000"

    def test_data_dir_default(self):
        """Data directory has a sensible default."""
        settings = Settings()
        assert settings.data_dir == "data"
        assert settings.documents_dir == "data/documents"
