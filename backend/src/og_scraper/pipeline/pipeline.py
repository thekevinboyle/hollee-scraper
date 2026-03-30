"""
Document processing pipeline orchestrator.

Runs all 7 stages: extract text -> classify -> extract fields -> normalize -> validate -> score -> route

Usage:
    pipeline = DocumentPipeline()
    result = pipeline.process(Path("document.pdf"), state="TX")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from og_scraper.pipeline.classifier import ClassificationResult, DocumentClassifier
from og_scraper.pipeline.confidence import ConfidenceScorer, DocumentScore
from og_scraper.pipeline.extractor import DataExtractor
from og_scraper.pipeline.extractor import FieldExtractionResult as FieldExtractionResult
from og_scraper.pipeline.normalizer import DataNormalizer, NormalizationResult
from og_scraper.pipeline.text_extractor import ExtractionResult as TextExtractionResult
from og_scraper.pipeline.text_extractor import TextExtractor

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Complete result from processing a document through the full pipeline."""

    # Input
    file_path: str
    state: str

    # Stage 1: Text extraction
    text_extraction: TextExtractionResult
    raw_text: str
    extraction_method: str

    # Stage 2: Classification
    classification: ClassificationResult
    doc_type: str

    # Stage 3: Field extraction
    field_extraction: FieldExtractionResult

    # Stage 4: Normalization
    normalization: NormalizationResult
    normalized_fields: dict[str, Any]

    # Stage 5+6: Validation & scoring
    score: DocumentScore
    disposition: Literal["accept", "review", "reject"]

    # Metadata
    processing_errors: list[str] = field(default_factory=list)
    processing_warnings: list[str] = field(default_factory=list)

    @property
    def overall_confidence(self) -> float:
        return self.score.document_confidence


class DocumentPipeline:
    """
    Orchestrates the full document processing pipeline.

    Stages:
    1. Text Extraction (PyMuPDF4LLM / PaddleOCR)
    2. Classification (form number / header / keyword)
    3. Field Extraction (regex patterns)
    4. Normalization (cross-state standardization)
    5. Validation (format checks, range checks)
    6. Confidence Scoring (three-tier)
    7. Disposition Routing (accept / review / reject)
    """

    def __init__(self) -> None:
        self.text_extractor = TextExtractor()
        self.classifier = DocumentClassifier()
        self.data_extractor = DataExtractor()
        self.normalizer = DataNormalizer()
        self.scorer = ConfidenceScorer()

    def process(self, file_path: Path | str, state: str = "") -> ProcessingResult:
        """
        Process a document through all pipeline stages.

        Args:
            file_path: Path to the document file (PDF)
            state: State code hint (e.g., "TX"). Optional but improves classification.

        Returns:
            ProcessingResult with all stage outputs and final disposition.
        """
        file_path = Path(file_path)
        errors: list[str] = []
        warnings: list[str] = []

        logger.info("Pipeline: Starting processing of %s (state=%s)", file_path, state)

        # Stage 1: Text Extraction
        logger.info("Pipeline: Stage 1 -- Text Extraction")
        text_result = self.text_extractor.extract(file_path)
        raw_text = text_result.text

        if not raw_text.strip():
            errors.append("No text extracted from document")
            logger.warning("Pipeline: No text extracted from %s", file_path)

        # Stage 2: Classification
        logger.info("Pipeline: Stage 2 -- Classification")
        metadata = {"state": state} if state else None
        classification = self.classifier.classify(raw_text, metadata=metadata)
        doc_type = classification.doc_type

        logger.info(
            "Pipeline: Classified as '%s' (confidence=%.3f, strategy=%s)",
            doc_type,
            classification.confidence,
            classification.strategy,
        )

        # Stage 3: Field Extraction
        logger.info("Pipeline: Stage 3 -- Field Extraction")
        field_extraction = self.data_extractor.extract(raw_text, doc_type, state)

        logger.info(
            "Pipeline: Extracted %d fields, %d errors",
            len(field_extraction.fields),
            len(field_extraction.extraction_errors),
        )
        errors.extend(field_extraction.extraction_errors)

        # Stage 4: Normalization
        logger.info("Pipeline: Stage 4 -- Normalization")
        normalization = self.normalizer.normalize(field_extraction)
        warnings.extend(normalization.warnings)

        # Stage 5+6: Validation & Confidence Scoring
        logger.info("Pipeline: Stage 5+6 -- Validation & Confidence Scoring")
        expected_fields = self.data_extractor.EXPECTED_FIELDS.get(doc_type, [])
        score = self.scorer.score(
            ocr_confidence=text_result.ocr_confidence,
            classification_confidence=classification.confidence,
            fields=field_extraction.fields,
            expected_fields=expected_fields,
        )

        logger.info(
            "Pipeline: Score=%.3f, disposition=%s, critical_override=%s",
            score.document_confidence,
            score.disposition,
            score.critical_field_override,
        )

        # Stage 7: Build result (routing happens in the caller -- Huey task or API)
        return ProcessingResult(
            file_path=str(file_path),
            state=state,
            text_extraction=text_result,
            raw_text=raw_text,
            extraction_method=text_result.method,
            classification=classification,
            doc_type=doc_type,
            field_extraction=field_extraction,
            normalization=normalization,
            normalized_fields=normalization.fields,
            score=score,
            disposition=score.disposition,
            processing_errors=errors,
            processing_warnings=warnings,
        )
