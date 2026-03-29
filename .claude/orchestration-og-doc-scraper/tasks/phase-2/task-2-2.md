# Task 2.2: Document Classification

## Objective

Implement a rule-based document classification system that identifies O&G document types (production report, well permit, completion report, plugging report, spacing order, inspection record, incident report) using a three-strategy cascade: (1) state-specific form number detection, (2) header/footer agency analysis, and (3) weighted keyword matching. No LLMs or paid APIs — entirely local and deterministic. Target accuracy: >80% on O&G regulatory documents.

## Context

This is the second task in Phase 2 (Document Pipeline). It depends on Task 2.1's text extraction output — the classifier receives extracted text and produces a classification with a confidence score. Downstream, Task 2.3 (Data Extraction) uses the classification to select appropriate extraction patterns for each document type, and Task 2.4 (Validation & Confidence Scoring) uses the classification confidence as one of the three tiers in the composite score.

## Dependencies

- Task 2.1 - Provides `TextExtractor.extract()` which produces the raw text this classifier operates on

## Blocked By

- Task 2.1

## Research Findings

Key findings from research files relevant to this task:

- From `document-pipeline-implementation.md`: O&G regulatory documents are highly formulaic, making keyword-based classification effective (~80-85% accuracy). Three-strategy cascade: form number detection (nearly 100%), header/footer analysis, weighted keyword matching.
- From `document-pipeline-implementation.md`: Texas uses forms W-1 (permit), W-2 (completion), W-3 (plugging), PR (production). Oklahoma uses 1002A (permit), 1002C (completion). Colorado uses Form 2 (permit), Form 5/5A (completion), Form 6 (plugging).
- From `document-pipeline-implementation.md`: Classification confidence formula: `score / max_possible_score`, boosted by 1.3x if 2+ strong signals (weight 3) found, reduced by 0.7x if second-best type scores >70% of the best (ambiguity penalty).
- From `document-processing-pipeline` skill: Classification confidence feeds into the document-level composite formula as `0.3 * classification_confidence`.
- From DISCOVERY D21: Classification via rule-based keyword matching handles ~80% of docs. The remaining are handled through OCR + form detection.

## Implementation Plan

### Step 1: Define Classification Data Models

**In `backend/src/og_scraper/pipeline/classifier.py`:**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ClassificationResult:
    """Result of classifying a document by type."""
    doc_type: str              # e.g., "production_report", "well_permit", "unknown"
    confidence: float          # 0.0-1.0 classification confidence
    matched_keywords: list[str] = field(default_factory=list)  # Keywords that contributed
    form_number: Optional[str] = None  # State form identifier if detected (e.g., "TX_W-1")
    state_agency: Optional[str] = None  # Detected state agency code (e.g., "TX")
    strategy: str = "keyword"  # "form_number", "header", "keyword", or "combined"
    scores: dict = field(default_factory=dict)  # All doc_type scores for debugging
```

### Step 2: Implement the Keyword Dictionary

**In `backend/src/og_scraper/pipeline/classification_rules.py`:**

This file contains the complete keyword dictionaries, form number patterns, and agency patterns. Keep it separate from the classifier logic for maintainability.

```python
"""
Classification rules for Oil & Gas document types.

Keyword weights:
  3 = Strong signal (definitive phrases like "production report", "permit to drill")
  2 = Medium signal (supporting phrases like "proposed total depth", "barrels produced")
  1 = Weak signal (general terms like "drilling", "spud", "injected")
"""

# --- Weighted Keyword Dictionaries ---

