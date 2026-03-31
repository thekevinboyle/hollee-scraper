"""Huey task queue instance with SQLite backend.

This module provides the Huey instance shared between the API server
(for enqueuing tasks) and the worker process (for executing tasks).

Per DISCOVERY.md: no Redis. Huey uses a local SQLite file.
"""

from huey import SqliteHuey

from og_scraper.config import get_settings

settings = get_settings()

# Ensure the data directory exists
_huey_db_path = settings.huey_db_dir

huey_app = SqliteHuey(
    "og-scraper",
    filename=settings.huey_db_path,
)


def register_tasks():
    """Import task modules to register them with Huey. Called after module init."""
    import og_scraper.tasks.scrape_task  # noqa: F401


# Register tasks - this runs after huey_app is fully initialized
register_tasks()
