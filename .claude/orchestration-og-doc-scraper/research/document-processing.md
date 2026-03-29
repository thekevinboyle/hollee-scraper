# Document Processing, PDF Extraction & OCR — Research Report

**Research Date**: 2026-03-27
**Project**: Oil & Gas Document Scraper
**Scope**: PDF text extraction, OCR, table extraction, document classification, LLM-based extraction, batch processing

---

## Table of Contents

1. [PDF Text Extraction Libraries](#1-pdf-text-extraction-libraries)
2. [OCR Solutions for Scanned Documents](#2-ocr-solutions-for-scanned-documents)
3. [Table Extraction from PDFs](#3-table-extraction-from-pdfs)
4. [Handling Mixed PDF Types](#4-handling-mixed-pdf-types)
5. [Excel/CSV Parsing](#5-excelcsv-parsing)
6. [HTML Table Extraction](#6-html-table-extraction)
7. [Document Classification Approaches](#7-document-classification-approaches)
8. [LLM-Based Document Understanding & Extraction](#8-llm-based-document-understanding--extraction)
9. [Structured Data Extraction from Unstructured Documents](#9-structured-data-extraction-from-unstructured-documents)
10. [Handling Poor Quality Scans, Rotated Pages, Multi-Column Layouts](#10-handling-poor-quality-scans-rotated-pages-multi-column-layouts)
11. [Cost Analysis: Local vs Cloud OCR](#11-cost-analysis-local-vs-cloud-ocr)
12. [Confidence Scoring for Extracted Data](#12-confidence-scoring-for-extracted-data)
13. [Batch Processing Strategies](#13-batch-processing-strategies)
14. [Integrated Document Processing Frameworks](#14-integrated-document-processing-frameworks)
15. [Oil & Gas Document Types Reference](#15-oil--gas-document-types-reference)
16. [Recommendations for This Project](#16-recommendations-for-this-project)

---

## 1. PDF Text Extraction Libraries

### Library Comparison Matrix

| Library | Speed | Layout Analysis | Table Support | Dependencies | Maintenance | Best For |
|---------|-------|----------------|---------------|-------------|-------------|----------|
| **PyPDF (PyPDF2)** | Fast | Basic | No | Pure Python | Active (merged back into PyPDF) | Simple text extraction, metadata |
| **pdfminer.six** | Moderate | Excellent | No | Pure Python | Active | CJK languages, detailed layout |
| **pdfplumber** | Moderate | Excellent | Yes | Built on pdfminer.six | Active | Tables, coordinate-based extraction |
| **PyMuPDF (fitz)** | Very Fast | Good | Basic | C library (MuPDF) | Active | High-throughput, images |
| **PyMuPDF4LLM** | Very Fast | Excellent | Good | C library (MuPDF) | Active | LLM-optimized markdown output |
| **pypdfium2** | Blazing | Basic | No | C library (PDFium) | Active | Maximum speed, basic text |

### Detailed Assessment

**PyPDF (formerly PyPDF2)**
- Pure Python, zero external dependencies
- Good for simple text extraction and PDF manipulation (merge, split, encrypt)
- Fastest for straightforward documents, but limited layout understanding
- PyPDF2 has been merged back into the main PyPDF library
- Install: `pip install pypdf`

**pdfminer.six**
- Gold standard for detailed layout analysis
- Supports CJK languages and vertical writing
- Extracts text with position coordinates, font info, and page structure
- Slower than PyPDF but far more precise
- Install: `pip install pdfminer.six`

**pdfplumber**
- Built on top of pdfminer.six with a friendlier API
- Excellent table extraction capabilities built-in
- Provides character-level coordinate data
- Good balance of features and ease of use
- Install: `pip install pdfplumber`

**PyMuPDF / PyMuPDF4LLM**
- C-backed library, extremely fast (0.12s benchmark vs 1.29s for unstructured)
- PyMuPDF4LLM variant outputs clean markdown optimized for LLM consumption
- Cuts infrastructure costs by up to 250x compared to cloud-based parsing
- Supports text, images, and basic table extraction
- Install: `pip install pymupdf` / `pip install pymupdf4llm`

**pypdfium2**
- Fastest raw text extraction (0.003s benchmark)
- Based on Google's PDFium engine
- Best for high-throughput scenarios where layout fidelity is not critical
- Install: `pip install pypdfium2`

### Recommendation for O&G Project

**Primary: PyMuPDF4LLM** for speed and LLM-optimized output. **Secondary: pdfplumber** for documents requiring precise table extraction. Use PyMuPDF4LLM as the default first-pass parser and fall back to pdfplumber when tables are detected that need more precise extraction.

---

## 2. OCR Solutions for Scanned Documents

### Solution Comparison Matrix

| Solution | Type | Accuracy | Speed | Cost | Table Support | Languages | Best For |
|----------|------|----------|-------|------|---------------|-----------|----------|
| **Tesseract 5** | Open Source / Local | Good (90-95%) | Moderate | Free | Poor | 100+ | Budget-constrained, simple docs |
| **PaddleOCR v3** | Open Source / Local | Very Good (95%+) | Fast | Free | Good | 109 | Best open-source option |
| **AWS Textract** | Cloud API | Excellent (97%+) | Fast | $1.50/1K pages | Excellent | Limited | Tables, forms, AWS ecosystem |
| **Google Document AI** | Cloud API | Excellent (97%+) | Fast | $1.50/1K pages | Excellent | 200+ | Multi-language, GCP ecosystem |
| **Azure Document Intelligence** | Cloud API | Excellent (97%+) | Fast | $1.50/1K pages | Excellent | Many | Forms, custom models, Azure ecosystem |
| **Chandra (9B)** | Open Source VLM | Best (83.1 olmOCR-Bench) | 1.29 pg/s | ~$605/1M pages (GPU) | Good | 40+ | Complex layouts, degraded scans |
| **OlmOCR-2 (7.7B)** | Open Source VLM | Excellent (82.4) | 1.78 pg/s | ~$439/1M pages (GPU) | Good | English focus | Large-scale English digitization |
| **DeepSeek-OCR (3B)** | Open Source VLM | Good (75.7) | 4.65 pg/s | ~$168/1M pages (GPU) | Good | Many | High-throughput batch processing |
| **LightOn OCR (1B)** | Open Source VLM | Good (76.1) | 5.55 pg/s | ~$141/1M pages (GPU) | Good | Many | Cost-optimized, fine-tunable |

### Tesseract 5 (Open Source)

**Strengths:**
- Completely free, no licensing costs
- Mature ecosystem, well-documented
- Works offline, no network dependency
- Good for clean, well-formatted documents

**Weaknesses:**
- Struggles with complex layouts, tables, multi-column text
- Requires significant image preprocessing for poor scans
- No built-in table structure recognition
- Accuracy degrades sharply on noisy/skewed documents
- Requires multi-stage pipeline (detection + recognition)

**When to use:** Budget-constrained scenarios with clean, single-column documents.

### PaddleOCR v3 (Open Source, Baidu)

**Strengths:**
- Best open-source traditional OCR system (PP-OCRv5 improved accuracy by 13%)
- 109 language support in compact 0.9B model
- PP-StructureV3 for document layout analysis and table recognition
- PP-DocLayout-plus for multi-column, magazine, and newspaper layouts
- Converts results to Markdown and JSON
- Leads both open-source and closed-source on OmniDocBench benchmark
- 50,000+ GitHub stars

**Weaknesses:**
- PaddlePaddle framework dependency (not as mainstream as PyTorch)
- More complex setup than Tesseract
- GPU strongly recommended for production speed

**When to use:** When you need strong open-source OCR with table detection and can invest in setup complexity.

### AWS Textract (Cloud)

**Strengths:**
- Excellent accuracy on forms, tables, and structured documents
- AnalyzeDocument can answer queries over pages (2025 update)
- Supports superscripts, subscripts, rotated text (2025 update)
- Improved accuracy on low-resolution documents like faxes
- Confidence scores per word and field
- Async batch processing support
- Tight AWS ecosystem integration (S3, Lambda, SQS)

**Weaknesses:**
- Vendor lock-in to AWS
- Per-page pricing adds up at scale
- Limited language support compared to Google
- No on-premises deployment option

### Google Document AI (Cloud)

**Strengths:**
- 25 years of Google OCR research
- 200+ language support
- Pre-trained processors for invoices, receipts, contracts, tax forms
- Enterprise Document OCR with high accuracy
- Can use generative AI for extraction without training
- Integrates with BigQuery, Cloud Storage, Vertex AI
- $300 free credit for new customers

**Weaknesses:**
- Vendor lock-in to GCP
- Complex pricing structure
- Less form-specific than Textract

### Azure AI Document Intelligence (Cloud)

**Strengths:**
- Pre-built models for invoices, receipts, ID cards, tax forms, mortgage documents
- Custom model training (template models: free; neural models: $3/hr after 10 free hours)
- Free tier (F0) for testing
- Layout detection with tables, titles, paragraphs, selection marks
- Content Understanding (Nov 2025) expands to audio and video
- Good for organizations already on Azure

**Weaknesses:**
- Azure ecosystem dependency
- Custom model training can be expensive at scale

### Modern Open-Source VLMs (Vision Language Models)

The 2024-2025 generation of VLM-based OCR models represents a fundamental architectural shift from pipeline-based systems to end-to-end models. These models process entire pages in a single forward pass, understanding spatial relationships and preserving document structure. Key advantages over Tesseract:

- No multi-stage pipeline (detection, segmentation, recognition)
- Native table understanding
- Better handling of complex layouts
- Continuous improvement through model updates

**Chandra** is the current accuracy leader at 83.1 on olmOCR-Bench, excelling on complex layouts and degraded scans across 40+ languages.

**DeepSeek-OCR** offers the best speed/cost ratio at 4.65 pages/second and $168 per million pages on GPU.

---

## 3. Table Extraction from PDFs

This is critical for the O&G project since production reports, well permits, and regulatory filings are heavily table-based.

### Library Comparison

| Library | Table Detection | Complex Tables | Bordered Tables | Borderless Tables | Speed | Scanned PDFs |
|---------|----------------|---------------|-----------------|-------------------|-------|--------------|
| **Camelot** | Auto-detect | Good | Excellent (Lattice) | Good (Stream) | Moderate | No (text-only) |
| **Tabula-py** | Auto-detect | Poor | Good | Fair | Moderate | No (text-only) |
| **pdfplumber** | Manual | Excellent | Good | Good | Moderate | No (text-only) |
| **AWS Textract** | Auto-detect | Excellent | Excellent | Excellent | Fast | Yes |
| **Google Document AI** | Auto-detect | Excellent | Excellent | Excellent | Fast | Yes |
| **Docling (IBM)** | Auto-detect | Excellent (97.9%) | Excellent | Good | Moderate | Yes |
| **PaddleOCR PP-StructureV3** | Auto-detect | Very Good | Very Good | Good | Fast | Yes |

### Camelot

**Lattice mode**: Designed for tables with visible cell borders. Uses image processing to detect table boundaries. Produces the cleanest output for bordered tables.

**Stream mode**: For borderless tables. Uses whitespace patterns to identify column boundaries. More configurable but requires tuning.

```python
import camelot
# Lattice mode for bordered tables
tables = camelot.read_pdf('document.pdf', flavor='lattice')
# Stream mode for borderless tables
tables = camelot.read_pdf('document.pdf', flavor='stream')
# Export to DataFrame
df = tables[0].df
```

**Key limitation**: Only works on text-based (not scanned) PDFs. Cannot handle OCR scenarios.

### Tabula-py

- Java wrapper (requires JRE installed)
- Better table detection than Camelot in some borderless cases
- Parsing output quality is often inferior to Camelot
- Simpler API but less configurable

```python
import tabula
# Extract all tables
dfs = tabula.read_pdf("document.pdf", pages='all')
# Extract tables from specific area
df = tabula.read_pdf("document.pdf", area=(100, 0, 500, 800))
```

### pdfplumber

- Most flexible for complex table structures
- Does not auto-detect tables; requires manual configuration
- Character-level coordinate access for custom extraction logic
- Best when other tools fail on complex layouts

```python
import pdfplumber
with pdfplumber.open("document.pdf") as pdf:
    page = pdf.pages[0]
    table = page.extract_table()
    # Fine-grained control
    table = page.extract_table(table_settings={
        "vertical_strategy": "text",
        "horizontal_strategy": "lines"
    })
```

### Docling (IBM) TableFormer

- Trained on 1M+ tables from scientific, financial, and general datasets
- 97.9% accuracy on complex table extraction benchmarks
- Handles nested tables, merged cells, and irregular structures
- Works on both text-based and scanned PDFs
- Open source under Apache 2.0

### Recommendation for O&G Project

**Tier 1 (Primary)**: Use **Docling** or **PaddleOCR PP-StructureV3** for automatic table detection and extraction across both text and scanned PDFs. These handle the widest range of table types.

**Tier 2 (Fallback for text PDFs)**: Use **Camelot (Lattice)** for bordered production report tables, **pdfplumber** for complex borderless tables that need custom extraction logic.

**Tier 3 (Cloud backup)**: For high-value documents where local extraction fails, route to **AWS Textract** or **Google Document AI** for table extraction.

---

## 4. Handling Mixed PDF Types

Many O&G regulatory documents are mixed: some pages are digitally generated text, others are scanned paper documents within the same PDF. This requires automatic detection and routing.

### Detection Libraries

**ocr-detection**
- Analyzes PDF pages and classifies them as: `text`, `scanned`, `mixed`, or `empty`
- Returns per-page classification
- 5x faster performance with smart image extraction
- Install: `pip install ocr-detection`

```python
from ocr_detection import detect_ocr
result = detect_ocr("document.pdf")
# Returns: {"page_1": "text", "page_2": "scanned", "page_3": "mixed"}
```

**PreOCR**
- Open source detection and classification library
- Detects scanned vs digital PDFs
- Extracts native text instantly from digital pages
- Runs OCR only when required, reducing API costs and compute
- Install: `pip install preocr`

**PyMuPDF-based detection**
- Use `fitz` to check text content vs image content ratio per page
- If text extraction yields minimal/no text but large images exist, classify as scanned
- Custom but reliable approach

```python
import fitz
doc = fitz.open("document.pdf")
for page in doc:
    text = page.get_text()
    images = page.get_images()
    if len(text.strip()) < 50 and len(images) > 0:
        # Likely scanned page - needs OCR
        pass
    else:
        # Text-based page - direct extraction
        pass
```

### Processing Strategy for Mixed PDFs

```
1. Page Classification
   - Run ocr-detection or PyMuPDF heuristic on each page
   - Classify: text | scanned | mixed | empty

2. Route by Type
   - Text pages -> PyMuPDF4LLM / pdfplumber direct extraction
   - Scanned pages -> OCR pipeline (PaddleOCR or cloud OCR)
   - Mixed pages -> OCR pipeline (safest approach)
   - Empty pages -> Skip

3. Merge Results
   - Combine extracted content maintaining page order
   - Flag pages that required OCR (lower confidence baseline)
```

### OCRmyPDF

- Adds searchable text layer to scanned PDF pages
- Highly tolerant of mixed PDFs (born-digital + scanned)
- Uses Tesseract internally
- Preserves original PDF quality
- Can be used as a preprocessing step before text extraction
- Install: `pip install ocrmypdf`

```python
import ocrmypdf
ocrmypdf.ocr("input.pdf", "output.pdf",
              skip_text=True,  # Skip pages that already have text
              deskew=True,     # Fix rotated pages
              clean=True)      # Clean up scan artifacts
```

---

## 5. Excel/CSV Parsing

Many state regulatory sites provide data as downloadable Excel (.xlsx, .xls) or CSV files.

### Libraries and Strategies

| Library | Format Support | Memory | Speed | Features |
|---------|---------------|--------|-------|----------|
| **pandas** | xlsx, xls, csv | High (loads all) | Good | Full data analysis, dtype inference |
| **openpyxl** | xlsx only | Moderate | Moderate | Cell-level control, formatting, formulas |
| **xlrd** | xls (legacy) | Low | Fast | Read-only for old Excel format |
| **polars** | csv, xlsx | Low (lazy eval) | Very Fast | Modern alternative to pandas |
| **Dask** | csv, xlsx | Low (chunked) | Good | Distributed/parallel processing |

### pandas (Primary)

```python
import pandas as pd

# Read Excel (uses openpyxl backend for .xlsx)
df = pd.read_excel("report.xlsx", sheet_name="Production")

# Read CSV with type control
df = pd.read_csv("wells.csv", dtype={"API_NUMBER": str, "PRODUCTION": float})

# Handle multiple sheets
all_sheets = pd.read_excel("report.xlsx", sheet_name=None)  # Returns dict of DataFrames

# Chunked CSV reading for large files
for chunk in pd.read_csv("large_data.csv", chunksize=10000):
    process(chunk)
```

### Key Strategies for O&G Data

1. **Preserve string types for identifiers**: API numbers, well numbers, and permit numbers must be read as strings (not integers) to preserve leading zeros.
2. **Handle inconsistent headers**: State data often has inconsistent column naming. Use `header=None` and manual mapping.
3. **Multi-row headers**: Some state reports use 2-3 row headers. Use `header=[0,1]` for multi-level.
4. **Convert Excel to CSV first**: CSV parsing is 10-15x faster. Convert on ingest, then process CSV.
5. **Use PyArrow engine for CSVs**: `pd.read_csv(..., engine='pyarrow')` for significant speed improvement.
6. **Handle encoding issues**: Government files often use Windows-1252 or Latin-1 encoding. Try `encoding='utf-8'`, fall back to `encoding='latin-1'`.

### Poorly Structured Excel Files

Government Excel files are often poorly structured (merged cells, inconsistent formatting, data starting at different rows). Use openpyxl directly for fine-grained control:

```python
from openpyxl import load_workbook
wb = load_workbook("messy_report.xlsx", data_only=True)
ws = wb.active
# Find actual data start row by scanning for header patterns
for row in ws.iter_rows():
    if any("API" in str(cell.value or "") for cell in row):
        header_row = row
        break
```

---

## 6. HTML Table Extraction

Several state regulatory sites display data in HTML tables rather than downloadable files.

### Methods

**pandas.read_html() (Primary)**

```python
import pandas as pd

# Extract all tables from a URL or HTML string
tables = pd.read_html("https://state-site.gov/well-data")

# Filter by matching text in table
tables = pd.read_html(url, match="Production")

# Specify table by attributes
tables = pd.read_html(url, attrs={"id": "production-table"})

# Handle multi-level headers
tables = pd.read_html(url, header=[0, 1])
```

**BeautifulSoup + pandas (Complex cases)**

```python
from bs4 import BeautifulSoup
import pandas as pd
import requests

response = requests.get(url)
soup = BeautifulSoup(response.text, 'html.parser')

# Find specific table
table = soup.find('table', {'class': 'well-data'})

# Handle nested tables
for nested in table.find_all('table'):
    nested.decompose()  # Remove nested tables

# Convert to DataFrame
df = pd.read_html(str(table))[0]
```

### Strategies for Government Sites

1. **Dynamic content**: Many state sites use JavaScript to load tables. Use Playwright/Selenium to render first, then extract from rendered HTML.
2. **Pagination**: Tables are often paginated. Iterate through pages and concatenate results.
3. **Session-based access**: Some sites require form submissions or session cookies. Use `requests.Session()`.
4. **Rate limiting**: Add delays between requests (1-3 seconds) to avoid being blocked.

---

## 7. Document Classification Approaches

The O&G project must automatically classify unlabeled documents into types like: well permit, production report, completion report, inspection record, spacing order, plugging report, etc.

### Approach Comparison

| Approach | Accuracy | Setup Cost | Runtime Cost | Training Data Needed | Adaptability |
|----------|----------|-----------|-------------|---------------------|-------------|
| **Rule-based (regex/keyword)** | 70-85% | Low | Free | None | Manual updates |
| **Traditional ML (SVM/NB)** | 80-90% | Medium | Free | 100-500 per class | Retrain needed |
| **Fine-tuned BERT/RoBERTa** | 90-95% | High | Low (local GPU) | 200-1000 per class | Retrain needed |
| **Zero-shot LLM** | 80-90% | Very Low | Moderate (API) | None | Instant adaptation |
| **Few-shot LLM** | 85-93% | Low | Moderate (API) | 3-10 per class | Easy updates |
| **Fine-tuned small LLM** | 92-97% | High | Low (local) | 500+ per class | Retrain needed |

### Rule-Based Classification (Tier 1 - Fast & Free)

Good as a first pass before more expensive methods:

```python
DOCUMENT_PATTERNS = {
    "well_permit": ["application to drill", "permit to drill", "form w-1", "drilling permit"],
    "production_report": ["production report", "monthly production", "oil production", "gas production"],
    "completion_report": ["completion report", "well completion", "form 2"],
    "plugging_report": ["plugging report", "plug and abandon", "form w-3", "form 2a"],
    "inspection_record": ["inspection report", "well inspection", "field inspection"],
    "spacing_order": ["spacing order", "drilling unit", "pooling order"],
}

def classify_by_keywords(text):
    text_lower = text.lower()
    scores = {}
    for doc_type, keywords in DOCUMENT_PATTERNS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[doc_type] = score
    if scores:
        return max(scores, key=scores.get)
    return "unknown"
```

### Zero-Shot LLM Classification (Tier 2 - Flexible)

Using Claude or GPT for documents that rule-based can't classify:

```python
import anthropic

def classify_document_llm(text_excerpt, client):
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"""Classify this oil and gas regulatory document into one of these types:
            - well_permit
            - production_report
            - completion_report
            - plugging_report
            - inspection_record
            - spacing_order
            - other

            Document text (first 2000 chars):
            {text_excerpt[:2000]}

            Respond with JSON: {{"type": "...", "confidence": 0.0-1.0, "reasoning": "..."}}"""
        }]
    )
    return response
```

### Recommended Hybrid Approach

```
Document -> Rule-based classifier (fast, free)
  |
  +--> High confidence match -> Use classification
  |
  +--> Low/no confidence -> LLM zero-shot classifier (Claude)
         |
         +--> High confidence -> Use classification
         |
         +--> Low confidence -> Flag for human review
```

This approach minimizes API costs (only ~10-20% of documents need LLM classification) while maintaining high accuracy.

### Training a Custom Classifier (Phase 2)

Once enough labeled documents accumulate from the hybrid approach:
1. Export labeled dataset (document text + classification)
2. Fine-tune a small model (DistilBERT or similar) on the labeled data
3. Replace LLM calls with the fine-tuned model for cost savings
4. Continue routing low-confidence results to LLM as fallback

---

## 8. LLM-Based Document Understanding & Extraction

### Claude API PDF Support

Claude has native PDF support that is particularly well-suited for this project:

- **Direct PDF input**: Send PDFs directly to the API (no preprocessing needed)
- **Vision-based processing**: Each page is converted to an image internally
- **Limits**: 32MB per request, 100 pages per request
- **Token cost**: 1,500-3,000 tokens per page depending on density
- **No additional PDF fees**: Standard API pricing applies
- **Structured output**: Can return JSON matching a defined schema
- **Supported models**: All current Claude models

```python
import anthropic
import base64

client = anthropic.Anthropic()

# Send PDF directly
with open("production_report.pdf", "rb") as f:
    pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf_data,
                },
            },
            {
                "type": "text",
                "text": """Extract the following fields from this O&G document as JSON:
                {
                    "document_type": "string",
                    "state": "string",
                    "api_number": "string",
                    "operator_name": "string",
                    "well_name": "string",
                    "county": "string",
                    "date": "string",
                    "production_data": {
                        "oil_bbls": "number or null",
                        "gas_mcf": "number or null",
                        "water_bbls": "number or null"
                    },
                    "confidence": "number 0-1"
                }"""
            }
        ],
    }],
)
```

### Model Comparison for Document Extraction

| Model | Strengths | Cost (Input/Output per 1M tokens) | Best For |
|-------|-----------|------|----------|
| **Claude Sonnet** | Balance of speed/quality, structured output | $3 / $15 | Primary extraction workhorse |
| **Claude Haiku** | Fast, cheap | $0.25 / $1.25 | Classification, simple extraction |
| **Claude Opus** | Highest reasoning | $15 / $75 | Complex documents, ambiguous data |
| **GPT-4o** | Good vision, fast | $2.50 / $10 | Alternative to Claude Sonnet |
| **GPT-4o-mini** | Cheap, fast | $0.15 / $0.60 | Classification, simple tasks |
| **Gemini 1.5 Pro** | Long context (1M tokens) | $1.25 / $5 | Very large documents |

### Structured Output with Claude

Claude supports enforced structured output through tool definitions:

```python
# Define extraction schema as a tool
extraction_tool = {
    "name": "extract_well_data",
    "description": "Extract structured well data from O&G document",
    "input_schema": {
        "type": "object",
        "properties": {
            "api_number": {"type": "string", "description": "API well number (14-digit)"},
            "operator": {"type": "string"},
            "well_name": {"type": "string"},
            "production_oil_bbls": {"type": "number"},
            "production_gas_mcf": {"type": "number"},
        },
        "required": ["api_number"]
    }
}

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    tools=[extraction_tool],
    tool_choice={"type": "tool", "name": "extract_well_data"},
    messages=[...]
)
```

### When to Use LLMs vs Traditional Extraction

| Scenario | Approach | Reasoning |
|----------|----------|-----------|
| Standardized form with fixed layout | Template/regex | Cheaper, faster, reliable |
| Structured table in text PDF | pdfplumber/Camelot | No API cost, deterministic |
| Unstructured narrative text | LLM | Only way to understand context |
| Scanned document needing interpretation | LLM (via vision) | Can read directly from image |
| Classification of unknown document | LLM (zero-shot) | No training data needed |
| High-value extraction needing verification | LLM + human review | Confidence scoring built in |

---

## 9. Structured Data Extraction from Unstructured Documents

### Multi-Layer Extraction Strategy

**Layer 1: Pattern Matching (Regex)**
Fast, free, deterministic. Ideal for well-known patterns in O&G documents.

```python
import re

PATTERNS = {
    "api_number": r'\b\d{2}-\d{3}-\d{5}(?:-\d{2}-\d{2})?\b',
    "permit_number": r'(?:Permit|Permit No\.?|Permit #)\s*[:.]?\s*(\d+)',
    "operator": r'(?:Operator|Lessee)\s*[:.]?\s*([A-Z][A-Za-z\s&.,]+?)(?:\n|$)',
    "well_name": r'(?:Well Name|Well)\s*[:.]?\s*(.+?)(?:\n|$)',
    "county": r'(?:County)\s*[:.]?\s*([A-Za-z\s]+?)(?:\n|,|$)',
    "date": r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
    "production_oil": r'(?:Oil|Crude)\s*(?:Production|Prod\.?)?\s*[:.]?\s*([\d,.]+)\s*(?:BBL|bbl|Bbls?)',
    "production_gas": r'(?:Gas)\s*(?:Production|Prod\.?)?\s*[:.]?\s*([\d,.]+)\s*(?:MCF|mcf|Mcf)',
}

def extract_by_patterns(text):
    results = {}
    for field, pattern in PATTERNS.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        results[field] = matches[0] if matches else None
    return results
```

**Layer 2: Named Entity Recognition (NER)**
For extracting entities that regex can't reliably capture.

- **spaCy**: Fast, efficient NER with custom training support
- **Hugging Face Transformers**: Pre-trained NER models
- Consider fine-tuning on O&G entity types (operator names, well identifiers, field names)

**Layer 3: Template Matching**
For documents with known layouts (specific state forms):

```python
# Define extraction zones by document type and state
TEMPLATES = {
    "TX_W1": {  # Texas Form W-1 (Drilling Permit)
        "api_number": {"page": 1, "bbox": (x1, y1, x2, y2)},
        "operator": {"page": 1, "bbox": (x1, y1, x2, y2)},
        "well_name": {"page": 1, "bbox": (x1, y1, x2, y2)},
    }
}
```

**Layer 4: LLM Extraction**
For documents where layers 1-3 fail or produce low-confidence results. See Section 8 above.

**Layer 5: LangExtract (Google, 2025)**
Open-source library for extracting structured information from unstructured text using LLMs with precise source grounding and interactive visualization. Useful for converting free-form regulatory text into structured data.

### Extraction Pipeline

```
Document Text
    |
    v
Layer 1: Regex pattern matching -> Extract known patterns
    |
    v
Layer 2: NER -> Extract entities regex missed
    |
    v
Layer 3: Template matching (if document type known) -> Extract positional data
    |
    v
Layer 4: LLM extraction (if confidence < threshold) -> Fill gaps
    |
    v
Merge & Validate -> Resolve conflicts, compute confidence
    |
    v
Structured Output (JSON)
```

---

## 10. Handling Poor Quality Scans, Rotated Pages, Multi-Column Layouts

### Image Preprocessing Pipeline

For scanned documents, preprocessing can boost OCR accuracy by 10-30%:

```python
from PIL import Image, ImageFilter, ImageEnhance
import cv2
import numpy as np

def preprocess_for_ocr(image_path):
    img = cv2.imread(image_path)

    # 1. Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Deskew (fix rotation)
    coords = np.column_stack(np.where(gray > 0))
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    rotated = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)

    # 3. Noise removal
    denoised = cv2.fastNlMeansDenoising(rotated)

    # 4. Binarization (Otsu's method)
    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 5. Sharpening
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(binary, -1, kernel)

    return sharpened
```

### Rotation Detection and Correction

**Tesseract OSD (Orientation and Script Detection):**
```python
import pytesseract
from PIL import Image

osd = pytesseract.image_to_osd(Image.open("page.png"))
# Returns: Page number, orientation (degrees), rotation confidence, script
```

**OCRmyPDF auto-rotation:**
```bash
ocrmypdf --rotate-pages --deskew input.pdf output.pdf
```

**AWS Textract**: 2025 update added native support for rotated text detection without preprocessing.

### Multi-Column Layout Handling

| Tool | Multi-Column Support | Approach |
|------|---------------------|----------|
| **PaddleOCR PP-DocLayout-plus** | Excellent | Layout detection model trained on multi-column docs |
| **Docling Heron model** | Good | Layout analysis with reading order recovery |
| **Unstructured (hi_res)** | Good | Computer vision + OCR combination |
| **Tesseract** | Poor | No layout awareness; columns get merged |
| **AWS Textract** | Good | Layout detection built-in |

**Recommended approach:**
1. Run layout detection (PaddleOCR PP-DocLayout-plus or Docling Heron) to identify text regions and reading order
2. Extract text from each region independently
3. Merge text following detected reading order
4. For tables spanning columns, use table-specific extraction

### Minimum Scan Quality Requirements

- **Resolution**: 300 DPI minimum for text, 600 DPI for fine print
- **Color depth**: Grayscale sufficient for most O&G docs; color for maps/diagrams
- **Format**: TIFF or PNG preferred (lossless); JPEG acceptable at quality 85+
- **Skew**: Less than 5 degrees for best results; auto-deskew above that

---

## 11. Cost Analysis: Local vs Cloud OCR

### Pricing Comparison (per 1,000 pages)

| Solution | Basic Text | Tables | Forms | Notes |
|----------|-----------|--------|-------|-------|
| **Tesseract** | $0 | N/A | N/A | Free but compute costs for server |
| **PaddleOCR** | $0 | $0 | $0 | Free but GPU recommended |
| **Self-hosted VLM (H100)** | $0.14-$0.61 | Included | Included | Depends on model |
| **AWS Textract** | $1.50 | $15.00 | $50.00 | Both charges apply if combined |
| **Google Document AI** | $1.50 | $1.50 | $1.50 | Simpler pricing |
| **Azure Doc Intelligence** | $1.50 | Included | Included | Layout model includes tables |
| **Claude API (vision)** | ~$4.50-$9.00 | Included | Included | 1500-3000 tokens/page |

### Detailed AWS Textract Pricing

| Feature | First 1M pages/month | Over 1M pages/month |
|---------|----------------------|---------------------|
| Detect Document Text | $1.50/1K | $0.60/1K |
| Analyze Document (Tables) | $15.00/1K | $10.00/1K |
| Analyze Document (Forms) | $50.00/1K | $40.00/1K |
| Queries | $15.00/1K | N/A |

**Free tier**: 1,000 pages/month for 3 months (new accounts).

### Detailed Google Document AI Pricing

| Volume | Cost per 1,000 pages |
|--------|---------------------|
| First 1,000 units/month | Free |
| 1,001 - 5,000,000 | $1.50/1K |
| Over 5,000,000 | $0.60/1K (40% discount) |

**New customer credit**: $300 in free credit.

### Cost Projection for O&G Project

Assuming **100,000 pages/month** processing volume:

| Solution | Monthly Cost | Annual Cost | Notes |
|----------|-------------|-------------|-------|
| Tesseract (self-hosted) | ~$50 (compute) | ~$600 | Server costs only; lower accuracy |
| PaddleOCR (GPU server) | ~$200 (GPU) | ~$2,400 | Good accuracy, GPU rental |
| Self-hosted VLM (A100) | ~$60 | ~$720 | Best cost/accuracy ratio at scale |
| AWS Textract (text only) | $150 | $1,800 | Good for text extraction |
| AWS Textract (tables) | $1,500 | $18,000 | Expensive for table extraction |
| Google Document AI | $150 | $1,800 | Simpler pricing, good features |
| Claude API (all pages) | $450-$900 | $5,400-$10,800 | Best understanding, highest cost |

### Recommended Cost Strategy

```
Tier 1: Free/Cheap (80% of pages)
  - PyMuPDF4LLM for text PDFs (free)
  - PaddleOCR for scanned pages (free, GPU cost only)

Tier 2: Moderate (15% of pages)
  - Cloud OCR (Textract/Document AI) for complex tables
  - Cost: ~$1.50/1K pages

Tier 3: Premium (5% of high-value pages)
  - Claude API for complex/ambiguous documents
  - Document classification and understanding
  - Cost: ~$4.50-$9.00/1K pages
```

**Estimated blended cost**: ~$0.20-$0.50 per 1,000 pages (vs $1.50+ for all-cloud).

---

## 12. Confidence Scoring for Extracted Data

### Confidence Score Architecture

Confidence scoring is critical for the O&G project because the PRD explicitly states: "Data quality is inherently poor -- the tool needs to surface confidence, not pretend data is clean."

### Multi-Level Confidence Scoring

**Level 1: OCR Confidence (Character/Word Level)**
- Tesseract and cloud OCR services provide per-character and per-word confidence
- Typical threshold: words below 80% confidence flagged for review
- Aggregate page-level OCR confidence from word-level scores

**Level 2: Extraction Confidence (Field Level)**
- How certain the system is that it extracted the right value for each field
- Based on: pattern match strength, positional consistency, value validation

**Level 3: Document Confidence (Document Level)**
- Overall confidence that the document was correctly classified and extracted
- Aggregate of field-level confidences weighted by field importance

### Implementation Approach

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ExtractedField:
    field_name: str
    value: any
    confidence: float  # 0.0 - 1.0
    source: str  # "regex", "ocr", "llm", "template"
    ocr_confidence: Optional[float] = None  # Raw OCR confidence if applicable

    @property
    def needs_review(self) -> bool:
        return self.confidence < 0.85

@dataclass
class ExtractionResult:
    document_type: str
    classification_confidence: float
    fields: list[ExtractedField]

    @property
    def overall_confidence(self) -> float:
        if not self.fields:
            return 0.0
        return sum(f.confidence for f in self.fields) / len(self.fields)

    @property
    def fields_needing_review(self) -> list[ExtractedField]:
        return [f for f in self.fields if f.needs_review]
```

### Confidence Calibration

- Ensure 90% confidence means approximately 90% actual accuracy
- Track validation outcomes at different confidence levels
- Recalibrate regularly as more data is processed
- Use ensemble methods: run multiple extractors and measure agreement

### Confidence Thresholds for O&G Data

| Field Type | Auto-accept Threshold | Review Threshold | Reject Threshold |
|-----------|----------------------|-----------------|-----------------|
| API Number | >= 0.95 | 0.70 - 0.95 | < 0.70 |
| Operator Name | >= 0.90 | 0.60 - 0.90 | < 0.60 |
| Production Values | >= 0.90 | 0.70 - 0.90 | < 0.70 |
| Dates | >= 0.90 | 0.65 - 0.90 | < 0.65 |
| Well Location/Coords | >= 0.95 | 0.80 - 0.95 | < 0.80 |
| Document Classification | >= 0.85 | 0.50 - 0.85 | < 0.50 |

---

## 13. Batch Processing Strategies

### Architecture Overview

```
                    ┌─────────────┐
                    │  File Watcher│
                    │  / Ingestion │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Job Queue   │
                    │  (Redis/RMQ) │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼────┐ ┌────▼─────┐ ┌────▼─────┐
        │ Worker 1  │ │ Worker 2  │ │ Worker N  │
        │           │ │           │ │           │
        │ Classify  │ │ Classify  │ │ Classify  │
        │ Extract   │ │ Extract   │ │ Extract   │
        │ Validate  │ │ Validate  │ │ Validate  │
        └─────┬────┘ └────┬─────┘ └────┬─────┘
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────▼──────┐
                    │  Result Store│
                    │  (Database)  │
                    └─────────────┘
```

### Celery-Based Pipeline (Recommended for Python)

```python
from celery import Celery, chain

app = Celery('document_processor', broker='redis://localhost:6379')

@app.task(bind=True, max_retries=3)
def classify_document(self, document_id):
    """Step 1: Classify document type"""
    doc = load_document(document_id)
    classification = classify(doc)
    return {"document_id": document_id, "type": classification}

@app.task(bind=True, max_retries=3)
def extract_data(self, classification_result):
    """Step 2: Extract data based on document type"""
    doc_id = classification_result["document_id"]
    doc_type = classification_result["type"]
    data = extract(doc_id, doc_type)
    return {"document_id": doc_id, "data": data}

@app.task
def store_results(extraction_result):
    """Step 3: Store extracted data"""
    save_to_database(extraction_result)

# Pipeline execution
def process_document(document_id):
    pipeline = chain(
        classify_document.s(document_id),
        extract_data.s(),
        store_results.s()
    )
    pipeline.apply_async()

# Batch processing
def process_batch(document_ids):
    from celery import group
    jobs = group(
        chain(
            classify_document.s(doc_id),
            extract_data.s(),
            store_results.s()
        ) for doc_id in document_ids
    )
    jobs.apply_async()
```

### Processing Pipeline Stages

```
Stage 1: Ingestion
  - Download document from source
  - Store original in document store (S3/filesystem)
  - Record provenance (source URL, download time, state, etc.)
  - Create job record in database

Stage 2: Preprocessing
  - Detect PDF type (text/scanned/mixed) per page
  - Run image preprocessing on scanned pages (deskew, denoise, binarize)
  - Split large documents if needed

Stage 3: Text Extraction
  - Text pages: PyMuPDF4LLM direct extraction
  - Scanned pages: PaddleOCR or cloud OCR
  - Tables: Docling or Camelot/pdfplumber
  - Merge all extracted content

Stage 4: Classification
  - Rule-based classifier (first pass)
  - LLM classifier (fallback for uncertain documents)
  - Record classification confidence

Stage 5: Data Extraction
  - Run extraction pipeline (regex -> NER -> template -> LLM)
  - Compute field-level confidence scores
  - Validate extracted data (format checks, range checks, cross-field validation)

Stage 6: Storage & Indexing
  - Store structured data in database
  - Index for search
  - Flag low-confidence extractions for review
  - Update processing status
```

### Scaling Considerations

| Scale | Architecture | Workers | Throughput |
|-------|-------------|---------|------------|
| < 1K docs/day | Single server, Celery | 2-4 | Sufficient |
| 1K-10K docs/day | Multi-server, Celery | 8-16 | Good |
| 10K-100K docs/day | Distributed, Kubernetes | 32+ | High |
| 100K+ docs/day | Cloud-native (Lambda/Cloud Functions) | Auto-scale | Very High |

### Priority Queue Strategy

For the O&G project, implement priority-based processing:

1. **High priority**: User-requested specific documents (targeted search)
2. **Medium priority**: New documents from monitored state sites
3. **Low priority**: Batch re-processing of existing documents with improved models

### Error Handling & Retry Strategy

```python
RETRY_CONFIG = {
    "max_retries": 3,
    "retry_backoff": True,
    "retry_backoff_max": 300,  # 5 minutes max
    "retry_jitter": True,
}

# Dead letter queue for permanent failures
@app.task(bind=True, **RETRY_CONFIG)
def process_document(self, doc_id):
    try:
        result = do_processing(doc_id)
        return result
    except TransientError:
        self.retry(countdown=60)
    except PermanentError:
        send_to_dead_letter_queue(doc_id)
        raise
```

---

## 14. Integrated Document Processing Frameworks

### Framework Comparison

These are higher-level frameworks that combine multiple capabilities (OCR, layout analysis, table extraction, etc.) into unified pipelines.

| Framework | OCR | Tables | Layout | LLM-Ready | License | Maturity |
|-----------|-----|--------|--------|-----------|---------|----------|
| **Docling (IBM)** | Yes | Excellent (97.9%) | Yes (Heron) | Yes (Markdown/JSON) | Apache 2.0 | High (37K+ stars) |
| **Unstructured** | Yes | Good | Yes (hi_res) | Yes (elements) | Apache 2.0 | High |
| **LlamaParse** | Yes | Good | Yes | Yes (RAG-optimized) | Proprietary (free tier) | Medium |
| **PaddleOCR/PaddleX** | Yes | Very Good | Yes (PP-DocLayout) | Yes (Markdown/JSON) | Apache 2.0 | High (50K+ stars) |

### Docling (IBM) - Recommended Primary Framework

**Key features:**
- Supports PDF, DOCX, PPTX, XLSX, HTML, and more
- TableFormer model (1M+ training tables, 97.9% accuracy)
- Heron layout model (Dec 2025) for faster PDF parsing
- Granite-Docling-258M VLM for single-pass document processing
- Outputs to Markdown and JSON
- Active development (100+ releases since Aug 2025)

```python
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("production_report.pdf")

# Get markdown output
markdown = result.document.export_to_markdown()

# Get structured tables
for table in result.document.tables:
    df = table.export_to_dataframe()
```

### Unstructured

**Key features:**
- Unified `partition()` function that auto-detects file type
- Multiple strategies: fast, hi_res, ocr_only
- Returns typed elements (Title, NarrativeText, Table, ListItem, etc.)
- Good for RAG pipeline integration
- Enterprise platform available for production

```python
from unstructured.partition.pdf import partition_pdf

elements = partition_pdf(
    "document.pdf",
    strategy="hi_res",  # Uses CV + OCR
    infer_table_structure=True
)

for element in elements:
    print(f"Type: {type(element).__name__}")
    print(f"Text: {element.text[:100]}")
```

---

## 15. Oil & Gas Document Types Reference

Understanding the document types is essential for building the classification system.

### Primary Document Types

| Document Type | Description | Key Data Points | Common Formats |
|--------------|-------------|-----------------|----------------|
| **Drilling Permit (W-1)** | Application to drill a new well | API#, operator, location, proposed depth, target formation | PDF (form), HTML |
| **Completion Report (Form 2)** | Report after well is drilled and completed | API#, completion date, perforations, initial production | PDF (form) |
| **Production Report** | Monthly/annual production volumes | API#, oil BBL, gas MCF, water BBL, producing days | PDF, Excel, CSV, HTML |
| **Plugging Report (W-3/Form 4)** | Report when well is plugged and abandoned | API#, plug date, cement volumes, depth intervals | PDF (form) |
| **Inspection Record** | Field inspection results | API#, inspection date, violations, compliance status | PDF |
| **Spacing Order** | Regulatory order defining drilling units | Section/Township/Range, spacing requirements, operators | PDF |
| **P-5 Organization Report** | Texas-specific operator registration | Operator name, P-5 number, contact info | PDF, HTML |
| **Well Plat** | Survey map showing well location | Section/Township/Range, coordinates, distances | PDF (map) |
| **Driller's Log** | Geological log from drilling | Depth intervals, formation names, lithology | PDF, image |
| **Certificate of Compliance** | Regulatory compliance certification | Operator, well, compliance status | PDF |

### Key Identifiers in O&G Documents

| Identifier | Format | Description |
|-----------|--------|-------------|
| **API Number** | XX-XXX-XXXXX(-XX-XX) | American Petroleum Institute well identifier (state-county-well-sidetrack-completion) |
| **Permit Number** | Varies by state | State-issued drilling permit number |
| **Lease Number** | Varies | Identifies the mineral lease |
| **Operator Number** | Varies by state | State-assigned operator identifier |
| **P-5 Number** | Texas-specific | Organization report number |
| **RRC District** | 01-12 | Texas Railroad Commission district |

### State-Specific Variations

| State | Regulatory Body | Key Document Differences |
|-------|----------------|------------------------|
| **Texas** | Railroad Commission (RRC) | Forms W-1, W-2, P-5; largest document volume |
| **Oklahoma** | Corporation Commission (OCC) | Spacing/pooling orders are major document type |
| **North Dakota** | Industrial Commission (NDIC) | Confidential period for new well data |
| **New Mexico** | Oil Conservation Division (OCD) | C-101, C-103, C-104 forms |
| **Colorado** | COGCC | Location assessment, COGIS database |
| **Louisiana** | SONRIS | Well serial numbers instead of API in some contexts |
| **Wyoming** | WOGCC | APD (Application for Permit to Drill) |
| **Pennsylvania** | DEP | Unconventional well reporting requirements |

---

## 16. Recommendations for This Project

### Recommended Technology Stack

```
PDF Text Extraction:
  Primary:     PyMuPDF4LLM (speed + LLM-optimized output)
  Table focus:  pdfplumber (complex tables in text PDFs)

OCR (Scanned Documents):
  Primary:     PaddleOCR v3 / PP-StructureV3 (free, excellent accuracy)
  Fallback:    AWS Textract (for complex tables in scans)
  Premium:     Claude API vision (for ambiguous/complex documents)

Mixed PDF Detection:
  Primary:     ocr-detection library
  Alternative: PyMuPDF heuristic (text vs image ratio)
  Preprocessing: OCRmyPDF (add text layer to scans)

Table Extraction:
  Primary:     Docling TableFormer (97.9% accuracy, handles scans)
  Secondary:   Camelot (lattice mode for bordered tables)
  Fallback:    pdfplumber (custom extraction for edge cases)
  Cloud:       AWS Textract AnalyzeDocument (Tables)

Document Classification:
  Tier 1:      Rule-based keyword matching (fast, free)
  Tier 2:      Claude Haiku zero-shot classification (flexible)
  Tier 3:      Fine-tuned classifier (after labeled data accumulates)

Data Extraction:
  Layer 1:     Regex patterns (API numbers, dates, known formats)
  Layer 2:     spaCy NER (entity extraction)
  Layer 3:     Template matching (known state forms)
  Layer 4:     Claude Sonnet structured extraction (complex docs)

Excel/CSV:
  Primary:     pandas (with openpyxl backend)
  Large files: polars or pandas with chunking

HTML Tables:
  Primary:     pandas.read_html()
  Complex:     BeautifulSoup + pandas

Batch Processing:
  Queue:       Celery + Redis
  Pipeline:    Chain tasks (classify -> extract -> store)
  Storage:     PostgreSQL + S3 (documents)

Confidence Scoring:
  Multi-level: OCR confidence + extraction confidence + document confidence
  Thresholds:  Auto-accept (>0.90), review (0.70-0.90), reject (<0.70)
```

### Implementation Phases

**Phase 1: Core Pipeline (Weeks 1-3)**
- PyMuPDF4LLM for text PDF extraction
- pdfplumber for table extraction from text PDFs
- ocr-detection for page type classification
- PaddleOCR for scanned page OCR
- Rule-based document classification
- Regex-based data extraction for known patterns
- pandas for Excel/CSV/HTML parsing
- Basic confidence scoring

**Phase 2: Intelligence Layer (Weeks 4-6)**
- Claude API integration for document classification fallback
- Claude API for structured data extraction from complex documents
- Docling integration for advanced table extraction
- NER with spaCy for entity extraction
- Confidence calibration and threshold tuning

**Phase 3: Scale & Optimize (Weeks 7-9)**
- Celery-based batch processing pipeline
- Priority queue for different processing needs
- Fine-tuned classifier from accumulated labeled data
- Template matching for known state forms
- Error handling, retry logic, dead letter queues
- Monitoring and alerting

**Phase 4: Continuous Improvement (Ongoing)**
- Human-in-the-loop for low-confidence corrections
- Model retraining from corrections
- New state form templates
- Performance optimization
- Cost optimization (shift more to local processing)

### Key Technical Decisions

1. **PyMuPDF4LLM over pdfminer/PyPDF2**: 10x faster, better LLM integration, good enough layout analysis for most O&G documents.

2. **PaddleOCR over Tesseract**: Significantly better accuracy on complex layouts, built-in table and layout detection, 109 language support, and actively maintained with major 2025 updates.

3. **Hybrid classification (rule-based + LLM)**: Keeps costs low (80% of documents classified for free) while maintaining high accuracy on edge cases.

4. **Multi-layer extraction**: Regex first (free, fast), LLM last (expensive, powerful). Only escalate when confidence is low.

5. **Docling for tables**: 97.9% accuracy on complex tables beats all pure-Python alternatives. Worth the dependency for production report extraction.

6. **Claude Sonnet for extraction**: Best balance of cost and quality for structured data extraction from complex O&G documents. Native PDF support eliminates OCR preprocessing.

7. **Celery for batch processing**: Proven Python task queue, easy to scale, good error handling, supports priority queues.

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| OCR accuracy on old scans | Multi-tier approach: PaddleOCR -> Textract -> Claude vision |
| Table extraction failures | Fallback chain: Docling -> Camelot -> pdfplumber -> Claude |
| Document classification errors | Hybrid approach + human review for low confidence |
| API cost overruns | Local processing first, cloud only for escalation |
| Government site changes | Automated monitoring, adapter pattern per state |
| Data quality issues | Confidence scoring, validation rules, human review queue |

---

## Sources

### PDF Text Extraction
- [Comparing 6 Frameworks for Rule-based PDF parsing](https://www.ai-bites.net/comparing-6-frameworks-for-rule-based-pdf-parsing/)
- [I Tested 7 Python PDF Extractors (2025 Edition)](https://onlyoneaman.medium.com/i-tested-7-python-pdf-extractors-so-you-dont-have-to-2025-edition-c88013922257)
- [py-pdf/benchmarks on GitHub](https://github.com/py-pdf/benchmarks)
- [Comparative Study of PDF Parsing Tools](https://arxiv.org/html/2410.09871v1)
- [pdfplumber on GitHub](https://github.com/jsvine/pdfplumber)
- [PyMuPDF4LLM Documentation](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/)
- [Best Python PDF to Text Parser Libraries: 2026 Evaluation](https://unstract.com/blog/evaluating-python-pdf-to-text-libraries/)

### OCR Solutions
- [OCR with Tesseract, Amazon Textract, and Google Document AI: Benchmarking](https://link.springer.com/article/10.1007/s42001-021-00149-1)
- [Comparing Top 6 OCR Models in 2025](https://www.marktechpost.com/2025/11/02/comparing-the-top-6-ocr-optical-character-recognition-models-systems-in-2025/)
- [7 Best Open-Source OCR Models 2025: Benchmarks & Cost Comparison](https://www.e2enetworks.com/blog/complete-guide-open-source-ocr-models-2025)
- [Is Tesseract Still the Best Open-Source OCR in 2026?](https://www.koncile.ai/en/ressources/is-tesseract-still-the-best-open-source-ocr)
- [OCR Technology in 2026: How AI and LLMs Changed Everything](https://photes.io/blog/posts/ocr-research-trend)

### Table Extraction
- [Best Python Libraries to Extract Tables From PDF in 2026](https://unstract.com/blog/extract-tables-from-pdf-python/)
- [Camelot Wiki: Comparison with other libraries](https://github.com/camelot-dev/camelot/wiki/Comparison-with-other-PDF-Table-Extraction-libraries-and-tools)
- [Camelot Documentation](https://camelot-py.readthedocs.io/)

### Document Classification
- [Large Language Models for Text Classification: Zero-Shot to Instruction-Tuning](https://journals.sagepub.com/doi/10.1177/00491241251325243)
- [Document Classification: End-to-End ML Workflow 2026](https://labelyourdata.com/articles/document-classification)
- [Zero-Shot Classification with Granite (IBM)](https://www.ibm.com/think/tutorials/zero-shot-classification)
- [LLMs in Document Intelligence: Comprehensive Survey](https://dl.acm.org/doi/10.1145/3768156)

### LLM Document Processing
- [Claude API PDF Support](https://platform.claude.com/docs/en/build-with-claude/pdf-support)
- [Claude Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Best LLM Models for Document Processing 2025](https://algodocs.com/best-llm-models-for-document-processing-in-2025/)
- [Claude vs GPT vs Gemini for Invoice Extraction](https://www.koncile.ai/en/ressources/claude-gpt-or-gemini-which-is-the-best-llm-for-invoice-extraction)

### Integrated Frameworks
- [Docling on GitHub](https://github.com/docling-project/docling)
- [IBM Granite-Docling Announcement](https://www.ibm.com/new/announcements/granite-docling-end-to-end-document-conversion)
- [PDF Extraction Benchmark 2025: Docling vs Unstructured vs LlamaParse](https://procycons.com/en/blogs/pdf-data-extraction-benchmark/)
- [Unstructured on GitHub](https://github.com/Unstructured-IO/unstructured)
- [LlamaParse by LlamaIndex](https://www.llamaindex.ai/llamaparse)
- [PaddleOCR on GitHub](https://github.com/PaddlePaddle/PaddleOCR)

### Cloud OCR Pricing
- [AWS Textract Pricing](https://aws.amazon.com/textract/pricing/)
- [Google Document AI Pricing](https://cloud.google.com/document-ai/pricing)
- [Azure Document Intelligence Pricing](https://azure.microsoft.com/en-us/pricing/details/document-intelligence/)
- [OCR APIs Pricing: Free vs Paid 2025](https://www.mindee.com/blog/ocr-api-pricing-free-vs-paid)

### Batch Processing & Architecture
- [OCR Batch Workflows: Scalable Text Extraction with ZenML](https://www.zenml.io/blog/ocr-batch-workflows-scalable-text-extraction-with-zenml)
- [Building a Scalable OCR Pipeline (HealthEdge)](https://healthedge.com/resources/blog/building-a-scalable-ocr-pipeline-technical-architecture-behind-healthedge-s-document-processing-platform)
- [End-to-End Distributed PDF Processing Pipeline](https://www.daft.ai/blog/end-to-end-distributed-pdf-processing-pipeline)
- [Production-Ready Data Pipelines for LLMs](https://medium.com/techthync/production-ready-data-pipelines-scaling-pdf-document-extraction-for-llms-9d975bc31213)

### Confidence Scoring
- [Best Confidence Scoring Systems 2026](https://www.extend.ai/resources/best-confidence-scoring-systems-document-processing)
- [OCR Confidence Scores as Proxy for Quality (ICDAR 2023)](https://dl.acm.org/doi/10.1007/978-3-031-41734-4_7)
- [Azure Document Intelligence Accuracy and Confidence](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/accuracy-confidence)

### Structured Data Extraction
- [Google LangExtract on GitHub](https://github.com/google/langextract)
- [Structured Data Extraction with LLMs (Arize AI)](https://arize.com/blog-course/structured-data-extraction-openai-function-calling/)
- [LlamaIndex Structured Data Extraction](https://docs.llamaindex.ai/en/stable/use_cases/extraction/)

### Oil & Gas Document Types
- [Texas RRC Oil and Gas Well Records](https://www.rrc.texas.gov/oil-and-gas/research-and-statistics/obtaining-commission-records/oil-and-gas-well-records/)
- [New York State Oil, Gas and Solution Salt Mining Forms](https://dec.ny.gov/environmental-protection/oil-gas/regulatory-program-forms)

### Image Preprocessing
- [How to Improve OCR Accuracy for Scanned Documents](https://pdf-lab.com/blogs/how-to-improve-ocr-accuracy-for-scanned-documents)
- [Tesseract: Improving Quality of Output](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html)
- [OCRmyPDF Documentation](https://ocrmypdf.readthedocs.io/en/latest/introduction.html)
