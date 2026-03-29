# US State Oil & Gas Regulatory Sites - Research Report

**Date**: 2026-03-27
**Purpose**: Comprehensive research on US state oil & gas regulatory websites, data availability, scraping feasibility, and technical considerations to inform the Oil & Gas Document Scraper project.

---

## Table of Contents

1. [Top Producing States & Priority Ranking](#1-top-producing-states--priority-ranking)
2. [State-by-State Regulatory Site Analysis](#2-state-by-state-regulatory-site-analysis)
3. [Document Types by State](#3-document-types-by-state)
4. [Data Formats & Access Methods](#4-data-formats--access-methods)
5. [Scraping Difficulty Assessment](#5-scraping-difficulty-assessment)
6. [Common Identifiers (API Numbers, Permit Numbers, etc.)](#6-common-identifiers)
7. [Existing Open-Source Tools & Projects](#7-existing-open-source-tools--projects)
8. [Cross-State Data Standards (RBDMS, FracFocus)](#8-cross-state-data-standards)
9. [Commercial Data Aggregators](#9-commercial-data-aggregators)
10. [Recommendations for Implementation](#10-recommendations-for-implementation)

---

## 1. Top Producing States & Priority Ranking

Based on 2025 EIA production data, the following states should be prioritized by production volume:

### Oil Production Ranking (barrels/day, 2025)

| Rank | State | Production (M bbl/day) | % of US Total | Priority |
|------|-------|----------------------|---------------|----------|
| 1 | Texas | 5.70 | 42.9% | Critical |
| 2 | New Mexico | 2.00+ | 15.1% | Critical |
| 3 | North Dakota | 1.13 | 8.5% | High |
| 4 | Colorado | 0.44 | 3.3% | High |
| 5 | Alaska | 0.43 | 3.2% | High |
| 6 | Oklahoma | 0.40 | 3.0% | High |
| 7 | Wyoming | 0.23 | 1.7% | Medium |
| 8 | California | 0.34 | 2.6% | Medium |
| 9 | Louisiana | 0.08 (oil) | <1% (but major gas) | High (gas) |
| 10 | Pennsylvania | - | - (major gas) | High (gas) |

**Note**: Louisiana and Pennsylvania are critical for natural gas (Haynesville Shale, Marcellus Shale respectively). About 76% of total US crude oil production comes from just six states: TX, NM, ND, CO, AK, OK.

### Recommended Priority Tiers

- **Tier 1 (must-have)**: Texas, New Mexico, North Dakota, Oklahoma, Colorado
- **Tier 2 (high value)**: Wyoming, Louisiana, Pennsylvania, California, Alaska
- **Tier 3 (moderate)**: Ohio, West Virginia, Kansas, Utah, Montana
- **Tier 4 (lower priority)**: Michigan, Mississippi, Arkansas, Kentucky, Illinois, Indiana, New York, Nebraska

---

## 2. State-by-State Regulatory Site Analysis

### TEXAS - Railroad Commission of Texas (RRC)

| Attribute | Details |
|-----------|---------|
| **Agency** | Railroad Commission of Texas (RRC) |
| **Main URL** | https://www.rrc.texas.gov/ |
| **Data Portal** | https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/ |
| **Query System** | https://webapps2.rrc.texas.gov/EWA/ewaPdqMain.do (Production Data Query) |
| **Well Records** | https://www.rrc.texas.gov/oil-and-gas/research-and-statistics/obtaining-commission-records/oil-and-gas-well-records-online/ |
| **Login Required** | No (bulk downloads are free and public) |
| **Bulk Download** | Yes - extensive bulk data sets via HTTPS (formerly FTP) |
| **Anti-Scraping** | **YES - the RRC explicitly detects and blocks automated query tools on the PDQ system.** Automated tools cause system degradation and sessions will be terminated. |
| **Best Approach** | Use bulk data downloads (not web scraping of the query interface) |

**Data Sets Available for Bulk Download** (all free, no login):
- **Drilling Permits**: ASCII format, updated monthly/nightly. Includes permit numbers, dates, lease names, locations, spud dates, spacing exceptions. Daily files with coordinates updated nightly.
- **Production Data**: EBCDIC and CSV formats. Production Data Query (PDQ) dump available as CSV on last Saturday of each month. Oil/gas ledgers by district in EBCDIC, updated monthly.
- **Well Data**: Full wellbore data in EBCDIC/ASCII, updated weekly. Completion information in ASCII (zipped), updated nightly. Imaged completion files as PDF/TIFF, updated nightly.
- **Field Data**: Oil/gas field tables in ASCII, updated monthly. Field names, numbers, rules, spacing.
- **Regulatory Data**: Inspections & violations as TXT, updated weekly. Docket information in ASCII. P5 organization data.
- **Digital Maps**: ArcView Shape files by county, updated twice weekly. Statewide API data in ASCII and dBase (.dbf).
- **UIC Data**: Underground injection control database in EBCDIC/ASCII, monthly updates.
- **Directional Surveys**: PDF format, nightly updates.

**Download URL Pattern**: `https://mft.rrc.texas.gov/link/{GUID}`

**Data Formats**: ASCII (fixed-width), EBCDIC, dBase (.dbf), CSV, JSON (new for some datasets), PDF, TIFF, ArcView Shapefile

**Key Caveat**: Many legacy datasets use EBCDIC encoding (IBM mainframe format) which requires conversion. Layout manuals (PDFs) are provided for each dataset describing field positions.

---

### NEW MEXICO - Oil Conservation Division (OCD)

| Attribute | Details |
|-----------|---------|
| **Agency** | Energy, Minerals and Natural Resources Dept - Oil Conservation Division (OCD) |
| **Main URL** | https://www.emnrd.nm.gov/ocd/ |
| **Data Hub** | https://ocd-hub-nm-emnrd.hub.arcgis.com/ |
| **Permitting Portal** | https://wwwapps.emnrd.nm.gov/ocd/ocdpermitting/ |
| **Well Search** | https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/Wells.aspx |
| **ONGARD System** | https://www.nmstatelands.org/divisions/oil-gas-and-minerals/ongard-and-data-resources/ |
| **GO-TECH Search** | https://octane.nmt.edu/gotech/Petroleum_Data/general.aspx |
| **Login Required** | No for most data; some ONGARD features may require registration |
| **Bulk Download** | Yes via ArcGIS Hub (CSV, KML, GeoJSON, Zip) |
| **Anti-Scraping** | Moderate - ArcGIS Hub has built-in API rate limits |
| **Best Approach** | ArcGIS REST API for well/production data; OCD Permitting portal for permits |

**Key Systems**:
- **ONGARD** (Oil and Natural Gas Administration and Revenue Database): Tracks production, taxes, royalties. Managed by NM State Land Office.
- **OCD Hub** (ArcGIS): Allows data discovery, analysis, and download in CSV, KML, Zip, GeoJSON, GeoTIFF, PNG formats. Provides API links for GeoServices, WMS, WFS.
- **OCD E-Permitting**: Electronic submission/viewing of C-101 (permit to drill), C-102 (acreage plat), C-103 (sundries), C-145 (operator change), C-115 (monthly report).
- **GO-TECH** (NM Tech): Additional petroleum data search interface.

**ArcGIS REST API Endpoints**:
- Oil and Gas Wells: `https://ocd-hub-nm-emnrd.hub.arcgis.com/datasets/dd971b8e25c54d1a8ab7c549244cf3cc`
- Oil and Gas Production Areas: `https://ocd-hub-nm-emnrd.hub.arcgis.com/items/5c8bd8d90fe143579ec69956ffbcd6d1`

---

### NORTH DAKOTA - Department of Mineral Resources (DMR)

| Attribute | Details |
|-----------|---------|
| **Agency** | ND Dept of Mineral Resources, Oil & Gas Division |
| **Main URL** | https://www.dmr.nd.gov/oilgas/ |
| **Well Search** | https://www.dmr.nd.gov/oilgas/findwellsvw.asp |
| **GIS Map** | https://gis.dmr.nd.gov/ |
| **Monthly Production** | https://www.dmr.nd.gov/oilgas/mprindex.asp |
| **Daily Activity** | https://www.dmr.nd.gov/oilgas/dailyindex.asp |
| **Login Required** | **YES for production data** - requires paid subscription |
| **Bulk Download** | Limited - subscription required for most detailed data |
| **Anti-Scraping** | Moderate - subscription login required for key data |
| **Best Approach** | Subscription service + static report scraping for free data |

**Subscription Service (as of Jan 2026)**:
- **Basic**: $100/year - additional data downloads
- **Premium**: $500/year - full data access including production/injection volumes
- Production/injection numbers for confidential wells are excluded even from premium

**Freely Available Data (no login)**:
- Monthly production report summaries (PDF/HTML reports indexed by year)
- Daily activity reports (indexed by month/year)
- Weekly permit listings (operator, well name, location, permit number, field, formation, classification, total depth)
- Well search interface (basic well header data)

**Subscription-Only Data**:
- Detailed well data including scout tickets
- Production and injection volumes by well
- Field orders, case files, unitization statistics

**NorthSTAR**: New system being deployed for data access (FAQ available at dmr.nd.gov)

---

### COLORADO - Energy & Carbon Management Commission (ECMC, formerly COGCC)

| Attribute | Details |
|-----------|---------|
| **Agency** | Colorado Energy & Carbon Management Commission (ECMC) |
| **Main URL** | https://ecmc.state.co.us/ |
| **COGIS Database** | https://ecmc.colorado.gov/data-maps/cogis-database |
| **GIS Online** | https://cogccmap.state.co.us/cogcc_gis_online/ |
| **Production Query** | https://ecmc.colorado.gov/data-maps-reports/cogis-database/cogis-production-data-inquiry |
| **Facility Search** | https://ecmc.state.co.us/cogisdb/Facility/FacilitySearch |
| **Downloadable Data** | https://ecmc.colorado.gov/data-maps-reports/downloadable-data-documents |
| **Dashboard** | https://ecmc.state.co.us/dashboard.html |
| **Login Required** | No |
| **Bulk Download** | Yes - downloadable data tables |
| **Anti-Scraping** | Low - standard government site |
| **Best Approach** | COGIS database queries + bulk data downloads |

**COGIS (Colorado Oil and Gas Information System)**:
The central online database containing well, production, and operator information. Databases contain the most current data and are updated throughout the day.

**Key Data Available**:
- Well permits (last 12 months approved + pending, filterable by county)
- Production data (annual oil, gas, water production per formation per well)
- Well completions (spud date, TD date, wellbore status, first production date)
- Facility inquiry (search by API number, location, well name)
- Inspection reports
- Downloadable data tables (various formats)

**Data Download Guide**: https://ecmc.state.co.us/documents/data/downloads/COGCC_Download_Guidance.pdf

---

### OKLAHOMA - Corporation Commission (OCC)

| Attribute | Details |
|-----------|---------|
| **Agency** | Oklahoma Corporation Commission, Oil & Gas Division |
| **Main URL** | https://oklahoma.gov/occ/divisions/oil-gas.html |
| **Data Files** | https://oklahoma.gov/occ/divisions/oil-gas/oil-gas-data.html |
| **Well Data Finder** | https://gis.occ.ok.gov/portal/apps/webappviewer/index.html?id=ba9b8612132f4106be6e3553dc0b827b |
| **Well Browse** | https://wellbrowse.occ.ok.gov/ |
| **GIS Data** | https://gisdata-occokc.opendata.arcgis.com/ |
| **Database Search** | https://oklahoma.gov/occ/divisions/oil-gas/database-search-imaged-documents.html |
| **Login Required** | No |
| **Bulk Download** | Yes - extensive downloadable files (CSV, XLSX, shapefiles) |
| **Anti-Scraping** | Low |
| **Best Approach** | Direct file downloads (nightly CSV/XLSX updates) |

**Downloadable Data Files** (all public, no login):

| File | Format | Update |
|------|--------|--------|
| RBDMS Well Data | CSV | Nightly |
| RBDMS Wells (GIS) | Shapefile (ZIP) | Nightly |
| Incident Report Archive | CSV | Daily |
| Orphan Well List | XLSX | Weekly (Thu) |
| Intent to Drill (7-day) | XLSX | Daily |
| Intent to Drill Master | XLSX | Daily |
| Monthly Well Completions | XLSX | Daily |
| Well Completion (7-day) | XLSX | Daily |
| Well Transfer File | XLSX | Daily |
| Operator List | XLSX | Daily |
| Purchaser List | XLSX | Daily |
| UIC Wells | XLSX | Various |
| UIC Injection Volumes (2011-2026) | XLSX | Weekly |
| Arbuckle AOI Well Data (1012D) | XLSX | Weekly |

**Important Note**: Production data for Oklahoma is maintained by the **Oklahoma Tax Commission**, not the OCC. Production data must be accessed separately through their portal.

---

### WYOMING - Oil & Gas Conservation Commission (WOGCC)

| Attribute | Details |
|-----------|---------|
| **Agency** | Wyoming Oil and Gas Conservation Commission (WOGCC) |
| **Main URL** | https://wogcc.wyo.gov/ |
| **Data Explorer** | https://dataexplorer.wogcc.wyo.gov/ |
| **WellFinder App** | https://wogcc.wyo.gov/wogcc-information/wogcc-news/wellfinder-app |
| **Oil & Gas Resources** | https://wogcc.wyo.gov/public-resources/oil-gas-resources |
| **Legacy Portal** | https://pipeline.wyo.gov/legacywogcce.cfm |
| **Login Required** | No |
| **Bulk Download** | Limited - Data Explorer provides search interface; header files downloadable |
| **Anti-Scraping** | Moderate - older web technology, may need browser automation |
| **Best Approach** | Data Explorer for queries; GIS data from ArcGIS portal |

**Data Explorer** (dataexplorer.wogcc.wyo.gov):
Primary interface for well data queries. Allows searching by location, operator, API number.

**WellFinder App**: Mobile/web application for locating wells and permits with proximity features.

**GIS Data**: Available through Wyoming Geospatial Hub at data.geospatialhub.org. Well data available in ArcGIS format.

**Historical Data**: USGS hosts 120 years of drilling data (1900-2020) from WOGCC records.

---

### LOUISIANA - SONRIS (Strategic Online Natural Resources Information System)

| Attribute | Details |
|-----------|---------|
| **Agency** | Louisiana Dept of Conservation and Energy (formerly DNR, changed Oct 2025) |
| **Main URL** | https://www.sonris.com/ |
| **Data Portal** | https://www.sonris.com/homemain.htm |
| **GIS Map** | https://sonris-gis.dnr.la.gov/gis/agsweb/IE/JSViewer/index.html?TemplateID=181 |
| **Production Data** | https://www.dnr.louisiana.gov/page/oil-and-gas-production-data |
| **IDR Index** | https://www.dnr.louisiana.gov/page/cons-sonris-idr-index-by-topic |
| **Login Required** | No for most data; some data entry features require account |
| **Bulk Download** | Limited - primarily through Interactive Data Reports (IDR) exportable to Excel |
| **Anti-Scraping** | Moderate-High - complex web application, recently redesigned |
| **Best Approach** | IDR reports with Excel export; GIS map for spatial data |

**SONRIS Overview**:
SONRIS provides public access via web browser to data retrieved from the DNR Oracle database using sophisticated queries and pre-built reports.

**Key Features**:
- **Interactive Data Reports (IDR)**: Criteria-specified dynamic reports that can be exported to Excel. Replaced the previous ROD system. Java-free.
- **Well Search**: Search by operator, field code, operator ID
- **GIS Mapping**: Interactive map with well locations and data layers

**Recent Changes**: As of October 2025, reorganized under Department of Conservation and Energy (C&E). Some older documentation at denr.louisiana.gov may be out of date. New portal at sonris.com with accessibility improvements.

**Contact**: 225-342-8955 or dnrinfo@la.gov

---

### PENNSYLVANIA - Department of Environmental Protection (DEP)

| Attribute | Details |
|-----------|---------|
| **Agency** | PA Dept of Environmental Protection, Office of Oil and Gas Management |
| **Main URL** | https://www.pa.gov/agencies/dep/data-and-tools/reports/oil-and-gas-reports |
| **Report Extracts** | https://greenport.pa.gov/ReportExtracts/OG/Index |
| **Production Reports** | https://greenport.pa.gov/ReportExtracts/OG/OilGasWellProdReport |
| **Well Inventory** | https://greenport.pa.gov/ReportExtracts/OG/OilGasWellInventoryReport |
| **Compliance Reports** | https://greenport.pa.gov/ReportExtracts/OG/OilComplianceReport |
| **Plugged Wells** | https://greenport.pa.gov/ReportExtracts/OG/OGPluggedWellsReport |
| **Waste Reports** | https://greenport.pa.gov/ReportExtracts/OG/OilGasWellWasteReport |
| **GIS Mapping** | https://gis.dep.pa.gov/PaOilAndGasMapping/ |
| **Login Required** | No |
| **Bulk Download** | **Yes - excellent CSV export from GreenPort** |
| **Anti-Scraping** | Low |
| **Best Approach** | Direct CSV downloads from GreenPort Report Extracts |

**PA GreenPort Report Extracts** (live data, CSV download):
- Production reports (choose reporting period, export statewide)
- Well inventory (permits, locations, operators)
- Compliance reports (inspections, violations, enforcement)
- Plugged wells reports
- Well waste reports
- SPUD date data

**Data Dictionary**: Available at https://files.dep.state.pa.us/oilgas/bogm/bogmportalfiles/oilgasreports/HelpDocs/SSRS_Report_Data_Dictionary/DEP_Oil_and_GAS_Reports_Data_Dictionary.pdf

Pennsylvania is one of the **easiest states to scrape** due to structured CSV exports with live data.

---

### CALIFORNIA - Geologic Energy Management Division (CalGEM)

| Attribute | Details |
|-----------|---------|
| **Agency** | CalGEM (formerly DOGGR), Dept of Conservation |
| **Main URL** | https://www.conservation.ca.gov/calgem/ |
| **Well Finder** | https://maps.conservation.ca.gov/doggr/wellfinder/ |
| **WellSTAR** | https://www.conservation.ca.gov/calgem/for_operators/Pages/WellSTAR.aspx |
| **Data Dashboard** | https://www.conservation.ca.gov/calgem/Online_Data/Pages/WellSTAR-Data-Dashboard.aspx |
| **Open Data** | https://data.ca.gov/dataset/wellstar-oil-and-gas-wells |
| **Oil & Gas Map** | https://maps.conservation.ca.gov/oilgas/ |
| **Login Required** | No |
| **Bulk Download** | Yes via California Open Data portal (CSV, API) |
| **Anti-Scraping** | Low - data available through Open Data API |
| **Best Approach** | California Open Data API for bulk data; Well Finder for interactive queries |

**WellSTAR** (Well Statewide Tracking and Reporting System):
Comprehensive electronic database updated nightly. Search by location, API number, operator, field. Export to Excel available.

**California Open Data Portal**: Provides a query web API to retrieve WellSTAR data with basic parameters. Available at data.ca.gov.

---

### ALASKA - Oil & Gas Conservation Commission (AOGCC)

| Attribute | Details |
|-----------|---------|
| **Agency** | Alaska Oil and Gas Conservation Commission (AOGCC) |
| **Main URL** | https://www.commerce.alaska.gov/web/aogcc/ |
| **Data Portal** | https://www.commerce.alaska.gov/web/aogcc/Data.aspx |
| **Data Miner** | http://aogweb.state.ak.us/DataMiner4/Forms/WellData.aspx |
| **Open Data** | https://dog-soa-dnr.opendata.arcgis.com/ |
| **Login Required** | No |
| **Bulk Download** | Yes - Data Miner supports full table downloads and CSV export |
| **Anti-Scraping** | Low |
| **Best Approach** | Data Miner CSV exports + ArcGIS Open Data |

**Data Miner Features**:
- Download entire tables
- Well info and history with production/injection records
- Facility info with NGL records
- Filter by operator, well name, area, permit number, date range
- "CSV Production" button downloads production data as comma-delimited text

---

### OHIO - Department of Natural Resources (ODNR)

| Attribute | Details |
|-----------|---------|
| **Agency** | Ohio DNR, Division of Oil & Gas Resources |
| **Main URL** | https://oilandgas.ohiodnr.gov/ |
| **Well Database** | https://apps.ohiodnr.gov/oilgas/rbdmsreports/Downloads_PermitAndPlug.aspx |
| **GIS Mapping** | https://gis.ohiodnr.gov/mapviewer/?config=oilgaswells |
| **Open Data** | https://gis-odnr.opendata.arcgis.com/ |
| **Login Required** | No |
| **Bulk Download** | Yes - permits and plugging data; GIS data through ArcGIS |
| **Anti-Scraping** | Low |
| **Best Approach** | Direct downloads for permits; ArcGIS for spatial data |

**Data Updated**: Every Saturday. Horizontal well production data reported quarterly.

---

### WEST VIRGINIA - Department of Environmental Protection (DEP)

| Attribute | Details |
|-----------|---------|
| **Agency** | WV DEP, Office of Oil and Gas |
| **Main URL** | https://dep.wv.gov/oil-and-gas |
| **Well Search** | https://dep.wv.gov/SearchDEP/Pages/Oil-and-Gas-Well-Search.aspx |
| **TAGIS (GIS)** | https://tagis.dep.wv.gov/oog/ |
| **Well Header Search** | https://www.wvgs.wvnet.edu/pipe2/OGDataSearch.aspx |
| **Login Required** | No |
| **Bulk Download** | Limited - GIS downloads available; production data via DOE EDX |
| **Anti-Scraping** | Low-Moderate |
| **Best Approach** | TAGIS GIS downloads + WV Geological Survey search |

---

### Additional State Portals (Tier 3-4)

| State | Agency | Portal URL | Key Notes |
|-------|--------|-----------|-----------|
| **Kansas** | KGS / Corp Commission | https://www.kgs.ku.edu/Magellan/Qualified/ | 450K+ wells; ArcGIS Hub data; interactive map at maps.kgs.ku.edu/oilgas/ |
| **Utah** | Div of Oil, Gas & Mining | https://datamining.ogm.utah.gov/ | Data Explorer with search filters; production reports by well at ogm.utah.gov |
| **Montana** | Board of Oil & Gas (BOGC) | https://bogapps.dnrc.mt.gov/ | Dataminer app for query/export of well, production, permitting data |
| **Michigan** | EGLE | https://www.egle.state.mi.us/dataminer/ | GeoWebFace mapping; Dataminer for well files, logs, production records |
| **Mississippi** | State Oil & Gas Board | https://www.ogb.state.ms.us/ | Well data browser; scout card/log search; production search; shape file downloads |
| **Kentucky** | Energy & Environment Cabinet | https://www.uky.edu/KGS/emsweb/ | KGS EMS web search |
| **Arkansas** | Oil & Gas Commission (AOGC) | https://www.aogc.state.ar.us/welldata/wells/default.aspx | Well data search interface |
| **New York** | DEC | https://extapps.dec.ny.gov/cfmx/extapps/GasOil/search/wells/ | Searchable database with 40K+ wells; downloadable production data at dec.ny.gov |
| **Illinois** | State Geological Survey | https://prairie-research.maps.arcgis.com/ | ArcGIS interactive map |
| **Indiana** | Geological Survey | https://legacy.igws.indiana.edu/pdms/ | Petroleum Database Management System |
| **Nebraska** | NOGCC | https://nogcc.ne.gov/ | GIS Data Mining; eReports at ereport.nogcc.ne.gov |

---

## 3. Document Types by State

### Common Document Types Across States

| Document Type | Description | Common Formats | States with Online Access |
|--------------|-------------|----------------|--------------------------|
| **Well Permits (APDs)** | Application for Permit to Drill | PDF, XLSX, CSV, HTML | All major states |
| **Production Reports** | Monthly/annual oil, gas, water volumes | CSV, XLSX, EBCDIC, HTML | All major states (ND requires subscription) |
| **Completion Reports** | Well completion details, formations, dates | PDF, ASCII, CSV | TX, CO, OK, NM, WY, PA |
| **Spacing Orders** | Well spacing and density rulings | PDF | TX, ND, OK, NM, CO |
| **Inspection Records** | Field inspection reports, violations | PDF, TXT, CSV | TX, CO, PA, OK, WY |
| **Scout Tickets** | Summary well data cards | PDF, HTML | TX, ND, CO |
| **Directional Surveys** | Wellbore trajectory data | PDF, ASCII | TX, CO, WY |
| **Plugging Reports** | Well plugging and abandonment records | PDF, CSV | TX, PA, OH, CO |
| **Docket/Hearing Orders** | Regulatory hearing decisions | PDF | TX, OK, ND, NM |
| **Well Logs** | Geophysical/petrophysical logs | LAS, PDF, TIFF | TX, ND (premium), CO, OK |
| **Injection Reports** | UIC injection volumes and data | XLSX, CSV, EBCDIC | TX, OK, OH, CO |
| **Operator Reports** | Company information, operator changes | CSV, XLSX | TX, OK, NM, CO |

### State-Specific Document Availability

| State | Permits | Production | Completions | Spacing | Inspections | Logs | Injection |
|-------|---------|-----------|-------------|---------|------------|------|-----------|
| TX | Bulk DL | Bulk DL | Bulk DL | PDF | Bulk DL | PDF | Bulk DL |
| NM | Portal | ONGARD | Portal | PDF | Portal | Limited | Portal |
| ND | Free | **Paid** | Paid | PDF | Free | Paid | Paid |
| CO | Portal | Portal/DL | Portal | Portal | Portal | Limited | Portal |
| OK | Bulk DL | Tax Comm. | Bulk DL | PDF | Bulk DL | Browse | Bulk DL |
| WY | Explorer | Explorer | Explorer | PDF | Explorer | Limited | Explorer |
| LA | SONRIS | SONRIS | SONRIS | PDF | SONRIS | Limited | SONRIS |
| PA | CSV DL | CSV DL | CSV DL | N/A | CSV DL | N/A | N/A |
| CA | Open Data | WellSTAR | WellSTAR | N/A | WellSTAR | Limited | WellSTAR |
| AK | DataMiner | DataMiner | DataMiner | PDF | DataMiner | Limited | DataMiner |

---

## 4. Data Formats & Access Methods

### Format Availability by State

| State | CSV | XLSX | PDF | ASCII Fixed | EBCDIC | Shapefile | ArcGIS API | JSON | HTML Tables |
|-------|-----|------|-----|-------------|--------|-----------|------------|------|-------------|
| TX | Yes | No | Yes | Yes (primary) | Yes | Yes | No | Yes (some) | Yes |
| NM | Yes | No | Yes | No | No | No | **Yes** | Yes | Yes |
| ND | Limited | No | Yes | No | No | No | Yes | No | Yes |
| CO | Yes | No | Yes | No | No | No | Yes | No | Yes |
| OK | Yes | **Yes** | Yes | No | No | Yes | Yes | No | Yes |
| WY | Limited | No | Yes | No | No | No | Yes | No | Yes |
| LA | No | Excel export | Yes | No | No | No | Yes | No | Yes |
| PA | **Yes** | No | Yes | No | No | No | Yes | No | Yes |
| CA | Yes | Excel export | Yes | No | No | No | Yes | No | Yes |
| AK | **Yes** | No | Yes | No | No | No | Yes | No | Yes |

### Access Methods Summary

| Method | States Using It | Pros | Cons |
|--------|----------------|------|------|
| **Bulk File Downloads (FTP/HTTPS)** | TX, OK, PA | Fastest, most complete data | Complex formats (EBCDIC, fixed-width ASCII) |
| **ArcGIS Hub/REST API** | NM, CO, OK, OH, CA | Standard API, multiple formats | Rate limits, pagination |
| **Web Query Interface** | TX (PDQ), ND, WY, LA | Real-time data | Anti-scraping blocks, session management |
| **Report Extracts (CSV)** | PA, OH | Clean CSV downloads | May need parameter selection |
| **Open Data Portal** | CA, NM | Standard API, well-documented | May lag behind real-time |
| **Data Miner Apps** | AK, MT, MI | Interactive query with export | Requires form interaction |
| **Subscription/Login** | ND | N/A | **Requires paid account** |

---

## 5. Scraping Difficulty Assessment

### Difficulty Rating by State

| State | Difficulty | Reason | Recommended Strategy |
|-------|-----------|--------|---------------------|
| **PA** | Easy | Clean CSV exports via GreenPort, no login | Direct HTTP download of CSV files |
| **OK** | Easy | Nightly CSV/XLSX bulk downloads, no login | Direct HTTP download of data files |
| **TX** | Easy-Medium | Excellent bulk downloads (but complex formats); **do NOT scrape PDQ** | Bulk download + format conversion (EBCDIC/ASCII parsing) |
| **CA** | Easy | Open Data API + WellSTAR exports | API calls to data.ca.gov |
| **AK** | Easy-Medium | Data Miner with CSV export | Browser automation for Data Miner forms |
| **NM** | Medium | ArcGIS Hub REST API, multiple systems | ArcGIS REST API calls + OCD portal scraping |
| **CO** | Medium | COGIS query interface, some downloadable data | COGIS queries + bulk data downloads |
| **OH** | Medium | ArcGIS + RBDMS reports, weekly updates | ArcGIS Open Data + direct downloads |
| **WY** | Medium-Hard | Data Explorer interface, limited bulk options | Browser automation (Playwright) for Data Explorer |
| **ND** | Hard | **Requires paid subscription** for production data; login-gated | Subscription account + authenticated scraping |
| **LA** | Hard | Complex SONRIS application, recently redesigned, Oracle backend | Browser automation, IDR report export |
| **WV** | Medium-Hard | Multiple fragmented systems | Combine TAGIS GIS + WVGS search |
| **MS** | Medium | Older web application, limited bulk download | Form-based scraping |

### Technical Challenges by Category

**JavaScript-Heavy Sites (require browser automation)**:
- Louisiana SONRIS (complex web application)
- Wyoming WOGCC Data Explorer
- North Dakota NorthSTAR system
- Some COGIS features in Colorado
- ArcGIS-based mapping portals (NM, OK, OH, CA)

**Login/Subscription Required**:
- North Dakota DMR ($100-$500/year subscription)
- Some ONGARD features in New Mexico

**Anti-Bot Protection**:
- Texas RRC PDQ system (explicitly detects and blocks automated tools)
- Some state sites behind Cloudflare or similar CDNs

**Legacy Technology**:
- Texas RRC data in EBCDIC format (IBM mainframe encoding)
- Louisiana SONRIS (Oracle-backed, complex query system)
- Wyoming legacy portal (ColdFusion-based at pipeline.wyo.gov)
- Some state sites use ColdFusion, classic ASP, or Java applets

**Data Quality Issues**:
- Inconsistent field naming across states
- Missing or null values common
- Date format variations
- Coordinate system differences (NAD 27, NAD 83, WGS 84)

---

## 6. Common Identifiers

### API Well Number System

The API (American Petroleum Institute) well number is the universal well identification system used across all US states. Format: **XX-YYY-ZZZZZ-SS-EE** (up to 14 digits).

| Segment | Digits | Description | Example |
|---------|--------|-------------|---------|
| State Code | 2 | Alphabetical state numbering (IBM 1952 scheme) | 42 = Texas |
| County Code | 3 | County within state | 453 = Travis County, TX |
| Well Sequence | 5 | Unique well number within county | 12345 |
| Sidetrack Code | 2 (optional) | Directional sidetrack (00 = original vertical) | 01 = first sidetrack |
| Event Code | 2 (optional) | Sequence of events/completions | 00 = original completion |

**Common State Codes**:

| Code | State | Code | State |
|------|-------|------|-------|
| 01 | Alabama | 30 | Montana |
| 02 | Alaska (old) / 50 (current) | 31 | Nebraska |
| 03 | Arizona | 32 | Nevada |
| 05 | Arkansas | 33 | New Hampshire |
| 06 | California | 35 | New Mexico |
| 08 | Colorado | 36 | New York |
| 15 | Kansas | 37 | North Carolina |
| 16 | Kentucky | 38 | North Dakota |
| 17 | Louisiana | 34 | Ohio |
| 21 | Michigan | 35 | Oklahoma |
| 23 | Mississippi | 37 | Oregon |
| 25 | Montana | 37 | Pennsylvania |
| 42 | Texas | 47 | West Virginia |
| 43 | Utah | 49 | Wyoming |

**Full mapping**: See https://en.wikipedia.org/wiki/API_well_number for complete list.

**Important**: The API number standard is evolving. Enverus has proposed a "US Well Number" (UWN) as a successor, but API numbers remain the primary identifier used by all state agencies.

### Other Identifier Types by State

| Identifier | States | Description |
|-----------|--------|-------------|
| **API Number** | All states | Universal well identifier (10-14 digits) |
| **Permit Number** | TX, ND, CO, NM, WY, OK | State-issued drilling permit number |
| **Lease Number** | TX, NM, OK | Identifies production lease (multiple wells) |
| **Well Number** | All states | Operator-assigned well identifier within lease |
| **Field Code** | TX, OK, LA, NM | Identifies oil/gas field |
| **District** | TX | RRC administrative district (1-10, 6E, 7B, 7C, 8A, 9) |
| **Operator Number/ID** | TX (P-5), OK, CO, NM | State-assigned operator identifier |
| **NDIC File Number** | ND | North Dakota-specific well file number |
| **Serial Number** | LA | Louisiana-specific well serial number |
| **County Code** | All states | FIPS county code or state-specific code |

### Cross-Referencing Challenges

- API numbers may be stored with or without dashes (4245312345 vs 42-453-12345)
- Some states use 10-digit API, others use 12 or 14-digit
- Lease numbers in Texas may map to multiple wells
- Operator names are not standardized across states (abbreviations, DBA names, mergers)
- Coordinate systems vary (NAD 27 for legacy TX data, NAD 83, WGS 84)

---

## 7. Existing Open-Source Tools & Projects

### Active/Notable Projects

| Project | URL | Description | States Covered | Tech Stack | Status |
|---------|-----|-------------|---------------|------------|--------|
| **rrc-scraper** | https://github.com/derrickturk/rrc-scraper | Texas RRC production data scraper | TX only | Python | Active |
| **TXRRC_data_harvest** | https://github.com/mlbelobraydi/TXRRC_data_harvest | TX RRC data download and organization | TX only | Python (Jupyter) | Active |
| **public-oil-gas-data** | https://github.com/derrickturk/public-oil-gas-data | Guide to freely available state data | Multiple | Documentation | Reference |
| **drilling-data-tools** | https://github.com/CMU-CREATE-Lab/drilling-data-tools | Nationwide well data scraper & visualizer | 34 states | JavaScript | Research |
| **PyFrackETL** | https://gist.github.com/KhepryQuixote/3704e1a727cf9913a41c | Multi-state well data download scripts | Multiple | Python | Gist |
| **oil-and-gas** | https://github.com/potokrm/oil-and-gas | ND web crawler for well data | ND | Python | Older |

### Key Observations from Existing Projects

1. **No comprehensive multi-state scraper exists** - Most projects target a single state (primarily Texas).
2. **Texas RRC is the most-scraped** due to its extensive bulk downloads, but format conversion (EBCDIC) is a challenge.
3. **CMU drilling-data-tools** is the closest to nationwide coverage but focuses on visualization, not document scraping.
4. The **derrickturk/public-oil-gas-data** repo is a useful reference for understanding what data is available where.
5. Most existing tools are **research-grade**, not production-ready.
6. The **rrc-scraper** project warns about TX RRC detecting automated access to the PDQ system.

### Data Aggregation Services (Non-Open-Source Reference)

| Service | Notes |
|---------|-------|
| **FracTracker Alliance** | https://www.fractracker.org/data/data-resources/ - Curated data library with links to state data by state |
| **WellDatabase** | https://welldatabase.com - Commercial tool with state-by-state data pages |
| **DrillingEdge** | https://www.drillingedge.com/ - Nationwide well data coverage |
| **USGS Links** | https://www.usgs.gov/core-research-center/links-state-well-data - Comprehensive links to state portals |
| **Library of Congress** | https://guides.loc.gov/oil-and-gas-industry/statistical-data - Research guide |

---

## 8. Cross-State Data Standards

### RBDMS (Risk Based Data Management System)

**Developed by**: Ground Water Protection Council (GWPC) with US Department of Energy
**URL**: https://www.rbdms.org/
**Significance**: The majority of oil & gas states use RBDMS to collect and manage regulatory data.

**Key Points**:
- RBDMS is a suite of integrated software products for state oil, gas, and UIC regulation
- Adopted as a national standard for state regulatory data management
- Data collected covers permits through production through plugging
- Originally Access-based, now .NET technologies
- **RBDMS WellFinder**: Free public mobile app showing nearby wells with links to state websites
- States using RBDMS share similar data structures, which helps with normalization

**States using RBDMS**: Oklahoma, Montana, Mississippi, and many others

### FracFocus Chemical Disclosure Registry

**URL**: https://fracfocus.org/
**Data Download**: https://fracfocus.org/data-download
**Significance**: Voluntary hydraulic fracturing chemical disclosure database

**Key Points**:
- Data available in SQL and CSV formats as downloadable ZIP files
- Updated 5 days/week with latest disclosures
- **API available** for automated downloading
- Three main tables: RegistryUpload (headers), RegistryUploadPurpose (additives), RegistryUploadIngredients (chemicals)
- SQL backup uses MS SQL Server 2019 format
- Data dictionary included in readme
- Managed by GWPC (same org as RBDMS)

---

## 9. Commercial Data Aggregators

Understanding the commercial landscape helps identify what data is valuable and how competitors approach the problem.

| Company | Product | Notes |
|---------|---------|-------|
| **Enverus** | DrillingInfo | Largest O&G data platform. Claims 98% US producer coverage. Partnerships with producers. Very expensive. |
| **Novi Labs** | Energy Analytics | Alternative to Enverus. Focus on accuracy and predictive analytics. |
| **Conduit Resources** | Conduit Well Finder | Direct link between Enverus data and state regulatory sites. Aggregates completion/production data. |
| **TGS** | Well Data Products | Industry-leading visualization and analytics for well data. |
| **IHS Markit / S&P Global** | Various | Major energy data provider. |

**Relevance to Project**: These companies charge significant subscription fees for aggregated state data. A well-built open scraper that normalizes state data could provide significant value. The fact that companies like Conduit explicitly bridge Enverus and state regulatory sites confirms the gap this project addresses.

---

## 10. Recommendations for Implementation

### Architecture Recommendations

1. **Use bulk downloads where available** (TX, OK, PA) rather than scraping query interfaces. This is faster, more reliable, and less likely to be blocked.

2. **Implement state-specific adapters** - Each state needs its own scraping strategy:
   - `BulkDownloadAdapter` (TX, OK, PA, CA) - HTTP downloads of CSV/data files
   - `ArcGISAdapter` (NM, OH, CO GIS data) - ArcGIS REST API calls
   - `BrowserAdapter` (LA SONRIS, WY Data Explorer, ND with subscription) - Playwright automation
   - `OpenDataAdapter` (CA, NM Hub) - Standard API queries

3. **Format conversion pipeline** - Priority parsers needed:
   - EBCDIC to UTF-8 converter (Texas data)
   - Fixed-width ASCII parser with layout definitions (Texas, some others)
   - dBase (.dbf) reader
   - CSV/XLSX standard parsers
   - PDF text extraction (permits, completion reports, hearing orders)
   - TIFF/image OCR (scanned legacy documents)

4. **API number normalization** - Build a universal parser that handles:
   - 10, 12, and 14-digit variants
   - With and without dashes
   - Leading zeros
   - State code validation

5. **Rate limiting and politeness** - Essential for all scrapers:
   - Respect robots.txt
   - Implement configurable delays between requests
   - Use reasonable user-agent strings
   - Cache responses to avoid re-fetching
   - Texas PDQ: do NOT scrape; use bulk downloads only

### Suggested Implementation Order

**Phase 1** (easiest, highest value):
1. Texas RRC bulk downloads (critical volume, straightforward downloads, complex format parsing)
2. Oklahoma OCC bulk downloads (easy CSV/XLSX, well-organized)
3. Pennsylvania GreenPort CSV exports (cleanest data of any state)

**Phase 2** (API-based access):
4. New Mexico OCD Hub (ArcGIS REST API)
5. California CalGEM (Open Data API)
6. Colorado ECMC COGIS (mix of downloads and queries)

**Phase 3** (browser automation needed):
7. Wyoming WOGCC Data Explorer
8. Alaska AOGCC Data Miner
9. Louisiana SONRIS (complex, recently redesigned)

**Phase 4** (special handling):
10. North Dakota DMR (requires subscription account)
11. Ohio ODNR (ArcGIS + RBDMS)
12. Remaining Tier 3-4 states

### Key Technical Decisions

| Decision | Recommendation | Reason |
|----------|---------------|--------|
| Browser automation | Playwright (not Selenium) | Faster, more reliable, better Python support |
| HTTP client | httpx or aiohttp | Async support for parallel downloads |
| PDF parsing | pdfplumber + pytesseract | Text extraction + OCR for scanned docs |
| Data storage | PostgreSQL + S3/MinIO | Structured data + document storage |
| EBCDIC conversion | Custom parser with layout definitions | TX data requires this |
| Scheduling | Configurable per-state cadence | TX: weekly, OK: nightly, PA: monthly |

### Legal & Ethical Considerations

- All data targeted is **public records** from government agencies
- Texas RRC explicitly prohibits automated access to PDQ (use bulk downloads instead)
- North Dakota requires paid subscription for production data
- Implement reasonable rate limiting on all scrapers
- Include clear user-agent identifying the tool
- Respect robots.txt directives
- Cache aggressively to minimize server load
- Some document types (well logs, survey data) may have copyright considerations even if publicly accessible

---

## Appendix A: Complete URL Reference

### Primary State Regulatory Portals

| State | Portal URL |
|-------|-----------|
| Texas | https://www.rrc.texas.gov/ |
| New Mexico | https://www.emnrd.nm.gov/ocd/ |
| North Dakota | https://www.dmr.nd.gov/oilgas/ |
| Colorado | https://ecmc.state.co.us/ |
| Oklahoma | https://oklahoma.gov/occ/divisions/oil-gas.html |
| Wyoming | https://wogcc.wyo.gov/ |
| Louisiana | https://www.sonris.com/ |
| Pennsylvania | https://www.pa.gov/agencies/dep/data-and-tools/reports/oil-and-gas-reports |
| California | https://www.conservation.ca.gov/calgem/ |
| Alaska | https://www.commerce.alaska.gov/web/aogcc/ |
| Ohio | https://oilandgas.ohiodnr.gov/ |
| West Virginia | https://dep.wv.gov/oil-and-gas |
| Kansas | https://www.kgs.ku.edu/Magellan/Qualified/ |
| Utah | https://datamining.ogm.utah.gov/ |
| Montana | https://bogapps.dnrc.mt.gov/ |
| Michigan | https://www.egle.state.mi.us/dataminer/ |
| Mississippi | https://www.ogb.state.ms.us/ |
| Arkansas | https://www.aogc.state.ar.us/welldata/wells/default.aspx |
| New York | https://extapps.dec.ny.gov/cfmx/extapps/GasOil/search/wells/ |
| Kentucky | https://www.uky.edu/KGS/emsweb/ |
| Illinois | https://prairie-research.maps.arcgis.com/ |
| Indiana | https://legacy.igws.indiana.edu/pdms/ |
| Nebraska | https://nogcc.ne.gov/ |

### Key Data Download URLs

| Resource | URL |
|----------|-----|
| TX RRC Bulk Downloads | https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/ |
| OK OCC Data Files | https://oklahoma.gov/occ/divisions/oil-gas/oil-gas-data.html |
| PA GreenPort Extracts | https://greenport.pa.gov/ReportExtracts/OG/Index |
| NM OCD Hub | https://ocd-hub-nm-emnrd.hub.arcgis.com/ |
| CA Open Data (WellSTAR) | https://data.ca.gov/dataset/wellstar-oil-and-gas-wells |
| AK AOGCC Data Miner | http://aogweb.state.ak.us/DataMiner4/Forms/WellData.aspx |
| CO ECMC Downloads | https://ecmc.colorado.gov/data-maps-reports/downloadable-data-documents |
| WY WOGCC Data Explorer | https://dataexplorer.wogcc.wyo.gov/ |
| OH ODNR Open Data | https://gis-odnr.opendata.arcgis.com/ |
| NY DEC Downloadable Data | https://dec.ny.gov/environmental-protection/oil-gas/wells-data-geographical-information/downloadable-data |
| FracFocus Data Download | https://fracfocus.org/data-download |
| USGS State Links | https://www.usgs.gov/core-research-center/links-state-well-data |

### Useful Reference Links

| Resource | URL |
|----------|-----|
| API Well Number (Wikipedia) | https://en.wikipedia.org/wiki/API_well_number |
| RBDMS (GWPC) | https://www.rbdms.org/ |
| FracTracker Data Library | https://www.fractracker.org/data/data-resources/ |
| LOC Oil & Gas Guide | https://guides.loc.gov/oil-and-gas-industry/statistical-data |
| EIA Production Data | https://www.eia.gov/naturalgas/data.php |
| derrickturk/public-oil-gas-data | https://github.com/derrickturk/public-oil-gas-data |
