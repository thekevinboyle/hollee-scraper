---
name: state-regulatory-sites
description: All 10 US state O&G regulatory site structures, URLs, and scraping strategies. Use when implementing state-specific scrapers or debugging site access.
---

# State Regulatory Sites Reference

## What This Is

A comprehensive reference guide for all 10 US state oil and gas regulatory websites targeted by the Oil & Gas Document Scraper project. Covers regulatory body details, data URLs, API endpoints, scraping strategies, data formats, difficulty ratings, and known quirks for each state.

## When to Use This Skill

- Implementing a specific state's scraper (spider/adapter)
- Debugging site access issues (timeouts, blocks, encoding problems)
- Understanding state-specific data formats (EBCDIC, fixed-width ASCII, ArcGIS REST)
- Planning implementation order or estimating development effort
- Looking up specific download URLs, API endpoints, or GUID links
- Determining whether a state needs Scrapy (static) or Playwright (JS-heavy)

---

## Tier Ranking

### Tier 1 -- Highest Data Volume (Must-Have)

| State | Agency | Production Share |
|-------|--------|-----------------|
| TX | Railroad Commission of Texas (RRC) | 42.9% of US oil |
| NM | Oil Conservation Division (OCD) | 15.1% of US oil |
| ND | Dept of Mineral Resources (DMR) | 8.5% of US oil |
| OK | Corporation Commission (OCC) | 3.0% of US oil |
| CO | Energy & Carbon Management Commission (ECMC) | 3.3% of US oil |

### Tier 2 -- High Value

| State | Agency | Notes |
|-------|--------|-------|
| WY | Oil & Gas Conservation Commission (WOGCC) | 1.7% of US oil |
| LA | Dept of Conservation & Energy (SONRIS) | Major gas (Haynesville Shale) |
| PA | Dept of Environmental Protection (DEP) | Major gas (Marcellus Shale) |
| CA | CalGEM (Geologic Energy Management Division) | 2.6% of US oil |
| AK | Oil & Gas Conservation Commission (AOGCC) | 3.2% of US oil |

---

## Per-State Reference

---

### TX -- Texas (Railroad Commission of Texas)

| Attribute | Value |
|-----------|-------|
| **Regulatory Body** | Railroad Commission of Texas (RRC) |
| **Main URL** | https://www.rrc.texas.gov/ |
| **Data Portal** | https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/ |
| **Query System** | https://webapps2.rrc.texas.gov/EWA/ewaPdqMain.do (PDQ -- DO NOT SCRAPE) |
| **Site Type** | Static / Bulk Download -- **Scrapy only, no Playwright needed** |
| **Data Formats** | EBCDIC, ASCII fixed-width, CSV, JSON (some), dBase (.dbf), PDF, TIFF, Shapefile |
| **Authentication** | None -- all bulk downloads are free and public |
| **Difficulty** | Easy-Medium |
| **Est. Dev Days** | 3-5 days |
| **Rate Limit** | 10s base delay, 2 max concurrent |

**Key Data URLs (via mft.rrc.texas.gov GUIDs):**

| Dataset | Format | Update Frequency | URL |
|---------|--------|-----------------|-----|
| PDQ Dump (production) | CSV | Last Saturday/month | `https://mft.rrc.texas.gov/link/1f5ddb8d-329a-4459-b7f8-177b4f5ee60d` |
| Statewide Production Oil | EBCDIC | Monthly (by 27th) | `https://mft.rrc.texas.gov/link/20ff2205-6579-450f-a2ee-cbd37986b557` |
| Statewide Production Gas | EBCDIC | Monthly (by 27th) | `https://mft.rrc.texas.gov/link/22b56e60-e700-4ee0-a718-9a4bb690f3c8` |
| Full Wellbore | EBCDIC + ASCII | Weekly (Monday) | `https://mft.rrc.texas.gov/link/b070ce28-5c58-4fe2-9eb7-8b70befb7af9` |
| Completion Info | ASCII | Nightly | `https://mft.rrc.texas.gov/link/ed7ab066-879f-40b6-8144-2ae4b6810c04` |
| Drilling Permits (daily w/ coords) | ASCII | Nightly | `https://mft.rrc.texas.gov/link/5f07cc72-2e79-4df8-ade1-9aeb792e03fc` |
| Inspections/Violations (ICE) | TXT | Weekly (Monday) | `https://mft.rrc.texas.gov/link/c7c28dc9-b218-4f0a-8278-bf15d009def1` |
| Well Layers by County | Shapefile | Twice weekly | `https://mft.rrc.texas.gov/link/d551fb20-442e-4b67-84fa-ac3f23ecabb4` |