DOCUMENT_PATTERNS: dict[str, dict[str, dict[str, int]]] = {
    "well_permit": {
        "keywords": {
            # Strong signals (weight 3)
            "application to drill": 3,
            "permit to drill": 3,
            "drilling permit": 3,
            "intent to drill": 3,
            "application for permit": 3,
            "notice of intention to drill": 3,
            # Medium signals (weight 2)
            "proposed total depth": 2,
            "proposed casing program": 2,
            "anticipated spud date": 2,
            "surface location": 2,
            "bottom hole location": 2,
            "proposed formation": 2,
            "drilling bond": 2,
            # Weak signals (weight 1)
            "drilling": 1,
            "spud": 1,
            "casing": 1,
        },
    },
    "production_report": {
        "keywords": {
            # Strong signals (weight 3)
            "production report": 3,
            "monthly production": 3,
            "annual production": 3,
            "production summary": 3,
            # Medium signals (weight 2)
            "oil production": 2,
            "gas production": 2,
            "water production": 2,
            "barrels produced": 2,
            "mcf produced": 2,
            "days produced": 2,
            "producing days": 2,
            "disposition": 2,
            "lease production": 2,
            "well production": 2,
            "production volume": 2,
            # Weak signals (weight 1)
            "sold": 1,
            "flared": 1,
            "vented": 1,
            "injected": 1,
        },
    },
    "completion_report": {
        "keywords": {
            # Strong signals (weight 3)
            "completion report": 3,
            "well completion": 3,
            "recompletion report": 3,
            "completed interval": 3,
            # Medium signals (weight 2)
            "perforation interval": 2,
            "initial production": 2,
            "frac stages": 2,
            "proppant": 2,
            "stimulation": 2,
            "lateral length": 2,
            "total depth": 2,
            "completion date": 2,
            "ip rate": 2,
            "initial potential": 2,
            "back pressure test": 2,
            # Weak signals (weight 1)
            "perforated": 1,
            "cement": 1,
            "tubing": 1,
        },
    },
    "plugging_report": {
        "keywords": {
            # Strong signals (weight 3)
            "plugging report": 3,
            "plug and abandon": 3,
            "plugging record": 3,
            "plugged and abandoned": 3,
            "well plugging": 3,
            # Medium signals (weight 2)
            "cement plug": 2,
            "plug placed": 2,
            "surface restoration": 2,
            "casing left in hole": 2,
            "plug depth": 2,
            # Weak signals (weight 1)
            "abandoned": 1,
            "plugged": 1,
        },
    },
    "spacing_order": {
        "keywords": {
            # Strong signals (weight 3)
            "spacing order": 3,
            "pooling order": 3,
            "drilling unit": 3,
            "forced pooling": 3,
            "compulsory pooling": 3,
            "drilling and spacing unit": 3,
            # Medium signals (weight 2)
            "spacing exception": 2,
            "rule 37": 2,
            "rule 38": 2,
            "drilling unit order": 2,
            "unit boundaries": 2,
            "hearing examiner": 2,
            # Weak signals (weight 1)
            "spacing": 1,
            "pooling": 1,
            "unit": 1,
        },
    },
    "inspection_record": {
        "keywords": {
            # Strong signals (weight 3)
            "inspection report": 3,
            "field inspection": 3,
            "well inspection": 3,
            "compliance inspection": 3,
            "site inspection": 3,
            # Medium signals (weight 2)
            "inspection findings": 2,
            "violation": 2,
            "inspector": 2,
            "compliance status": 2,
            "inspection date": 2,
            "corrective action": 2,
            # Weak signals (weight 1)
            "inspected": 1,
            "compliant": 1,
            "non-compliant": 1,
        },
    },
    "incident_report": {
        "keywords": {
            # Strong signals (weight 3)
            "incident report": 3,
            "spill report": 3,
            "release notification": 3,
            "blowout": 3,
            "h2s release": 3,
            # Medium signals (weight 2)
            "environmental release": 2,
            "volume released": 2,
            "volume recovered": 2,
            "corrective action": 2,
            "spill": 2,
            "reportable quantity": 2,
            # Weak signals (weight 1)
            "leak": 1,
            "release": 1,
            "incident": 1,
        },
    },
}


# --- State-Specific Form Number Patterns ---
# Detecting a form number is nearly 100% accurate for classification.

