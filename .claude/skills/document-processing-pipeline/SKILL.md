---
name: document-processing-pipeline
description: 7-stage document pipeline with PaddleOCR and PyMuPDF4LLM. Use when implementing document classification, OCR, text extraction, confidence scoring, or data normalization.
---

# Document Processing Pipeline

Seven-stage pipeline for processing oil and gas regulatory documents: **discover -> download -> classify -> extract -> normalize -> validate -> store**. Uses PaddleOCR for scanned documents and PyMuPDF4LLM for text-based PDFs. Fully local, no paid APIs.

---

## When to Use This Skill

- Implementing any stage of the 7-stage document pipeline
- Working with PaddleOCR or PyMuPDF4LLM for text extraction
- Building document classification (rule-based keyword matching, form number detection)
- Extracting structured data from O&G documents (API numbers, production volumes, dates, operators)
- Implementing confidence scoring at OCR, field, or document level
- Handling mixed PDFs (some pages text, some scanned)
- Building table extraction from production reports
- Setting up the review queue for low-confidence documents

---

## Pipeline Architecture

```
discover --> download --> classify --> extract --> normalize --> validate --> store
    |            |            |            |            |            |          |
    v            v            v            v            v            v          v
 Find docs    Fetch &      Identify    Pull out    Standardize  Cross-check  Write to
 on state     store        doc type    fields &    units, names  values &    PostgreSQL
 websites     originals    & state     tables      dates, etc.   flag low    & filesystem
                                                                 confidence
```

Each stage is independently retriable. If extraction (stage 4) fails, the document stays in "downloaded + classified" state and can be re-processed from stage 4 without re-downloading.

**Pipeline state machine stages:** `DISCOVERED` -> `DOWNLOADED` -> `CLASSIFIED` -> `EXTRACTED` -> `NORMALIZED` -> `VALIDATED` -> `STORED` (plus `FAILED` and `REVIEW` branches).

---

## Authentication and Setup

### PaddleOCR v3 (Scanned Document OCR)

**Packages:** `paddlepaddle` + `paddleocr`

```bash
# Create virtual environment (Python 3.9-3.12 supported)
python3 -m venv .venv
source .venv/bin/activate

# Install PaddlePaddle (CPU only on macOS Apple Silicon)
python -m pip install paddlepaddle==3.2.1

# Verify installation
python -c "import paddle; print(paddle.__version__)"

# Install PaddleOCR with document parsing support
python -m pip install "paddleocr[doc-parser]"
```

**macOS Apple Silicon environment variable (required):**

```bash
export KMP_DUPLICATE_LIB_OK=TRUE
```

**Memory management environment variable (recommended for batch processing):**

```python
import os
os.environ["CPU_RUNTIME_CACHE_CAPACITY"] = "20"  # Limit cached shapes to prevent memory leak
```

**Apple Silicon notes:**
- Uses CPU version only -- no GPU acceleration on macOS
- ARM64 natively supported in PaddlePaddle >= 3.2.x (no Rosetta needed)
- AVX extensions not available on ARM -- PaddlePaddle handles this natively
- Server models require ~200-400MB RAM each; full pipeline (layout + OCR + tables) uses ~1-1.5GB baseline

**Linux/Docker installation:**

```bash
# CPU
python -m pip install paddlepaddle==3.2.0

# GPU (CUDA 11.8)
python -m pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/
```

### PyMuPDF4LLM (Text-Based PDF Extraction)

```bash
python -m pip install pymupdf4llm
```

- Extremely fast: 50-100 pages/second for text PDFs on CPU
- Outputs clean markdown optimized for LLM consumption
- Based on C-backed MuPDF library (0.12s benchmark vs 1.29s for unstructured)
- No external dependencies beyond the pip package

### PPStructureV3 (Table Extraction)

Included with PaddleOCR. Provides 97.9% accuracy on table extraction benchmarks.

```python
from paddleocr import PPStructureV3

parser = PPStructureV3(
    use_doc_orientation_classify=True,
    use_table_recognition=True,
    use_seal_recognition=False,
    use_formula_recognition=False,
    use_chart_recognition=False,
    device="cpu",
    cpu_threads=4,
)
```

