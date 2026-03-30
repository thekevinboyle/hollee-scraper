"""File storage pipeline -- saves documents to organized folder structure."""

import hashlib
import logging
import os
import re
from pathlib import Path

from og_scraper.scrapers.items import DocumentItem

logger = logging.getLogger(__name__)

# Base directory for document storage
DATA_DIR = os.environ.get("DOCUMENTS_DIR", "data/documents")


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:100]  # Limit length


class FileStoragePipeline:
    """Saves document files to the organized folder structure.

    Path format: data/documents/{state_code}/{operator_slug}/{doc_type}/{hash}.{ext}

    If operator_name is unknown, uses '_unknown' as the operator slug.
    """

    def process_item(self, item, spider):
        if not isinstance(item, DocumentItem):
            return item

        if not item.file_content:
            return item  # No file content to save

        # Compute hash if not already set
        if not item.file_hash:
            item.file_hash = hashlib.sha256(item.file_content).hexdigest()

        # Build the directory path
        operator_slug = slugify(item.operator_name) if item.operator_name else "_unknown"
        doc_type_slug = item.doc_type.replace("_", "-")
        ext = item.file_format or "bin"

        dir_path = Path(DATA_DIR) / item.state_code / operator_slug / doc_type_slug
        dir_path.mkdir(parents=True, exist_ok=True)

        # Filename is first 16 chars of SHA-256 hash + extension
        filename = f"{item.file_hash[:16]}.{ext}"
        file_path = dir_path / filename

        # Write the file
        if not file_path.exists():
            file_path.write_bytes(item.file_content)
            logger.info(f"Saved document: {file_path}")
        else:
            logger.debug(f"File already exists: {file_path}")

        # Update item with the file path (relative to DATA_DIR)
        item.file_path = str(file_path)
        item.file_size_bytes = len(item.file_content)

        # Clear file_content from memory after saving
        item.file_content = None

        return item
