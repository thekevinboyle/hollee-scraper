"""Huey task definitions package.

Re-exports the canonical Huey instance from the worker module.
Do NOT create a second instance -- there must be exactly one shared
between the API server and the Huey worker process.
"""

from og_scraper.worker import huey_app as huey

__all__ = ["huey"]