**Document Types:** Production reports, well permits (W-1), completion reports, directional surveys, spacing/field orders, inspection records (ICE), UIC injection data, operator records (P-5), horizontal drilling permits, field rules, gas processing plant reports (R-3).

**Known Quirks:**
- **EBCDIC encoding**: Many datasets use IBM mainframe EBCDIC with COMP-3 packed decimal fields. Use `ebcdic-parser` library with JSON layout definitions. Code page `cp037` (US/Canada).
- **CRITICAL -- DO NOT scrape the PDQ web interface**: RRC explicitly detects and blocks automated query tools. Sessions will be terminated. Use bulk downloads only.
- **CSV alternative**: The monthly PDQ dump (CSV) provides the same production data as EBCDIC ledger files in a far easier format. Prefer it.
- **Fixed-width ASCII**: No delimiters; fields at fixed byte positions. RRC provides PDF layout manuals for each dataset.
- **Compressed files**: Some downloads use .Z (Unix compress) or .zip.
- **mft.rrc.texas.gov GUIDs**: Static per dataset but verify periodically.
- **Multiple districts**: Oil/gas ledger files are split by RRC administrative district (1-10, 6E, 7B, 7C, 8A, 9).

**Spider:** `tx_rrc.py` -- `BulkDownloadSpider` pattern.

---

### NM -- New Mexico (Oil Conservation Division)

| Attribute | Value |
|-----------|-------|
| **Regulatory Body** | Energy, Minerals and Natural Resources Dept -- Oil Conservation Division (OCD) |
| **Main URL** | https://www.emnrd.nm.gov/ocd/ |
| **Data Hub** | https://ocd-hub-nm-emnrd.hub.arcgis.com/ |
| **Permitting Portal** | https://wwwapps.emnrd.nm.gov/ocd/ocdpermitting/ |
| **Well Search** | https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/Wells.aspx |
| **ONGARD System** | https://www.nmstatelands.org/divisions/oil-gas-and-minerals/ongard-and-data-resources/ |
| **Site Type** | ArcGIS REST API (primary) + ASP.NET forms -- **Scrapy primary, Playwright optional** |
| **Data Formats** | CSV, GeoJSON, KML, Shapefile, JSON (ArcGIS REST) |
| **Authentication** | None for most data; some ONGARD features may require registration |
| **Difficulty** | Medium |
| **Est. Dev Days** | 3-4 days |
| **Rate Limit** | 5s base delay, 2 max concurrent |

**Key API Endpoints:**

| Resource | URL |
|----------|-----|
| Wells Feature Service (Hub) | `https://ocd-hub-nm-emnrd.hub.arcgis.com/datasets/dd971b8e25c54d1a8ab7c549244cf3cc` |
| Wells MapServer | `https://mapservice.nmstatelands.org/arcgis/rest/services/Public/NMOCD_Wells_V3/MapServer/5` |
| Well Details | `https://wwwapps.emnrd.nm.gov/ocd/ocdpermitting/Data/WellDetails.aspx?api={API_NUMBER}` |

**ArcGIS query pattern:**
```
https://mapservice.nmstatelands.org/arcgis/rest/services/Public/NMOCD_Wells_V3/MapServer/5/query?
  where=1%3D1&outFields=*&resultOffset=0&resultRecordCount=1000&f=json
```

**Document Types:** C-101 (Permit to Drill), C-102 (Acreage Plat), C-103 (Sundries/Notices), C-115 (Monthly Production Report), C-145 (Operator Change), well header/location/pool data, production data (via ONGARD).

**Known Quirks:**
- **Multiple fragmented systems**: Data spread across OCD Hub, OCD Permitting (ASP.NET), ONGARD (State Land Office), and GO-TECH (NM Tech). No single unified source.
- **ArcGIS pagination**: Feature services limit to 1,000-2,000 records per query. Must paginate with `resultOffset` and `resultRecordCount`.
- **ONGARD is separate**: Production data managed by NM State Land Office, not OCD.
- **OCD Permitting is ASP.NET**: Server-side rendered with ViewState. Can use Scrapy `FormRequest` but may need Playwright for complex interactions.