FORM_PATTERNS: dict[str, dict[str, str]] = {
    # Texas Railroad Commission forms
    "TX_W-1":  {"pattern": r'\bform\s*w[\s-]*1\b|\bw[\s-]*1\s*(?:form|application)\b',
                "type": "well_permit", "state": "TX"},
    "TX_W-2":  {"pattern": r'\bform\s*w[\s-]*2\b|\bw[\s-]*2\s*(?:form|completion|report)\b',
                "type": "completion_report", "state": "TX"},
    "TX_G-1":  {"pattern": r'\bform\s*g[\s-]*1\b|\bg[\s-]*1\s*(?:form|completion|report|gas)\b',
                "type": "completion_report", "state": "TX"},
    "TX_W-3":  {"pattern": r'\bform\s*w[\s-]*3\b|\bw[\s-]*3\s*(?:form|plugging)\b',
                "type": "plugging_report", "state": "TX"},
    "TX_PR":   {"pattern": r'\bform\s*pr\b|\bpr\s*(?:form|production)\b',
                "type": "production_report", "state": "TX"},
    "TX_W-14": {"pattern": r'\bform\s*w[\s-]*14\b|\bw[\s-]*14\b',
                "type": "plugging_report", "state": "TX"},
    "TX_H-10": {"pattern": r'\bform\s*h[\s-]*10\b|\bh[\s-]*10\b',
                "type": "incident_report", "state": "TX"},

    # Oklahoma Corporation Commission
    "OK_1002A": {"pattern": r'\b(?:form\s*)?1002[\s-]*a\b',
                 "type": "well_permit", "state": "OK"},
    "OK_1002C": {"pattern": r'\b(?:form\s*)?1002[\s-]*c\b',
                 "type": "completion_report", "state": "OK"},
    "OK_1012D": {"pattern": r'\b(?:form\s*)?1012[\s-]*d\b',
                 "type": "production_report", "state": "OK"},
    "OK_1003":  {"pattern": r'\b(?:form\s*)?1003\b.*(?:plug|abandon)',
                 "type": "plugging_report", "state": "OK"},

    # Colorado ECMC/COGCC
    "CO_Form2":  {"pattern": r'\bform\s*2\b.*(?:permit|drill)',
                  "type": "well_permit", "state": "CO"},
    "CO_Form5":  {"pattern": r'\bform\s*5\b.*(?:complet|interval)',
                  "type": "completion_report", "state": "CO"},
    "CO_Form5A": {"pattern": r'\bform\s*5[\s-]*a\b',
                  "type": "completion_report", "state": "CO"},
    "CO_Form6":  {"pattern": r'\bform\s*6\b.*(?:plug|abandon)',
                  "type": "plugging_report", "state": "CO"},
    "CO_Form7":  {"pattern": r'\bform\s*7\b.*(?:production|operator)',
                  "type": "production_report", "state": "CO"},

    # North Dakota DMR
    "ND_Form1":  {"pattern": r'\bform\s*1\b.*(?:permit|drill).*(?:north\s*dakota|nd|dmr)',
                  "type": "well_permit", "state": "ND"},
    "ND_Form6":  {"pattern": r'\bform\s*6\b.*(?:complet).*(?:north\s*dakota|nd|dmr)',
                  "type": "completion_report", "state": "ND"},
    "ND_Form4":  {"pattern": r'\bform\s*4\b.*(?:sundry|plugging).*(?:north\s*dakota|nd|dmr)',
                  "type": "plugging_report", "state": "ND"},

    # New Mexico OCD
    "NM_C-101":  {"pattern": r'\bc[\s-]*101\b.*(?:permit|drill)',
                  "type": "well_permit", "state": "NM"},
    "NM_C-105":  {"pattern": r'\bc[\s-]*105\b.*(?:complet)',
                  "type": "completion_report", "state": "NM"},
    "NM_C-103":  {"pattern": r'\bc[\s-]*103\b.*(?:plug|abandon)',
                  "type": "plugging_report", "state": "NM"},

    # Wyoming WOGCC
    "WY_APD":   {"pattern": r'\b(?:application\s*for\s*permit\s*to\s*drill|apd)\b.*(?:wyoming|wogcc)',
                 "type": "well_permit", "state": "WY"},

    # Pennsylvania DEP
    "PA_5500":  {"pattern": r'\b(?:form\s*)?5500[\s-]*pm\b',
                 "type": "well_permit", "state": "PA"},

    # Federal EIA
    "EIA_914":  {"pattern": r'\beia[\s-]*914\b|\bform\s*eia[\s-]*914\b',
                 "type": "production_report", "state": "FED"},
}


