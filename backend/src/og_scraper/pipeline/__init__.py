"""Document processing pipeline: text extraction, OCR, classification, data extraction, and normalization."""

from og_scraper.pipeline.classifier import ClassificationResult, DocumentClassifier
from og_scraper.pipeline.confidence import ConfidenceScorer, DocumentScore
from og_scraper.pipeline.extractor import DataExtractor, FieldExtractionResult, FieldValue
from og_scraper.pipeline.normalizer import DataNormalizer, NormalizationResult, slugify
from og_scraper.pipeline.pipeline import DocumentPipeline, ProcessingResult
from og_scraper.pipeline.text_extractor import ExtractionResult, PageResult, TextExtractor

__all__ = [
    "ClassificationResult",
    "ConfidenceScorer",
    "DataExtractor",
    "DataNormalizer",
    "DocumentClassifier",
    "DocumentPipeline",
    "DocumentScore",
    "ExtractionResult",
    "FieldExtractionResult",
    "FieldValue",
    "NormalizationResult",
    "PageResult",
    "ProcessingResult",
    "TextExtractor",
    "slugify",
]