**Spider:** `nm_ocd.py` -- `ArcGISAPISpider` pattern (primary) + `FormSpider` (OCD Permitting).

---

### ND -- North Dakota (Department of Mineral Resources)

| Attribute | Value |
|-----------|-------|
| **Regulatory Body** | ND Dept of Mineral Resources, Oil & Gas Division |
| **Main URL** | https://www.dmr.nd.gov/oilgas/ |
| **Well Search** | https://www.dmr.nd.gov/oilgas/findwellsvw.asp |
| **Monthly Production** | https://www.dmr.nd.gov/oilgas/mprindex.asp |
| **NorthSTAR System** | https://www.dmr.nd.gov/dmr/oilgas/reporting/northstar |
| **Site Type** | Classic ASP (legacy) + NorthSTAR (modern JS) -- **Playwright required** |
| **Data Formats** | PDF, HTML, Excel (subscription) |
| **Authentication** | **YES -- paid subscription required for production data** |
| **Difficulty** | Hard |
| **Est. Dev Days** | 4-6 days |
| **Rate Limit** | 15s base delay, 1 max concurrent |

**Subscription Tiers:**

| Tier | Cost | Access |
|------|------|--------|
| Free | $0 | Monthly production report summaries (PDF), daily activity reports, well search (basic headers), weekly permits |
| Basic | $100/year | Well index (Excel), scout tickets, well files (PDF), production/injection histories, GIS Map |
| Premium | $500/year | Everything in Basic + field orders, case files, hearing audio, well logs, core photos, unitization stats |

**Free Data URLs:**

| Data | URL Pattern | Format |
|------|-------------|--------|
| Monthly Production Reports | `https://www.dmr.nd.gov/oilgas/mpr{YYYY}{MM}.pdf` | PDF |
| Daily Activity Reports | Indexed at `https://www.dmr.nd.gov/oilgas/dailyindex.asp` | PDF |
| Annual Production Statistics | `https://www.dmr.nd.gov/oilgas/stats/AnnualProduction/{YYYY}AnnualProductionReport.pdf` | PDF |

**Document Types:** Well permits, production reports (monthly/annual), completion reports, scout tickets, well logs, field/hearing orders, daily activity reports, injection data, spacing orders. Most detailed data requires subscription.

**Known Quirks:**
- **Paywall**: The most valuable data (per-well production, scout tickets, well logs) requires $100-$500/year. Budget for this.
- **NorthSTAR migration**: ND is migrating to a new cloud-based system. URLs and interfaces may change without notice.
- **Classic ASP backend**: Legacy pages use .asp extensions (IIS/Classic ASP). ViewState and session management can be tricky.
- **PDF-heavy free data**: Free monthly production reports are PDFs requiring OCR/text extraction.
- **Confidential wells**: Production data for confidential wells is withheld even from premium subscribers.

**Spider:** `nd_dmr.py` -- `HybridSpider` (Scrapy for free PDF/HTML + Playwright for authenticated subscription portal).

---

### OK -- Oklahoma (Corporation Commission)

| Attribute | Value |
|-----------|-------|
| **Regulatory Body** | Oklahoma Corporation Commission, Oil & Gas Division |
| **Main URL** | https://oklahoma.gov/occ/divisions/oil-gas.html |
| **Data Files** | https://oklahoma.gov/occ/divisions/oil-gas/oil-gas-data.html |
| **Well Browse** | https://wellbrowse.occ.ok.gov/ |
| **GIS Data** | https://gisdata-occokc.opendata.arcgis.com/ |
| **Site Type** | Static / Bulk Download -- **Scrapy only, no Playwright needed** |
| **Data Formats** | CSV, XLSX, Shapefile, PDF |
| **Authentication** | None |
| **Difficulty** | Easy |
| **Est. Dev Days** | 2-3 days |
| **Rate Limit** | 3s base delay, 4 max concurrent |

**Key Bulk Download Files (base URL: `https://oklahoma.gov`):**

