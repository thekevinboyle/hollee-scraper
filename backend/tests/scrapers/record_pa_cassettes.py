#!/usr/bin/env python3
"""Record VCR.py cassettes for PA DEP GreenPort spider tests.

Run this script to record real HTTP responses from GreenPort endpoints.
The cassettes are stored as YAML files in tests/scrapers/cassettes/pa/
and replayed during test runs without hitting real servers.

Usage:
    uv run python backend/tests/scrapers/record_pa_cassettes.py
"""

import os
import sys

import httpx
import vcr

CASSETTE_DIR = os.path.join(
    os.path.dirname(__file__), "cassettes", "pa"
)
os.makedirs(CASSETTE_DIR, exist_ok=True)

GREENPORT_BASE = "https://greenport.pa.gov/ReportExtracts/OG"

ENDPOINTS = {
    "greenport_index": f"{GREENPORT_BASE}/Index",
    "greenport_well_inventory": f"{GREENPORT_BASE}/OilGasWellInventoryReport",
    "greenport_production": f"{GREENPORT_BASE}/OilGasWellProdReport",
    "greenport_compliance": f"{GREENPORT_BASE}/OilComplianceReport",
    "greenport_plugged": f"{GREENPORT_BASE}/OGPluggedWellsReport",
}

HEADERS = {
    "User-Agent": "OGDocScraper/1.0 (Research tool; cassette recording)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def record_cassettes():
    """Record one cassette per GreenPort endpoint."""
    my_vcr = vcr.VCR(
        cassette_library_dir=CASSETTE_DIR,
        record_mode="new_episodes",
        match_on=["uri", "method"],
        decode_compressed_response=True,
    )

    for name, url in ENDPOINTS.items():
        cassette_path = os.path.join(CASSETTE_DIR, f"{name}.yaml")
        print(f"Recording {name}: {url}")
        try:
            with my_vcr.use_cassette(cassette_path):
                response = httpx.get(url, headers=HEADERS, timeout=30.0, follow_redirects=True)
                print(f"  Status: {response.status_code}, Size: {len(response.text)} chars")
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)

    print(f"\nCassettes saved to: {CASSETTE_DIR}")


if __name__ == "__main__":
    record_cassettes()
