"""Per-state scraper configuration registry.

Maps each state code to its scraping configuration. Spider classes
are set to None as placeholders until actual spiders are implemented
in Phase 4 (PA, CO, OK) and Phase 6 (remaining 7 states).
"""

from dataclasses import dataclass, field


@dataclass
class StateConfig:
    """Configuration for a single state's scraping setup."""

    code: str
    name: str
    agency: str
    base_url: str
    requires_playwright: bool = False
    scrape_type: str = "bulk_download"  # bulk_download, arcgis_api, browser_form
    rate_limit_seconds: float = 5.0
    max_concurrent: int = 2
    data_formats: list[str] = field(default_factory=list)
    spider_class: str | None = None  # Dotted path to spider class (None = not yet implemented)
    tier: int = 1
    notes: str = ""


STATE_REGISTRY: dict[str, StateConfig] = {
    "TX": StateConfig(
        code="TX",
        name="Texas",
        agency="Railroad Commission of Texas (RRC)",
        base_url="https://www.rrc.texas.gov/",
        requires_playwright=False,
        scrape_type="bulk_download",
        rate_limit_seconds=10.0,
        max_concurrent=2,
        data_formats=["EBCDIC", "ASCII", "CSV", "JSON", "dBase", "PDF", "Shapefile"],
        spider_class="og_scraper.scrapers.spiders.tx_spider.TexasRRCSpider",
        tier=1,
        notes="DO NOT scrape the PDQ web interface. Use bulk downloads only.",
    ),
    "NM": StateConfig(
        code="NM",
        name="New Mexico",
        agency="Oil Conservation Division (OCD)",
        base_url="https://ocdimage.emnrd.nm.gov/",
        requires_playwright=False,
        scrape_type="arcgis_api",
        rate_limit_seconds=5.0,
        max_concurrent=2,
        data_formats=["ArcGIS JSON", "PDF", "CSV"],
        spider_class="og_scraper.scrapers.spiders.nm_spider.NewMexicoOCDSpider",
        tier=1,
        notes="Data spread across OCD Hub, OCD Permitting, ONGARD, and GO-TECH.",
    ),
    "ND": StateConfig(
        code="ND",
        name="North Dakota",
        agency="Dept of Mineral Resources (DMR)",
        base_url="https://www.dmr.nd.gov/oilgas/",
        requires_playwright=True,
        scrape_type="browser_form",
        rate_limit_seconds=15.0,
        max_concurrent=1,
        data_formats=["PDF", "CSV", "HTML"],
        spider_class="og_scraper.scrapers.spiders.nd_spider.NorthDakotaNDICSpider",
        tier=1,
        notes="Subscription portal -- free data limited to PDFs and basic well search.",
    ),
    "OK": StateConfig(
        code="OK",
        name="Oklahoma",
        agency="Corporation Commission (OCC)",
        base_url="https://oklahoma.gov/occ/divisions/oil-gas.html",
        requires_playwright=False,
        scrape_type="bulk_download",
        rate_limit_seconds=3.0,
        max_concurrent=4,
        data_formats=["CSV", "XLSX", "Shapefile", "PDF"],
        spider_class="og_scraper.scrapers.spiders.ok_arcgis_spider.OklahomaArcGISSpider",
        tier=1,
        notes="Production data from OkTAP (Tax Commission), not OCC.",
    ),
    "CO": StateConfig(
        code="CO",
        name="Colorado",
        agency="Energy & Carbon Management Commission (ECMC)",
        base_url="https://ecmc.colorado.gov/",
        requires_playwright=False,
        scrape_type="mixed",
        rate_limit_seconds=8.0,
        max_concurrent=2,
        data_formats=["CSV", "PDF"],
        spider_class="og_scraper.scrapers.spiders.co_arcgis_spider.ColoradoArcGISSpider",
        tier=1,
        notes="Dual domains: ecmc.colorado.gov (new) and ecmc.state.co.us (legacy).",
    ),
    "WY": StateConfig(
        code="WY",
        name="Wyoming",
        agency="Oil & Gas Conservation Commission (WOGCC)",
        base_url="https://wogcc.wyo.gov/",
        requires_playwright=True,
        scrape_type="browser_form",
        rate_limit_seconds=10.0,
        max_concurrent=1,
        data_formats=["CSV", "PDF", "ArcGIS JSON"],
        spider_class="og_scraper.scrapers.spiders.wy_spider.WyomingWOGCCSpider",
        tier=2,
        notes="Data Explorer is JS-heavy. Legacy portal uses ColdFusion.",
    ),
    "LA": StateConfig(
        code="LA",
        name="Louisiana",
        agency="Dept of Conservation & Energy (SONRIS)",
        base_url="https://www.sonris.com/",
        requires_playwright=True,
        scrape_type="browser_form",
        rate_limit_seconds=15.0,
        max_concurrent=1,
        data_formats=["Excel", "PDF", "HTML"],
        spider_class="og_scraper.scrapers.spiders.la_spider.LouisianaSONRISSpider",
        tier=2,
        notes="Hardest to scrape. Oracle backend, complex JS, no REST API.",
    ),
    "PA": StateConfig(
        code="PA",
        name="Pennsylvania",
        agency="Dept of Environmental Protection (DEP)",
        base_url="https://greenport.pa.gov/ReportExtracts/OG/Index",
        requires_playwright=False,
        scrape_type="bulk_download",
        rate_limit_seconds=3.0,
        max_concurrent=4,
        data_formats=["CSV"],
        spider_class="og_scraper.scrapers.spiders.pa_spider.PennsylvaniaDEPSpider",
        tier=2,
        notes="Easiest to scrape. All data as on-demand CSV exports.",
    ),
    "CA": StateConfig(
        code="CA",
        name="California",
        agency="Geologic Energy Management Division (CalGEM)",
        base_url="https://gis.conservation.ca.gov/",
        requires_playwright=False,
        scrape_type="arcgis_api",
        rate_limit_seconds=3.0,
        max_concurrent=3,
        data_formats=["ArcGIS JSON", "CSV"],
        spider_class="og_scraper.scrapers.spiders.ca_spider.CaliforniaCalGEMSpider",
        tier=2,
        notes="ArcGIS returns Web Mercator (EPSG:3857). Convert to WGS84.",
    ),
    "AK": StateConfig(
        code="AK",
        name="Alaska",
        agency="Oil & Gas Conservation Commission (AOGCC)",
        base_url="http://aogweb.state.ak.us/",
        requires_playwright=True,
        scrape_type="browser_form",
        rate_limit_seconds=5.0,
        max_concurrent=2,
        data_formats=["HTML", "PDF", "CSV"],
        spider_class="og_scraper.scrapers.spiders.ak_spider.AlaskaAOGCCSpider",
        tier=2,
        notes="Data Miner on plain HTTP. ASP.NET WebForms with ViewState.",
    ),
}


def get_state_config(state_code: str) -> StateConfig:
    """Get configuration for a state. Raises KeyError if state not found."""
    state_code = state_code.upper()
    if state_code not in STATE_REGISTRY:
        raise KeyError(f"Unknown state code: {state_code}. Valid: {list(STATE_REGISTRY.keys())}")
    return STATE_REGISTRY[state_code]


def get_all_states() -> list[StateConfig]:
    """Get configurations for all 10 states."""
    return list(STATE_REGISTRY.values())


def get_states_by_tier(tier: int) -> list[StateConfig]:
    """Get state configurations filtered by tier (1 or 2)."""
    return [s for s in STATE_REGISTRY.values() if s.tier == tier]


def get_implemented_states() -> list[StateConfig]:
    """Get state configurations that have spider implementations."""
    return [s for s in STATE_REGISTRY.values() if s.spider_class is not None]