| File | Format | Frequency | Path |
|------|--------|-----------|------|
| RBDMS Well Data | CSV | Nightly | `/content/dam/ok/en/occ/documents/og/ogdatafiles/rbdms-wells.csv` |
| RBDMS Data Dictionary | XLSX | Nightly | `/content/dam/ok/en/occ/documents/og/ogdatafiles/rbdms-wells-data-dictionary.xlsx` |
| Incident Report Archive | CSV | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/ogcd-incidents.csv` |
| Intent to Drill Master | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/ITD-wells-formations-base.xlsx` |
| Well Completions Monthly | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/completions-wells-formations-base.xlsx` |
| Operator List | XLSX | Daily | `/content/dam/ok/en/occ/documents/og/ogdatafiles/operator-list.xlsx` |
| UIC Injection Volumes | XLSX | Weekly | `/content/dam/ok/en/occ/documents/og/ogdatafiles/2025-uic-injection-volumes.xlsx` |

**Document Types:** Well data (RBDMS), drilling permits (Intent to Drill), completions, incidents, orphan wells, operator/purchaser lists, UIC injection volumes, well transfers, imaged documents.

**Known Quirks:**
- **Production data is maintained separately**: Production data comes from the **Oklahoma Tax Commission**, NOT the OCC. Access via OkTAP at `https://oktap.tax.ok.gov/OkTAP/web?link=PUBLICPUNLKP`. May need Playwright for form interaction.
- **RBDMS standard**: Oklahoma uses RBDMS, so data structure is somewhat standardized.
- **Data dictionaries included**: XLSX data dictionaries accompany most files, making parsing straightforward.

**Spider:** `ok_occ.py` -- `BulkDownloadSpider` pattern.

---

### CO -- Colorado (Energy & Carbon Management Commission)

| Attribute | Value |
|-----------|-------|
| **Regulatory Body** | Colorado Energy & Carbon Management Commission (ECMC, formerly COGCC) |
| **Main URL** | https://ecmc.state.co.us/ (legacy) / https://ecmc.colorado.gov/ (new) |
| **COGIS Database** | https://ecmc.colorado.gov/data-maps/cogis-database |
| **Downloadable Data** | https://ecmc.colorado.gov/data-maps-reports/downloadable-data-documents |
| **Facility Search** | https://ecmc.state.co.us/cogisdb/Facility/FacilitySearch |
| **Dashboard** | https://ecmc.state.co.us/dashboard.html |
| **Site Type** | Mixed -- bulk CSV + COGIS ASP.NET forms -- **Scrapy primary, Playwright for some COGIS queries** |
| **Data Formats** | CSV (primary), PDF |
| **Authentication** | None |
| **Difficulty** | Medium |
| **Est. Dev Days** | 3-4 days |
| **Rate Limit** | 8s base delay, 2 max concurrent |

**Downloadable Data:**

| Dataset | Format | Frequency |
|---------|--------|-----------|
| Well Spots (APIs) | CSV | Regular |
| Well Permits | CSV | Regular |
| Pending Well Permits | CSV | Regular |
| Production Data (all wells since 1999) | CSV (zipped + uncompressed) | Monthly |
| Oil & Gas Well Analytical Data | CSV | Monthly |

**Data Download Guide:** https://ecmc.state.co.us/documents/data/downloads/COGCC_Download_Guidance.pdf

**Document Types:** Well permits (pending + approved), production data (annual oil/gas/water per formation per well), well completions, facility data, inspection reports, operator data, financial assurance records.

**Known Quirks:**
- **Dual domains**: ECMC uses both `ecmc.colorado.gov` (new) and `ecmc.state.co.us` (legacy). Some features live on one or the other.
- **COGIS ASP.NET forms**: Query interfaces require form submission. May need Playwright for complex queries.
- **Large production CSV**: The downloadable production CSV contains ALL production reports since 1999 in a single file.
- **Data Download Guide available**: ECMC provides a detailed PDF guide for understanding their data.

**Spider:** `co_ecmc.py` -- `MixedSpider` (bulk CSV downloads + COGIS form queries).

---

### WY -- Wyoming (Oil & Gas Conservation Commission)

| Attribute | Value |
|-----------|-------|
| **Regulatory Body** | Wyoming Oil and Gas Conservation Commission (WOGCC) |
| **Main URL** | https://wogcc.wyo.gov/ |
| **Data Explorer** | https://dataexplorer.wogcc.wyo.gov/ |
| **Legacy Portal** | https://pipeline.wyo.gov/legacywogcce.cfm (ColdFusion) |
| **ArcGIS Wells** | https://gis.deq.wyoming.gov/arcgis_443/rest/services/WOGCC_WELLS/MapServer |
| **Geospatial Hub** | https://data.geospatialhub.org/ |
| **Site Type** | Mixed -- JS-heavy Data Explorer + ArcGIS + ColdFusion legacy -- **Playwright needed** |
| **Data Formats** | Excel (DB5 well header), Shapefile, PDF, ArcGIS REST (JSON, GeoJSON) |
| **Authentication** | None |
| **Difficulty** | Medium-Hard |
| **Est. Dev Days** | 3-5 days |
| **Rate Limit** | 10s base delay, 1 max concurrent |