---

## Key Patterns

### 1. Text Extraction Strategy: PyMuPDF4LLM First, PaddleOCR Fallback

Classify each page as text or scanned, then route accordingly:

```python
import fitz  # PyMuPDF

def classify_pdf_pages(pdf_path: str) -> list[dict]:
    """Classify each page as text-based, scanned, or mixed."""
    doc = fitz.open(pdf_path)
    page_classifications = []

    for page_num, page in enumerate(doc):
        text = page.get_text("text").strip()
        text_length = len(text)
        images = page.get_images(full=True)
        page_rect = page.rect
        page_area = page_rect.width * page_rect.height

        image_coverage = 0.0
        for img in images:
            xref = img[0]
            try:
                img_rects = page.get_image_rects(xref)
                if img_rects:
                    for rect in img_rects:
                        image_coverage += (rect.width * rect.height) / page_area
            except Exception:
                image_coverage += 0.5 if images else 0.0

        has_substantial_text = text_length > 100
        is_mostly_image = image_coverage > 0.85

        if is_mostly_image and not has_substantial_text:
            classification = "scanned"
        elif has_substantial_text and image_coverage <= 0.5:
            classification = "text"
        elif text_length < 20 and not images:
            classification = "empty"
        else:
            classification = "mixed"

        page_classifications.append({
            "page_num": page_num,
            "classification": classification,
            "text_length": text_length,
            "image_count": len(images),
            "image_coverage": min(image_coverage, 1.0),
        })

    doc.close()
    return page_classifications
```

**Routing logic:**
- `text` pages -> PyMuPDF4LLM direct extraction (fast, confidence 1.0)
- `scanned` pages -> PaddleOCR (slower, confidence from OCR engine)
- `mixed` pages -> Try both, use whichever produces more text
- `empty` pages -> Skip

### 2. PaddleOCR Configuration for Government Documents

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(
    text_detection_model_name="PP-OCRv5_server_det",
    text_recognition_model_name="PP-OCRv5_server_rec",
    use_doc_orientation_classify=True,   # Auto-detect rotation
    use_doc_unwarping=False,             # Only for photographed docs
    text_det_thresh=0.3,                 # Lower catches faint text
    text_det_box_thresh=0.5,             # Lower for faded scans (default 0.6)
    text_rec_score_thresh=0.0,           # Keep ALL results, filter ourselves
    device="cpu",
    cpu_threads=4,
    enable_mkldnn=True,
)

# Access OCR results
results = ocr.predict("page_scan.png")
for res in results:
    for item in res.res:
        text = item["rec_text"]           # Recognized text
        confidence = item["rec_score"]     # Confidence 0-1
        bbox = item["dt_polys"]            # Bounding box coordinates
