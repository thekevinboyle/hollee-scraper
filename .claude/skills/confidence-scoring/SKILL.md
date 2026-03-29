---
name: confidence-scoring
description: Three-tier confidence scoring (OCR → field → document) with auto-accept/review/reject thresholds. Use when implementing data quality validation or review queue logic.
---

# Three-Tier Confidence Scoring System

## What It Is

A three-tier confidence scoring system that determines whether extracted data is **auto-accepted**, **sent to a review queue**, or **rejected**. This is the core quality control mechanism for the document processing pipeline, implementing the strict rejection policy defined in DISCOVERY D10: "Only store data above a confidence threshold. Low-confidence documents go to a review queue in the dashboard for manual verification."

Every document that passes through the seven-stage pipeline (discover, download, classify, extract, normalize, validate, store) receives a composite confidence score that gates whether its extracted data enters the production database.

## When to Use This Skill

- Implementing any part of the scoring pipeline (OCR processing, field extraction, document aggregation)
- Building or modifying the review queue logic and its dashboard UI
- Adding new field-level validation rules or extraction patterns
- Tuning confidence thresholds or field weights
- Working on the `extracted_documents` or `extracted_fields` database tables
- Debugging why documents are being rejected or sent to review unexpectedly
- Adding new document types or fields that need scoring

---

## The Three Tiers

### Tier 1: OCR Confidence

PaddleOCR provides two native confidence metrics per detected text region:

| Score | Field | Range | Meaning |
|-------|-------|-------|---------|
| Detection confidence | `dt_scores` | 0.0-1.0 | Probability that a detected bounding box contains text |
| Recognition confidence | `rec_score` | 0.0-1.0 | Probability that OCR recognized the text correctly |

**How OCR confidence flows upward:**
1. Each text line gets a `rec_score` from PaddleOCR
2. Per-page OCR confidence is calculated as a **weighted average** of all text line confidences on that page, weighted by text region size (bounding box area)
3. Document-level OCR confidence uses the **minimum page confidence** across all pages (weakest-link approach), stored as `min_page_ocr_confidence`

**Text PDFs vs. scanned PDFs:**
- Text-extractable PDFs get a confidence of 1.0 (no OCR needed)
- Scanned PDFs use actual PaddleOCR scores
- Mixed documents track per-page extraction method in `page_confidences` JSONB column

```python
# Per-page confidence metadata stored as JSONB
# Example: [
#   {"page": 0, "method": "text", "confidence": 1.0},
#   {"page": 1, "method": "ocr", "confidence": 0.87}
# ]
```

### Tier 2: Field-Level Confidence

Each extracted field receives its own confidence score based on multiple signals:

**Base confidence by extraction method:**

| Extraction Method | Base Confidence | Notes |
|-------------------|----------------|-------|
| `text_extraction` | 0.95 | Text PDFs are near-perfect |
| `ocr` | Uses raw `rec_score` | Varies per line quality |
| `table_extraction` | 0.85 (text) or `ocr_confidence * 0.9` (scanned) | Tables can have parsing errors |
| `regex` / `header_analysis` | 0.80 | Pattern-dependent |

**Modifiers applied to base confidence:**

1. **Pattern specificity** (`pattern_specificity`): Multiplier 0.0-1.0. A labeled match like `"API No: 42-501-20130"` has higher specificity than a bare 14-digit number found in body text.
2. **Validation penalty**: If the extracted value fails format validation, confidence is multiplied by 0.7.
3. **Cross-reference bonus**: If the value matches data from another source or field, confidence is multiplied by 1.1 (capped at 0.99).

```python
# Final field confidence formula:
confidence = base * pattern_specificity
if not value_validated:
    confidence *= 0.7
if cross_reference_match:
    confidence = min(confidence * 1.1, 0.99)
confidence = clamp(confidence, 0.0, 1.0)
```

**Field importance weights** (used when aggregating to document level):

| Weight | Fields |
|--------|--------|
| 3.0 | `api_number` |
| 2.5 | `operator_name`, `document_type` |
| 2.0 | `well_name`, `reporting_period`, `oil_bbls`, `gas_mcf` |
| 1.5 | `county`, `state`, `water_bbls`, `permit_number`, `dates`, `location` |
| 1.0 | `days_produced`, `well_status` (and any unlisted field) |

### Tier 3: Document-Level Confidence

A single composite score combining all tiers:

```
overall_confidence = 0.3 * classification_confidence
                   + 0.5 * weighted_field_confidence
                   + 0.2 * min_page_ocr_confidence
```

Where:
- `classification_confidence` = how confident the system is that it identified the correct document type (from the classify stage)
- `weighted_field_confidence` = weighted average of all field confidences using the importance weights above
- `min_page_ocr_confidence` = lowest OCR confidence across all pages in the document

