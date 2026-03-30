"""Rule-based document classifier for Oil & Gas regulatory documents.

Implements a three-strategy cascade for identifying document types:
1. Form number detection (confidence 0.98, nearly 100% accurate)
2. Header/footer agency analysis (combined with keyword matching)
3. Weighted keyword matching (fallback, confidence 0.30-0.90)

No LLMs or paid APIs -- entirely local and deterministic.

Usage:
    classifier = DocumentClassifier()
    result = classifier.classify(extracted_text)
    print(result.doc_type)       # e.g. "production_report"
    print(result.confidence)     # e.g. 0.85
    print(result.form_number)    # e.g. "TX_W-1" or None
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from og_scraper.pipeline.classification_rules import (
    AGENCY_PATTERNS,
    DOCUMENT_PATTERNS,
    FORM_PATTERNS,
)


@dataclass
class ClassificationResult:
    """Result of classifying a document by type."""

    doc_type: str  # e.g. "production_report", "well_permit", "unknown"
    confidence: float  # 0.0-1.0 classification confidence
    matched_keywords: list[str] = field(default_factory=list)
    form_number: str | None = None  # State form ID if detected (e.g. "TX_W-1")
    state_agency: str | None = None  # Detected state agency code (e.g. "TX")
    strategy: str = "keyword"  # "form_number", "header", "keyword", "combined", "none"
    scores: dict = field(default_factory=dict)  # All doc_type scores for debugging


def detect_form_number(text: str) -> tuple[str, str, str] | None:
    """Detect state-specific form numbers in document text.

    Returns (form_id, doc_type, state_code) or None.
    Nearly 100% accurate when a form number is found.
    """
    text_lower = text.lower()
    for form_id, config in FORM_PATTERNS.items():
        if re.search(config["pattern"], text_lower, re.IGNORECASE):
            return (form_id, config["type"], config["state"])
    return None


def analyze_header_footer(text: str, num_lines: int = 10) -> dict:
    """Analyze the first and last N lines of a document for classification clues.

    Detects:
    - State regulatory agency from header text
    - Document title patterns from first few lines

    Args:
        text: Full document text.
        num_lines: Number of lines to examine from head and tail.

    Returns:
        Dict with detected clues:
        {"state_agency": "TX" | None, "document_title": str | None}
    """
    lines = text.strip().split("\n")
    header_lines = lines[:num_lines]
    header_text = "\n".join(header_lines).lower()

    clues: dict[str, str | None] = {
        "state_agency": None,
        "document_title": None,
    }

    # Detect state agency from header
    for state, pattern in AGENCY_PATTERNS.items():
        if re.search(pattern, header_text, re.IGNORECASE):
            clues["state_agency"] = state
            break

    # Detect document title from header (common government form patterns)
    title_patterns = [
        r"^(.+?(?:report|permit|order|record|application).*)$",
    ]
    for pattern in title_patterns:
        for line in header_lines:
            match = re.search(pattern, line.strip(), re.IGNORECASE)
            if match and len(match.group(1)) < 100:
                clues["document_title"] = match.group(1).strip()
                break
        if clues["document_title"]:
            break

    return clues


def classify_by_keywords(text: str) -> ClassificationResult:
    """Classify document type using weighted keyword matching.

    Algorithm:
    1. For each document type, sum keyword weights for matched keywords
    2. Best type = highest total score
    3. Confidence = score / max_possible_score for that type
    4. Boost if 2+ strong signals (weight 3) found: * 1.3
    5. Penalty if second-best type is close (>70% of best): * 0.7

    Returns:
        ClassificationResult with type, confidence, and matched keywords.
    """
    text_lower = text.lower()
    scores: dict[str, tuple[float, list[str]]] = {}

    for doc_type, config in DOCUMENT_PATTERNS.items():
        total_score = 0
        matched: list[str] = []
        for keyword, weight in config["keywords"].items():
            if keyword in text_lower:
                total_score += weight
                matched.append(keyword)

        if total_score > 0:
            scores[doc_type] = (total_score, matched)

    if not scores:
        return ClassificationResult(doc_type="unknown", confidence=0.0, strategy="keyword")

    # Best scoring type
    best_type = max(scores, key=lambda k: scores[k][0])
    best_score, best_keywords = scores[best_type]

    # Confidence = normalized score
    max_possible = sum(DOCUMENT_PATTERNS[best_type]["keywords"].values())
    confidence = min(best_score / max_possible, 1.0)

    # Boost: 2+ strong signals found
    strong_matches = sum(1 for kw in best_keywords if DOCUMENT_PATTERNS[best_type]["keywords"].get(kw, 0) >= 3)
    if strong_matches >= 2:
        confidence = min(confidence * 1.3, 1.0)

    # Penalty: ambiguity -- second-best type is close
    sorted_scores = sorted(scores.values(), key=lambda x: x[0], reverse=True)
    if len(sorted_scores) >= 2:
        ratio = sorted_scores[1][0] / sorted_scores[0][0]
        if ratio > 0.7:
            confidence *= 0.7

    return ClassificationResult(
        doc_type=best_type,
        confidence=round(confidence, 4),
        matched_keywords=best_keywords,
        strategy="keyword",
        scores={dt: s[0] for dt, s in scores.items()},
    )


class DocumentClassifier:
    """Multi-strategy document classifier for O&G regulatory documents.

    Classification cascade (in priority order):
    1. Form number detection -- nearly 100% accurate, confidence 0.98
    2. Header/footer analysis + keyword matching -- combined for higher accuracy
    3. Keyword matching alone -- fallback, confidence 0.30-0.90

    If no strategy exceeds 0.30 confidence, returns "unknown".
    """

    # Minimum confidence to accept a classification (below this = "unknown")
    MIN_CONFIDENCE_THRESHOLD = 0.30

    def classify(self, text: str, metadata: dict | None = None) -> ClassificationResult:
        """Classify a document by type.

        Args:
            text: Extracted text from the document (from TextExtractor).
            metadata: Optional metadata dict with keys like "source_url", "filename",
                      "state" that can provide classification hints.

        Returns:
            ClassificationResult with doc_type, confidence, matched_keywords, form_number.
        """
        if not text or not text.strip():
            return ClassificationResult(
                doc_type="unknown",
                confidence=0.0,
                strategy="none",
            )

        # Strategy 1: Form number detection (highest priority, ~100% accurate)
        form_result = detect_form_number(text)
        if form_result:
            form_id, doc_type, state = form_result
            return ClassificationResult(
                doc_type=doc_type,
                confidence=0.98,
                matched_keywords=[form_id],
                form_number=form_id,
                state_agency=state,
                strategy="form_number",
            )

        # Strategy 2: Header/footer analysis
        header_clues = analyze_header_footer(text)

        # Strategy 3: Keyword matching
        keyword_result = classify_by_keywords(text)

        # Combine: if header gives us a state agency and keywords matched, boost confidence
        if header_clues["state_agency"] and keyword_result.confidence > 0:
            keyword_result.confidence = min(keyword_result.confidence * 1.15, 1.0)
            keyword_result.confidence = round(keyword_result.confidence, 4)
            keyword_result.state_agency = header_clues["state_agency"]
            keyword_result.strategy = "combined"

        # If metadata provides a state hint and it matches header detection, another small boost
        if metadata and metadata.get("state"):
            meta_state = metadata["state"].upper()
            if header_clues["state_agency"] == meta_state:
                keyword_result.confidence = min(keyword_result.confidence * 1.05, 1.0)
                keyword_result.confidence = round(keyword_result.confidence, 4)

        # Below threshold = unknown
        if keyword_result.confidence < self.MIN_CONFIDENCE_THRESHOLD:
            return ClassificationResult(
                doc_type="unknown",
                confidence=keyword_result.confidence,
                matched_keywords=keyword_result.matched_keywords,
                state_agency=header_clues.get("state_agency"),
                strategy=keyword_result.strategy,
                scores=keyword_result.scores,
            )

        return keyword_result