```

**Important:** PaddleOCR 3.x has breaking API changes from 2.x. Use `PaddleOCR` class with `.predict()` method.

### 3. Document Classification: Rule-Based Keyword Matching

Handles ~80% of documents. Three-strategy cascade:

1. **Form number detection** (nearly 100% accurate when found)
2. **Header/footer analysis** (state agency identification)
3. **Weighted keyword matching** (fallback)

```python
# Weighted keyword patterns -- higher weight = stronger signal
DOCUMENT_PATTERNS = {
    "well_permit": {
        "keywords": {
            "application to drill": 3, "permit to drill": 3, "drilling permit": 3,
            "proposed total depth": 2, "surface location": 2,
            "drilling": 1, "spud": 1,
        },
    },
    "production_report": {
        "keywords": {
            "production report": 3, "monthly production": 3, "annual production": 3,
            "oil production": 2, "gas production": 2, "barrels produced": 2,
            "mcf produced": 2, "days produced": 2,
        },
    },
    "completion_report": {
        "keywords": {
            "completion report": 3, "well completion": 3,
            "perforation interval": 2, "initial production": 2, "frac stages": 2,
        },
    },
    "plugging_report": {
        "keywords": {
            "plugging report": 3, "plug and abandon": 3,
            "cement plug": 2, "surface restoration": 2,
        },
    },
    "spacing_order": {
        "keywords": {
            "spacing order": 3, "pooling order": 3, "drilling unit": 3,
            "rule 37": 2, "rule 38": 2,
        },
    },
    "inspection_record": {
        "keywords": {
            "inspection report": 3, "field inspection": 3,
            "compliance inspection": 3, "violation": 2,
        },
    },
    "incident_report": {
        "keywords": {
            "incident report": 3, "spill report": 3,
            "blowout": 3, "environmental release": 2,
        },
    },
}
```

**State form number patterns (definitive classification):**

| State | Form | Document Type |
|-------|------|---------------|
| TX | W-1 | well_permit |
| TX | W-2 | completion_report |
| TX | W-3 | plugging_report |
| TX | PR | production_report |
| OK | 1002A | well_permit |
| OK | 1002C | completion_report |
| CO | Form 2 | well_permit |
| CO | Form 5/5A | completion_report |
| CO | Form 6 | plugging_report |

### 4. Regex Patterns for O&G Data Extraction

**API Numbers (14-digit well identifiers):**

```python
API_NUMBER_PATTERNS = {
    "api_14_hyphen": r'\b(\d{2}-\d{3}-\d{5}-\d{2}-\d{2})\b',
    "api_12_hyphen": r'\b(\d{2}-\d{3}-\d{5}-\d{2})\b',
    "api_10_hyphen": r'\b(\d{2}-\d{3}-\d{5})\b',
    "api_labeled":   r'(?:API\s*(?:No\.?|Number|#)?\s*[:.]?\s*)(\d{2}[-\s]?\d{3}[-\s]?\d{5}(?:[-\s]?\d{2})?(?:[-\s]?\d{2})?)',
}
# Structure: SS-CCC-WWWWW-SS-EE (state-county-well-sidetrack-event)
```

**Production Volumes:**

```python
# Oil (barrels)
r'(?:oil|crude)\s*(?:production|prod\.?)?\s*[:.]?\s*([\d,]+\.?\d*)\s*(?:bbl|bbls?|barrels?)'

# Gas (MCF)
r'(?:gas|natural\s*gas)\s*(?:production|prod\.?)?\s*[:.]?\s*([\d,]+\.?\d*)\s*(?:mcf|mmcf|cf)'

# Water (barrels)
r'(?:water|produced\s*water)\s*(?:production|prod\.?)?\s*[:.]?\s*([\d,]+\.?\d*)\s*(?:bbl|bbls?|barrels?)'

# Days produced
r'(?:days?\s*(?:produced|producing|on))\s*[:.]?\s*(\d+)'
```

**Dates:**

```python
LABELED_DATE_PATTERNS = {
    "spud_date":             r'(?:spud\s*date)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    "completion_date":       r'(?:completion\s*date|date\s*completed)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    "first_production_date": r'(?:first\s*(?:production|prod\.?)\s*date)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    "permit_date":           r'(?:permit\s*date|date\s*(?:of\s+)?permit)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    "reporting_period":      r'(?:reporting?\s*period|production\s*(?:month|period))\s*[:.]?\s*(\w+\s*\d{4}|\d{1,2}[/-]\d{4})',
    "plug_date":             r'(?:plug(?:ging)?\s*date|date\s*plugged)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    "inspection_date":       r'(?:inspection\s*date|date\s*(?:of\s+)?inspection)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
}
```

**Operator Names and Well Names:**

```python
# Operator name
r'(?:operator|lessee|company)\s*(?:name)?\s*[:.]?\s*([A-Z][A-Za-z\s&.,\'()-]+?)(?:\n|\r|operator|lease|well|api|county)'

# Well name
r'(?:well\s*name|well)\s*[:.]?\s*([A-Za-z0-9\s#\'-]+?)(?:\n|\r|well\s*(?:no|number)|api)'