**Key Endpoints:**

| Resource | URL |
|----------|-----|
| ArcGIS Wells MapServer | `https://gis.deq.wyoming.gov/arcgis_443/rest/services/WOGCC_WELLS/MapServer` |
| Active Wells (Hub) | `https://data.geospatialhub.org/datasets/46d3629e4e3b4ef6978cb5e6598f97bb_0` |
| Bottom Hole Data (Hub) | `https://data.geospatialhub.org/datasets/290e6b5d473f47f783ef08691f613c87_0/geoservice` |
| WSGS MapServer | `https://portal.wsgs.wyo.gov/ags/rest/services/OilGas/Data_layers/MapServer` |

**Document Types:** Well headers (permits, locations, operators), production data, completion data, spacing orders (PDF), inspection reports, directional surveys, well logs (limited).

**Known Quirks:**
- **ColdFusion legacy portal**: The legacy site at `pipeline.wyo.gov` uses ColdFusion (.cfm) with quirky session management.
- **Data Explorer is JS-heavy**: The primary modern interface requires Playwright for browser automation.
- **Multiple data sources**: Data is spread across Data Explorer, legacy portal, ArcGIS services, and Geospatial Hub. No single unified download.
- **ArcGIS nightly refresh**: The WOGCC_WELLS feature class is recreated nightly from WOGCC data via Python scripts.
- **Well Header DB5**: Statewide well header data (~114,000 wells) available as Excel from legacy site download menu.

**Spider:** `wy_wogcc.py` -- `MixedSpider` (ArcGIS API primary + Playwright for Data Explorer).

---

### LA -- Louisiana (SONRIS)

| Attribute | Value |
|-----------|-------|
| **Regulatory Body** | Louisiana Dept of Conservation and Energy (formerly DNR, renamed Oct 2025) |
| **Main URL** | https://www.sonris.com/ |
| **IDR Reports** | https://www.dnr.louisiana.gov/page/cons-sonris-idr-index-by-topic |
| **GIS Map** | https://sonris-gis.dnr.la.gov/gis/agsweb/IE/JSViewer/index.html?TemplateID=181 |
| **Production Data** | https://www.dnr.louisiana.gov/page/oil-and-gas-production-data |
| **DOTD ArcGIS** | https://giswebnew.dotd.la.gov/arcgis/rest/services/LTRC/SONRIS/MapServer |
| **Site Type** | Complex JS web app + Oracle backend -- **Playwright required throughout** |
| **Data Formats** | Excel (IDR export), HTML, PDF |
| **Authentication** | None for most data; some data entry features require account |
| **Difficulty** | Hard -- **hardest state to scrape** |
| **Est. Dev Days** | 5-8 days |
| **Rate Limit** | 15s base delay, 1 max concurrent |

**IDR Reports (Interactive Data Reports -- primary extraction method):**
- Well Information (by serial number, operator, field)
- Production Data (oil, gas, condensate by well/field/parish)
- Injection Data
- Scout Reports
- Permit Data
- Well Test Data
- Plugging & Abandonment

**Document Types:** Well data (serial number-based), production data (oil/gas/condensate), injection data, scout reports, permits, well tests, P&A records, field data, hearing orders.

**Known Quirks:**
- **Oracle backend**: SONRIS is backed by millions of Oracle records. Complex queries can time out.
- **No REST API**: Unlike states with ArcGIS REST APIs, SONRIS does not expose a documented REST API. All access is through the web application.
- **IDR reports are the key**: Interactive Data Reports with Excel export are the primary extraction method. Must automate report parameter selection and export.
- **Recent reorganization**: As of Oct 2025, agency renamed from DENR to Dept of Conservation and Energy. URLs in flux -- some at `denr.louisiana.gov`, some at `dce.louisiana.gov`, some at `dnr.louisiana.gov`.
- **Serial number system**: Louisiana uses its own serial number system for wells (not just API numbers).
- **Session-based state management**: Expect complex JavaScript, potential CAPTCHAs, and Oracle query timeouts.

