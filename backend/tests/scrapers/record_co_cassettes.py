"""Helper script to record VCR.py cassettes for Colorado ECMC spider tests.

Run this script to record fresh HTTP responses from the ECMC website.
Cassettes are saved to backend/tests/scrapers/cassettes/co/ and
replayed during tests so they run offline.

Usage:
    uv run python backend/tests/scrapers/record_co_cassettes.py

Note: Only run this when you need to refresh cassettes (e.g., after
site changes). Recorded cassettes should be committed to version control.
"""

import httpx
import vcr

CASSETTE_DIR = "backend/tests/scrapers/cassettes/co"

HEADERS = {
    "User-Agent": "OGDocScraper/1.0 (Research tool; contact@example.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

my_vcr = vcr.VCR(
    cassette_library_dir=CASSETTE_DIR,
    record_mode="new_episodes",
    match_on=["uri", "method", "body"],
    decode_compressed_response=True,
)


def record_download_page():
    """Record the ECMC downloadable data page."""
    print("Recording: ecmc_download_page.yaml")
    with my_vcr.use_cassette("ecmc_download_page.yaml"):
        resp = httpx.get(
            "https://ecmc.colorado.gov/data-maps-reports/downloadable-data-documents",
            headers=HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )
        print(f"  Status: {resp.status_code}, Length: {len(resp.text)}")


def record_legacy_data_page():
    """Record the legacy ECMC data page."""
    print("Recording: ecmc_legacy_data_page.yaml")
    with my_vcr.use_cassette("ecmc_legacy_data_page.yaml"):
        resp = httpx.get(
            "https://ecmc.state.co.us/data2.html",
            headers=HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )
        print(f"  Status: {resp.status_code}, Length: {len(resp.text)}")


def record_cogis_facility_search():
    """Record COGIS facility search form and results."""
    print("Recording: ecmc_cogis_facility_search.yaml")
    with my_vcr.use_cassette("ecmc_cogis_facility_search.yaml"):
        # GET the form page
        resp = httpx.get(
            "https://ecmc.state.co.us/cogisdb/Facility/FacilitySearch",
            headers=HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )
        print(f"  Form page status: {resp.status_code}")


if __name__ == "__main__":
    print(f"Recording VCR cassettes to: {CASSETTE_DIR}/")
    print("=" * 60)

    record_download_page()
    record_legacy_data_page()
    record_cogis_facility_search()

    print("=" * 60)
    print("Done! Cassettes recorded. Note: CSV data cassettes use")
    print("synthetic data and do not need live recording.")