---

## Thresholds and Disposition

Per DISCOVERY decisions D10 and D23:

### Document-Level Thresholds

| Disposition | Confidence Range | Action | Dashboard Display |
|-------------|-----------------|--------|-------------------|
| **Auto-accept** | >= 0.85 | Stored in `extracted_data` tables immediately, no review needed | Green checkmark |
| **Review queue** | 0.50 to 0.84 | Stored in staging tables, flagged in `review_queue`, shown in "Needs Review" dashboard tab | Yellow warning |
| **Reject** | < 0.50 | Rejected; metadata logged but data is NOT stored as valid; link to original PDF preserved | Red X |

### Field-Level Thresholds (Stricter for Critical Fields)

| Field | Auto-Accept | Review | Reject |
|-------|------------|--------|--------|
| API Number | >= 0.95 | 0.70 - 0.94 | < 0.70 |
| Operator Name | >= 0.90 | 0.60 - 0.89 | < 0.60 |
| Production Values (oil/gas/water) | >= 0.90 | 0.70 - 0.89 | < 0.70 |
| Dates | >= 0.90 | 0.65 - 0.89 | < 0.65 |
| Well Location / Coordinates | >= 0.95 | 0.80 - 0.94 | < 0.80 |
| Document Classification | >= 0.85 | 0.50 - 0.84 | < 0.50 |

### Critical Field Override Rule

If ANY critical field (API number, production values) falls below its reject threshold, the entire document is routed to the review queue regardless of the overall document confidence score.

---

## Field-Level Validation Patterns

### API Number
- Must match 14-digit format: `XX-YYY-ZZZZZ-SS-EE`
- Validate state code prefix against known state codes (02=Alaska, 04=California, 05=Colorado, 15=Kansas, 17=Louisiana, 25=Mississippi, 30=Montana, 32=New Mexico, 33=New York, 35=North Dakota, 36=Ohio, 37=Oklahoma, 39=Pennsylvania, 42=Texas, 45=Utah, 47=West Virginia, 49=Wyoming)
- County code must be a valid code for the given state
- Not all documents include the full 14 digits; some use 10 or 12 digits (dropping sidetrack/event codes). Accept both but note shorter formats in confidence metadata.
- Watch for Kern County, California overflow: uses two county codes (029 and 030)

### Production Volumes
- Must be positive numbers (or zero for shut-in wells)
- Oil: typically 0-50,000 bbls/month for a single well; flag values above 100,000
- Gas: typically 0-500,000 MCF/month; flag values above 1,000,000
- Water: typically 0-100,000 bbls/month
- Watch for unit confusion: MCF vs MMCF vs BCF (off by factors of 1,000)
- Cross-validate: if oil is reported but gas is missing (or vice versa), lower confidence

### Dates
- Must parse to a valid date
- Must not be in the future
- Reporting period dates should be within the last 2-6 months (states lag 2-6 months behind actual production)
- Accept multiple formats: MM/DD/YYYY, YYYY-MM-DD, DD-Mon-YY
- Permit dates can be older; completion dates must follow permit dates

### Coordinates (Latitude/Longitude)
- Must be within the boundaries of the stated US state
- Latitude range for continental US: approximately 24.5 to 49.0
- Longitude range for continental US: approximately -125.0 to -66.9
- Alaska: Lat 51.0-71.5, Lon -130.0 to -180.0 (and positive longitudes for Aleutians)
- Cross-check: coordinates should place the well within the stated county
- Watch for datum issues: NAD27 vs NAD83 vs WGS84 (can introduce 100+ meter errors)
- Historical wells may only have PLSS descriptions (no lat/long); flag as lower confidence

### Operator Names
- Cross-reference against a known operators table (built progressively as data is ingested)
- Fuzzy matching needed: the same operator appears under many name variations (e.g., "Devon Energy Corporation", "Devon Energy Production Co LP", "DEVON ENERGY CORP", "Devon")
- Normalize to canonical name when a match is found with sufficient confidence
- Flag completely unknown operators for review (they may be legitimate new/small operators)

---

## Review Queue Workflow

### Database Structure

Documents in the review queue live in the `extracted_documents` table with `processing_status = 'review_queue'`. Their extracted fields are in `extracted_fields` with `needs_review = TRUE` on fields below the field-level threshold.

```sql
-- Fast review queue queries use these indexes:
-- idx_documents_review ON extracted_documents(processing_status)
--     WHERE processing_status IN ('review_queue', 'pending');
-- idx_fields_review ON extracted_fields(needs_review) WHERE needs_review = TRUE;
```

### Dashboard Interaction

The "Needs Review" dashboard tab shows documents ordered by confidence (highest first, since those are easiest/quickest to review). For each document:

1. **Side-by-side view**: Source document (original PDF) displayed alongside extracted values
2. **Flagged fields highlighted**: Fields below their confidence threshold are visually marked
3. **Per-field confidence shown**: Each extracted value displays its confidence score and extraction method

### User Actions

| Action | Result | Database Update |
|--------|--------|----------------|
| **Approve** | Accept all extracted values as-is | `processing_status` -> `'manually_accepted'`; `reviewed_at` and `reviewed_by` set |
| **Correct** | User edits one or more field values | Original value saved to `original_value`; new value written to `field_value`; `manually_corrected` -> `TRUE`; correction logged in `data_corrections` table |
| **Reject** | Discard extracted data entirely | `processing_status` -> `'rejected'`; source file retained for reference |

### Corrections Tracking

Corrections are stored in the `data_corrections` table for future reference. This data can be used to:
- Identify systematic extraction errors (e.g., a regex that consistently misparses a field)
- Improve extraction patterns over time
- Audit data quality and reviewer accuracy

---

## Common Pitfalls

### Do NOT average OCR confidence naively
Weight by text region size (bounding box area). A tiny footnote with low OCR confidence should not drag down the score as much as a large data table with high confidence. Use `dt_polys` bounding box coordinates to calculate area.

### Use weighted scoring for fields
Some fields are far more important than others. The API number (weight 3.0) matters much more than `days_produced` (weight 1.0). A perfectly extracted API number with a slightly uncertain county name is very different from the reverse. The `FIELD_WEIGHTS` dictionary defines these weights.

### Adjust expectations for scanned documents
Scanned documents will naturally have lower OCR confidence (PaddleOCR averages ~90% accuracy per D5/D9). Do not set thresholds so high that all scanned documents are rejected. The 0.50 review-queue floor and 0.85 auto-accept threshold were chosen with this in mind.

### Missing/empty fields must penalize the score
If a field that should be present is missing entirely, it should contribute a confidence of 0.0 at its full weight to the weighted average. An empty API number on a production report is a serious quality issue and should push the document toward the review queue. Do not simply skip missing fields in the weighted average.

### Watch for the critical field override
Even if the overall document confidence is above 0.85, a single critical field (API number, production values) below its reject threshold forces the document into the review queue. This is by design -- an otherwise perfect document with a garbled API number is not trustworthy.

### Text PDFs are not always perfect
While text-extractable PDFs get a base confidence of 0.95 (not 1.0), some text PDFs have encoding issues, embedded fonts that map to wrong characters, or copy-protection that produces garbage text. Always validate extracted values regardless of extraction method.

### Per-page minimum vs. average
Document-level OCR confidence uses the **minimum** page confidence, not the average. One badly scanned page in a 10-page document should flag the whole document for review, because critical data might be on that bad page.

---

## Key Database Tables

| Table | Purpose |
|-------|---------|
| `extracted_documents` | Document-level metadata, confidence scores, processing status, review tracking |
| `extracted_fields` | Per-field extracted values, confidence, extraction method, review/correction state |
| `data_corrections` | Audit log of manual corrections for future pattern improvement |

### Key Columns on `extracted_documents`

- `processing_status`: `'pending'`, `'processing'`, `'auto_accepted'`, `'review_queue'`, `'rejected'`, `'manually_accepted'`, `'manually_corrected'`
- `overall_confidence`: The composite Tier 3 score
- `classification_confidence`: How confident the classify stage was
- `min_page_ocr_confidence`: Weakest OCR page
- `weighted_field_confidence`: Weighted average of all Tier 2 scores
- `page_confidences`: JSONB array of per-page OCR details

### Key Columns on `extracted_fields`

- `confidence`: The Tier 2 field confidence
- `extraction_method`: `'regex'`, `'ocr'`, `'table'`, `'text'`
- `needs_review`: Boolean flag for the review queue dashboard
- `manually_corrected`: Whether a reviewer edited this value
- `original_value`: Pre-correction value (populated only after correction)

---

## References

- **DISCOVERY document**: `.claude/orchestration-og-doc-scraper/DISCOVERY.md` -- See D10 (strict rejection policy), D15 (review queue), D23 (three-level confidence scoring)
- **Pipeline implementation research**: `.claude/orchestration-og-doc-scraper/research/document-pipeline-implementation.md` -- Section 5 (Confidence Scoring Implementation) contains full Python code for `FieldConfidence`, `DocumentConfidence`, `FIELD_WEIGHTS`, threshold tables, SQL schema, and dashboard query examples
- **Data models research**: `.claude/orchestration-og-doc-scraper/research/og-data-models.md` -- Section 2 (API Number Format), Section 6 (Data Quality Issues including operator name variations, unit inconsistencies, location data quality)