# Permit number (generic)
r'(?:permit\s*(?:no\.?|number|#))\s*[:.]?\s*(\d{3,12})'
```

### 5. Three-Tier Confidence Scoring

**Level 1 -- OCR Confidence (per text line):**
- Provided by PaddleOCR `rec_score` field (0.0-1.0)
- Set `text_rec_score_thresh=0.0` to keep all results and filter downstream

**Level 2 -- Field-Level Confidence:**
- Based on extraction method, pattern specificity, and value validation
- Base confidence by method: text extraction (0.95), OCR (raw score), table extraction (0.85), regex (0.80-0.90)
- Apply pattern specificity multiplier (labeled "API No: XX" > bare digit sequence)
- Penalty for failed validation (0.7x), bonus for cross-reference match (1.1x)

**Level 3 -- Document-Level Confidence:**
- Composite formula: `0.3 * classification + 0.5 * weighted_fields + 0.2 * min_page_ocr`
- Fields weighted by importance: API number (3.0), operator (2.5), production values (2.0), dates (1.5)

**Disposition thresholds:**

| Tier | Overall Confidence | Action |
|------|-------------------|--------|
| **Auto-Accept** | >= 0.85 | Store in main tables immediately |
| **Review Queue** | 0.50 - 0.84 | Store in staging tables, flag for human review |
| **Reject** | < 0.50 | Store metadata only, link to original PDF |

**Field-level thresholds (stricter for critical fields):**

| Field | Auto-Accept | Review | Reject |
|-------|------------|--------|--------|
| API Number | >= 0.95 | 0.70-0.95 | < 0.70 |
| Operator Name | >= 0.90 | 0.60-0.90 | < 0.60 |
| Production Values | >= 0.90 | 0.70-0.90 | < 0.70 |
| Dates | >= 0.90 | 0.65-0.90 | < 0.65 |
| Well Location/Coords | >= 0.95 | 0.80-0.95 | < 0.80 |
| Document Classification | >= 0.85 | 0.50-0.85 | < 0.50 |

**Rejection policy:** If ANY critical field (API number, production values) is below the reject threshold, the entire document goes to the review queue regardless of overall confidence.

### 6. Table Extraction Strategy

| Table Type | PDF Type | Primary Tool | Fallback |
|-----------|----------|-------------|----------|
| Bordered tables | Text PDF | pdfplumber (lattice) | Camelot (lattice) |
| Borderless tables | Text PDF | pdfplumber (text strategy) | Camelot (stream) |
| Bordered tables | Scanned PDF | PP-StructureV3 (SLANeXt wired) | None |
| Borderless tables | Scanned PDF | PP-StructureV3 (SLANeXt wireless) | None |
| Complex/nested | Either | PP-StructureV3 | Manual extraction |

### 7. Image Preprocessing for Poor Quality Scans

```python
import cv2
import numpy as np

def preprocess_government_scan(image_path: str) -> np.ndarray:
    """Preprocess a scanned government document for optimal OCR accuracy."""
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    binary = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10
    )
    # Deskew
    coords = np.column_stack(np.where(binary > 0))
    if len(coords) > 100:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) > 0.5:
            (h, w) = binary.shape[:2]
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            binary = cv2.warpAffine(binary, M, (w, h),
                                     flags=cv2.INTER_CUBIC,
                                     borderMode=cv2.BORDER_REPLICATE)
    return binary