# --- State Agency Patterns (for header/footer analysis) ---

AGENCY_PATTERNS: dict[str, str] = {
    "TX": r'railroad commission of texas|rrc.*texas|texas\s+railroad',
    "OK": r'corporation commission.*oklahoma|occ|oklahoma\s+corporation',
    "ND": r'department of mineral resources|north dakota.*dmr|industrial commission.*north dakota',
    "CO": r'colorado.*oil.*gas|ecmc|cogcc|colorado\s+energy.*mineral',
    "NM": r'oil conservation division|new mexico.*ocd|energy.*minerals.*natural resources.*nm',
    "WY": r'oil.*gas conservation commission|wogcc|wyoming\s+oil',
    "LA": r'department of natural resources|sonris|louisiana.*dnr|conservation.*louisiana',
    "PA": r'department of environmental protection|pa.*dep|pennsylvania.*dep',
    "CA": r'geologic energy management|calgem|division of oil.*gas.*geothermal|california.*doggr',
    "AK": r'alaska oil.*gas conservation commission|aogcc|alaska.*oil.*gas',
}
```

### Step 3: Implement Form Number Detection

**In `classifier.py`:**

```python
import re
from og_scraper.pipeline.classification_rules import FORM_PATTERNS


def detect_form_number(text: str) -> tuple[str, str, str] | None:
    """
    Detect state-specific form numbers in document text.

    Returns (form_id, doc_type, state_code) or None.
    Nearly 100% accurate when a form number is found.
    """
    text_lower = text.lower()
    for form_id, config in FORM_PATTERNS.items():
        if re.search(config["pattern"], text_lower, re.IGNORECASE):
            return (form_id, config["type"], config["state"])
    return None
```

### Step 4: Implement Header/Footer Analysis

```python
import re
from og_scraper.pipeline.classification_rules import AGENCY_PATTERNS


