# Document Processing Pipeline — Implementation Guide

**Research Date**: 2026-03-27
**Project**: Oil & Gas Document Scraper
**Scope**: PaddleOCR setup, document classification, PDF processing, data extraction, confidence scoring, pipeline architecture
**Constraint**: PaddleOCR only — no paid APIs. Must handle all scans. Strict confidence rejection with review queue.

---

## Table of Contents

1. [PaddleOCR v3 Setup and Usage](#1-paddleocr-v3-setup-and-usage)
2. [Document Classification Without LLMs](#2-document-classification-without-llms)
3. [PDF Processing Pipeline](#3-pdf-processing-pipeline)
4. [Data Extraction Patterns](#4-data-extraction-patterns)
5. [Confidence Scoring Implementation](#5-confidence-scoring-implementation)
6. [Seven-Stage Pipeline Architecture](#6-seven-stage-pipeline-architecture)

---

## 1. PaddleOCR v3 Setup and Usage

### 1.1 Installation on macOS (Apple Silicon)

PaddlePaddle supports Apple Silicon (M1/M2/M3/M4) in CPU-only mode. No GPU acceleration is available on macOS. The ARM64 architecture is supported natively (no Rosetta needed for PaddlePaddle >= 3.2.x).

**Step-by-step installation:**

```bash
# 1. Create a virtual environment (Python 3.9-3.12 supported)
python3 -m venv .venv
source .venv/bin/activate

# 2. Install PaddlePaddle (CPU only on macOS)
python -m pip install paddlepaddle==3.2.1

# 3. Verify PaddlePaddle installation
python -c "import paddle; print(paddle.__version__)"
# Expected: 3.2.1

# 4. Install PaddleOCR with document parsing support
python -m pip install "paddleocr[doc-parser]"

# Or install all features (doc parsing + information extraction + translation)
python -m pip install "paddleocr[all]"
```

**Known Apple Silicon issues:**
- PaddleOCR-VL (the vision-language model variant) has been verified on M4; other chips may need testing
- AVX extensions are not available on ARM — PaddlePaddle handles this natively in >= 3.x
- For MLX-optimized inference on Apple Silicon, a community port exists (`PaddleOCR-VL-MLX` on Hugging Face), but the standard CPU pipeline is sufficient for this project

### 1.2 Installation on Linux (Production/Docker)

```bash
# CPU Installation
python -m pip install paddlepaddle==3.2.0

# GPU Installation (CUDA 11.8)
python -m pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/

# GPU Installation (CUDA 12.6)
python -m pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

# Install PaddleOCR
python -m pip install "paddleocr[doc-parser]"
```

**Docker deployment (recommended for reproducibility):**

```bash
# CPU Docker
docker run --name paddleocr -v $PWD:/paddle --shm-size=8G --network=host -it \
  ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.0.0 /bin/bash

# GPU Docker (CUDA 11.8)
docker run --gpus all --name paddleocr -v $PWD:/paddle --shm-size=8G --network=host -it \
  ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.0.0-gpu-cuda11.8-cudnn8.9-trt8.6 /bin/bash
```

**Docker Compose integration (for the project):**

```yaml
# In docker-compose.yml
services:
  ocr-worker:
    build:
      context: .
      dockerfile: Dockerfile.ocr
    volumes:
      - ./data:/app/data
    shm_size: '8g'
    environment:
      - PADDLE_DEVICE=cpu
    deploy:
      resources:
        limits:
          memory: 4G
```

### 1.3 Python API Usage Patterns

**PaddleOCR 3.x has breaking changes from 2.x.** The new API uses `PaddleOCR` and `PPStructureV3` classes with a `.predict()` method.

#### Basic OCR (Text Detection + Recognition)

```python
from paddleocr import PaddleOCR

# Initialize once, reuse for all pages
ocr = PaddleOCR(
    text_detection_model_name="PP-OCRv5_server_det",
    text_recognition_model_name="PP-OCRv5_server_rec",
    use_doc_orientation_classify=True,   # Auto-detect rotation
    use_doc_unwarping=False,             # Enable for photographed docs
    use_textline_orientation=False,      # Enable for mixed orientation text
    device="cpu",                        # "gpu:0" for GPU
    cpu_threads=4,                       # Limit CPU threads
    enable_mkldnn=True,                  # MKL-DNN acceleration on CPU
)

# Process single image
results = ocr.predict("page_scan.png")

for res in results:
    res.print()                          # Print to console
    res.save_to_json("output/")          # Save structured JSON
    res.save_to_img("output/")           # Save visualization with boxes

# Access raw results
for res in results:
    for item in res.res:
        # item structure: {
        #   "dt_polys": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]],  # bounding box
        #   "rec_text": "PRODUCTION REPORT",                    # recognized text
        #   "rec_score": 0.9847                                 # confidence 0-1
        # }
        text = item["rec_text"]
        confidence = item["rec_score"]
        bbox = item["dt_polys"]
```

#### Document Structure Parsing (PP-StructureV3)

```python
from paddleocr import PPStructureV3

# Initialize the full document parsing pipeline
parser = PPStructureV3(
    use_doc_orientation_classify=True,
    use_table_recognition=True,
    use_seal_recognition=False,          # Not needed for O&G docs
    use_formula_recognition=False,       # Not needed for O&G docs
    use_chart_recognition=False,         # Not needed for O&G docs
    device="cpu",
    cpu_threads=4,
)

# Process a PDF document (handles multi-page automatically)
results = parser.predict("document.pdf")

for res in results:
    res.save_to_markdown("output/")      # Markdown preserving structure
    res.save_to_json("output/")          # Structured JSON

# Process a directory of images/PDFs
results = parser.predict("scanned_pages/")
```

#### PDF Processing (Per-Page Results)

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(device="cpu")

# PDF input returns results per page
results = ocr.predict("multi_page_document.pdf")

for res in results:
    page_index = res.page_index   # Page number (0-indexed, None for images)
    # Each result contains text, confidence, and bounding boxes for that page
```

#### Batch Processing with Memory Management

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(device="cpu", cpu_threads=4)

# Use predict_iter() for large datasets — returns generator, saves memory
for result in ocr.predict_iter(input="large_document_folder/"):
    result.save_to_json("output/")

# Process specific pages of a PDF
# Note: PaddleOCR processes all pages; filter results by page_index
results = list(ocr.predict("big_document.pdf"))
page_5_result = [r for r in results if r.page_index == 4]  # 0-indexed
```

### 1.4 Configuration for Best Accuracy on Government Documents

Government O&G documents are typically typewritten forms, printed tables, and stamped/signed official records. They have predictable layouts but may be poor quality scans.

**Optimal configuration:**

```python
from paddleocr import PaddleOCR, PPStructureV3

# For OCR of scanned government forms
ocr = PaddleOCR(
    # Use server (larger, more accurate) models instead of mobile
    text_detection_model_name="PP-OCRv5_server_det",
    text_recognition_model_name="PP-OCRv5_server_rec",

    # Document preprocessing
    use_doc_orientation_classify=True,  # Fix 90/180/270 rotation
    use_doc_unwarping=False,            # Only for photographed docs, not scans

    # Detection thresholds — tuned for government documents
    text_det_thresh=0.3,         # Pixel-level confidence (default 0.3, lower catches faint text)
    text_det_box_thresh=0.5,     # Region acceptance (default 0.6, lower for faded scans)
    text_det_unclip_ratio=2.0,   # Box dilation (default 2.0)

    # Recognition threshold
    text_rec_score_thresh=0.0,   # Keep ALL results, filter by confidence ourselves

    # Performance
    device="cpu",
    cpu_threads=4,
    enable_mkldnn=True,
)

# For full document structure parsing (tables, layout)
parser = PPStructureV3(
    use_doc_orientation_classify=True,
    use_table_recognition=True,

    # Layout detection — use the large model for best accuracy
    # PP-DocLayout-L: 90.4% mAP vs PP-DocLayout-S: 70.9% mAP
    layout_threshold=0.4,        # Lower from 0.5 to catch more layout elements
    layout_nms=True,             # Non-max suppression for overlapping regions

    # Table recognition settings
    use_e2e_wired_table_rec_model=True,    # Better for bordered tables
    use_e2e_wireless_table_rec_model=True,  # Better for borderless tables

    device="cpu",
)
```

**Image preprocessing before OCR (for very poor scans):**

```python
import cv2
import numpy as np

def preprocess_government_scan(image_path: str) -> np.ndarray:
    """Preprocess a scanned government document for optimal OCR accuracy."""
    img = cv2.imread(image_path)

    # 1. Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Denoise (preserve text edges)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    # 3. Adaptive thresholding (handles uneven lighting from scans)
    binary = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10
    )

    # 4. Deskew
    coords = np.column_stack(np.where(binary > 0))
    if len(coords) > 100:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) > 0.5:  # Only rotate if skew is noticeable
            (h, w) = binary.shape[:2]
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            binary = cv2.warpAffine(binary, M, (w, h),
                                     flags=cv2.INTER_CUBIC,
                                     borderMode=cv2.BORDER_REPLICATE)

    return binary

# Usage: preprocess then feed to PaddleOCR
preprocessed = preprocess_government_scan("scan.png")
cv2.imwrite("/tmp/preprocessed.png", preprocessed)
results = ocr.predict("/tmp/preprocessed.png")
```

### 1.5 Table Detection and Extraction Capabilities

PP-StructureV3 includes specialized table recognition via the SLANeXt model family:

| Model | Type | Accuracy (TEDS) | GPU Latency | CPU Latency | Size |
|-------|------|-----------------|-------------|-------------|------|
| SLANeXt (wired) | Bordered tables | 69.65% mAP | 85.92ms | 501.66ms | 351MB |
| SLANeXt (wireless) | Borderless tables | Competitive | Similar | Similar | Similar |
| SLANet | General tables | Lower | 32.65ms | 196.98ms | 30MB |

**Key table capabilities:**
- Detects 20 layout element types including `table`, `table_caption`, `table_footnote`
- Recognizes both wired (bordered) and wireless (borderless) table structures
- Outputs table content as HTML `<table>` structure or Markdown
- Handles merged cells and multi-row/multi-column spans
- Can extract tables from both text-based and scanned PDFs

**Table extraction output format:**

```python
# PP-StructureV3 table output (in JSON)
{
    "layout_type": "table",
    "bbox": [x1, y1, x2, y2],
    "table_html": "<table><tr><td>Oil BBL</td><td>Gas MCF</td></tr>...</table>",
    "table_cells": [
        {"row": 0, "col": 0, "text": "Oil BBL", "confidence": 0.95},
        {"row": 0, "col": 1, "text": "Gas MCF", "confidence": 0.93},
        # ...
    ]
}
```

### 1.6 Confidence Score Output Format and Thresholds

PaddleOCR provides confidence scores at multiple levels:

**Text Detection Confidence (`dt_scores`):**
- Per-box confidence that a detected region contains text
- Range: 0.0 to 1.0
- Filtered by `text_det_box_thresh` (default 0.6)

**Text Recognition Confidence (`rec_score`):**
- Per-text-line confidence in the recognized characters
- Range: 0.0 to 1.0
- Filtered by `text_rec_score_thresh` (default 0.0 — keep everything)

**Accessing confidence programmatically:**

```python
results = ocr.predict("page.png")
for res in results:
    for item in res.res:
        detection_confidence = item.get("dt_scores", None)  # Box confidence
        recognition_confidence = item["rec_score"]            # Text confidence
        recognized_text = item["rec_text"]

        # For our strict policy: flag anything below 0.80
        if recognition_confidence < 0.80:
            flag_for_review(recognized_text, recognition_confidence)
```

**Recommended thresholds for O&G documents:**

| Scenario | `text_det_box_thresh` | `text_rec_score_thresh` | Notes |
|----------|----------------------|------------------------|-------|
| Default | 0.6 | 0.0 | PaddleOCR defaults |
| Government forms (clean) | 0.6 | 0.0 | Keep all, filter ourselves |
| Poor quality scans | 0.4 | 0.0 | Lower detection to catch faded text |
| High-throughput batch | 0.7 | 0.5 | Reject low quality early |

**Strategy: Set `text_rec_score_thresh=0.0` to keep ALL recognized text, then apply our own multi-level confidence filtering downstream.** This ensures we never silently drop low-confidence data that might be important.

### 1.7 Performance Benchmarks (CPU)

Exact pages-per-second varies by document complexity, resolution, and hardware. Based on available benchmarks and model latency data:

**PP-OCRv5 Server Model Latency (per operation):**

| Component | GPU (T4) | CPU (Xeon Gold) | Notes |
|-----------|----------|-----------------|-------|
| Text Detection | 89.55ms | ~500-800ms | Per page, depends on text density |
| Text Recognition | 8.46ms | ~30-50ms | Per text line |
| Layout Detection (L) | 33.59ms | 503.01ms | PP-DocLayout-L model |
| Table Recognition | 85.92ms | 501.66ms | SLANeXt model |

**Estimated throughput (CPU, single-threaded):**

| Task | Est. Pages/Second | Notes |
|------|-------------------|-------|
| OCR only (simple page) | 0.5-1.0 pg/s | Detection + recognition |
| OCR only (dense page) | 0.3-0.5 pg/s | Many text regions |
| Full structure parsing | 0.2-0.5 pg/s | Layout + OCR + tables |
| Text extraction (PyMuPDF) | 50-100 pg/s | Text PDFs only, no OCR |

**Mobile (lighter) model option:** PP-OCRv5 mobile models are ~15MB total and process 370+ characters/second on CPU. Trade accuracy for speed when processing high volumes of clean documents.

**Practical estimate for this project:** Processing 1,000 scanned government document pages on a modern laptop CPU (M-series Mac or Intel i7/i9) at full structure parsing will take approximately 30-60 minutes. For text-only PDFs using PyMuPDF, the same volume processes in under a minute.

### 1.8 Memory Usage and Batch Processing Patterns

**Known memory issues and mitigations:**

1. **Memory leak in PaddleOCR 3.x (CPU mode):** RAM usage increases steadily when processing many different files due to internal runtime caching. The default cache holds up to 5,000 compiled shapes.

   **Mitigation:**
   ```python
   import os
   # Limit the runtime cache to prevent memory growth
   os.environ["CPU_RUNTIME_CACHE_CAPACITY"] = "20"  # Limit to 20 cached shapes
   # Or disable entirely (slight performance cost on varied image sizes)
   os.environ["CPU_RUNTIME_CACHE_CAPACITY"] = "0"
   ```

2. **Model loading memory:** Server models require ~200-400MB RAM each. With layout detection + OCR + table recognition loaded, expect ~1-1.5GB baseline RAM usage.

3. **Batch processing strategy:**

   ```python
   import gc
   from paddleocr import PaddleOCR

   # Initialize model once
   ocr = PaddleOCR(device="cpu", cpu_threads=4)

   def process_documents_batch(file_paths: list[str], batch_size: int = 50):
       """Process documents in batches with memory management."""
       for i in range(0, len(file_paths), batch_size):
           batch = file_paths[i:i + batch_size]
           for file_path in batch:
               # Use predict_iter for memory efficiency
               for result in ocr.predict_iter(input=file_path):
                   yield file_path, result

           # Force garbage collection between batches
           gc.collect()
   ```

4. **Multi-process strategy for heavy workloads:**

   ```python
   from multiprocessing import Pool

   def process_single_document(file_path: str) -> dict:
       """Process one document in a separate process (clean memory per doc)."""
       from paddleocr import PaddleOCR
       ocr = PaddleOCR(device="cpu", cpu_threads=2)
       results = list(ocr.predict(file_path))
       return {"file": file_path, "pages": len(results)}

   # Use process pool — each process gets its own memory space
   with Pool(processes=2) as pool:
       results = pool.map(process_single_document, document_paths)
   ```

   **Trade-off:** Each process loads the model separately (~400MB each). With 2 processes on a 16GB machine, total OCR memory usage is ~1-2GB, leaving ample room for other services.

---

## 2. Document Classification Without LLMs

Since the project prohibits paid APIs, classification must be entirely rule-based and local. The good news: O&G regulatory documents are highly formulaic, making keyword-based classification effective (~80-85% accuracy).

### 2.1 Rule-Based Keyword Matching

**Comprehensive keyword dictionary for O&G document types:**

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ClassificationResult:
    document_type: str
    confidence: float
    matched_keywords: list[str]
    matched_form_number: Optional[str] = None

# Weighted keyword patterns — higher weight = stronger signal
DOCUMENT_PATTERNS = {
    "well_permit": {
        "keywords": {
            # Strong signals (weight 3)
            "application to drill": 3,
            "permit to drill": 3,
            "drilling permit": 3,
            "intent to drill": 3,
            "application for permit": 3,
            # Medium signals (weight 2)
            "proposed total depth": 2,
            "proposed casing program": 2,
            "anticipated spud date": 2,
            "surface location": 2,
            "bottom hole location": 2,
            # Weak signals (weight 1)
            "drilling": 1,
            "spud": 1,
            "casing": 1,
        },
    },
    "production_report": {
        "keywords": {
            "production report": 3,
            "monthly production": 3,
            "annual production": 3,
            "oil production": 2,
            "gas production": 2,
            "water production": 2,
            "barrels produced": 2,
            "mcf produced": 2,
            "days produced": 2,
            "producing days": 2,
            "disposition": 2,
            "sold": 1,
            "flared": 1,
            "vented": 1,
            "injected": 1,
            "lease production": 2,
            "well production": 2,
        },
    },
    "completion_report": {
        "keywords": {
            "completion report": 3,
            "well completion": 3,
            "recompletion report": 3,
            "completed interval": 3,
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
        },
    },
    "plugging_report": {
        "keywords": {
            "plugging report": 3,
            "plug and abandon": 3,
            "plugging record": 3,
            "plugged and abandoned": 3,
            "cement plug": 2,
            "plug placed": 2,
            "surface restoration": 2,
            "casing left in hole": 2,
            "well plugging": 2,
        },
    },
    "spacing_order": {
        "keywords": {
            "spacing order": 3,
            "pooling order": 3,
            "drilling unit": 3,
            "forced pooling": 3,
            "compulsory pooling": 3,
            "spacing exception": 2,
            "rule 37": 2,  # Texas specific
            "rule 38": 2,  # Texas specific
            "drilling unit order": 2,
            "unit boundaries": 2,
        },
    },
    "inspection_record": {
        "keywords": {
            "inspection report": 3,
            "field inspection": 3,
            "well inspection": 3,
            "compliance inspection": 3,
            "inspection findings": 2,
            "violation": 2,
            "inspector": 2,
            "compliance status": 2,
        },
    },
    "incident_report": {
        "keywords": {
            "incident report": 3,
            "spill report": 3,
            "release notification": 3,
            "blowout": 3,
            "environmental release": 2,
            "volume released": 2,
            "volume recovered": 2,
            "corrective action": 2,
            "spill": 2,
            "leak": 1,
        },
    },
}

def classify_by_keywords(text: str) -> ClassificationResult:
    """Classify document type using weighted keyword matching."""
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
        return ClassificationResult("unknown", 0.0, [])

    # Get the top scoring type
    best_type = max(scores, key=lambda k: scores[k][0])
    best_score, best_keywords = scores[best_type]

    # Calculate confidence based on score relative to max possible
    max_possible = sum(DOCUMENT_PATTERNS[best_type]["keywords"].values())
    confidence = min(best_score / max_possible, 1.0)

    # Boost confidence if multiple strong signals found
    strong_matches = sum(1 for kw in best_keywords
                         if DOCUMENT_PATTERNS[best_type]["keywords"].get(kw, 0) >= 3)
    if strong_matches >= 2:
        confidence = min(confidence * 1.3, 1.0)

    # Check for ambiguity — if second-best type is close, lower confidence
    sorted_scores = sorted(scores.values(), key=lambda x: x[0], reverse=True)
    if len(sorted_scores) >= 2:
        ratio = sorted_scores[1][0] / sorted_scores[0][0]
        if ratio > 0.7:  # Second type scored >70% of first
            confidence *= 0.7  # Ambiguous — lower confidence

    return ClassificationResult(best_type, confidence, best_keywords)
```

### 2.2 Form Number Detection

Texas and other states use specific form numbers that are definitive classifiers. Detecting these is nearly 100% accurate.

```python
import re

# State-specific form patterns
FORM_PATTERNS = {
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
    "TX_P-4":  {"pattern": r'\bform\s*p[\s-]*4\b|\bp[\s-]*4\s*(?:form|transportation)\b',
                "type": "transportation_authority", "state": "TX"},
    "TX_P-5":  {"pattern": r'\bform\s*p[\s-]*5\b|\bp[\s-]*5\s*(?:form|organization)\b',
                "type": "organization_report", "state": "TX"},

    # Oklahoma Corporation Commission
    "OK_1002A": {"pattern": r'\b(?:form\s*)?1002[\s-]*a\b',
                 "type": "well_permit", "state": "OK"},
    "OK_1002C": {"pattern": r'\b(?:form\s*)?1002[\s-]*c\b',
                 "type": "completion_report", "state": "OK"},
    "OK_1012D": {"pattern": r'\b(?:form\s*)?1012[\s-]*d\b',
                 "type": "production_report", "state": "OK"},

    # Colorado ECMC
    "CO_Form2":  {"pattern": r'\bform\s*2\b.*(?:permit|drill)',
                  "type": "well_permit", "state": "CO"},
    "CO_Form5":  {"pattern": r'\bform\s*5\b.*(?:complet|interval)',
                  "type": "completion_report", "state": "CO"},
    "CO_Form5A": {"pattern": r'\bform\s*5[\s-]*a\b',
                  "type": "completion_report", "state": "CO"},
    "CO_Form6":  {"pattern": r'\bform\s*6\b.*(?:plug|abandon)',
                  "type": "plugging_report", "state": "CO"},

    # North Dakota DMR
    "ND_Form1": {"pattern": r'\bform\s*1\b.*(?:permit|drill).*(?:north\s*dakota|nd)',
                 "type": "well_permit", "state": "ND"},

    # Federal EIA
    "EIA_914":  {"pattern": r'\beia[\s-]*914\b|\bform\s*eia[\s-]*914\b',
                 "type": "production_report", "state": "FED"},
}

def detect_form_number(text: str) -> tuple[str, str, str] | None:
    """Detect state form numbers. Returns (form_id, doc_type, state) or None."""
    text_lower = text.lower()
    for form_id, config in FORM_PATTERNS.items():
        if re.search(config["pattern"], text_lower, re.IGNORECASE):
            return (form_id, config["type"], config["state"])
    return None
```

### 2.3 Regex Patterns for O&G Identifiers

```python
import re

# API Number patterns — the primary well identifier
API_NUMBER_PATTERNS = {
    # Full 14-digit with hyphens: XX-YYY-ZZZZZ-SS-EE
    "api_14_hyphen": r'\b(\d{2}-\d{3}-\d{5}-\d{2}-\d{2})\b',

    # 12-digit with hyphens: XX-YYY-ZZZZZ-SS
    "api_12_hyphen": r'\b(\d{2}-\d{3}-\d{5}-\d{2})\b',

    # 10-digit with hyphens: XX-YYY-ZZZZZ
    "api_10_hyphen": r'\b(\d{2}-\d{3}-\d{5})\b',

    # Continuous digits (no hyphens) — 14, 12, or 10 digit
    "api_14_flat": r'\b(\d{14})\b',
    "api_12_flat": r'\b(\d{12})\b',
    "api_10_flat": r'\b(\d{10})\b',

    # Labeled API numbers
    "api_labeled": r'(?:API\s*(?:No\.?|Number|#)?\s*[:.]?\s*)(\d{2}[-\s]?\d{3}[-\s]?\d{5}(?:[-\s]?\d{2})?(?:[-\s]?\d{2})?)',
}

# Valid state codes for the 10 target states
VALID_STATE_CODES = {
    "02": "Alaska",
    "04": "California",  # Note: California in tier 2
    "05": "Colorado",
    "17": "Louisiana",
    "30": "Montana",      # Not in scope but useful for validation
    "32": "New Mexico",
    "35": "North Dakota",
    "37": "Oklahoma",
    "39": "Pennsylvania",
    "42": "Texas",
    "49": "Wyoming",
}

def extract_api_numbers(text: str) -> list[dict]:
    """Extract and normalize API numbers from text."""
    results = []

    # Try labeled pattern first (most reliable)
    for match in re.finditer(API_NUMBER_PATTERNS["api_labeled"], text, re.IGNORECASE):
        raw = match.group(1)
        normalized = re.sub(r'[-\s]', '', raw)  # Remove separators
        results.append(_parse_api(normalized, raw, "labeled"))

    # Try hyphenated patterns (14, 12, 10)
    for name in ["api_14_hyphen", "api_12_hyphen", "api_10_hyphen"]:
        for match in re.finditer(API_NUMBER_PATTERNS[name], text):
            raw = match.group(1)
            normalized = raw.replace("-", "")
            if not any(r["normalized"] == normalized for r in results):
                results.append(_parse_api(normalized, raw, "hyphenated"))

    # Try flat digit patterns (most likely to produce false positives)
    for name in ["api_14_flat", "api_12_flat", "api_10_flat"]:
        for match in re.finditer(API_NUMBER_PATTERNS[name], text):
            raw = match.group(1)
            state_code = raw[:2]
            # Only accept if state code is valid
            if state_code in VALID_STATE_CODES:
                if not any(r["normalized"].startswith(raw) or raw.startswith(r["normalized"])
                           for r in results):
                    results.append(_parse_api(raw, raw, "flat"))

    return results

def _parse_api(normalized: str, raw: str, source: str) -> dict:
    """Parse an API number into its components."""
    return {
        "raw": raw,
        "normalized": normalized,
        "state_code": normalized[:2],
        "county_code": normalized[2:5],
        "well_id": normalized[5:10],
        "sidetrack": normalized[10:12] if len(normalized) >= 12 else "00",
        "event": normalized[12:14] if len(normalized) >= 14 else "00",
        "state_name": VALID_STATE_CODES.get(normalized[:2], "Unknown"),
        "format": f"api_{len(normalized)}",
        "source": source,
        "confidence": 0.95 if source == "labeled" else 0.85 if source == "hyphenated" else 0.70,
    }
```

### 2.4 Header/Footer Analysis

```python
def analyze_header_footer(text: str, num_lines: int = 10) -> dict:
    """Analyze first and last lines for classification clues."""
    lines = text.strip().split('\n')
    header_lines = lines[:num_lines]
    footer_lines = lines[-num_lines:] if len(lines) > num_lines else []

    header_text = '\n'.join(header_lines).lower()
    footer_text = '\n'.join(footer_lines).lower()

    clues = {
        "state_agency": None,
        "form_number": None,
        "document_title": None,
    }

    # Detect state agency from header
    agency_patterns = {
        "TX": r'railroad commission of texas|rrc.*texas',
        "OK": r'corporation commission.*oklahoma|occ',
        "ND": r'department of mineral resources|north dakota.*dmr',
        "CO": r'colorado.*oil.*gas|ecmc|cogcc',
        "NM": r'oil conservation division|new mexico.*ocd',
        "WY": r'oil.*gas conservation commission|wogcc',
        "LA": r'department of natural resources|sonris|louisiana.*dnr',
        "PA": r'department of environmental protection|pa.*dep',
        "CA": r'geologic energy management|calgem',
        "AK": r'alaska oil.*gas conservation commission|aogcc',
    }

    for state, pattern in agency_patterns.items():
        if re.search(pattern, header_text, re.IGNORECASE):
            clues["state_agency"] = state
            break

    # Detect form number from header
    form_result = detect_form_number(header_text)
    if form_result:
        clues["form_number"] = form_result[0]

    return clues
```

### 2.5 Combined Classification Pipeline

```python
def classify_document(text: str) -> ClassificationResult:
    """
    Multi-strategy document classification (no LLM).

    Priority:
    1. Form number detection (nearly 100% accurate)
    2. Header/footer analysis
    3. Weighted keyword matching
    """
    # Strategy 1: Form number detection
    form_result = detect_form_number(text)
    if form_result:
        form_id, doc_type, state = form_result
        return ClassificationResult(
            document_type=doc_type,
            confidence=0.98,  # Very high confidence for form number match
            matched_keywords=[form_id],
            matched_form_number=form_id,
        )

    # Strategy 2: Header analysis + keyword matching
    header_clues = analyze_header_footer(text)
    keyword_result = classify_by_keywords(text)

    # If header gives us a state, boost confidence
    if header_clues["state_agency"] and keyword_result.confidence > 0:
        keyword_result.confidence = min(keyword_result.confidence * 1.15, 1.0)

    # If confidence is still below threshold, mark as unknown
    if keyword_result.confidence < 0.30:
        return ClassificationResult("unknown", keyword_result.confidence,
                                     keyword_result.matched_keywords)

    return keyword_result
```

---

## 3. PDF Processing Pipeline

### 3.1 Detecting Text-Based vs Scanned PDFs (Page-Level)

Use PyMuPDF to analyze each page independently. A scanned page is one where a large image covers most of the page area and extractable text is minimal.

```python
import fitz  # PyMuPDF

def classify_pdf_pages(pdf_path: str) -> list[dict]:
    """
    Classify each page of a PDF as text-based, scanned, or mixed.

    Returns list of dicts with page_num, classification, and metadata.
    """
    doc = fitz.open(pdf_path)
    page_classifications = []

    for page_num, page in enumerate(doc):
        # Extract text
        text = page.get_text("text").strip()
        text_length = len(text)

        # Get images on the page
        images = page.get_images(full=True)
        page_rect = page.rect
        page_area = page_rect.width * page_rect.height

        # Calculate image coverage
        image_coverage = 0.0
        for img in images:
            xref = img[0]
            try:
                img_rect = page.get_image_rects(xref)
                if img_rect:
                    for rect in img_rect:
                        img_area = rect.width * rect.height
                        image_coverage += img_area / page_area
            except Exception:
                # If we can't determine image rect, estimate
                image_coverage += 0.5 if images else 0.0

        # Classification heuristics
        has_substantial_text = text_length > 100
        has_large_images = image_coverage > 0.5
        is_mostly_image = image_coverage > 0.85

        if is_mostly_image and not has_substantial_text:
            classification = "scanned"
        elif has_substantial_text and not has_large_images:
            classification = "text"
        elif has_substantial_text and has_large_images:
            classification = "mixed"
        elif text_length < 20 and not images:
            classification = "empty"
        else:
            classification = "mixed"  # Default to mixed (safer — will OCR)

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

### 3.2 Text PDF Extraction (PyMuPDF / pdfplumber)

For pages classified as "text", use PyMuPDF for speed or pdfplumber for table-heavy pages.

```python
import fitz
import pdfplumber

def extract_text_page_pymupdf(pdf_path: str, page_num: int) -> str:
    """Fast text extraction using PyMuPDF. Best for general text."""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    text = page.get_text("text")
    doc.close()
    return text

def extract_text_page_pymupdf_structured(pdf_path: str, page_num: int) -> str:
    """Extract text as markdown-like structure using PyMuPDF."""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    # "dict" mode gives detailed block-level structure
    blocks = page.get_text("dict")["blocks"]
    doc.close()

    structured_text = []
    for block in blocks:
        if block["type"] == 0:  # Text block
            for line in block["lines"]:
                line_text = " ".join(span["text"] for span in line["spans"])
                structured_text.append(line_text)
        # type 1 = image block (skip for text extraction)

    return "\n".join(structured_text)

def extract_tables_pdfplumber(pdf_path: str, page_num: int) -> list:
    """Extract tables using pdfplumber. Best for bordered tables."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        tables = page.extract_tables(table_settings={
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "intersection_x_tolerance": 5,
            "intersection_y_tolerance": 5,
        })

        # Also try text-based strategy for borderless tables
        if not tables:
            tables = page.extract_tables(table_settings={
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
            })

        return tables
```

### 3.3 Scanned PDF Processing (PaddleOCR)

For pages classified as "scanned", convert to image and run PaddleOCR.

```python
import fitz
import numpy as np
from paddleocr import PaddleOCR

# Initialize once
ocr_engine = PaddleOCR(
    text_detection_model_name="PP-OCRv5_server_det",
    text_recognition_model_name="PP-OCRv5_server_rec",
    use_doc_orientation_classify=True,
    text_rec_score_thresh=0.0,  # Keep all results
    device="cpu",
    cpu_threads=4,
)

def extract_scanned_page(pdf_path: str, page_num: int, dpi: int = 300) -> dict:
    """
    Extract text from a scanned PDF page using PaddleOCR.

    Returns dict with text, per-line confidence scores, and overall confidence.
    """
    # Convert PDF page to image
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)  # Scale factor
    pix = page.get_pixmap(matrix=mat)

    # Save temporarily (PaddleOCR accepts file paths)
    temp_path = f"/tmp/ocr_page_{page_num}.png"
    pix.save(temp_path)
    doc.close()

    # Run OCR
    results = list(ocr_engine.predict(temp_path))

    # Parse results
    lines = []
    confidences = []

    for res in results:
        for item in res.res:
            text = item["rec_text"]
            score = item["rec_score"]
            bbox = item["dt_polys"]

            lines.append({
                "text": text,
                "confidence": score,
                "bbox": bbox,
            })
            confidences.append(score)

    # Calculate page-level confidence
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    min_confidence = min(confidences) if confidences else 0.0

    # Clean up
    import os
    os.remove(temp_path)

    return {
        "page_num": page_num,
        "full_text": "\n".join(line["text"] for line in lines),
        "lines": lines,
        "avg_confidence": avg_confidence,
        "min_confidence": min_confidence,
        "num_lines": len(lines),
        "method": "paddleocr",
    }
```

### 3.4 Table Extraction Strategy

Based on research, the recommended approach for this project (no paid APIs):

| Table Type | PDF Type | Primary Tool | Fallback |
|-----------|----------|-------------|----------|
| Bordered tables | Text PDF | pdfplumber (lattice) | Camelot (lattice) |
| Borderless tables | Text PDF | pdfplumber (text strategy) | Camelot (stream) |
| Bordered tables | Scanned PDF | PP-StructureV3 (SLANeXt wired) | None |
| Borderless tables | Scanned PDF | PP-StructureV3 (SLANeXt wireless) | None |
| Complex/nested | Either | PP-StructureV3 | Manual extraction |

**Why not Docling?** Docling (IBM) has excellent accuracy (97.9% on benchmarks) but is significantly slower than pdfplumber/Camelot (10x+) due to its computer vision models. For this project running on CPU, the speed penalty is too high for routine use. Docling is also heavier in dependencies. PP-StructureV3 provides comparable table extraction that is already part of the PaddleOCR ecosystem.

**Table extraction implementation:**

```python
from paddleocr import PPStructureV3
import pdfplumber

# For scanned PDFs — use PP-StructureV3
table_parser = PPStructureV3(
    use_table_recognition=True,
    use_formula_recognition=False,
    use_chart_recognition=False,
    device="cpu",
)

def extract_tables_from_scanned_page(image_path: str) -> list[dict]:
    """Extract tables from a scanned page using PP-StructureV3."""
    results = list(table_parser.predict(image_path))
    tables = []

    for res in results:
        # PP-StructureV3 identifies layout regions
        # Filter for table regions
        for item in res.res.get("layout_results", []):
            if item.get("layout_type") == "table":
                tables.append({
                    "bbox": item["bbox"],
                    "html": item.get("table_html", ""),
                    "cells": item.get("table_cells", []),
                })

    return tables

def extract_tables_from_text_page(pdf_path: str, page_num: int) -> list[list]:
    """Extract tables from a text-based PDF page using pdfplumber."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]

        # Try bordered tables first
        tables = page.extract_tables(table_settings={
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
        })

        # If no bordered tables found, try borderless
        if not tables:
            tables = page.extract_tables(table_settings={
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "snap_y_tolerance": 5,
            })

        return tables
```

### 3.5 Handling Mixed PDFs (Some Pages Text, Some Scanned)

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class PageResult:
    page_num: int
    method: str                # "text_extraction" or "ocr"
    text: str
    confidence: float          # 1.0 for text extraction, OCR confidence for scanned
    tables: list
    classification: str        # "text", "scanned", "mixed", "empty"

def process_mixed_pdf(pdf_path: str) -> list[PageResult]:
    """
    Process a PDF with mixed text and scanned pages.
    Each page is routed to the appropriate extraction method.
    """
    # Step 1: Classify each page
    page_classes = classify_pdf_pages(pdf_path)

    results = []
    for page_info in page_classes:
        page_num = page_info["page_num"]
        classification = page_info["classification"]

        if classification == "empty":
            results.append(PageResult(
                page_num=page_num, method="skip", text="",
                confidence=1.0, tables=[], classification="empty",
            ))
            continue

        if classification == "text":
            # Direct text extraction — fast, high confidence
            text = extract_text_page_pymupdf(pdf_path, page_num)
            tables = extract_tables_from_text_page(pdf_path, page_num)
            results.append(PageResult(
                page_num=page_num, method="text_extraction", text=text,
                confidence=1.0, tables=tables, classification="text",
            ))

        elif classification in ("scanned", "mixed"):
            # OCR processing — slower, variable confidence
            ocr_result = extract_scanned_page(pdf_path, page_num)
            # For mixed pages, also try text extraction and merge
            if classification == "mixed":
                text_result = extract_text_page_pymupdf(pdf_path, page_num)
                # Use whichever produced more text
                if len(text_result) > len(ocr_result["full_text"]):
                    text = text_result
                    confidence = 0.95  # High but not 1.0 since page was ambiguous
                else:
                    text = ocr_result["full_text"]
                    confidence = ocr_result["avg_confidence"]
            else:
                text = ocr_result["full_text"]
                confidence = ocr_result["avg_confidence"]

            results.append(PageResult(
                page_num=page_num, method="ocr", text=text,
                confidence=confidence, tables=[], classification=classification,
            ))

    return results
```

---

## 4. Data Extraction Patterns

### 4.1 Regex Patterns for Production Volumes

```python
import re
from typing import Optional

def extract_production_volumes(text: str) -> dict:
    """
    Extract oil, gas, and water production volumes from document text.
    Handles common O&G abbreviations and units.
    """
    results = {
        "oil_bbls": None,
        "gas_mcf": None,
        "water_bbls": None,
        "condensate_bbls": None,
        "days_produced": None,
    }

    # Oil production (barrels)
    oil_patterns = [
        # "Oil: 1,234 BBL" or "Oil Production: 1234.5 Bbls"
        r'(?:oil|crude)\s*(?:production|prod\.?)?\s*[:.]?\s*([\d,]+\.?\d*)\s*(?:bbl|bbls?|barrels?)',
        # "1,234 BBL oil" (value before unit)
        r'([\d,]+\.?\d*)\s*(?:bbl|bbls?|barrels?)\s*(?:of\s+)?(?:oil|crude)',
        # Table context: labeled column followed by value
        r'(?:oil|crude)\s*(?:\(bbl\))?\s*[:|\t]\s*([\d,]+\.?\d*)',
    ]
    for pattern in oil_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            results["oil_bbls"] = _parse_number(match.group(1))
            break

    # Gas production (MCF)
    gas_patterns = [
        r'(?:gas|natural\s*gas|casinghead)\s*(?:production|prod\.?)?\s*[:.]?\s*([\d,]+\.?\d*)\s*(?:mcf|mmcf|cf)',
        r'([\d,]+\.?\d*)\s*(?:mcf|mmcf)\s*(?:of\s+)?(?:gas|natural)',
        r'(?:gas)\s*(?:\(mcf\))?\s*[:|\t]\s*([\d,]+\.?\d*)',
    ]
    for pattern in gas_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = _parse_number(match.group(1))
            # Check if MMCF (million cubic feet) — convert to MCF
            if re.search(r'mmcf', match.group(0), re.IGNORECASE):
                value *= 1000
            results["gas_mcf"] = value
            break

    # Water production (barrels)
    water_patterns = [
        r'(?:water|produced\s*water|brine)\s*(?:production|prod\.?)?\s*[:.]?\s*([\d,]+\.?\d*)\s*(?:bbl|bbls?|barrels?)',
        r'([\d,]+\.?\d*)\s*(?:bbl|bbls?)\s*(?:of\s+)?(?:water|produced\s*water)',
        r'(?:water)\s*(?:\(bbl\))?\s*[:|\t]\s*([\d,]+\.?\d*)',
    ]
    for pattern in water_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            results["water_bbls"] = _parse_number(match.group(1))
            break

    # Days produced
    days_patterns = [
        r'(?:days?\s*(?:produced|producing|on))\s*[:.]?\s*(\d+)',
        r'(\d+)\s*(?:days?\s*(?:produced|producing|on))',
        r'(?:producing\s*days?)\s*[:.]?\s*(\d+)',
    ]
    for pattern in days_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            results["days_produced"] = int(match.group(1))
            break

    return results

def _parse_number(s: str) -> float:
    """Parse a number string, handling commas and whitespace."""
    cleaned = s.replace(",", "").replace(" ", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0
```

### 4.2 Regex for Dates in Government Documents

```python
import re
from datetime import datetime
from typing import Optional

DATE_PATTERNS = [
    # MM/DD/YYYY or MM-DD-YYYY
    (r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b', "%m/%d/%Y"),
    # MM/DD/YY
    (r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2})\b', "%m/%d/%y"),
    # YYYY-MM-DD (ISO format)
    (r'\b(\d{4})-(\d{2})-(\d{2})\b', "%Y-%m-%d"),
    # Month DD, YYYY (e.g., "January 15, 2024")
    (r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b', "%B %d %Y"),
    # DD-Mon-YYYY (e.g., "15-Jan-2024")
    (r'\b(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{4})\b', "%d-%b-%Y"),
    # Mon YYYY (e.g., "Jan 2024") — production period
    (r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\b', "month_year"),
    # MMYYYY or MM/YYYY (production period format)
    (r'\b(\d{2})[/]?(\d{4})\b', "mm_yyyy"),
]

# Labeled date patterns for specific O&G fields
LABELED_DATE_PATTERNS = {
    "spud_date": r'(?:spud\s*date)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    "completion_date": r'(?:completion\s*date|date\s*completed)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    "first_production_date": r'(?:first\s*(?:production|prod\.?)\s*date)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    "permit_date": r'(?:permit\s*date|date\s*(?:of\s+)?permit)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    "reporting_period": r'(?:reporting?\s*period|production\s*(?:month|period))\s*[:.]?\s*(\w+\s*\d{4}|\d{1,2}[/-]\d{4})',
    "plug_date": r'(?:plug(?:ging)?\s*date|date\s*plugged)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    "inspection_date": r'(?:inspection\s*date|date\s*(?:of\s+)?inspection)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
}

def extract_dates(text: str) -> dict:
    """Extract labeled dates from O&G document text."""
    results = {}
    for field, pattern in LABELED_DATE_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw_date = match.group(1)
            results[field] = {
                "raw": raw_date,
                "parsed": _try_parse_date(raw_date),
            }
    return results

def _try_parse_date(date_str: str) -> Optional[str]:
    """Try to parse a date string into ISO format (YYYY-MM-DD)."""
    formats = ["%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y",
               "%Y-%m-%d", "%d-%b-%Y", "%B %d, %Y", "%B %d %Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
```

### 4.3 Regex for Operator Names, Well Names, Locations

```python
import re

def extract_operator_info(text: str) -> dict:
    """Extract operator, well name, and location from document text."""
    results = {}

    # Operator name
    operator_patterns = [
        r'(?:operator|lessee|company)\s*(?:name)?\s*[:.]?\s*([A-Z][A-Za-z\s&.,\'()-]+?)(?:\n|\r|operator|lease|well|api|county)',
        r'(?:filed\s*by|submitted\s*by|reported\s*by)\s*[:.]?\s*([A-Z][A-Za-z\s&.,\'()-]+?)(?:\n|\r)',
    ]
    for pattern in operator_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip().rstrip(',.')
            if len(name) > 3 and len(name) < 100:  # Sanity check
                results["operator_name"] = name
                break

    # Well name
    well_name_patterns = [
        r'(?:well\s*name|well)\s*[:.]?\s*([A-Za-z0-9\s#\'-]+?)(?:\n|\r|well\s*(?:no|number)|api)',
        r'(?:lease\s*(?:name|&\s*well))\s*[:.]?\s*([A-Za-z0-9\s#\'-]+?)(?:\n|\r)',
    ]
    for pattern in well_name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if len(name) > 1 and len(name) < 80:
                results["well_name"] = name
                break

    # County
    county_pattern = r'(?:county)\s*[:.]?\s*([A-Za-z\s]+?)(?:\n|,|\s+state|\s+district)'
    match = re.search(county_pattern, text, re.IGNORECASE)
    if match:
        results["county"] = match.group(1).strip()

    # State
    state_pattern = r'(?:state)\s*[:.]?\s*([A-Za-z\s]+?)(?:\n|,|\s+county)'
    match = re.search(state_pattern, text, re.IGNORECASE)
    if match:
        results["state"] = match.group(1).strip()

    # PLSS location (Section-Township-Range)
    plss_pattern = r'(?:(?:sec(?:tion)?\.?\s*)(\d+)).*?(?:(?:t(?:wp|ownship)?\.?\s*)(\d+[ns])).*?(?:(?:r(?:ng|ange)?\.?\s*)(\d+[ew]))'
    match = re.search(plss_pattern, text, re.IGNORECASE)
    if match:
        results["plss"] = {
            "section": match.group(1),
            "township": match.group(2).upper(),
            "range": match.group(3).upper(),
        }

    # Latitude/Longitude
    latlon_pattern = r'(?:lat(?:itude)?)\s*[:.]?\s*([-]?\d+\.?\d*)[,\s]+(?:lon(?:g(?:itude)?)?)\s*[:.]?\s*([-]?\d+\.?\d*)'
    match = re.search(latlon_pattern, text, re.IGNORECASE)
    if match:
        lat = float(match.group(1))
        lon = float(match.group(2))
        # Sanity check for US coordinates
        if 24.0 <= lat <= 72.0 and -180.0 <= lon <= -60.0:
            results["latitude"] = lat
            results["longitude"] = lon

    return results
```

### 4.4 Permit Number Extraction (State-Specific)

```python
import re

PERMIT_PATTERNS = {
    "TX": [
        r'(?:permit\s*(?:no\.?|number|#))\s*[:.]?\s*(\d{5,8})',
        r'(?:drilling\s*permit)\s*[:.]?\s*(\d{5,8})',
    ],
    "OK": [
        r'(?:permit\s*(?:no\.?|number|#))\s*[:.]?\s*(\d{4,10})',
    ],
    "ND": [
        r'(?:file\s*(?:no\.?|number))\s*[:.]?\s*(\d{4,10})',
        r'(?:permit\s*(?:no\.?|number|#))\s*[:.]?\s*(\d{4,10})',
    ],
    "CO": [
        r'(?:permit\s*(?:no\.?|number|#))\s*[:.]?\s*(\d{3,8})',
        r'(?:sequence\s*(?:no\.?|number))\s*[:.]?\s*(\d{3,8})',
    ],
    "NM": [
        r'(?:permit\s*(?:no\.?|number|#))\s*[:.]?\s*(\d{4,10})',
        r'(?:case\s*(?:no\.?|number))\s*[:.]?\s*(\d{4,10})',
    ],
    "GENERIC": [
        r'(?:permit\s*(?:no\.?|number|#))\s*[:.]?\s*(\d{3,12})',
    ],
}

def extract_permit_number(text: str, state: str = "GENERIC") -> Optional[str]:
    """Extract permit number using state-specific patterns."""
    patterns = PERMIT_PATTERNS.get(state, []) + PERMIT_PATTERNS["GENERIC"]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None
```

### 4.5 Named Entity Recognition with spaCy

For entities that regex cannot reliably capture (e.g., operator names that vary widely), spaCy provides a trainable NER pipeline. This is a Phase 2 enhancement.

**Custom O&G entity types to train:**

| Entity Label | Examples | Training Approach |
|-------------|---------|-------------------|
| `OPERATOR` | "Devon Energy Corporation", "Pioneer Natural Resources" | Train on extracted operator names from state databases |
| `WELL_NAME` | "Smith Ranch #1H", "State Lease 42-3" | Train on well name patterns |
| `FORMATION` | "Wolfcamp", "Eagle Ford", "Bakken" | Train on finite list of known formations |
| `FIELD_NAME` | "Permian Basin", "Spraberry Trend" | Train on finite list of known fields |
| `UNIT_VALUE` | "1,234 BBL", "5,678 MCF" | Pattern-based + training |

**Setup (Phase 2, once labeled data accumulates):**

```python
import spacy
from spacy.training import Example

# Start with a blank English model
nlp = spacy.blank("en")

# Add NER pipeline component
ner = nlp.add_pipe("ner")

# Add custom O&G entity labels
ner.add_label("OPERATOR")
ner.add_label("WELL_NAME")
ner.add_label("FORMATION")
ner.add_label("API_NUMBER")
ner.add_label("PRODUCTION_VALUE")

# Training data format
TRAIN_DATA = [
    ("Devon Energy Corporation reported production from Smith Ranch #1H",
     {"entities": [(0, 26, "OPERATOR"), (56, 72, "WELL_NAME")]}),
    ("API 42-501-20130 in the Wolfcamp formation produced 1,234 BBL",
     {"entities": [(4, 16, "API_NUMBER"), (24, 32, "FORMATION"), (53, 62, "PRODUCTION_VALUE")]}),
    # ... hundreds more annotated examples
]

# Train (simplified — use spacy train CLI for production)
optimizer = nlp.begin_training()
for epoch in range(30):
    for text, annotations in TRAIN_DATA:
        example = Example.from_dict(nlp.make_doc(text), annotations)
        nlp.update([example], sgd=optimizer)

nlp.to_disk("models/og_ner")
```

**For Phase 1 (immediate):** Use the regex patterns from sections 4.1-4.4 above. They cover the most critical fields. Reserve spaCy NER for Phase 2 when labeled data from the review queue accumulates.

### 4.6 Extracting Structured Data from Production Report Tables

Production reports are the most common and most valuable document type. They typically contain tabular data with monthly volumes.

```python
import pandas as pd
import re
from typing import Optional

def parse_production_table(table_data: list[list], state: str = "TX") -> list[dict]:
    """
    Parse a production report table into structured records.

    Args:
        table_data: List of rows, where each row is a list of cell values
        state: State code for state-specific parsing rules

    Returns:
        List of production records
    """
    if not table_data or len(table_data) < 2:
        return []

    # Try to identify header row
    header_row = None
    for i, row in enumerate(table_data[:3]):  # Check first 3 rows for headers
        row_text = " ".join(str(cell) for cell in row if cell).lower()
        if any(kw in row_text for kw in ["oil", "gas", "production", "bbl", "mcf", "month"]):
            header_row = i
            break

    if header_row is None:
        header_row = 0  # Assume first row is header

    headers = [str(h).strip().lower() if h else f"col_{i}"
               for i, h in enumerate(table_data[header_row])]

    # Map common header variations to standard field names
    HEADER_MAP = {
        "oil": "oil_bbls",
        "oil (bbl)": "oil_bbls",
        "oil prod": "oil_bbls",
        "crude": "oil_bbls",
        "gas": "gas_mcf",
        "gas (mcf)": "gas_mcf",
        "gas prod": "gas_mcf",
        "water": "water_bbls",
        "water (bbl)": "water_bbls",
        "month": "reporting_month",
        "period": "reporting_month",
        "year": "reporting_year",
        "days": "days_produced",
        "days produced": "days_produced",
        "prod days": "days_produced",
        "operator": "operator_name",
        "lease": "lease_name",
        "well": "well_name",
        "api": "api_number",
    }

    # Normalize headers
    normalized_headers = []
    for h in headers:
        matched = False
        for pattern, standard in HEADER_MAP.items():
            if pattern in h:
                normalized_headers.append(standard)
                matched = True
                break
        if not matched:
            normalized_headers.append(h)

    # Parse data rows
    records = []
    for row in table_data[header_row + 1:]:
        if not row or all(not cell for cell in row):
            continue  # Skip empty rows

        record = {}
        for i, cell in enumerate(row):
            if i < len(normalized_headers):
                field = normalized_headers[i]
                value = str(cell).strip() if cell else ""

                # Parse numeric fields
                if field in ("oil_bbls", "gas_mcf", "water_bbls"):
                    record[field] = _parse_number(value) if value else None
                elif field == "days_produced":
                    try:
                        record[field] = int(float(value)) if value else None
                    except (ValueError, TypeError):
                        record[field] = None
                else:
                    record[field] = value if value else None

        if any(record.get(f) for f in ["oil_bbls", "gas_mcf", "water_bbls"]):
            records.append(record)

    return records
```

---

## 5. Confidence Scoring Implementation

### 5.1 PaddleOCR's Built-In Confidence Scores

PaddleOCR provides two native confidence metrics:

| Score | Field | Range | Meaning |
|-------|-------|-------|---------|
| Detection confidence | `dt_scores` | 0.0-1.0 | Probability that a detected box contains text |
| Recognition confidence | `rec_score` | 0.0-1.0 | Probability that OCR recognized the text correctly |

**Important:** The recognition confidence is per text line, not per character. A line with one uncertain character will have a lower score than a line with all clear characters.

### 5.2 Field-Level Confidence Calculation

Each extracted field gets a confidence score based on how it was extracted:

```python
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum

class ExtractionMethod(Enum):
    TEXT_EXTRACTION = "text_extraction"      # From text PDF (highest confidence)
    OCR = "ocr"                              # From PaddleOCR
    REGEX = "regex"                          # Pattern matching
    TABLE_EXTRACTION = "table_extraction"    # From table parsing
    HEADER_ANALYSIS = "header_analysis"      # From document header

@dataclass
class FieldConfidence:
    """Confidence scoring for a single extracted field."""
    field_name: str
    value: Any
    confidence: float                        # Final computed confidence (0.0-1.0)
    extraction_method: ExtractionMethod
    ocr_confidence: Optional[float] = None   # Raw OCR confidence if applicable
    pattern_match_quality: Optional[float] = None  # How well regex matched
    validation_passed: bool = True           # Cross-validation result

    @staticmethod
    def compute(
        extraction_method: ExtractionMethod,
        ocr_confidence: Optional[float] = None,
        pattern_specificity: float = 1.0,    # How specific the regex pattern is
        value_validated: bool = True,         # Did value pass format validation
        cross_reference_match: bool = False,  # Does it match other extracted data
    ) -> float:
        """
        Compute field confidence from multiple signals.

        Base confidence by method:
        - text_extraction: 0.95 (text PDFs are near-perfect)
        - ocr: uses OCR confidence directly
        - regex on text: 0.90 * pattern_specificity
        - regex on OCR: OCR confidence * pattern_specificity
        - table_extraction: 0.85 (tables can have parsing errors)
        """
        # Base confidence by extraction method
        if extraction_method == ExtractionMethod.TEXT_EXTRACTION:
            base = 0.95
        elif extraction_method == ExtractionMethod.OCR:
            base = ocr_confidence if ocr_confidence else 0.5
        elif extraction_method == ExtractionMethod.TABLE_EXTRACTION:
            base = 0.85 if ocr_confidence is None else ocr_confidence * 0.9
        else:
            base = 0.80

        # Apply pattern specificity (labeled patterns like "API No: XX" > bare numbers)
        confidence = base * pattern_specificity

        # Validation bonus/penalty
        if not value_validated:
            confidence *= 0.7  # Significant penalty for failed validation

        # Cross-reference bonus
        if cross_reference_match:
            confidence = min(confidence * 1.1, 0.99)

        return round(min(max(confidence, 0.0), 1.0), 4)
```

### 5.3 Document-Level Confidence Aggregation

```python
from dataclasses import dataclass
from typing import Optional

# Field importance weights for document-level confidence
FIELD_WEIGHTS = {
    # Critical fields (highest weight)
    "api_number": 3.0,
    "operator_name": 2.5,
    "document_type": 2.5,

    # Important fields
    "well_name": 2.0,
    "county": 1.5,
    "state": 1.5,
    "reporting_period": 2.0,

    # Production values
    "oil_bbls": 2.0,
    "gas_mcf": 2.0,
    "water_bbls": 1.5,

    # Standard fields
    "permit_number": 1.5,
    "dates": 1.5,
    "location": 1.5,

    # Lower priority
    "days_produced": 1.0,
    "well_status": 1.0,
}

@dataclass
class DocumentConfidence:
    """Document-level confidence aggregation."""
    classification_confidence: float
    field_confidences: dict[str, FieldConfidence]
    ocr_page_confidences: list[float]       # Per-page OCR confidence

    @property
    def weighted_field_confidence(self) -> float:
        """Weighted average of field confidences."""
        if not self.field_confidences:
            return 0.0

        total_weight = 0.0
        weighted_sum = 0.0

        for field_name, field_conf in self.field_confidences.items():
            weight = FIELD_WEIGHTS.get(field_name, 1.0)
            weighted_sum += field_conf.confidence * weight
            total_weight += weight

        return weighted_sum / total_weight if total_weight > 0 else 0.0

    @property
    def min_page_confidence(self) -> float:
        """Minimum OCR confidence across all pages."""
        return min(self.ocr_page_confidences) if self.ocr_page_confidences else 1.0

    @property
    def overall_confidence(self) -> float:
        """
        Composite document confidence.

        Formula: 0.3 * classification + 0.5 * weighted_fields + 0.2 * min_page_ocr
        """
        return (
            0.3 * self.classification_confidence +
            0.5 * self.weighted_field_confidence +
            0.2 * self.min_page_confidence
        )

    @property
    def disposition(self) -> str:
        """Determine document disposition based on confidence thresholds."""
        overall = self.overall_confidence

        if overall >= 0.85:
            return "auto_accept"
        elif overall >= 0.50:
            return "review_queue"
        else:
            return "reject"

    @property
    def fields_needing_review(self) -> list[str]:
        """List of fields below the review threshold."""
        review_fields = []
        for field_name, field_conf in self.field_confidences.items():
            threshold = _get_field_threshold(field_name)
            if field_conf.confidence < threshold:
                review_fields.append(field_name)
        return review_fields

def _get_field_threshold(field_name: str) -> float:
    """Get the auto-accept confidence threshold for a specific field."""
    THRESHOLDS = {
        "api_number": 0.95,
        "operator_name": 0.90,
        "oil_bbls": 0.90,
        "gas_mcf": 0.90,
        "water_bbls": 0.90,
        "dates": 0.90,
        "location": 0.95,
        "well_name": 0.85,
        "county": 0.85,
        "state": 0.90,
        "document_type": 0.85,
    }
    return THRESHOLDS.get(field_name, 0.85)
```

### 5.4 Threshold Values for Strict Rejection Policy

Per the discovery document (D10): "Only store data above a confidence threshold. Low-confidence documents go to a review queue."

**Three-tier disposition system:**

| Tier | Overall Confidence | Action | Dashboard Display |
|------|-------------------|--------|-------------------|
| **Auto-Accept** | >= 0.85 | Store in main tables immediately | Green checkmark |
| **Review Queue** | 0.50 - 0.84 | Store in staging tables, flag for review | Yellow warning |
| **Reject** | < 0.50 | Store metadata only, link to original PDF | Red X |

**Field-level thresholds (stricter for critical fields):**

| Field | Auto-Accept | Review | Reject |
|-------|------------|--------|--------|
| API Number | >= 0.95 | 0.70-0.95 | < 0.70 |
| Operator Name | >= 0.90 | 0.60-0.90 | < 0.60 |
| Production Values (oil/gas/water) | >= 0.90 | 0.70-0.90 | < 0.70 |
| Dates | >= 0.90 | 0.65-0.90 | < 0.65 |
| Well Location/Coordinates | >= 0.95 | 0.80-0.95 | < 0.80 |
| Document Classification | >= 0.85 | 0.50-0.85 | < 0.50 |

**Rejection policy:** If ANY critical field (API number, production values) is below the reject threshold, the entire document goes to review queue regardless of overall confidence.

### 5.5 Storing Confidence Metadata in PostgreSQL

```sql
-- Documents table with confidence metadata
CREATE TABLE extracted_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file_path TEXT NOT NULL,
    source_url TEXT,
    state VARCHAR(2) NOT NULL,
    document_type VARCHAR(50),
    processing_status VARCHAR(20) NOT NULL DEFAULT 'pending',
        -- 'pending', 'processing', 'auto_accepted', 'review_queue', 'rejected',
        -- 'manually_accepted', 'manually_corrected'

    -- Classification confidence
    classification_confidence FLOAT,
    classification_method VARCHAR(30),  -- 'form_number', 'keyword', 'header'

    -- Overall confidence
    overall_confidence FLOAT,
    min_page_ocr_confidence FLOAT,
    weighted_field_confidence FLOAT,

    -- Per-page OCR confidence (JSONB array)
    page_confidences JSONB,
    -- Example: [{"page": 0, "method": "text", "confidence": 1.0},
    --           {"page": 1, "method": "ocr", "confidence": 0.87}]

    -- Extraction metadata
    extraction_method VARCHAR(30),  -- 'text_only', 'ocr_only', 'mixed'
    pages_total INTEGER,
    pages_ocr INTEGER,
    pages_text INTEGER,
    processing_time_ms INTEGER,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    reviewed_by TEXT
);

-- Extracted fields with per-field confidence
CREATE TABLE extracted_fields (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES extracted_documents(id) ON DELETE CASCADE,
    field_name VARCHAR(50) NOT NULL,
    field_value TEXT,
    field_value_numeric FLOAT,       -- For numeric fields (production volumes)
    field_value_date DATE,           -- For date fields

    -- Confidence metadata
    confidence FLOAT NOT NULL,
    extraction_method VARCHAR(30),    -- 'regex', 'ocr', 'table', 'text'
    ocr_confidence FLOAT,            -- Raw OCR confidence (if from OCR)
    pattern_match_quality FLOAT,     -- How specific the pattern match was
    validation_passed BOOLEAN DEFAULT TRUE,

    -- Review support
    needs_review BOOLEAN DEFAULT FALSE,
    manually_corrected BOOLEAN DEFAULT FALSE,
    original_value TEXT,             -- Pre-correction value (if corrected)
    corrected_by TEXT,
    corrected_at TIMESTAMPTZ,

    -- Source location in document
    page_num INTEGER,
    bbox JSONB,                      -- Bounding box: {"x1": 0, "y1": 0, "x2": 100, "y2": 50}

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast review queue queries
CREATE INDEX idx_documents_review ON extracted_documents(processing_status)
    WHERE processing_status IN ('review_queue', 'pending');

CREATE INDEX idx_documents_confidence ON extracted_documents(overall_confidence);

CREATE INDEX idx_fields_review ON extracted_fields(needs_review)
    WHERE needs_review = TRUE;

-- Index for field confidence queries
CREATE INDEX idx_fields_confidence ON extracted_fields(document_id, confidence);

-- GIN index on page_confidences for JSONB queries
CREATE INDEX idx_documents_page_conf ON extracted_documents
    USING GIN (page_confidences);
```

**Query examples for the dashboard:**

```sql
-- Get review queue (documents needing human review)
SELECT id, source_file_path, document_type, overall_confidence,
       state, created_at
FROM extracted_documents
WHERE processing_status = 'review_queue'
ORDER BY overall_confidence DESC;  -- Show highest confidence first (easiest to review)

-- Get fields needing review for a specific document
SELECT field_name, field_value, confidence, extraction_method,
       ocr_confidence, page_num
FROM extracted_fields
WHERE document_id = $1 AND needs_review = TRUE
ORDER BY confidence ASC;  -- Show lowest confidence first

-- Confidence distribution for monitoring
SELECT
    CASE
        WHEN overall_confidence >= 0.85 THEN 'auto_accepted'
        WHEN overall_confidence >= 0.50 THEN 'review_queue'
        ELSE 'rejected'
    END as tier,
    COUNT(*) as doc_count,
    AVG(overall_confidence) as avg_confidence
FROM extracted_documents
GROUP BY tier;

-- Average OCR confidence by state (identify problem states)
SELECT state,
       AVG(min_page_ocr_confidence) as avg_ocr_confidence,
       COUNT(*) as doc_count
FROM extracted_documents
WHERE extraction_method IN ('ocr_only', 'mixed')
GROUP BY state
ORDER BY avg_ocr_confidence ASC;
```

---

## 6. Seven-Stage Pipeline Architecture

### 6.1 Pipeline Overview

```
discover --> download --> classify --> extract --> normalize --> validate --> store
    |           |            |            |            |            |          |
    v           v            v            v            v            v          v
 Find docs   Fetch &     Identify     Pull out     Standardize  Cross-check  Write to
 on state    store       doc type     fields &     units, names, values &    PostgreSQL
 websites    originals   & state      tables       dates, etc.   flag low    & filesystem
                                                                 confidence
```

Each stage is independently retriable. If stage 4 (extract) fails, the document stays in "downloaded + classified" state and can be re-processed from stage 4 without re-downloading or re-classifying.

### 6.2 Pipeline State Machine

```python
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
import uuid

class PipelineStage(Enum):
    DISCOVERED = "discovered"
    DOWNLOADED = "downloaded"
    CLASSIFIED = "classified"
    EXTRACTED = "extracted"
    NORMALIZED = "normalized"
    VALIDATED = "validated"
    STORED = "stored"
    FAILED = "failed"
    REVIEW = "review"

class PipelineStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

@dataclass
class PipelineJob:
    """Tracks a document through the seven-stage pipeline."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_url: str = ""
    state: str = ""                        # US state code
    current_stage: PipelineStage = PipelineStage.DISCOVERED
    status: PipelineStatus = PipelineStatus.PENDING

    # Stage results (populated as document moves through pipeline)
    local_file_path: Optional[str] = None  # After download
    document_type: Optional[str] = None    # After classify
    extracted_data: Optional[dict] = None  # After extract
    normalized_data: Optional[dict] = None # After normalize
    validation_result: Optional[dict] = None  # After validate
    database_id: Optional[str] = None      # After store

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    processing_time_ms: int = 0

    # Confidence
    overall_confidence: float = 0.0

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def advance_to(self, stage: PipelineStage):
        self.current_stage = stage
        self.status = PipelineStatus.PENDING
        self.updated_at = datetime.utcnow()

    def fail(self, error: str):
        self.status = PipelineStatus.FAILED
        self.error_message = error
        self.updated_at = datetime.utcnow()

    def to_review(self):
        self.current_stage = PipelineStage.REVIEW
        self.status = PipelineStatus.COMPLETED
        self.updated_at = datetime.utcnow()
```

### 6.3 Stage Implementations

```python
import os
import time
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("pipeline")

class PipelineStageHandler(ABC):
    """Base class for pipeline stage handlers."""

    @abstractmethod
    def process(self, job: PipelineJob) -> PipelineJob:
        """Process a job through this stage. Returns updated job."""
        pass

    def execute(self, job: PipelineJob) -> PipelineJob:
        """Execute with timing and error handling."""
        start = time.time()
        try:
            job.status = PipelineStatus.PROCESSING
            result = self.process(job)
            result.processing_time_ms += int((time.time() - start) * 1000)
            return result
        except Exception as e:
            job.fail(str(e))
            logger.error(f"Stage {self.__class__.__name__} failed for job {job.id}: {e}")
            return job


class DiscoverStage(PipelineStageHandler):
    """Stage 1: Find documents on state websites."""

    def process(self, job: PipelineJob) -> PipelineJob:
        # This stage is handled by the scraping system (Scrapy/Playwright)
        # The job arrives here with source_url already populated
        job.advance_to(PipelineStage.DISCOVERED)
        job.status = PipelineStatus.COMPLETED
        return job


class DownloadStage(PipelineStageHandler):
    """Stage 2: Download and store original document."""

    def __init__(self, base_data_dir: str):
        self.base_data_dir = base_data_dir

    def process(self, job: PipelineJob) -> PipelineJob:
        import requests

        # Determine storage path: data/{state}/{doc_type}/{filename}
        # doc_type is unknown at this stage — use 'unclassified'
        state_dir = os.path.join(self.base_data_dir, job.state, "unclassified")
        os.makedirs(state_dir, exist_ok=True)

        filename = job.source_url.split("/")[-1] or f"{job.id}.pdf"
        file_path = os.path.join(state_dir, filename)

        # Download
        response = requests.get(job.source_url, timeout=60)
        response.raise_for_status()

        with open(file_path, "wb") as f:
            f.write(response.content)

        job.local_file_path = file_path
        job.advance_to(PipelineStage.DOWNLOADED)
        job.status = PipelineStatus.COMPLETED
        return job


class ClassifyStage(PipelineStageHandler):
    """Stage 3: Classify document type."""

    def process(self, job: PipelineJob) -> PipelineJob:
        # Step 1: Extract text (fast path for text PDFs, OCR for scanned)
        page_classes = classify_pdf_pages(job.local_file_path)
        has_scanned = any(p["classification"] == "scanned" for p in page_classes)

        if has_scanned:
            # OCR the first few pages for classification
            text_parts = []
            for p in page_classes[:3]:  # First 3 pages usually enough
                if p["classification"] == "text":
                    text_parts.append(extract_text_page_pymupdf(
                        job.local_file_path, p["page_num"]))
                else:
                    ocr_result = extract_scanned_page(
                        job.local_file_path, p["page_num"])
                    text_parts.append(ocr_result["full_text"])
            text = "\n".join(text_parts)
        else:
            # All text pages — fast extraction
            text = extract_text_page_pymupdf(job.local_file_path, 0)

        # Step 2: Classify
        classification = classify_document(text)
        job.document_type = classification.document_type
        job.overall_confidence = classification.confidence

        # Step 3: Move file to classified folder
        if classification.document_type != "unknown":
            new_dir = os.path.join(
                os.path.dirname(os.path.dirname(job.local_file_path)),
                classification.document_type,
            )
            os.makedirs(new_dir, exist_ok=True)
            new_path = os.path.join(new_dir, os.path.basename(job.local_file_path))
            if not os.path.exists(new_path):
                os.rename(job.local_file_path, new_path)
                job.local_file_path = new_path

        job.advance_to(PipelineStage.CLASSIFIED)
        job.status = PipelineStatus.COMPLETED
        return job


class ExtractStage(PipelineStageHandler):
    """Stage 4: Extract fields and tables from document."""

    def process(self, job: PipelineJob) -> PipelineJob:
        # Process all pages
        page_results = process_mixed_pdf(job.local_file_path)

        # Combine text from all pages
        full_text = "\n".join(pr.text for pr in page_results)

        # Extract fields using regex patterns
        extracted = {}
        extracted["api_numbers"] = extract_api_numbers(full_text)
        extracted["production"] = extract_production_volumes(full_text)
        extracted["dates"] = extract_dates(full_text)
        extracted["operator_info"] = extract_operator_info(full_text)
        extracted["permit_number"] = extract_permit_number(full_text, job.state)

        # Extract tables
        extracted["tables"] = []
        for pr in page_results:
            if pr.tables:
                for table in pr.tables:
                    parsed = parse_production_table(table, job.state)
                    if parsed:
                        extracted["tables"].extend(parsed)

        # Store page-level OCR confidences
        extracted["page_confidences"] = [
            {"page": pr.page_num, "method": pr.method, "confidence": pr.confidence}
            for pr in page_results
        ]

        job.extracted_data = extracted
        job.advance_to(PipelineStage.EXTRACTED)
        job.status = PipelineStatus.COMPLETED
        return job


class NormalizeStage(PipelineStageHandler):
    """Stage 5: Normalize extracted data into standard format."""

    def process(self, job: PipelineJob) -> PipelineJob:
        data = job.extracted_data
        normalized = {}

        # Normalize API number (pick best match, pad to 14 digits)
        api_numbers = data.get("api_numbers", [])
        if api_numbers:
            # Pick highest confidence match
            best = max(api_numbers, key=lambda x: x["confidence"])
            normalized["api_number"] = best["normalized"].ljust(14, "0")
            normalized["api_number_confidence"] = best["confidence"]
        else:
            normalized["api_number"] = None

        # Normalize operator name (trim, title case)
        op_info = data.get("operator_info", {})
        if op_info.get("operator_name"):
            name = op_info["operator_name"].strip()
            # Don't title-case if already has mixed case (like "ConocoPhillips")
            if name == name.upper():
                name = name.title()
            normalized["operator_name"] = name

        # Normalize dates to ISO format
        dates = data.get("dates", {})
        for date_field, date_info in dates.items():
            if date_info.get("parsed"):
                normalized[date_field] = date_info["parsed"]
            else:
                normalized[date_field] = date_info.get("raw")

        # Normalize production values (ensure consistent units)
        prod = data.get("production", {})
        normalized["oil_bbls"] = prod.get("oil_bbls")
        normalized["gas_mcf"] = prod.get("gas_mcf")
        normalized["water_bbls"] = prod.get("water_bbls")
        normalized["days_produced"] = prod.get("days_produced")

        # Normalize location
        if op_info.get("latitude") and op_info.get("longitude"):
            normalized["latitude"] = op_info["latitude"]
            normalized["longitude"] = op_info["longitude"]

        normalized["state"] = job.state
        normalized["county"] = op_info.get("county")
        normalized["document_type"] = job.document_type

        job.normalized_data = normalized
        job.advance_to(PipelineStage.NORMALIZED)
        job.status = PipelineStatus.COMPLETED
        return job


class ValidateStage(PipelineStageHandler):
    """Stage 6: Validate and compute confidence scores."""

    def process(self, job: PipelineJob) -> PipelineJob:
        data = job.normalized_data
        page_confs = job.extracted_data.get("page_confidences", [])
        issues = []

        # Validate API number format
        api = data.get("api_number")
        if api:
            if len(api) < 10 or not api[:2].isdigit():
                issues.append(("api_number", "Invalid API number format"))
            elif api[:2] not in VALID_STATE_CODES:
                issues.append(("api_number", f"Unknown state code: {api[:2]}"))

        # Validate production values are reasonable
        for field in ["oil_bbls", "gas_mcf", "water_bbls"]:
            val = data.get(field)
            if val is not None and val < 0:
                issues.append((field, f"Negative production value: {val}"))
            if val is not None and val > 10_000_000:  # 10M BBL/MCF per month is extreme
                issues.append((field, f"Suspiciously high value: {val}"))

        # Validate days produced
        days = data.get("days_produced")
        if days is not None and (days < 0 or days > 31):
            issues.append(("days_produced", f"Invalid days produced: {days}"))

        # Compute document confidence
        ocr_confidences = [p["confidence"] for p in page_confs]

        # Build field confidences
        field_confidences = {}
        for field_name in ["api_number", "operator_name", "oil_bbls", "gas_mcf",
                           "water_bbls", "county", "state"]:
            if data.get(field_name) is not None:
                # Determine if field came from OCR
                avg_ocr = sum(ocr_confidences) / len(ocr_confidences) if ocr_confidences else 1.0
                has_issues = any(f == field_name for f, _ in issues)

                conf = FieldConfidence.compute(
                    extraction_method=ExtractionMethod.OCR if ocr_confidences else ExtractionMethod.TEXT_EXTRACTION,
                    ocr_confidence=avg_ocr if ocr_confidences else None,
                    pattern_specificity=0.9,
                    value_validated=not has_issues,
                )
                field_confidences[field_name] = FieldConfidence(
                    field_name=field_name,
                    value=data[field_name],
                    confidence=conf,
                    extraction_method=ExtractionMethod.OCR if ocr_confidences else ExtractionMethod.TEXT_EXTRACTION,
                )

        doc_confidence = DocumentConfidence(
            classification_confidence=job.overall_confidence,
            field_confidences=field_confidences,
            ocr_page_confidences=ocr_confidences,
        )

        job.validation_result = {
            "overall_confidence": doc_confidence.overall_confidence,
            "disposition": doc_confidence.disposition,
            "issues": issues,
            "fields_needing_review": doc_confidence.fields_needing_review,
        }
        job.overall_confidence = doc_confidence.overall_confidence

        job.advance_to(PipelineStage.VALIDATED)
        job.status = PipelineStatus.COMPLETED
        return job


class StoreStage(PipelineStageHandler):
    """Stage 7: Store results in PostgreSQL."""

    def __init__(self, db_connection):
        self.db = db_connection

    def process(self, job: PipelineJob) -> PipelineJob:
        disposition = job.validation_result["disposition"]

        if disposition == "auto_accept":
            status = "auto_accepted"
        elif disposition == "review_queue":
            status = "review_queue"
        else:
            status = "rejected"

        # Insert into extracted_documents table
        # (Using parameterized queries — simplified here)
        doc_id = self._insert_document(job, status)

        # Insert extracted fields
        if job.normalized_data:
            self._insert_fields(doc_id, job)

        job.database_id = doc_id
        job.advance_to(PipelineStage.STORED)
        job.status = PipelineStatus.COMPLETED
        return job

    def _insert_document(self, job: PipelineJob, status: str) -> str:
        """Insert document record. Returns document ID."""
        # Implementation uses psycopg2 or asyncpg
        # See PostgreSQL schema in section 5.5
        pass

    def _insert_fields(self, doc_id: str, job: PipelineJob):
        """Insert per-field extraction records with confidence."""
        pass
```

### 6.4 Task Queue with Huey (Local Deployment)

Huey is the recommended task queue for this project because:
- Works with SQLite backend (no Redis dependency)
- Built-in retry with configurable delay
- Task pipelines/chaining
- Task priority support
- Result storage
- Lightweight (single Python package)
- Thread-based or process-based workers

**Setup:**

```python
# pipeline/tasks.py
from huey import SqliteHuey

# SQLite backend — no external services needed
huey = SqliteHuey(
    filename='data/pipeline_queue.db',
    immediate=False,  # Use background workers
)

# --- Stage Tasks ---

@huey.task(retries=3, retry_delay=30, priority=10)
def task_download(job_dict: dict) -> dict:
    """Stage 2: Download document."""
    job = PipelineJob(**job_dict)
    handler = DownloadStage(base_data_dir="data/documents")
    result = handler.execute(job)
    return result.__dict__

@huey.task(retries=2, retry_delay=10, priority=20)
def task_classify(job_dict: dict) -> dict:
    """Stage 3: Classify document type."""
    job = PipelineJob(**job_dict)
    handler = ClassifyStage()
    result = handler.execute(job)
    return result.__dict__

@huey.task(retries=2, retry_delay=30, priority=30)
def task_extract(job_dict: dict) -> dict:
    """Stage 4: Extract data from document."""
    job = PipelineJob(**job_dict)
    handler = ExtractStage()
    result = handler.execute(job)
    return result.__dict__

@huey.task(retries=1, retry_delay=5, priority=40)
def task_normalize(job_dict: dict) -> dict:
    """Stage 5: Normalize extracted data."""
    job = PipelineJob(**job_dict)
    handler = NormalizeStage()
    result = handler.execute(job)
    return result.__dict__

@huey.task(retries=1, retry_delay=5, priority=50)
def task_validate(job_dict: dict) -> dict:
    """Stage 6: Validate and score confidence."""
    job = PipelineJob(**job_dict)
    handler = ValidateStage()
    result = handler.execute(job)
    return result.__dict__

@huey.task(retries=3, retry_delay=10, priority=60)
def task_store(job_dict: dict) -> dict:
    """Stage 7: Store in database."""
    job = PipelineJob(**job_dict)
    handler = StoreStage(db_connection=get_db())
    result = handler.execute(job)
    return result.__dict__

# --- Pipeline Orchestration ---

def enqueue_document_pipeline(source_url: str, state: str):
    """Enqueue a full document processing pipeline."""
    job = PipelineJob(source_url=source_url, state=state)

    # Chain stages using Huey's pipeline feature
    pipeline = (
        task_download.s(job.__dict__)
        .then(task_classify)
        .then(task_extract)
        .then(task_normalize)
        .then(task_validate)
        .then(task_store)
    )
    result = huey.enqueue(pipeline)
    return job.id, result

def enqueue_batch(urls_and_states: list[tuple[str, str]]):
    """Enqueue multiple documents for processing."""
    job_ids = []
    for url, state in urls_and_states:
        job_id, _ = enqueue_document_pipeline(url, state)
        job_ids.append(job_id)
    return job_ids
```

**Running the Huey consumer:**

```bash
# Start 2 thread-based workers
huey_consumer.py pipeline.tasks.huey -w 2 -k thread

# Or with process-based workers (better for CPU-bound OCR)
huey_consumer.py pipeline.tasks.huey -w 2 -k process

# With verbose logging
huey_consumer.py pipeline.tasks.huey -w 2 -k process --logfile logs/pipeline.log -v
```

### 6.5 Alternative: asyncio-Based Pipeline (Simpler, No External Queue)

For simpler deployments without Huey, use asyncio with an in-memory queue:

```python
import asyncio
import logging
from collections import defaultdict
from typing import Callable

logger = logging.getLogger("pipeline")

class AsyncPipeline:
    """Simple asyncio-based pipeline with retry and progress reporting."""

    def __init__(self):
        self.stages: list[tuple[str, Callable]] = []
        self.progress: dict[str, dict] = {}
        self.progress_callbacks: list[Callable] = []

    def add_stage(self, name: str, handler: Callable):
        self.stages.append((name, handler))

    def on_progress(self, callback: Callable):
        self.progress_callbacks.append(callback)

    def _report_progress(self, job_id: str, stage: str, status: str,
                          detail: str = ""):
        self.progress[job_id] = {
            "stage": stage,
            "status": status,
            "detail": detail,
        }
        for cb in self.progress_callbacks:
            cb(job_id, stage, status, detail)

    async def process_document(self, job: PipelineJob,
                                max_retries: int = 3) -> PipelineJob:
        """Process a single document through all stages with retry."""
        for stage_name, handler in self.stages:
            retries = 0
            while retries <= max_retries:
                try:
                    self._report_progress(job.id, stage_name, "processing")

                    # Run CPU-bound work in thread pool
                    loop = asyncio.get_event_loop()
                    job = await loop.run_in_executor(None, handler.execute, job)

                    if job.status == PipelineStatus.FAILED:
                        raise Exception(job.error_message)

                    self._report_progress(job.id, stage_name, "completed")
                    break

                except Exception as e:
                    retries += 1
                    if retries > max_retries:
                        self._report_progress(
                            job.id, stage_name, "failed", str(e))
                        job.fail(f"Stage {stage_name} failed after {max_retries} retries: {e}")
                        return job

                    self._report_progress(
                        job.id, stage_name, "retrying",
                        f"Attempt {retries}/{max_retries}")
                    await asyncio.sleep(retries * 5)  # Exponential-ish backoff

        return job

    async def process_batch(self, jobs: list[PipelineJob],
                             concurrency: int = 3) -> list[PipelineJob]:
        """Process multiple documents with limited concurrency."""
        semaphore = asyncio.Semaphore(concurrency)
        results = []

        async def bounded_process(job):
            async with semaphore:
                return await self.process_document(job)

        tasks = [bounded_process(job) for job in jobs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return [r if isinstance(r, PipelineJob) else None for r in results]


# Setup and usage
pipeline = AsyncPipeline()
pipeline.add_stage("download", DownloadStage("data/documents"))
pipeline.add_stage("classify", ClassifyStage())
pipeline.add_stage("extract", ExtractStage())
pipeline.add_stage("normalize", NormalizeStage())
pipeline.add_stage("validate", ValidateStage())
pipeline.add_stage("store", StoreStage(get_db()))

# Progress callback for dashboard integration (via WebSocket or SSE)
def on_progress(job_id, stage, status, detail):
    logger.info(f"Job {job_id}: {stage} -> {status} {detail}")
    # Could push to WebSocket here for real-time dashboard updates

pipeline.on_progress(on_progress)

# Run
async def main():
    jobs = [PipelineJob(source_url=url, state=state)
            for url, state in documents_to_process]
    results = await pipeline.process_batch(jobs, concurrency=2)
```

### 6.6 Progress Reporting for Dashboard Integration

The dashboard needs real-time progress updates for scraping/processing jobs.

**Approach: Server-Sent Events (SSE) from FastAPI**

```python
# api/progress.py
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio
import json

app = FastAPI()

# In-memory progress store (shared with pipeline)
progress_store: dict[str, dict] = {}

@app.get("/api/pipeline/progress/{job_id}")
async def stream_progress(job_id: str):
    """SSE endpoint for real-time pipeline progress."""

    async def event_generator():
        last_stage = None
        while True:
            current = progress_store.get(job_id, {})
            if current.get("stage") != last_stage or current.get("status") == "completed":
                data = json.dumps(current)
                yield f"data: {data}\n\n"
                last_stage = current.get("stage")

                # Stop streaming if pipeline is done
                if current.get("stage") in ("stored", "failed", "review"):
                    break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )

@app.get("/api/pipeline/batch/progress")
async def batch_progress():
    """Get progress summary for all active jobs."""
    active_jobs = {
        job_id: info for job_id, info in progress_store.items()
        if info.get("status") != "completed"
    }
    return {
        "active_count": len(active_jobs),
        "jobs": active_jobs,
        "stage_counts": _count_by_stage(active_jobs),
    }

def _count_by_stage(jobs: dict) -> dict:
    counts = {}
    for info in jobs.values():
        stage = info.get("stage", "unknown")
        counts[stage] = counts.get(stage, 0) + 1
    return counts
```

### 6.7 Making Stages Independently Retriable

The key to independent retriability is storing pipeline state in the database at each stage boundary:

```sql
-- Pipeline jobs table for state tracking
CREATE TABLE pipeline_jobs (
    id UUID PRIMARY KEY,
    source_url TEXT NOT NULL,
    state VARCHAR(2) NOT NULL,
    current_stage VARCHAR(20) NOT NULL DEFAULT 'discovered',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    -- File reference
    local_file_path TEXT,

    -- Stage outputs (JSONB for flexibility)
    classification_result JSONB,
    extraction_result JSONB,
    normalization_result JSONB,
    validation_result JSONB,

    -- Metadata
    error_message TEXT,
    processing_time_ms INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for finding retriable jobs
CREATE INDEX idx_pipeline_failed ON pipeline_jobs(current_stage, status)
    WHERE status = 'failed' AND retry_count < max_retries;
```

**Retry logic:**

```python
def retry_failed_jobs(db):
    """Find and re-enqueue failed jobs that haven't exceeded retry limit."""
    failed_jobs = db.execute("""
        SELECT id, current_stage, source_url, state, retry_count
        FROM pipeline_jobs
        WHERE status = 'failed' AND retry_count < max_retries
        ORDER BY created_at ASC
    """).fetchall()

    for job_row in failed_jobs:
        job = load_job_from_db(job_row["id"])

        # Resume from the failed stage (not from the beginning)
        stage_name = job.current_stage.value
        logger.info(f"Retrying job {job.id} from stage {stage_name} "
                     f"(attempt {job.retry_count + 1})")

        job.retry_count += 1
        job.status = PipelineStatus.RETRYING

        # Re-enqueue from the appropriate stage
        STAGE_TASKS = {
            "downloaded": task_classify,
            "classified": task_extract,
            "extracted": task_normalize,
            "normalized": task_validate,
            "validated": task_store,
        }

        task_fn = STAGE_TASKS.get(stage_name)
        if task_fn:
            task_fn(job.__dict__)
```

### 6.8 Recommended Architecture Decision: Huey vs asyncio

| Factor | Huey (SQLite) | asyncio (in-memory) |
|--------|--------------|---------------------|
| Persistence | Jobs survive process restart | Lost on restart |
| Setup complexity | Requires consumer process | Single process |
| Retry | Built-in decorator | Manual implementation |
| Monitoring | CLI tools, signal-based | Custom |
| Concurrency | Multi-process or multi-thread | Async + thread pool |
| Dashboard integration | Poll database or emit events | Direct callback |
| Best for | Production, reliability | Development, simplicity |

**Recommendation:** Start with the **asyncio approach** during development for simplicity. Move to **Huey with SQLite** for the production Docker deployment. The pipeline stage handlers are the same — only the orchestration layer changes. The pipeline_jobs PostgreSQL table provides persistence and retriability regardless of which queue is used for in-flight processing.

---

## Appendix A: Complete pip Requirements

```
# Core OCR and document processing
paddlepaddle==3.2.1          # PaddlePaddle framework (CPU)
paddleocr[doc-parser]        # PaddleOCR with document parsing

# PDF processing
PyMuPDF>=1.24.0              # Fast PDF text extraction (fitz)
pdfplumber>=0.11.0           # Table extraction from text PDFs

# Image preprocessing
opencv-python-headless>=4.8  # Image preprocessing for OCR
Pillow>=10.0                 # Image handling
numpy>=1.24                  # Array operations

# Task queue
huey>=2.6.0                  # Task queue with SQLite backend

# Database
psycopg2-binary>=2.9         # PostgreSQL driver
# or: asyncpg>=0.29          # Async PostgreSQL driver (for FastAPI)

# NER (Phase 2)
# spacy>=3.7                 # Named entity recognition
# en_core_web_sm             # spaCy English model
```

## Appendix B: Performance Tuning Quick Reference

| Setting | Development (macOS) | Production (Linux Docker) |
|---------|-------------------|---------------------------|
| PaddlePaddle device | `cpu` | `cpu` (or `gpu:0` if available) |
| CPU threads | 4 | 4-8 (match container CPU limit) |
| MKL-DNN | Enabled | Enabled |
| Batch size | 1 (sequential) | 2-4 (parallel workers) |
| Huey workers | 1 (thread) | 2 (process) |
| OCR model | Server (accuracy) | Server (accuracy) |
| Memory limit | No limit | 4GB container limit |
| Runtime cache | 20 shapes | 20 shapes |
| Image DPI for OCR | 300 | 300 |
| `text_det_box_thresh` | 0.5 | 0.5 |
| `text_rec_score_thresh` | 0.0 | 0.0 |

## Appendix C: Sources

- [PaddleOCR GitHub Repository](https://github.com/PaddlePaddle/PaddleOCR)
- [PaddleOCR Documentation — OCR Pipeline](http://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html)
- [PaddleOCR Documentation — PP-StructureV3](http://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PP-StructureV3.html)
- [PaddleOCR Installation Guide](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/installation.en.md)
- [PaddleOCR 3.0 Technical Report](https://arxiv.org/html/2507.05595v1)
- [PaddleOCR Python API (DeepWiki)](https://deepwiki.com/PaddlePaddle/PaddleOCR/3.3-python-api-usage)
- [PP-OCRv5 on Hugging Face](https://huggingface.co/blog/baidu/ppocrv5)
- [PaddleOCR Apple Silicon Discussion](https://github.com/PaddlePaddle/PaddleOCR/discussions/12795)
- [Building PaddlePaddle on Apple Silicon](https://gist.github.com/keyboardsamurai/9c7d444119f4ea3398a2ad0d1412320e)
- [PaddleOCR Memory Leak Issue](https://github.com/PaddlePaddle/PaddleOCR/issues/15631)
- [PaddleOCR Memory Leak Fix (OpenVINO)](https://medium.com/@dannysiu/solving-a-stubborn-memory-leak-in-my-openvino-paddleocr-service-f4e38a966e24)
- [PaddleOCR Benchmark Comparisons](https://tildalice.io/ocr-tesseract-easyocr-paddleocr-benchmark/)
- [PyMuPDF Scanned PDF Detection](https://github.com/pymupdf/PyMuPDF/discussions/1653)
- [PyMuPDF Documentation](https://pymupdf.readthedocs.io/en/latest/)
- [PDF Table Extraction Comparison (2025)](https://medium.com/@kramermark/i-tested-12-best-in-class-pdf-table-extraction-tools-and-the-results-were-appalling-f8a9991d972e)
- [Best Python Libraries for PDF Table Extraction (2026)](https://unstract.com/blog/extract-tables-from-pdf-python/)
- [Huey Task Queue](https://github.com/coleifer/huey)
- [Huey Documentation](https://huey.readthedocs.io/en/latest/)
- [spaCy Training Guide](https://spacy.io/usage/training)
- [Texas RRC Oil & Gas Forms](https://www.rrc.texas.gov/oil-and-gas/oil-and-gas-forms/)
- [API Well Number — Wikipedia](https://en.wikipedia.org/wiki/API_well_number)
- [Asyncio Pipelines (Towards Data Science)](https://towardsdatascience.com/blazing-hot-python-asyncio-pipelines-438b34bed9f/)
- [PaddleOCR-VL MLX Port](https://huggingface.co/gamhtoi/PaddleOCR-VL-MLX)
- [OmniDocBench Benchmark](https://github.com/opendatalab/OmniDocBench)