**Spider:** `la_sonris.py` -- `PlaywrightFormSpider` pattern. Expect significant effort for browser automation, session management, and error handling.

---

### PA -- Pennsylvania (Department of Environmental Protection)

| Attribute | Value |
|-----------|-------|
| **Regulatory Body** | PA Dept of Environmental Protection, Office of Oil and Gas Management |
| **Main URL** | https://www.pa.gov/agencies/dep/data-and-tools/reports/oil-and-gas-reports |
| **GreenPort Extracts** | https://greenport.pa.gov/ReportExtracts/OG/Index |
| **Production Report** | https://greenport.pa.gov/ReportExtracts/OG/OilGasWellProdReport |
| **Well Inventory** | https://greenport.pa.gov/ReportExtracts/OG/OilGasWellInventoryReport |
| **Compliance Report** | https://greenport.pa.gov/ReportExtracts/OG/OilComplianceReport |
| **Plugged Wells** | https://greenport.pa.gov/ReportExtracts/OG/OGPluggedWellsReport |
| **Waste Report** | https://greenport.pa.gov/ReportExtracts/OG/OilGasWellWasteReport |
| **GIS Mapping** | https://gis.dep.pa.gov/PaOilAndGasMapping/ |
| **Data Dictionary** | https://files.dep.state.pa.us/oilgas/bogm/bogmportalfiles/oilgasreports/HelpDocs/SSRS_Report_Data_Dictionary/DEP_Oil_and_GAS_Reports_Data_Dictionary.pdf |
| **Site Type** | Static / CSV export -- **Scrapy only, no Playwright needed** |
| **Data Formats** | CSV (all GreenPort exports) |
| **Authentication** | None |
| **Difficulty** | Easy -- **easiest state to scrape** |
| **Est. Dev Days** | 1-2 days |
| **Rate Limit** | 3s base delay, 4 max concurrent |

**GreenPort Report Extracts (live data, CSV download):**

| Report | Contents |
|--------|----------|
| Production Report | Monthly oil, gas, condensate production by well for selected period |
| Well Inventory | Permits, locations, operators, well status, spud dates |
| Compliance Report | Inspections, violations, enforcement actions |
| Plugged Wells | Plugging and abandonment records |
| Well Waste Report | Waste generation and disposal data |
| Production Not Submitted | Wells with missing production reports |

**Document Types:** Production reports, well permits/inventory, compliance/inspection records, plugging reports, waste reports.

**Known Quirks:**
- **Report parameters required**: Each GreenPort report requires selecting a reporting period (year/quarter). Must automate parameter selection to download historical data.
- **Live data**: Reports generated on-demand from live data; values may change between report generations.
- **Marcellus Shale focus**: PA primary activity is unconventional gas (Marcellus/Utica Shale), not oil.
- **No spacing/pooling orders**: Unlike western states, PA does not have spacing orders.
- **May need ViewState**: ASP.NET form submission with ViewState for parameter selection.

**Spider:** `pa_dep.py` -- `BulkDownloadSpider` pattern.

---

### CA -- California (CalGEM)

| Attribute | Value |
|-----------|-------|
| **Regulatory Body** | CalGEM (Geologic Energy Management Division), Dept of Conservation |
| **Main URL** | https://www.conservation.ca.gov/calgem/ |
| **Well Finder** | https://www.conservation.ca.gov/calgem/Pages/WellFinder.aspx |
| **WellSTAR Dashboard** | https://www.conservation.ca.gov/calgem/Online_Data/Pages/WellSTAR-Data-Dashboard.aspx |
| **CA Open Data -- Wells** | https://data.ca.gov/dataset/wellstar-oil-and-gas-wells |
| **CA Open Data -- Facilities** | https://data.ca.gov/dataset/wellstar-oil-and-gas-facilities |
| **CA Open Data -- Notices** | https://data.ca.gov/dataset/wellstar-notices |
| **ArcGIS Wells MapServer** | https://gis.conservation.ca.gov/server/rest/services/WellSTAR/Wells/MapServer/0 |
| **Site Type** | ArcGIS REST API + CKAN Open Data portal -- **Scrapy only, no Playwright needed (mostly)** |
| **Data Formats** | CSV, GeoJSON, Shapefile, KML, JSON (ArcGIS REST), PBF |
| **Authentication** | None -- Creative Commons Attribution license |
| **Difficulty** | Easy |
| **Est. Dev Days** | 2-3 days |
| **Rate Limit** | 3s base delay, 3 max concurrent |