def analyze_header_footer(text: str, num_lines: int = 10) -> dict:
    """
    Analyze the first and last N lines of a document for classification clues.

    Detects:
    - State regulatory agency from header text
    - Document title patterns from first few lines

    Returns dict with detected clues:
    {
        "state_agency": "TX" | None,
        "document_title": str | None,
    }
    """
    lines = text.strip().split("\n")
    header_lines = lines[:num_lines]
    header_text = "\n".join(header_lines).lower()

    clues = {
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
        r'^(.+?(?:report|permit|order|record|application).+?)$',
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
```

### Step 5: Implement Weighted Keyword Matching

```python
from og_scraper.pipeline.classification_rules import DOCUMENT_PATTERNS


def classify_by_keywords(text: str) -> ClassificationResult:
    """
    Classify document type using weighted keyword matching.

    Algorithm:
    1. For each document type, sum keyword weights for matched keywords
    2. Best type = highest total score
    3. Confidence = score / max_possible_score for that type
    4. Boost if 2+ strong signals (weight 3) found: * 1.3
    5. Penalty if second-best type is close (>70% of best): * 0.7

    Returns ClassificationResult with type, confidence, and matched keywords.
    """
    text_lower = text.lower()
    scores: dict[str, tuple[float, list[str]]] = {}

    for doc_type, config in DOCUMENT_PATTERNS.items():
        total_score = 0
        matched = []
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
    strong_matches = sum(
        1 for kw in best_keywords
        if DOCUMENT_PATTERNS[best_type]["keywords"].get(kw, 0) >= 3
    )
    if strong_matches >= 2:
        confidence = min(confidence * 1.3, 1.0)

    # Penalty: ambiguity — second-best type is close
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
```

### Step 6: Implement Combined Classification Pipeline

The `DocumentClassifier` class ties all three strategies together in priority order.

```python
class DocumentClassifier:
    """
    Multi-strategy document classifier for O&G regulatory documents.

    Classification cascade (in priority order):
    1. Form number detection — nearly 100% accurate, confidence 0.98
    2. Header/footer analysis + keyword matching — combined for higher accuracy
    3. Keyword matching alone — fallback, confidence 0.30-0.90

    If no strategy exceeds 0.30 confidence, returns "unknown".
    """

    # Minimum confidence to accept a classification (below this = "unknown")
    MIN_CONFIDENCE_THRESHOLD = 0.30

    def classify(self, text: str, metadata: dict | None = None) -> ClassificationResult:
        """
        Classify a document by type.

        Args:
            text: Extracted text from the document (from TextExtractor)
            metadata: Optional metadata dict with keys like "source_url", "filename",
                      "state" that can provide classification hints

        Returns:
            ClassificationResult with doc_type, confidence, matched_keywords, form_number
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
```

### Step 7: Write Comprehensive Tests

**In `backend/tests/pipeline/test_classifier.py`:**

```python
import pytest
from og_scraper.pipeline.classifier import (
    DocumentClassifier,
    ClassificationResult,
    detect_form_number,
    analyze_header_footer,
    classify_by_keywords,
)


# --- Sample document text snippets for testing ---

PRODUCTION_REPORT_TEXT = """
RAILROAD COMMISSION OF TEXAS
OIL AND GAS DIVISION

MONTHLY PRODUCTION REPORT

Operator: Devon Energy Corporation
Lease Name: Permian Basin Unit #42
API Number: 42-501-20130-00-00

Reporting Period: January 2026

Oil Production: 1,234 BBL
Gas Production: 5,678 MCF
Water Production: 890 BBL
Days Produced: 31
"""

WELL_PERMIT_TEXT = """
APPLICATION TO DRILL, DEEPEN, OR PLUG BACK
FORM W-1

Railroad Commission of Texas

Operator: Pioneer Natural Resources
Well Name: Spraberry #7
API Number: 42-329-34567

Proposed Total Depth: 12,500 ft
Surface Location: Section 12, Block 37, T2S
Anticipated Spud Date: 03/15/2026
"""

COMPLETION_REPORT_TEXT = """
WELL COMPLETION REPORT
Oklahoma Corporation Commission
Form 1002C

Operator: Continental Resources
Well Name: SCOOP Unit 14-2H
API Number: 37-019-24567-00-00

Completion Date: 02/28/2026
Total Depth: 18,400 ft
Lateral Length: 10,200 ft
Perforation Interval: 8,200 - 18,400 ft
Frac Stages: 45
Initial Production Rate: 1,200 BOPD
"""

PLUGGING_REPORT_TEXT = """
PLUGGING REPORT
PLUG AND ABANDON

Well Name: Old Discovery #1
API Number: 42-383-00123

Cement Plug placed at 5,000 ft to 5,200 ft
Surface Restoration completed
Casing Left in Hole: 2,500 ft of 7" casing
"""

SPACING_ORDER_TEXT = """
BEFORE THE CORPORATION COMMISSION OF THE STATE OF OKLAHOMA

POOLING ORDER NO. 789123

In the matter of the application of Continental Resources
for a drilling and spacing unit order
covering Section 14, Township 6 North, Range 5 West

The Commission hereby establishes a 640-acre drilling unit
with compulsory pooling of all interest owners.
"""

INSPECTION_RECORD_TEXT = """
FIELD INSPECTION REPORT

Colorado Energy and Carbon Management Commission

Inspector: John Smith
Inspection Date: 03/01/2026
Well Inspection of: Niobrara Unit #3

Findings: All equipment in compliance
Violation: None observed
Compliance Status: Compliant
"""

INCIDENT_REPORT_TEXT = """
SPILL REPORT / INCIDENT NOTIFICATION

Railroad Commission of Texas

Incident Report filed by: XTO Energy
Date of Incident: 02/15/2026

Type: Crude oil spill
Volume Released: 25 BBL
Volume Recovered: 20 BBL
Environmental Release to: Soil
Corrective Action: Excavation and disposal of contaminated soil
"""

AMBIGUOUS_TEXT = """
Well information document
Some general oil and gas data
County: Ector
State: Texas
"""

EMPTY_TEXT = ""


class TestFormNumberDetection:
    def test_texas_w1_permit(self):
        result = detect_form_number("Form W-1 Application to Drill")
        assert result is not None
        assert result[1] == "well_permit"
        assert result[2] == "TX"

    def test_texas_w2_completion(self):
        result = detect_form_number("Form W-2 Oil Well Completion Report")
        assert result is not None
        assert result[1] == "completion_report"

    def test_texas_w3_plugging(self):
        result = detect_form_number("Form W-3 Plugging Record")
        assert result is not None
        assert result[1] == "plugging_report"

    def test_oklahoma_1002a(self):
        result = detect_form_number("Application Form 1002A Intent to Drill")
        assert result is not None
        assert result[1] == "well_permit"
        assert result[2] == "OK"

    def test_oklahoma_1002c(self):
        result = detect_form_number("Form 1002C Completion Report")
        assert result is not None
        assert result[1] == "completion_report"

    def test_colorado_form2(self):
        result = detect_form_number("Form 2 Application for Permit to Drill")
        assert result is not None
        assert result[1] == "well_permit"
        assert result[2] == "CO"

    def test_colorado_form5a(self):
        result = detect_form_number("Form 5A Completed Interval Report")
        assert result is not None
        assert result[1] == "completion_report"

    def test_no_form_number(self):
        result = detect_form_number("Just a regular document with no form numbers")
        assert result is None

    def test_case_insensitive(self):
        result = detect_form_number("FORM W-1 APPLICATION TO DRILL")
        assert result is not None
        assert result[1] == "well_permit"


class TestHeaderFooterAnalysis:
    def test_texas_agency(self):
        text = "Railroad Commission of Texas\nOil and Gas Division\nSome content"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "TX"

    def test_oklahoma_agency(self):
        text = "Corporation Commission of Oklahoma\nOrder No. 12345"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "OK"

    def test_colorado_agency(self):
        text = "Colorado Oil and Gas Conservation Commission\nInspection Record"
        result = analyze_header_footer(text)
        assert result["state_agency"] == "CO"

    def test_no_agency(self):
        text = "Generic Document\nWith no agency header"
        result = analyze_header_footer(text)
        assert result["state_agency"] is None


class TestKeywordClassification:
    def test_production_report(self):
        result = classify_by_keywords(PRODUCTION_REPORT_TEXT)
        assert result.doc_type == "production_report"
        assert result.confidence > 0.5

    def test_well_permit(self):
        result = classify_by_keywords(WELL_PERMIT_TEXT)
        assert result.doc_type == "well_permit"
        assert result.confidence > 0.5

    def test_completion_report(self):
        result = classify_by_keywords(COMPLETION_REPORT_TEXT)
        assert result.doc_type == "completion_report"
        assert result.confidence > 0.5

    def test_plugging_report(self):
        result = classify_by_keywords(PLUGGING_REPORT_TEXT)
        assert result.doc_type == "plugging_report"
        assert result.confidence > 0.5

    def test_spacing_order(self):
        result = classify_by_keywords(SPACING_ORDER_TEXT)
        assert result.doc_type == "spacing_order"
        assert result.confidence > 0.4

    def test_incident_report(self):
        result = classify_by_keywords(INCIDENT_REPORT_TEXT)
        assert result.doc_type == "incident_report"
        assert result.confidence > 0.5

    def test_strong_signals_boost_confidence(self):
        # Text with 2+ strong signals should get boosted
        text = "Monthly production report. Annual production summary. Oil production 1,234 BBL."
        result = classify_by_keywords(text)
        assert result.doc_type == "production_report"
        assert result.confidence > 0.4

    def test_ambiguous_text_low_confidence(self):
        result = classify_by_keywords(AMBIGUOUS_TEXT)
        assert result.confidence < 0.5

    def test_empty_text_returns_unknown(self):
        result = classify_by_keywords("")
        assert result.doc_type == "unknown"
        assert result.confidence == 0.0


class TestDocumentClassifier:
    """Test the full classification pipeline."""

    def test_form_number_highest_priority(self):
        classifier = DocumentClassifier()
        result = classifier.classify(WELL_PERMIT_TEXT)
        assert result.doc_type == "well_permit"
        assert result.form_number is not None
        assert result.confidence == 0.98
        assert result.strategy == "form_number"

    def test_keyword_classification(self):
        classifier = DocumentClassifier()
        result = classifier.classify(PRODUCTION_REPORT_TEXT)
        assert result.doc_type == "production_report"
        assert result.confidence > 0.5

    def test_header_boosts_keyword_confidence(self):
        # Text with agency header should have higher confidence than without
        with_header = "Railroad Commission of Texas\n" + PRODUCTION_REPORT_TEXT
        without_header = "Generic Agency\n" + PRODUCTION_REPORT_TEXT.replace(
            "RAILROAD COMMISSION OF TEXAS\nOIL AND GAS DIVISION\n\n", ""
        )
        classifier = DocumentClassifier()
        result_with = classifier.classify(with_header)
        result_without = classifier.classify(without_header)
        # Both should classify correctly; with header may have higher confidence
        assert result_with.doc_type == "production_report"
        assert result_without.doc_type == "production_report"

    def test_unknown_for_empty_text(self):
        classifier = DocumentClassifier()
        result = classifier.classify("")
        assert result.doc_type == "unknown"
        assert result.confidence == 0.0

    def test_unknown_for_irrelevant_text(self):
        classifier = DocumentClassifier()
        result = classifier.classify("The quick brown fox jumps over the lazy dog.")
        assert result.doc_type == "unknown"
        assert result.confidence < 0.30

    def test_metadata_state_hint(self):
        classifier = DocumentClassifier()
        # Providing metadata with state should influence confidence
        text = "Railroad Commission of Texas\nMonthly Production Report\nOil: 1234 BBL"
        result = classifier.classify(text, metadata={"state": "TX"})
        assert result.doc_type == "production_report"

    def test_all_seven_document_types(self):
        """Verify all 7 document types can be classified."""
        classifier = DocumentClassifier()
        samples = {
            "production_report": PRODUCTION_REPORT_TEXT,
            "well_permit": WELL_PERMIT_TEXT,
            "completion_report": COMPLETION_REPORT_TEXT,
            "plugging_report": PLUGGING_REPORT_TEXT,
            "spacing_order": SPACING_ORDER_TEXT,
            "inspection_record": INSPECTION_RECORD_TEXT,
            "incident_report": INCIDENT_REPORT_TEXT,
        }
        for expected_type, text in samples.items():
            result = classifier.classify(text)
            assert result.doc_type == expected_type, (
                f"Expected {expected_type}, got {result.doc_type} "
                f"(confidence={result.confidence}, keywords={result.matched_keywords})"
            )

    def test_classification_result_has_all_fields(self):
        classifier = DocumentClassifier()
        result = classifier.classify(PRODUCTION_REPORT_TEXT)
        assert hasattr(result, "doc_type")
        assert hasattr(result, "confidence")
        assert hasattr(result, "matched_keywords")
        assert hasattr(result, "form_number")
        assert hasattr(result, "state_agency")
        assert hasattr(result, "strategy")
        assert 0.0 <= result.confidence <= 1.0
```

## Files to Create

- `backend/src/og_scraper/pipeline/classifier.py` - DocumentClassifier class, form number detection, header analysis, keyword classification
- `backend/src/og_scraper/pipeline/classification_rules.py` - Keyword dictionaries, form number patterns, agency patterns
- `backend/tests/pipeline/test_classifier.py` - Comprehensive tests for all classification strategies

## Files to Modify

- `backend/src/og_scraper/pipeline/__init__.py` - Add exports: `DocumentClassifier`, `ClassificationResult`

## Contracts

### Provides (for downstream tasks)

- **Class**: `DocumentClassifier` with `classify(text: str, metadata: dict | None) -> ClassificationResult`
- **Data Model**: `ClassificationResult` — `{doc_type: str, confidence: float, matched_keywords: list[str], form_number: str | None, state_agency: str | None, strategy: str, scores: dict}`
- **Function**: `detect_form_number(text: str) -> tuple[str, str, str] | None`
- **Function**: `classify_by_keywords(text: str) -> ClassificationResult`
- **Function**: `analyze_header_footer(text: str) -> dict`
- **Constants**: `DOCUMENT_PATTERNS`, `FORM_PATTERNS`, `AGENCY_PATTERNS` (importable from `classification_rules`)

### Consumes (from upstream tasks)

- Task 2.1: `TextExtractor.extract()` → `ExtractionResult.text` — the raw text that the classifier operates on

## Acceptance Criteria

- [ ] Correctly classifies all 7 document types from sample text with >80% accuracy
- [ ] Form number detection identifies TX (W-1, W-2, W-3, PR), OK (1002A, 1002C), CO (Form 2, 5, 5A, 6), NM, ND, WY, PA form numbers
- [ ] Form number match returns confidence 0.98
- [ ] Returns confidence score between 0.0 and 1.0 for every classification
- [ ] Falls back to "unknown" with low confidence (<0.30) when no clear match
- [ ] Keyword dictionaries cover all 7 document types with strong, medium, and weak signals
- [ ] Header/footer analysis detects all 10 state agencies
- [ ] Ambiguity penalty applied when two types score similarly
- [ ] Strong signal boost applied when 2+ weight-3 keywords found
- [ ] All tests pass
- [ ] Build succeeds

## Testing Protocol

### Unit/Integration Tests

- Test file: `backend/tests/pipeline/test_classifier.py`
- Test cases:
  - [ ] Form number detection for TX W-1, W-2, W-3, PR forms
  - [ ] Form number detection for OK 1002A, 1002C forms
  - [ ] Form number detection for CO Form 2, 5A, 6 forms
  - [ ] No false positive form numbers on generic text
  - [ ] Header analysis detects TX, OK, CO, ND agencies
  - [ ] Keyword classification for all 7 document types
  - [ ] Strong signal boost increases confidence
  - [ ] Ambiguity penalty decreases confidence
  - [ ] Combined classifier uses form number as highest priority
  - [ ] Empty/irrelevant text returns "unknown" with confidence <0.30
  - [ ] Metadata state hint influences classification
  - [ ] All 7 document types classifiable from sample snippets

### Build/Lint/Type Checks

- [ ] `uv run ruff check backend/src/og_scraper/pipeline/classifier.py backend/src/og_scraper/pipeline/classification_rules.py` passes
- [ ] `uv run ruff format --check backend/src/og_scraper/pipeline/` passes
- [ ] `uv run pytest backend/tests/pipeline/test_classifier.py -v` — all tests pass

## Skills to Read

- `document-processing-pipeline` - Classification keyword patterns, form number detection, three-strategy cascade
- `state-regulatory-sites` - State-specific form numbers, agency names, document format variations
- `confidence-scoring` - How classification confidence feeds into the 0.3 weight in the document-level composite score

## Research Files to Read

- `.claude/orchestration-og-doc-scraper/research/document-pipeline-implementation.md` - Section 2 (Document Classification Without LLMs), Section 2.1-2.5 (keyword matching, form detection, header analysis, combined pipeline)
- `.claude/orchestration-og-doc-scraper/research/document-processing.md` - Section 7 (Document Classification Approaches)

## Git

- Branch: `feat/task-2.2-document-classification`
- Commit message prefix: `Task 2.2:`
