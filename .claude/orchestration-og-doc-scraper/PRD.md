# Oil & Gas Document Scraper - Product Requirements Document

**Created**: 2026-03-27
**Status**: Draft
**Source**: User conversation with coworker about manual oil & gas data pain

---

## 1. Vision

Oil and gas regulatory data in the United States is fragmented, poorly labeled, and scattered across dozens of state-specific government websites. Each state maintains its own regulatory commission site (e.g., Texas Railroad Commission, Oklahoma Corporation Commission, North Dakota Industrial Commission, etc.) with unique layouts, file formats, and naming conventions. The data is often unlabeled — operators must open documents one by one to figure out what they contain.

Currently, gathering this data is a brutal manual process that takes a full day or more. Workers have to navigate each state's site individually, download documents, open them to determine what they are, and carefully identify which numbers and data points are correct — because the source of truth is fuzzy and data quality is poor across the industry.

This app automates that entire process: scraping oil & gas documents from US state regulatory sites, identifying/classifying unlabeled documents, extracting key data points, and normalizing everything into a clean, queryable format. It replaces a full day of manual work with an automated pipeline.

## 2. Core Features

### Web Scraping Engine
- Scrape oil & gas regulatory documents from all major US state sites
- Handle state-specific site structures (each state is different)
- Navigate paginated results, search interfaces, and document repositories
- Download documents in whatever format they exist (PDF, XLSX, CSV, HTML, etc.)
- Handle anti-bot protections, rate limiting, CAPTCHAs where applicable
- Retry logic and error recovery for flaky government sites

### Document Classification & Labeling
- Automatically identify/classify unlabeled documents after download
- Detect document type (well permit, production report, completion report, inspection record, spacing order, etc.)
- Extract metadata: state, county, operator, well name/number, API number, date, document type
- Handle multiple file formats (PDF text extraction, OCR for scanned docs, spreadsheet parsing)

### Data Extraction & Normalization
- Extract key numerical data from documents (production volumes, well depths, coordinates, etc.)
- Normalize data across states into a consistent schema
- Flag data quality issues and confidence levels
- Handle the "which numbers are you using" problem — identify and label different number types (API numbers, permit numbers, well numbers, lease numbers)

### Data Storage & Access
- Store scraped documents and extracted data in a structured database
- Provide search/query interface to find documents by state, operator, well, date, type
- Export capabilities (CSV, JSON, API)
- Track provenance — which state site, which URL, when scraped

### State Site Registry
- Maintain a registry of all US state oil & gas regulatory sites
- Track each site's structure, URL patterns, and scraping strategy
- Flag when a site changes layout (scraper breaks)
- Prioritize states by data volume/importance

## 3. User Flows

### Flow 1: Full State Scrape
1. User selects a state (or multiple states) to scrape
2. System navigates to state regulatory site
3. System crawls document repositories, downloading all relevant documents
4. System classifies each document and extracts metadata + key data
5. System stores everything in database with full provenance
6. User gets a summary report: X documents scraped, Y classified, Z data points extracted

### Flow 2: Targeted Search
1. User searches for a specific operator, well, or area
2. System queries relevant state sites for matching documents
3. System downloads, classifies, and extracts data from results
4. User gets structured results with links to source documents

### Flow 3: Data Quality Review
1. User reviews extracted data flagged as low-confidence
2. System shows the source document alongside extracted values
3. User confirms or corrects values
4. System learns from corrections to improve future extraction

### Flow 4: Monitoring / Incremental Updates
1. System periodically re-scrapes state sites for new documents
2. Only downloads new/updated documents (avoids re-downloading)
3. Notifies user of new data available

## 4. Technical Signals

- Web scraping is the core challenge — government sites are inconsistent and often outdated
- PDF parsing / OCR will be needed for scanned documents
- Browser automation (Playwright/Selenium) likely needed for JavaScript-heavy state sites
- The coworker mentioned an existing ETL pipeline that may already have some of this data
- Data normalization across states is a significant data engineering challenge
- Each state site will essentially need its own scraping adapter/strategy

## 5. Open Questions

- Which states are highest priority? (Top 5-10 producing states? All states?)
- What specific document types matter most? (Production reports? Permits? All of them?)
- What specific data fields need to be extracted? (Production volumes? Well locations? Operator info?)
- Is there an existing database/ETL to integrate with, or is this standalone?
- What format does the coworker need the output in? (Database? CSV? API?)
- How often does this need to run? (One-time scrape? Daily? Weekly?)
- Are there specific state sites that are known to be particularly difficult?
- What's the scale? (How many documents across how many states?)
- Does the coworker already have accounts/access to any state sites that require login?
- What's the budget for any paid APIs or services (OCR, anti-bot, etc.)?
- Should this have a UI or is CLI/script sufficient?
- What are the specific "numbers" the coworker is worried about getting wrong? (API numbers? Production figures?)

## 6. Explicit Constraints

- Must handle the fact that every state site is different (no one-size-fits-all scraper)
- Must handle unlabeled files — can't rely on filenames or metadata from state sites
- Must be careful about which numbers/identifiers are being used (multiple numbering systems exist in O&G)
- Data quality is inherently poor — the tool needs to surface confidence, not pretend data is clean

## 7. Success Criteria

- Replaces a full day of manual scraping work with an automated process
- Successfully scrapes documents from at least the top producing US states
- Correctly classifies unlabeled documents with high accuracy
- Extracts key data points and normalizes across states
- Flags data quality issues rather than silently passing bad data
- Coworker can query "show me all production reports for operator X in state Y" and get results
