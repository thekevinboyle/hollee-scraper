# Oil & Gas Data Models, Standards & Domain Knowledge

**Research Date**: 2026-03-27
**Purpose**: Comprehensive domain reference for the Oil & Gas Document Scraper project

---

## Table of Contents

1. [Industry Data Models & Standards](#1-industry-data-models--standards)
2. [API Number Format & Structure](#2-api-number-format--structure)
3. [Common O&G Identifiers & Their Relationships](#3-common-og-identifiers--their-relationships)
4. [Key Document Types in O&G Regulation](#4-key-document-types-in-og-regulation)
5. [Key Data Fields That Matter](#5-key-data-fields-that-matter)
6. [Data Quality Issues Common in O&G Data](#6-data-quality-issues-common-in-og-data)
7. [Commercial O&G Data Vendors](#7-commercial-og-data-vendors)
8. [Open Data Sources & APIs](#8-open-data-sources--apis)
9. [The Source of Truth Problem](#9-the-source-of-truth-problem)
10. [How State Data Feeds Into Commercial Products](#10-how-state-data-feeds-into-commercial-products)
11. [State Regulatory Agency Registry](#11-state-regulatory-agency-registry)
12. [Implications for the Scraper Project](#12-implications-for-the-scraper-project)

---

## 1. Industry Data Models & Standards

### 1.1 PPDM (Professional Petroleum Data Management)

**Current Version**: PPDM 3.9

The PPDM data model is the de-facto relational data model for oil and gas master data management. Developed collaboratively by the petroleum industry, it provides a structured approach to organizing well data, promoting consistency and enhancing data quality.

**Scope**: PPDM 3.9 describes **over 60 subject areas** using relational data definition language (DDL). Many subject areas are industry-neutral.

**Key Subject Areas**:

| Category | Subject Areas |
|----------|--------------|
| **Wells** | Wells, Wellbores, Well Status, Well Identification |
| **Production** | Production Entities, Production Reporting, Production Strings, Production Facilities, Production Lease Units |
| **Land** | Land Rights, Spacing Units, Instruments, Entitlements |
| **Geology** | Stratigraphy, Lithology, Paleontology, Fossils, Stratigraphic Field Stations |
| **Seismic** | Seismic (2D/3D survey data) |
| **Business** | Business Associates, Contracts, Obligations, Partnerships & Interest Sets, Finances |
| **Regulatory** | Applications, Consents, Consultations, Contests, Notifications, Restrictions |
| **HSE** | Health Safety and Environment |
| **Reference** | Areas, Classification Systems, Coordinate Reference Systems, Reporting Hierarchies |
| **Infrastructure** | Equipment, Support Facilities |
| **Reserves** | Reserves Reporting, Fields, Pools |
| **Data Mgmt** | Records Product & Info Mgmt, Data Management |
| **Sample** | Sample Analysis, Sample Management |

**Key Tables** (representative, not exhaustive):

| Table | Description |
|-------|-------------|
| `WELL` | General/header information about a well (an actual or proposed hole in the ground) |
| `WELL_BORE` | Cylindrical holes created by a drill; a well may have 0, 1, or more wellbores |
| `WELL_STATUS` | Historical account of operating status with dates |
| `WELL_NODE` | Surface and subsurface locations |
| `PRODUCTION_ENTITY` | Entity that production is reported against (well, lease, field) |
| `PDEN_VOL_SUMMARY` | Production volumes summarized by period |
| `BUSINESS_ASSOCIATE` | Operators, owners, regulators, service companies |
| `AREA` | Geographic/administrative areas |
| `LAND_RIGHT` | Mineral rights, leases, surface rights |
| `SPACING_UNIT` | Regulatory spacing units |

**Key Relationships**:
- Wells connect to wellbores via `PARENT_UWI` and `WELL_RELATIONSHIP`
- Production entities link to wells and business associates (operators)
- Recursive relationships stored in parent tables (e.g., `RM_DATA_STORE` self-references for containment)

**Core Principles**: Data accuracy, consistency, accessibility, and standardized formats/definitions to eliminate ambiguity.

---

### 1.2 OSDU (Open Subsurface Data Universe)

**Managed by**: The Open Group OSDU Forum (industry consortium including BP, Chevron, Shell, TotalEnergies, SLB, etc.)

OSDU is a cloud-native, open-source, standards-based, technology-agnostic data platform for the oil and gas industry. It aims to eliminate data silos and enable seamless data flow from exploration to production.

**Architecture**:
- JSON-based common technical data container structure
- Schema IDs follow: `<authority:source:entity-type:major.minor.patch>` (e.g., `osdu:wks:master-data--Well:1.0.0`)
- RESTful API-based access
- Cloud-native (implementations exist on AWS, Azure, GCP)

**Key Data Types**:

| Type | Kind | Description |
|------|------|-------------|
| **Master Data** | `master-data--Well` | Geolocated well facility with names, aliases, country, organization |
| **Master Data** | `master-data--Wellbore` | Aggregator of datasets (fluid reports, logs, markers, trajectories) |
| **Work Product Component** | `work-product-component--WellLog` | Digital well log data |
| **Work Product Component** | `work-product-component--WellboreTrajectory` | Wellbore path from surface to subsurface target |
| **Work Product Component** | `work-product-component--WellboreMarkerSet` | Formation tops/picks at noted depths |

**Key Wellbore Attributes**:
- `FacilityName` / `FacilityNameAliases`
- `WellID` / `WellboreID`
- `TopDepthMeasuredDepth` / `BaseDepthMeasuredDepth`
- Location data (latitude, longitude, spatial references)

**OSDU vs. PPDM**: These are complementary, not competing. PPDM provides semantic definitions and data management standards; OSDU provides the cloud-native platform architecture. PPDM definitions have directly fed into OSDU schemas. The industry envisions OSDU certifying technology while PPDM certifies people and data practices.

---

### 1.3 Energistics (WITSML / PRODML / RESQML)

Energistics is a global non-profit consortium maintaining open data exchange standards for the energy industry. The three main standards share a common foundation called **EnergyML**.

| Standard | Full Name | Scope | Current Version |
|----------|-----------|-------|----------------|
| **WITSML** | Wellsite Information Transfer Standard Markup Language | Drilling, completions, interventions, logging, MWD/LWD, mud logging, perforation, fracing, stimulation. Real-time wellsite data. | v2.1 |
| **PRODML** | Production Markup Language | Producing wells from reservoir-wellbore boundary to custody transfer point. Automated production data acquisition, monitoring, optimization, reporting. | v2.3 |
| **RESQML** | Reservoir Data Exchange Language | Reservoir life cycle from structural modeling through simulation to production surveillance. | v2.2 |

**Common Foundation**: All standards use Energistics Common v2.3.

**Key Difference from PPDM/OSDU**: Energistics standards focus on real-time data exchange and transfer between systems, whereas PPDM/OSDU focus on data storage and management at rest.

---

### 1.4 RBDMS (Risk Based Data Management System)

**Managed by**: Ground Water Protection Council (GWPC)

RBDMS is a suite of integrated software tools used by **23 state oil and gas agencies** for regulatory data management. It assists with:
- Permit applications
- Environmental inspections
- Oil, gas, UIC, water, and environmental data
- Workflow management

RBDMS is the backbone behind many state regulatory databases that this scraper will need to interact with. States using RBDMS share a common underlying data model, which means data from these states may have more structural consistency.

Originally built in Access 1.1, now evolved to .NET technologies with web-enabled interfaces.

---

## 2. API Number Format & Structure

The **API (American Petroleum Institute) well number** is the primary unique identifier for oil and gas wells in the United States. It is a "unique, permanent, numeric identifier" assigned to each well.

### 2.1 Complete 14-Digit Structure

Format: `XX-YYY-ZZZZZ-SS-EE`

| Digits | Name | Description | Example |
|--------|------|-------------|---------|
| 1-2 | **State Code** | State where well surface is located | `42` = Texas |
| 3-5 | **County Code** | County within the state (uses odd numbers; even reserved for new counties) | `501` = Yoakum County |
| 6-10 | **Unique Well Identifier** | Unique number within the county | `20130` |
| 11-12 | **Directional Sidetrack Code** | `00` = original vertical; `01` = first sidetrack; etc. | `03` |
| 13-14 | **Event Sequence Code** | Distinguishes separate operations in a single borehole | `00` |

**Full Example**: `42-501-20130-03-00` = Texas, Yoakum County, well 20130, 3rd sidetrack, original event.

### 2.2 Unique Well Identifier Ranges

| Range | Assignment |
|-------|-----------|
| 00001-20000 | **Historical**: Pre-1967, assigned by Petroleum Information |
| 20001-60000+ | **Current**: Post-1967, assigned by state agencies during permitting |
| 60001-95000 | **Reserved**: For informationally significant wells lacking official assignment |
| 95001-99999 | **Exempt**: Proprietary/confidential well information |

### 2.3 State Code Reference (Selected Major Producing States)

| Code | State | Code | State |
|------|-------|------|-------|
| 02 | Alaska | 30 | Montana |
| 04 | California | 32 | New Mexico |
| 05 | Colorado | 33 | New York |
| 15 | Kansas | 35 | North Dakota |
| 17 | Louisiana | 36 | Ohio |
| 21 | Michigan | 37 | Oklahoma |
| 25 | Mississippi | 39 | Pennsylvania |
| 42 | Texas | 45 | Utah |
| 47 | West Virginia | 49 | Wyoming |

**Offshore Pseudo-State Codes**: `50` = Alaska Offshore, `55` = Pacific Coast, `60` = Northern Gulf of Mexico, `61` = Atlantic Coast

### 2.4 Historical Notes & Known Issues

- System originated from Petroleum Information's internal scheme (1956 AAPG conference)
- Formalized by API Subcommittee in 1962; current standard from January 1979
- Custody transferred to PPDM Association in 2010 (updated standards in 2013)
- **State variations**: Illinois and North Dakota have no break between historical/current numbers; Arkansas starts current numbers at 10001; Texas at 30001; Colorado, Michigan, Utah have special systems
- **Overflow problem**: Kern County, California exceeded available unique identifier digits and now uses two county codes (029 and 030)
- **Not all 14 digits are always used**: Many systems store only 10 or 12 digits, dropping sidetrack and/or event codes

### 2.5 "The API Number Is Dead" (Enverus Perspective)

Enverus has argued that the API number system has inherent limitations for modern horizontal drilling with multiple laterals and complex wellbore architectures. They propose the "US Well Number" as a successor that better handles:
- Multi-lateral wells
- Re-entries and re-completions
- Wellbore-level vs. completion-level identification
- Cross-state horizontal wells

---

## 3. Common O&G Identifiers & Their Relationships

### 3.1 Identifier Types

| Identifier | Scope | Assigned By | Permanence | Format |
|-----------|-------|-------------|-----------|--------|
| **API Number** | National | State regulatory agency (at permitting) | Permanent to the wellbore | 10-14 digit numeric |
| **UWI (Unique Well Identifier)** | US/Canada | PPDM standard based on API | Permanent | Alphanumeric (country + API-based) |
| **Permit Number** | State-level | State regulatory agency | Per-event (can change on re-permit) | Varies by state |
| **Well Number** | Operator-defined | Operator | Can change with ownership transfer | Free text |
| **Lease Number** | State-level | State regulatory agency | Per-lease (multiple wells) | Varies by state |
| **Lease Name** | Operator-defined | Operator/landowner | Can change | Free text |
| **Operator Number** | State-level | State regulatory agency | Per-operator, per-state | Numeric |
| **RRC District/Lease ID** | Texas-specific | Railroad Commission of Texas | Per-lease | Numeric |

### 3.2 How They Relate

```
Operator (has Operator Number per state)
  └── holds Lease (has Lease Number, Lease Name)
        └── contains Well(s) (each has API Number)
              └── has Wellbore(s) (identified by API sidetrack code)
                    └── has Completion(s) (identified by API event sequence)
                          └── has Production (reported at lease OR well level)

Permit Number is assigned during the permitting event
  └── May or may not correspond to the API number
  └── A well can have multiple permits over its lifetime
```

### 3.3 The "Which Number Are You Using" Problem

This is the core confusion referenced in the PRD. The same physical well can be referenced by:
- Its 10-digit API number (no sidetrack/event)
- Its 12-digit API number (with sidetrack)
- Its 14-digit API number (with sidetrack + event)
- Its permit number (which may differ from the API)
- Its operator-assigned well name/number
- Its lease name and well number combination
- Its state-specific identifiers (e.g., Texas RRC lease ID)

**Critical implication for the scraper**: Documents from different sources may reference the same well using different identifiers. The system must maintain a mapping table that links all known identifiers for a single physical well.

---

## 4. Key Document Types in O&G Regulation

### 4.1 Well Permits / Drilling Permits

**What**: Application and approval to drill, deepen, plug back, or convert a well.

**Common Forms**:
| State | Form | Name |
|-------|------|------|
| Texas | W-1 | Application to Drill |
| Oklahoma | 1002A | Intent to Drill |
| Colorado | Form 2 | Application for Permit to Drill |
| North Dakota | Form 1 | Application for Permit to Drill |
| New York | APD | Application for Permit to Drill, Deepen, Plug Back or Convert |

**Key Data Fields**:
- Operator name and number
- Well name and number
- API number (assigned at this stage)
- Surface location (lat/long, PLSS section-township-range)
- Bottom hole location (for directional/horizontal wells)
- Proposed total depth
- Target formation(s)
- Lease name
- Casing program (proposed)
- Anticipated spud date

### 4.2 Completion Reports

**What**: Filed after a well is drilled and completed (or determined to be a dry hole). Documents what was actually done vs. what was planned.

**Common Forms**:
| State | Form | Name |
|-------|------|------|
| Texas | W-2 (oil) / G-1 (gas) | Oil/Gas Well Completion Report |
| Colorado | Form 5 / 5A | Completed Interval Report |
| Oklahoma | 1002C | Completion Report |

**Key Data Fields**:
- Actual total depth (TVD and MD)
- Lateral length (horizontal wells)
- Casing details (size, weight, depth set, cement)
- Perforation intervals (top and bottom depths)
- Number of frac stages
- Proppant type and volume
- Fluid volume pumped
- Initial production rates (IP - oil, gas, water)
- Formation(s) completed in
- Spud date, completion date, first production date

### 4.3 Production Reports (Monthly/Annual)

**What**: Periodic reporting of volumes produced from wells/leases.

**CRITICAL DISTINCTION**: Some states report at the **well level** (one record per well per month), while others report at the **lease level** (one record per lease per month, which may contain multiple wells).

| Reporting Level | States | Implication |
|----------------|--------|-------------|
| **Well-level** | Oklahoma, North Dakota, Colorado, Pennsylvania, New Mexico, Wyoming | Direct well performance data available |
| **Lease-level** | Texas | Must allocate/estimate well-level production from lease totals |

**Texas Lease-Level Allocation** (the hardest problem):
Texas requires operators to report only at the lease level via Form PR. To get well-level data, providers must allocate using:
1. Test data and decline curves (most reliable)
2. Historical production decline curves
3. Allowable-based weighting
4. Pro-rata division by producing days (least reliable)

**Key Data Fields**:
- Reporting period (month/year)
- Oil production (barrels - BBL)
- Gas production (thousand cubic feet - MCF)
- Water production (barrels - BBL)
- Casinghead gas / condensate volumes
- Days produced
- Well/lease status for the period
- Disposition (sold, used on lease, flared, vented, injected)

**Common Forms**:
| State | Form |
|-------|------|
| Texas | Form PR (Production Report) |
| Oklahoma | Form 1012D |
| Federal (EIA) | Form EIA-914 (Monthly Crude Oil, Lease Condensate, and Natural Gas Production Report) |

### 4.4 Spacing Orders / Pooling Orders

**What**: Regulatory orders that define the minimum distance between wells and/or combine mineral interests for drilling purposes.

**Spacing Orders**: Set minimum distance between:
- A well and the boundary lines of adjacent tracts
- A well and other wells on the same lease

**Pooling Orders**: Combine small mineral interest tracts into a single drilling unit.
- **Voluntary pooling**: Owners agree to combine interests
- **Forced/compulsory pooling**: Regulatory agency compels holdout owners to join
- Orders specify: unit boundaries, cost sharing, royalty rates, bonus payments

**Key Data Fields**:
- Legal description of the spacing/pooling unit
- Operator name
- Formation(s) covered
- Well locations within the unit
- Ownership interests and percentages
- Royalty rates and bonus terms (for pooling)

### 4.5 Plugging Reports

**What**: Filed when a well is permanently plugged and abandoned (P&A).

**Common Forms**:
| State | Form |
|-------|------|
| Texas | W-3 (Plugging Report) |
| Colorado | Form 6 |

**Key Data Fields**:
- Plug date
- Cement plugs placed (depth intervals)
- Casing left in hole
- Surface restoration status
- Final well status (DA = Dry and Abandoned, PA = Plugged and Abandoned)

### 4.6 Inspection Records

**What**: Records of physical inspections by state regulators.

**Key Data Fields**:
- Inspection date and inspector
- Well/facility inspected
- Type of inspection (routine, complaint-driven, witnessed operation)
- Findings (compliance status, violations noted)
- Follow-up actions required

### 4.7 Incident Reports

**What**: Reports of spills, leaks, blowouts, or other environmental/safety incidents.

**Key Data Fields**:
- Incident date and time
- Location
- Type of incident (spill, leak, blowout, fire)
- Materials released (oil, produced water, gas)
- Volume released and recovered
- Cause
- Corrective actions

---

## 5. Key Data Fields That Matter

### 5.1 Production Volumes

| Field | Unit | Abbreviation | Notes |
|-------|------|-------------|-------|
| Oil production | Barrels | BBL | 42 US gallons per barrel |
| Gas production | Thousand cubic feet | MCF | "M" = thousand in O&G convention |
| Water production | Barrels | BBL | Same unit as oil |
| Condensate | Barrels | BBL | Light liquid hydrocarbons |
| NGL (Natural Gas Liquids) | Barrels | BBL | Extracted from gas stream |
| BOE (Barrel of Oil Equivalent) | Barrels equivalent | BOE | ~6 MCF gas = 1 BOE (varies: 5,800-6,000 cf) |

**Important**: There is NO single standard conversion factor for BOE. The actual equivalency varies based on gas composition, pressure, and temperature conditions. The standard approximation is **6 MCF = 1 BOE** but this can vary between companies.

### 5.2 Well Location

| Format | Description | Where Used |
|--------|-------------|-----------|
| **Latitude / Longitude** | Decimal degrees or DMS | Modern systems, GIS |
| **Section-Township-Range (PLSS)** | Public Land Survey System | Western US states (30 of 50 states) |
| **Metes & Bounds** | Legal land description | Eastern/original colony states (TX, some others) |
| **Abstract / Survey** | Texas-specific survey system | Texas |
| **Offshore blocks** | OCS block/area designations | Federal offshore (BSEE) |

**PLSS Format**: `Section X, Township YN/S, Range ZE/W, Nth Principal Meridian`
- **Section**: 1 square mile (640 acres), numbered 1-36 within a township
- **Township**: 6x6 grid of sections, identified by distance N/S from baseline
- **Range**: Distance E/W from principal meridian
- Subdivisions: Quarter sections (NE, NW, SE, SW), quarter-quarters, etc.
- Example: `NW1/4 of NE1/4 of Section 8, T2N, R1E, 6th PM`

**Implication for scraper**: Must handle multiple location formats and convert between them. Many state sites use PLSS; modern databases prefer lat/long.

### 5.3 Well Depth

| Field | Description |
|-------|-------------|
| **Total Depth (TD)** | Deepest point reached by the drill bit |
| **True Vertical Depth (TVD)** | Vertical distance from surface to bottom |
| **Measured Depth (MD)** | Actual length along the wellbore path (longer than TVD for deviated wells) |
| **Kickoff Point (KOP)** | Depth where horizontal deviation begins |
| **Lateral Length** | Horizontal distance drilled (modern horizontal wells: 5,000-15,000+ ft) |

### 5.4 Other Critical Fields

| Field | Description |
|-------|-------------|
| **Operator Name** | Current operator of the well (changes with transfers) |
| **Well Status** | Current operational status (see section 5.5) |
| **Spud Date** | Date drilling began (first penetration of earth) |
| **Completion Date** | Date well was completed for production |
| **First Production Date** | Date first commercial production occurred |
| **Formation / Target Zone** | Geological formation being produced (e.g., Wolfcamp, Eagle Ford, Bakken) |
| **Well Type** | Oil, gas, injection, disposal, monitoring, etc. |
| **Well Configuration** | Vertical, directional, horizontal |

### 5.5 Well Status Codes

Status codes are **state-specific** but commonly include:

| Code | Status | Description |
|------|--------|-------------|
| AC | Active | Currently producing or operational |
| PR | Producing | Actively producing hydrocarbons |
| SI | Shut-In | Completed but not producing; mechanically capable of production; inactive < 12 months |
| TA | Temporarily Abandoned | Not mechanically capable of production without intervention; perforations isolated |
| PA | Plugged and Abandoned | Permanently plugged; well is done |
| DA | Dry and Abandoned | Drilled but no commercial quantities found; plugged |
| DG | Drilling | Currently being drilled |
| WO | Waiting on Completion | Drilled but not yet completed |
| IJ | Injecting | Water/gas injection well |
| AB | Abandoned | Abandoned wellbore or completion |
| AL | Abandoned Location | Location was permitted but never drilled |
| CL | Closed | Closed (regulatory) |
| CM | Commingled | Producing from multiple zones |
| DM | Domestic | Domestic use well |
| RC | Recompleted | Re-completed in a new zone |
| XX | Location | Permit approved, location staked, not yet drilled |

**Critical warning**: Each state has its OWN set of status codes with different meanings. The scraper must maintain a state-specific status code mapping table.

---

## 6. Data Quality Issues Common in O&G Data

### 6.1 Unit Inconsistencies

| Issue | Example |
|-------|---------|
| Gas volume units | MCF vs. MMCF vs. BCF vs. CF (off by factors of 1,000) |
| Gas pressure conditions | Standard vs. actual conditions |
| BOE conversions | 5,800 cf vs. 6,000 cf vs. variable per company |
| Temperature/pressure bases | 14.65 psi / 60F (most states) vs. 14.73 psi / 60F (some states) vs. 15.025 psi / 65F (Canada) |
| Date formats | MM/DD/YYYY vs. YYYY-MM-DD vs. DD-Mon-YY |
| Depth reference | KB (Kelly Bushing) vs. GL (Ground Level) vs. DF (Derrick Floor) vs. MSL (Mean Sea Level) |

### 6.2 Reporting Delays

- State production data typically lags **2-6 months** behind actual production
- Some states have longer lags (Pennsylvania data can lag by years for conventional wells)
- Initial filings are often incomplete; data "matures" over 6-18 months as corrections come in
- Revisions/amendments can arrive months or years after initial filing

### 6.3 Corrections & Amendments

- Production data is frequently revised after initial submission
- States handle corrections differently: some overwrite, some maintain revision history
- No standard way to identify whether a record is original or amended
- Cumulative production totals may not match sum of monthly production (due to adjustments)

### 6.4 Duplicate Wells

- Same physical well can appear with different API numbers (when re-drilled or re-permitted)
- API number reuse in rare cases
- State database errors creating duplicate records
- Mergers/acquisitions leading to duplicate well entries from different operators' data systems

### 6.5 Operator Name Variations

This is one of the most persistent data quality problems. The same operator appears under many names:

| Actual Operator | Variations Found in Data |
|----------------|-------------------------|
| Devon Energy | Devon Energy Corporation, Devon Energy Production Co LP, Devon Energy Operating Co, DEVON ENERGY CORP, Devon |
| Pioneer Natural Resources | Pioneer Natural Resources Company, Pioneer Natural Resources USA Inc, Pioneer Natural Res, PIONEER NAT RES |
| ConocoPhillips | Conoco Phillips, ConocoPhillips Company, CONOCOPHILLIPS CO, Burlington Resources (predecessor) |

**Root causes**: Manual data entry, no standardized operator registry across states, name changes from M&A activity, subsidiaries vs. parent companies, different legal entities operating in different states.

### 6.6 Location Data Quality

- Historical wells may have only PLSS descriptions (no lat/long)
- PLSS-to-coordinate conversions can introduce 100+ meter errors
- Coordinate datum issues (NAD27 vs. NAD83 vs. WGS84)
- Surface vs. bottom-hole location confusion for horizontal wells
- Some states only record surface location; others also track bottom-hole

### 6.7 Missing Data

- Older wells (pre-digital) often have minimal data
- Some states never digitized historical records
- Production data gaps during periods of inactivity
- Completion data missing for wells completed before reporting requirements changed

### 6.8 Lease-Level vs. Well-Level Production

- Texas reports production at the lease level only
- Allocating lease production to individual wells introduces estimation error
- Different data vendors use different allocation methodologies, yielding different "well-level" numbers for the same well
- Allowable data (used for allocation) can be set to zero for paperwork reasons, not actual shut-in

---

## 7. Commercial O&G Data Vendors

### 7.1 Vendor Comparison

| Vendor | Formerly Known As | Focus | Pricing (Approximate) | Data Coverage |
|--------|-------------------|-------|----------------------|---------------|
| **Enverus** | DrillingInfo | Comprehensive E&P analytics | ~$275/month/user (~$3,300/yr); enterprise pricing varies widely | 98% of US energy producers; 25+ years of data |
| **S&P Global Commodity Insights** | IHS Markit / IHS Energy | Comprehensive upstream data | Enterprise pricing (contact sales); $25/month browsing fee for Enerdeq | 5M+ well completions; 2.5M+ production entities |
| **TGS** | N/A | Subsurface & well data analytics | Enterprise pricing (contact sales) | 100+ years of public & proprietary data; millions of wells |
| **WellDatabase** | N/A | Simplified well data access | **Free** (Lite plan); $250/month (Basic); higher tiers available | All public US O&G data |
| **Novi Labs** | N/A | Analytics-focused, ML-driven | Contact for pricing | US well-level data with engineered completions datasets |
| **Oseberg** | N/A | Permit and regulatory tracking | Contact for pricing | US permit and regulatory data |

### 7.2 What Commercial Vendors Provide Over Raw State Data

| Capability | Raw State Data | Commercial Vendors |
|-----------|----------------|-------------------|
| **Normalization** | Each state has its own format | Unified schema across all states |
| **Well-level production** | Texas is lease-level only | Allocated to well level using proprietary methods |
| **Operator name standardization** | Free text, inconsistent | Standardized and linked |
| **Cross-state linking** | No linking between states | Wells linked across state boundaries |
| **Historical corrections** | Overwritten or absent | Revision history maintained |
| **Timeliness** | 2-6 month lag | Faster updates (some near real-time) |
| **API/data access** | Web scraping required | REST APIs, SQL databases, data feeds |
| **Analytics** | None | Decline analysis, type curves, economics |

### 7.3 Why Vendors Cost So Much

The value proposition of commercial vendors is primarily:
1. **Data aggregation labor**: Collecting from 30+ state sites with different formats
2. **Normalization engineering**: Mapping each state's schema to a unified model
3. **Production allocation**: Estimating well-level from lease-level (Texas and others)
4. **Operator matching**: Maintaining a master operator registry
5. **Quality assurance**: Catching and correcting errors, filling gaps
6. **Timeliness**: Faster data collection and processing than state agencies
7. **Historical data**: Decades of curated historical records

---

## 8. Open Data Sources & APIs

### 8.1 Federal / National Sources

| Source | URL | Data Available | Format | Cost |
|--------|-----|----------------|--------|------|
| **EIA Open Data** | https://www.eia.gov/opendata/ | National/state-level production, prices, reserves | REST API (JSON) | Free (API key required) |
| **FracFocus** | https://fracfocus.org/data-download | Hydraulic fracturing chemical disclosures | SQL Server backup, CSV, API | Free |
| **HIFLD** | https://hifld-geoplatform.opendata.arcgis.com/ | Oil and gas well locations (national) | CSV, KML, GeoJSON, Shapefile | Free |
| **USGS** | https://www.usgs.gov/ | Assessments, geological data | Various | Free |
| **BSEE** | https://www.data.bsee.gov/ | Offshore well/production data | Web query, downloads | Free |

### 8.2 Key State Data Portals

| State | Agency | Data Access | Formats | Notable Features |
|-------|--------|-------------|---------|-----------------|
| **Texas** | Railroad Commission (RRC) | Web query (PDQ), bulk download | Oracle DB dumps, PDF (permits), TIFF (plats) | Lease-level production only; no REST API; production DB available for purchase |
| **Oklahoma** | Corporation Commission (OCC) | Well Data Finder, GIS portal, data files | Web app, GIS, downloads | Weekly data updates; OCC Tax Commission is official production recordkeeper |
| **North Dakota** | Dept. of Mineral Resources (DMR) | Well search, GIS viewer, monthly production reports | Web, GIS, downloads by year | Hourly data updates via GIS; production data 2003-present |
| **Colorado** | ECMC (formerly COGCC) | COGIS database, downloadable data | CSV (production 1999+), GIS data | Well spots, production, completions all downloadable |
| **New Mexico** | Oil Conservation Division (OCD) | OCD Hub (ArcGIS), public FTP | CSV, KML, GeoJSON, GeoTIFF | ArcGIS Hub with modern download options |
| **Wyoming** | WOGCC | Data Explorer, GIS hub | Excel, GIS | Excel-format downloads |
| **Pennsylvania** | DEP | Oil and Gas Reports portal, GIS | CSV, interactive reports | Separate conventional/unconventional well data |
| **Louisiana** | DNR (SONRIS) | SONRIS Data Portal, GIS | JSON, AMF, geoJSON via map service | Recently revamped interface (Oct 2025); interactive reports |

### 8.3 FracFocus Database Structure

FracFocus is particularly relevant as a well-structured open data source:

| Table | Key Fields |
|-------|-----------|
| `RegistryUpload` | Job date, API number, location (lat/long, state, county), base water volume, TVD, operator |
| `RegistryUploadPurpose` | Additive names, suppliers, purposes |
| `RegistryUploadIngredients` | CAS number, chemical name, maximum percentages |

**Format**: SQL Server 2019 backup (bulk download), CSV, or per-record API access.

### 8.4 Other Open/Low-Cost Sources

| Source | Description |
|--------|-------------|
| **WellDatabase Lite** | Free tier with well names, APIs, operators, locations, depths, elevations, and production data |
| **FracTracker Alliance** | Free public data portals with maps and datasets on wells and petrochemical facilities |
| **Open-FF** | Transforms FracFocus data into a usable research resource |
| **PUDL** | Public Utility Data Liberation project (Catalyst Cooperative) includes EIA bulk API data |
| **data.gov** | Various federal datasets on petroleum |

---

## 9. The Source of Truth Problem

### 9.1 Why O&G Data Is Considered Unreliable

The fundamental problem: **there is no single authoritative source for oil and gas well data in the United States.**

**Fragmentation**: Each of 30+ producing states maintains its own regulatory database with:
- Different schemas and data models
- Different reporting requirements and deadlines
- Different data quality standards
- Different levels of digital sophistication
- Different definitions for the same concepts

**Regulatory vs. Fiscal vs. Technical Data**: Production volumes appear in at least three systems:
1. **State regulatory agency** (e.g., RRC in Texas) - for regulatory compliance
2. **State tax authority** (e.g., Oklahoma Tax Commission) - for severance tax collection
3. **Operator's internal systems** - for operational decisions

These three numbers often do not match due to different reporting periods, correction timelines, and measurement points.

### 9.2 Specific Source of Truth Failures

| Issue | Impact |
|-------|--------|
| **Regulatory data ≠ Tax data** | The OCC in Oklahoma collects well data, but the Tax Commission is the official production recordkeeper |
| **Lag time** | Regulatory data lags 2-6 months; by the time it's "final," corrections may still be incoming |
| **Operator self-reporting** | Production is self-reported by operators; governments lack staff to verify |
| **Corrections overwrite history** | Some states overwrite original values with corrections, losing the audit trail |
| **No national database** | No federal agency maintains comprehensive well-level data for all states |
| **EIA data is aggregated** | EIA data is at state/basin level, not individual wells |

### 9.3 The Verification Gap

As documented by E&E News/Politico, regulators rely on fossil fuel industry self-reported data but often lack the staff and resources to properly vet it. This creates a fundamental trust problem where:
- Operators report their own production
- State agencies accept it without independent verification
- Errors may persist for months or years
- There is no systematic auditing process

### 9.4 The Safety Dimension

Poor data has real consequences. The 2010 BP Gulf of Mexico oil spill has been cited as an example where inaccurate data (formation pressure predictions) contributed to catastrophic outcomes. Formation pressure data errors during well planning can cause "serious complications -- formation fracture or borehole stability -- which could lead to fatalities."

---

## 10. How State Data Feeds Into Commercial Products

### 10.1 The Data Value Chain

```
State Regulatory Agencies (original source)
  │
  ├── Web portals (HTML, PDF, scanned documents)
  ├── Bulk data downloads (CSV, Oracle dumps, FTP)
  ├── GIS services (ArcGIS, web map services)
  └── RBDMS databases (for 23 states)
        │
        ▼
Commercial Data Vendors (aggregation layer)
  │
  ├── Data collection (scraping, downloads, direct feeds)
  ├── Normalization (unified schema)
  ├── Quality assurance (dedup, name matching, corrections)
  ├── Enhancement (allocation, analytics, linking)
  └── Delivery (API, web app, data feeds)
        │
        ▼
End Users (operators, investors, analysts, landmen)
```

### 10.2 How Vendors Collect State Data

| Method | Description | States |
|--------|-------------|--------|
| **Direct database access** | Some states provide database dumps or direct SQL access | Texas (Oracle dump for purchase), Colorado (CSV downloads) |
| **Bulk file downloads** | States publish periodic data files | North Dakota, Colorado, New Mexico, Wyoming |
| **Web scraping** | Automated extraction from web interfaces | Many states with only web-based query tools |
| **GIS services** | ArcGIS REST APIs, WMS/WFS services | Oklahoma, New Mexico, most states with GIS portals |
| **Partnership agreements** | Direct data feeds from state agencies | Enverus claims partnerships with 98% of US producers |
| **Document scanning/OCR** | Digitizing scanned paper records | Older well records from many states |
| **Manual data entry** | Human operators reading and entering data | Historical records, poor-quality scans |

### 10.3 The Vendor Value-Add

Enverus, for example, provides **direct links between their data and state regulatory agency websites**, allowing users to trace any data point back to its regulatory source. This provenance tracking is a key differentiator -- users can verify vendor data against the original state source.

TGS leverages a **proprietary production data model** incorporating the most recent state regulator data with mastered well records to provide timely and reliable insights.

### 10.4 Time-to-Market

Commercial vendors aim to provide data faster than states publish it:
- State data lag: 2-6 months typical
- Vendor data lag: weeks to 1-2 months
- Some vendors claim near-real-time for permits and rig activity

---

## 11. State Regulatory Agency Registry

### Major Producing States (Priority for Scraper)

| Priority | State | Agency | Key URL | Data Quality |
|----------|-------|--------|---------|-------------|
| 1 | Texas | Railroad Commission (RRC) | rrc.texas.gov | Lease-level only; complex; Oracle DB available |
| 2 | New Mexico | Oil Conservation Division (OCD) | emnrd.nm.gov/ocd/ | ArcGIS Hub; modern; good data access |
| 3 | North Dakota | Dept. of Mineral Resources (DMR) | dmr.nd.gov/oilgas/ | Good; hourly updates; well-level production |
| 4 | Oklahoma | Corporation Commission (OCC) | oklahoma.gov/occ/ | Weekly updates; tax data separate |
| 5 | Colorado | ECMC (formerly COGCC) | ecmc.colorado.gov | Excellent; CSV downloads; COGIS database |
| 6 | Wyoming | WOGCC | wogcc.wyo.gov | Data Explorer; Excel format |
| 7 | Louisiana | DNR (SONRIS) | sonris.com | Revamped 2025; interactive reports |
| 8 | Pennsylvania | DEP | pa.gov/agencies/dep/ | CSV; separate conventional/unconventional |
| 9 | Alaska | AOGCC | doa.alaska.gov/ogc/ | Limited digital access |
| 10 | California | CalGEM (formerly DOGGR) | conservation.ca.gov | Complex; high-volume |

### Additional State Agencies (Comprehensive List)

| State | Agency |
|-------|--------|
| Alabama | Oil and Gas Board |
| Arizona | Oil and Gas Commission |
| Arkansas | Oil and Gas Commission |
| Florida | Geological Survey |
| Georgia | DNR |
| Idaho | Geological Survey |
| Illinois | DNR Oil and Gas Division |
| Indiana | DNR Division of Oil and Gas |
| Kansas | Corporation Commission (KCC) |
| Kentucky | DNR Oil and Gas Division |
| Michigan | Public Service Commission |
| Mississippi | State Oil and Gas Board |
| Missouri | DNR |
| Montana | Board of Oil and Gas Conservation |
| Nebraska | Oil and Gas Conservation Commission |
| Nevada | Bureau of Mines and Geology |
| New York | DEC (Division of Mineral Resources) |
| North Carolina | Geological Survey |
| Ohio | DNR Division of Oil and Gas |
| Oregon | DOGAMI (Oil, Gas, and Geothermal) |
| South Dakota | DNR |
| Utah | Division of Oil, Gas, and Mining |
| Virginia | Division of Gas and Oil |
| Washington | DNR |
| West Virginia | Office of Oil and Gas |

---

## 12. Implications for the Scraper Project

### 12.1 Schema Design Recommendations

Based on this research, the scraper's normalized data schema should draw from PPDM concepts while keeping things simpler for a scraping application:

**Core Entities**:
1. `well` - Master well record (API number as primary key)
2. `wellbore` - Physical wellbore (API + sidetrack code)
3. `completion` - Completion event (API + sidetrack + event code)
4. `operator` - Standardized operator registry with aliases
5. `production` - Monthly/annual production volumes
6. `document` - Source document metadata and classification
7. `permit` - Drilling permit data
8. `state_source` - Registry of state sites and scraping configurations

**Key Cross-Reference Tables**:
- `well_identifier` - Maps all known identifiers (API, permit, lease, state IDs) to a canonical well
- `operator_alias` - Maps variant operator names to canonical operator
- `status_code_map` - Maps state-specific status codes to normalized status

### 12.2 Critical Fields to Extract

**Priority 1 (Must Extract)**:
- API number (10, 12, or 14 digits)
- Operator name
- Well name
- Well location (lat/long and/or PLSS)
- Well status
- Production volumes (oil BBL, gas MCF, water BBL)
- Report dates

**Priority 2 (Should Extract)**:
- Spud date, completion date, first production date
- Total depth, lateral length
- Formation/target zone
- Permit number
- Lease name/number
- County, state

**Priority 3 (Nice to Have)**:
- Casing details
- Perforation intervals
- Frac stages, proppant volumes
- Initial production rates
- Well configuration (vertical/horizontal/directional)

### 12.3 Data Quality Flags

Every extracted data point should carry metadata:

| Flag | Description |
|------|-------------|
| `confidence_score` | 0.0-1.0 confidence in extraction accuracy |
| `source_url` | Original URL where data was found |
| `scrape_timestamp` | When data was scraped |
| `document_type` | Classified document type |
| `extraction_method` | How value was extracted (text parse, OCR, table extract) |
| `unit_assumed` | Whether units were explicit or assumed |
| `is_allocated` | Whether production data was allocated from lease-level |
| `revision_number` | Whether this is original or corrected data |

### 12.4 Known Challenges for the Scraper

| Challenge | Severity | Mitigation |
|-----------|----------|-----------|
| Every state site is different | Critical | Per-state adapter pattern |
| Texas lease-level production | High | Production allocation algorithm needed |
| Operator name variants | High | Fuzzy matching + manual review + master registry |
| PDF/scanned document parsing | High | OCR + ML classification pipeline |
| Anti-bot protections | Medium | Rate limiting, browser automation, respectful scraping |
| Status code variations | Medium | State-specific mapping tables |
| Unit inconsistencies | Medium | Explicit unit tracking and conversion |
| Location format variations | Medium | PLSS-to-coordinate converter; datum transformation |
| Historical data gaps | Low | Accept and flag; do not fill with assumptions |
| Site layout changes | Ongoing | Health monitoring + alerts when scrapers break |

---

## Appendix A: Unit Conversion Reference

| From | To | Factor |
|------|----|--------|
| 1 BBL oil | BOE | 1.0 |
| 1 MCF gas | BOE | ~0.167 (1/6) |
| 1 MMCF gas | BOE | ~167 |
| 1 BCF gas | BOE | ~167,000 |
| 1 BBL | Gallons | 42 |
| 1 MCF | Cubic feet | 1,000 |
| 1 MMCF | Cubic feet | 1,000,000 |
| 1 BCF | Cubic feet | 1,000,000,000 |
| 1 MCF gas (burned) | BTU | ~1,000,000 |

**WARNING**: The "M" prefix in O&G means "thousand" (from Roman numeral M), NOT "million" or "mega" as in SI units. This is a persistent source of confusion:
- **MCF** = 1,000 cubic feet (NOT million)
- **MMCF** = 1,000,000 cubic feet (M x M = thousand x thousand)
- **MMBTU** = 1,000,000 BTU

## Appendix B: Texas RRC Form Reference

| Form | Description | Key Data |
|------|-------------|----------|
| W-1 | Application to Drill | Permit data, operator, location, proposed depth |
| W-2 | Oil Well Completion Report | Completion data, actual depth, IP |
| G-1 | Gas Well Completion Report | Completion data, actual depth, IP |
| W-3 | Plugging Report | Plug date, cement plugs, final status |
| P-4 | Producer's Transportation Authority | Transportation authorization |
| PR | Production Report | Monthly lease-level production volumes |
| W-14 | Injection Well Permit | Injection well authorization |

## Appendix C: Glossary of Key Terms

| Term | Definition |
|------|-----------|
| **API Number** | American Petroleum Institute unique well identifier (up to 14 digits) |
| **UWI** | Unique Well Identifier (PPDM standard, based on API number) |
| **BBL** | Barrel (42 US gallons) |
| **BOE** | Barrel of Oil Equivalent (~6 MCF gas = 1 BOE) |
| **MCF** | Thousand cubic feet (of natural gas) |
| **PLSS** | Public Land Survey System (Section-Township-Range) |
| **TVD** | True Vertical Depth |
| **MD** | Measured Depth (along wellbore path) |
| **TD** | Total Depth |
| **IP** | Initial Production (first flow rates after completion) |
| **Spud** | First penetration of earth by drill bit |
| **P&A** | Plugged and Abandoned |
| **SI** | Shut-In (not producing, mechanically capable) |
| **TA** | Temporarily Abandoned (not mechanically capable without intervention) |
| **NRI** | Net Revenue Interest (owner's share of production revenue) |
| **WI** | Working Interest (owner's share of operating costs) |
| **Spacing Unit** | Regulatory minimum area per well |
| **Pooling** | Combining mineral interests into a drilling unit |
| **Forced Pooling** | Compulsory pooling ordered by regulatory agency |
| **Allowable** | State-set maximum production rate for a well/lease |
| **Form PR** | Texas production report (lease-level) |
| **PDQ** | Production Data Query (Texas RRC online tool) |
| **COGIS** | Colorado Oil and Gas Information System |
| **SONRIS** | Louisiana Strategic Online Natural Resources Information System |
| **RBDMS** | Risk Based Data Management System (used by 23 states) |