```

---

## Rate Limits and Constraints

- **PaddleOCR accuracy:** ~90% on scanned documents (higher on clean government forms, lower on poor scans)
- **No cloud fallback:** Local-only processing per project requirements. No paid OCR or LLM APIs
- **CPU throughput estimates:**
  - OCR (simple page): 0.5-1.0 pages/second
  - OCR (dense page): 0.3-0.5 pages/second
  - Full structure parsing (layout + OCR + tables): 0.2-0.5 pages/second
  - Text extraction via PyMuPDF: 50-100 pages/second
- **Memory:** Server models require ~1-1.5GB baseline RAM with layout + OCR + table models loaded
- **Batch estimate:** 1,000 scanned pages at full structure parsing takes ~30-60 minutes on modern laptop CPU (M-series Mac or Intel i7/i9). Text PDFs process the same volume in under a minute.
- **Minimum scan quality:** 300 DPI for text, 600 DPI for fine print. Grayscale sufficient for most documents.

---

## Common Pitfalls

1. **macOS Apple Silicon requires specific paddlepaddle build.** Use `paddlepaddle==3.2.1` (CPU). GPU is not available on macOS. Must set `KMP_DUPLICATE_LIB_OK=TRUE` environment variable.

2. **PaddleOCR 3.x has breaking API changes from 2.x.** The new API uses `PaddleOCR` class with `.predict()` method. Old 2.x patterns (`ocr.ocr()`) will not work.

3. **Memory leak in PaddleOCR 3.x CPU mode.** RAM grows steadily when processing many files due to runtime shape caching. Mitigate with `os.environ["CPU_RUNTIME_CACHE_CAPACITY"] = "20"` before importing PaddleOCR.

4. **Scanned documents with poor quality will have low OCR confidence.** Preprocessing (denoise, adaptive threshold, deskew) can boost accuracy by 10-30%. Always preprocess before OCR for faded or skewed scans.

5. **Some state documents use non-standard layouts.** Government Excel files often have merged cells, multi-row headers, and data starting at unexpected rows. Use openpyxl for fine-grained control, not just pandas.

6. **Table extraction needs PPStructureV3 for production reports** (scanned). For text PDFs, use pdfplumber with lattice strategy for bordered tables and text strategy for borderless tables.

7. **API numbers must be read as strings, not integers**, to preserve leading zeros. Same for permit numbers and well numbers.

8. **Set `text_rec_score_thresh=0.0` in PaddleOCR.** Never let PaddleOCR silently drop low-confidence text. Keep everything and apply your own confidence filtering downstream.

9. **Mixed PDFs are common.** Some pages are digital text, others are scanned within the same document. Always classify per-page, not per-document.

10. **MMCF vs MCF unit confusion.** MMCF is thousand MCF. When extracting gas production, check for MMCF and multiply by 1,000 to normalize to MCF.

---

## Testing Strategy

1. **Sample PDF collection:** Assemble test PDFs covering both text-based and scanned documents from multiple states. Include clean scans and poor-quality scans.

2. **OCR output verification:** For scanned test documents with known content, run PaddleOCR and compare output against known ground-truth values. Track character-level accuracy.

3. **Confidence scoring validation:**
   - Verify that text PDF extraction produces confidence ~1.0
   - Verify that OCR confidence correlates with actual accuracy
   - Verify that the three-tier disposition (auto-accept / review / reject) routes documents correctly
   - Test with deliberately degraded scans to confirm low-confidence documents hit the review queue

4. **Regex pattern testing:** For each extraction regex (API numbers, production volumes, dates, operator names, permit numbers), maintain a test suite of known document snippets with expected extraction results.

5. **Pipeline integration test:** Run a document through all 7 stages end-to-end. Verify each stage produces expected output and the document reaches STORED state with correct data in PostgreSQL.

6. **Classification accuracy:** Test the weighted keyword classifier and form number detector against a labeled set of documents. Target: form numbers = ~100% accuracy, keyword matching >= 80%.

7. **Table extraction:** Compare extracted table data against manually transcribed values from production reports. Test both bordered and borderless table formats.

---

## Cost Implications

**Fully free for the core pipeline.** No paid API costs.

- PaddleOCR: $0 (open source, Apache 2.0 license)
- PyMuPDF4LLM: $0 (open source)
- PPStructureV3: $0 (included with PaddleOCR)

**Compute cost estimate only:** ~$0.20-0.50 per 1,000 pages when factoring in electricity and hardware amortization for CPU processing on a local machine.

**Comparison to cloud alternatives:**
- AWS Textract: $1.50/1K pages (text), $15.00/1K pages (tables)
- Google Document AI: $1.50/1K pages
- Claude API vision: ~$4.50-9.00/1K pages

---

## References

- **Discovery document:** `.claude/orchestration-og-doc-scraper/DISCOVERY.md` -- Project scope, constraints (PaddleOCR only, no paid APIs, strict confidence rejection)
- **Document processing research:** `.claude/orchestration-og-doc-scraper/research/document-processing.md` -- Library comparisons, cost analysis, confidence scoring architecture, batch processing strategies
- **Pipeline implementation guide:** `.claude/orchestration-og-doc-scraper/research/document-pipeline-implementation.md` -- PaddleOCR setup, classification code, regex patterns, confidence scoring implementation, 7-stage pipeline architecture with full code examples