**ArcGIS query pattern:**
```
https://gis.conservation.ca.gov/server/rest/services/WellSTAR/Wells/MapServer/0/query?
  where=WellStatus%3D%27Active%27&outFields=*&resultOffset=0&resultRecordCount=5000&f=json
```

**WellSTAR Open Data Datasets:** Oil and Gas Wells, Oil and Gas Facilities, Facilities Boundaries, Underground Gas Storage Wells, Notices (NOIs).

**Document Types:** Well data (header, status, location, operator), facility data, production data (via WellSTAR Dashboard), notices of intention (NOI), permits, well logs (limited).

**Known Quirks:**
- **Max 5,000 records per query**: Must paginate through results using `resultOffset`. California has many wells.
- **Spatial reference**: API returns data in Web Mercator (EPSG:3857). Convert to WGS84 for standard lat/long.
- **WellSTAR under active development**: CalGEM continuously updates WellSTAR. Check for new datasets and API changes.
- **Production data separate**: Well location/status readily available via API, but production data is primarily through WellSTAR Dashboard (may need Playwright for export).

**Spider:** `ca_calgem.py` -- `ArcGISAPISpider` pattern.

---

### AK -- Alaska (Oil & Gas Conservation Commission)

| Attribute | Value |
|-----------|-------|
| **Regulatory Body** | Alaska Oil and Gas Conservation Commission (AOGCC) |
| **Main URL** | https://www.commerce.alaska.gov/web/aogcc/ |
| **Data Page** | https://www.commerce.alaska.gov/web/aogcc/Data.aspx |
| **Data Miner -- Wells** | http://aogweb.state.ak.us/DataMiner4/Forms/Wells.aspx |
| **Data Miner -- Well Data** | http://aogweb.state.ak.us/DataMiner4/Forms/WellData.aspx |
| **Data Miner -- Production** | http://aogweb.state.ak.us/DataMiner4/Forms/Production.aspx |
| **AK Open Data** | https://dog-soa-dnr.opendata.arcgis.com/ |
| **Site Type** | ASP.NET WebForms (Data Miner) + ArcGIS -- **Playwright needed for Data Miner exports** |
| **Data Formats** | CSV, Excel, MS Access (bulk), PDF, ArcGIS formats |
| **Authentication** | None |
| **Difficulty** | Easy-Medium |
| **Est. Dev Days** | 2-3 days |
| **Rate Limit** | 5s base delay, 2 max concurrent |

**Data Miner Forms:**

| Form | URL | Data |
|------|-----|------|
| Wells | `http://aogweb.state.ak.us/DataMiner4/Forms/Wells.aspx` | Well list, filter by operator/name/area/permit/date |
| Well Data | `http://aogweb.state.ak.us/DataMiner4/Forms/WellData.aspx` | Detailed well info, location, pools encountered |
| Well History | `http://aogweb.state.ak.us/DataMiner4/Forms/WellHistory.aspx` | Event history with descriptions |
| Production | `http://aogweb.state.ak.us/DataMiner4/Forms/Production.aspx` | Monthly production data (oil, gas, water) |

**Document Types:** Well data (headers, locations, pools), well history (events), production data (monthly oil/gas/water), injection data, facility data, NGL records, permits, well logs (limited).

**Known Quirks:**
- **HTTP not HTTPS**: Data Miner runs on plain HTTP (`http://aogweb.state.ak.us`), which is unusual and may cause issues with HTTP clients that enforce HTTPS.
- **ASP.NET WebForms**: Uses ViewState and PostBack patterns. Export buttons trigger server-side processing. May need Playwright to click "Export As..." and handle file downloads.
- **Smaller dataset**: Alaska has far fewer wells than TX or NM, making full-table exports feasible.
- **Two agencies**: AOGCC (Commerce Dept) handles conservation/regulatory data. Division of Oil and Gas (DNR) handles leasing/exploration. Separate portals.
- **Database upgrade pending**: As of late 2025, AOGCC was seeking a database upgrade. Data Miner interface may change.
- **Bulk MS Access DB**: Full database available as MS Access download for bulk import.

**Spider:** `ak_aogcc.py` -- `MixedSpider` (Playwright for Data Miner export + ArcGIS API).

---

## Implementation Priority Order

