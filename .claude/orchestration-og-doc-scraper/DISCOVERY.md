# Oil & Gas Document Scraper - Discovery Document

**Created**: 2026-03-27
**Status**: Complete
**Rounds of Q&A**: 4

---

## 1. Scope & Coverage

**D1: Which states to support?**
A: All major states (Tier 1 + Tier 2) — 10 states total:
- Tier 1: Texas, New Mexico, North Dakota, Oklahoma, Colorado
- Tier 2: Wyoming, Louisiana, Pennsylvania, California, Alaska

**D2: Which document types to scrape?**
A: All document types — production reports, well permits, completion reports, spacing/pooling orders, plugging reports, inspection records, incident reports.

**D3: How often does scraping need to run?**
A: On-demand only. User triggers scrapes from the dashboard when they need data. No scheduled/automated runs.

---

## 2. Technical Stack

**D4: Tech stack preference?**
A: Python + Next.js. Python backend (Scrapy + Playwright for scraping, FastAPI for API) and Next.js frontend for the dashboard.

**D5: AI/OCR budget?**
A: Free/local only. No paid API services. PaddleOCR (~90% accuracy) as the sole OCR engine. No cloud fallback.

**D6: Deployment target?**
A: Local machine. Docker Compose for easy setup. Runs on the coworker's laptop/desktop.

**D7: Authentication?**
A: None. Internal tool, no auth needed. Anyone with local access can use it.

---

## 3. Data & Identifiers

**D8: Primary search identifiers?**
A: All of them:
- API number (14-digit)
- Operator name
- Lease/well name
- Geographic (county/basin)

**D9: How to handle scanned/image PDFs?**
A: Must handle all scans. PaddleOCR is the sole engine — no cloud fallback. Accept ~90% accuracy on scanned documents.

**D10: Data quality strategy?**
A: Strict — reject uncertain data. Only store data above a confidence threshold. Low-confidence documents go to a review queue in the dashboard for manual verification.

**D11: Source document storage?**
A: Store originals organized into labeled folders by state/operator/type, PLUS extract and store structured data. Users can browse original files and verify against source.

---

## 4. Dashboard & UX

**D12: Dashboard primary workflow?**
A: Search/browse + interactive map. Search bar with filters (state, operator, type, date), click through to documents and extracted data, plus an interactive map with well-level pins.

**D13: Map detail level?**
A: Well-level pins. Each well plotted by lat/long coordinates. Click to see well details, associated documents, and production data.

**D14: How to trigger scraping?**
A: Dashboard button. "Scrape [State]" or "Scrape All" buttons in the web UI. Show real-time progress.

**D15: Where do rejected/low-confidence docs go?**
A: Review queue in the dashboard. A "Needs Review" tab where users can manually verify, approve, or correct extracted data from low-confidence documents.

---

## 5. Users & Polish

**D16: Who will use this?**
A: 1-2 people (the coworker and potentially the user). Functional > pretty. Can be rough around the edges.

**D17: Existing data to import?**
A: No existing data. Starting fresh — first time this data is being collected systematically.

**D18: Timeline / quality expectation?**
A: Full product. Build the complete system with all 10 states, dashboard, map, and quality. Quality over speed.

---

## 6. Architecture Decisions (Derived)

**D19: Database?**
A: PostgreSQL (relational + JSONB) for metadata and extracted data. Local filesystem with organized folder structure for original documents. Per research recommendations.

**D20: Scraping architecture?**
A: Per-state adapter pattern. Base scraper class with state-specific adapters. Scrapy + Playwright hybrid — Scrapy for static sites, Playwright for JS-heavy sites. Per research recommendations.

**D21: Document processing pipeline?**
A: Seven-stage pipeline: discover → download → classify → extract → normalize → validate → store. Classification via rule-based keyword matching (~80% of docs) + PaddleOCR for scanned content.

**D22: File organization structure?**
A: `data/{state}/{operator}/{doc_type}/{filename}` — original documents organized into labeled folders on the local filesystem.

**D23: Confidence scoring?**
A: Three-level scoring: OCR confidence, field-level confidence, document-level confidence. Documents below threshold go to review queue. Per D10 strict rejection policy.

**D24: Search implementation?**
A: PostgreSQL full-text search. Sufficient for 1-2 users and local deployment. No need for Elasticsearch at this scale.

**D25: Map implementation?**
A: Leaflet or Mapbox GL JS with OpenStreetMap tiles (free). Well pins from lat/long coordinates in the database. Click-to-detail interaction.

---

## 7. Scope Exclusions

**D26: What's explicitly NOT in scope?**
A:
- No user authentication or multi-tenancy
- No scheduled/automated scraping (on-demand only)
- No paid OCR or LLM API services
- No cloud deployment (local only)
- No mobile app
- No integration with existing ETL or commercial data vendors
- No real-time data streaming
- No data correction/amendment tracking across time (just current state)
