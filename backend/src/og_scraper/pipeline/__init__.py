"""Document processing pipeline: text extraction, OCR, data extraction, and normalization."""

from og_scraper.pipeline.extractor import DataExtractor, FieldExtractionResult, FieldValue
from og_scraper.pipeline.normalizer import DataNormalizer, NormalizationResult, slugify
from og_scraper.pipeline.text_extractor import ExtractionResult, PageResult, TextExtractor

__all__ = [
    "DataExtractor",
    "DataNormalizer",
    "ExtractionResult",
    "FieldExtractionResult",
    "FieldValue",
    "NormalizationResult",
    "PageResult",
    "TextExtractor",
    "slugify",
]