| Priority | State | Difficulty | Phase | Pattern | Est. Days |
|----------|-------|-----------|-------|---------|-----------|
| 1 | PA | Easy | Phase 1 (Bulk) | BulkDownloadSpider | 1-2 |
| 2 | OK | Easy | Phase 1 (Bulk) | BulkDownloadSpider | 2-3 |
| 3 | TX | Easy-Medium | Phase 1 (Bulk) | BulkDownloadSpider | 3-5 |
| 4 | CA | Easy | Phase 2 (API) | ArcGISAPISpider | 2-3 |
| 5 | NM | Medium | Phase 2 (API) | ArcGISAPISpider + FormSpider | 3-4 |
| 6 | CO | Medium | Phase 2 (API) | MixedSpider | 3-4 |
| 7 | AK | Easy-Medium | Phase 3 (Browser) | MixedSpider | 2-3 |
| 8 | WY | Medium-Hard | Phase 3 (Browser) | MixedSpider | 3-5 |
| 9 | ND | Hard | Phase 3 (Browser) | HybridSpider | 4-6 |
| 10 | LA | Hard | Phase 3 (Browser) | PlaywrightFormSpider | 5-8 |
| | **Total** | | | | **28-43** |

---

## Common Pitfalls

- **Sites go down frequently**: State government sites have unscheduled maintenance, especially on weekends and holidays. Build robust retry logic.
- **Layouts change without notice**: State agencies redesign portals without versioning or announcements. Monitor for DOM changes and broken selectors.
- **Rate limiting varies widely**: From essentially none (PA) to aggressive session termination (TX PDQ). Always configure per-state rate limits.
- **Some require specific User-Agent strings**: Set a polite, identifiable User-Agent: `OGDocScraper/1.0 (Research tool; contact@example.com)`.
- **Coordinate system differences**: Legacy TX data uses NAD 27; most modern data uses NAD 83 or WGS 84. Convert with `pyproj`.
- **API number inconsistency**: Stored with or without dashes, as 10/12/14-digit variants. Normalize to 14-digit format with dashes: `XX-YYY-ZZZZZ-SS-EE`.
- **Operator name inconsistency**: Not standardized across states (abbreviations, DBAs, mergers). Fuzzy matching may be needed.
- **Date format variations**: Each state may use different date formats in exports.
- **EBCDIC is only Texas**: No other state uses EBCDIC. But TX is the largest dataset, so this parser is critical.
- **robots.txt**: Respect it. Set `ROBOTSTXT_OBEY = True` in Scrapy settings.
- **Time-of-day**: Government sites have lower traffic overnight. Schedule heavy scraping for off-peak hours (11 PM - 6 AM local time for each state).

---

## Testing Strategy

**VCR.py cassettes per state**: Record real HTTP responses and replay them in tests. This avoids hitting live government sites during development and CI.

- One cassette directory per state: `tests/cassettes/{state_code}/`
- Record initial responses manually, then replay for all subsequent test runs
- Re-record cassettes periodically (monthly) to catch site changes
- For Playwright-dependent states, use `playwright-pytest` with HAR recording for network replay
- Each spider should have tests covering: successful data fetch, pagination, error handling, format parsing
- EBCDIC tests for TX should include known-good input/output pairs

---

## Quick Reference: Site Type Decision Matrix

| Need Playwright? | States |
|-------------------|--------|
| **No** (Scrapy HTTP only) | TX, OK, PA |
| **Partially** (some forms) | NM, CO, CA |
| **Yes** (required for key data) | ND, WY, LA, AK |

| Has Bulk Downloads? | States |
|----------------------|--------|
| **Excellent** | TX, OK, PA |
| **Good** (API/Open Data) | NM, CA, CO |
| **Limited** | WY, AK, LA, ND |

---

## References

- **Discovery Document**: `.claude/orchestration-og-doc-scraper/DISCOVERY.md`
- **State Regulatory Sites Research**: `.claude/orchestration-og-doc-scraper/research/state-regulatory-sites.md`
- **Per-State Scrapers Implementation Guide**: `.claude/orchestration-og-doc-scraper/research/per-state-scrapers-implementation.md`
- **USGS State Well Data Links**: https://www.usgs.gov/core-research-center/links-state-well-data
- **RBDMS (Cross-State Standard)**: https://www.rbdms.org/
- **FracFocus Chemical Disclosure**: https://fracfocus.org/data-download
- **TX RRC EBCDIC Parser**: `pip install ebcdic-parser` -- layout definitions via JSON, handles COMP-3 packed decimal
