"""Helper script to record VCR.py cassettes for OK spider tests.

Run from the project root:
    uv run python backend/tests/scrapers/record_ok_cassettes.py

This downloads small portions of each OCC bulk data file and
stores the HTTP interactions as VCR cassettes for offline testing.

NOTE: XLSX files are binary. VCR.py stores their content as
base64-encoded strings in the YAML cassette files. Ensure
decode_compressed_response=True to handle gzipped responses.
"""

import os

import requests
import vcr

CASSETTE_DIR = os.path.join(os.path.dirname(__file__), "cassettes", "ok")
os.makedirs(CASSETTE_DIR, exist_ok=True)

my_vcr = vcr.VCR(
    cassette_library_dir=CASSETTE_DIR,
    record_mode="new_episodes",
    match_on=["uri", "method"],
    decode_compressed_response=True,
)

BASE = "https://oklahoma.gov"

FILES = {
    "occ_rbdms_wells.yaml": "/content/dam/ok/en/occ/documents/og/ogdatafiles/rbdms-wells.csv",
    "occ_incidents.yaml": "/content/dam/ok/en/occ/documents/og/ogdatafiles/ogcd-incidents.csv",
    "occ_itd_master.yaml": "/content/dam/ok/en/occ/documents/og/ogdatafiles/ITD-wells-formations-base.xlsx",
    "occ_completions.yaml": "/content/dam/ok/en/occ/documents/og/ogdatafiles/completions-wells-formations-base.xlsx",
    "occ_operators.yaml": "/content/dam/ok/en/occ/documents/og/ogdatafiles/operator-list.xlsx",
    "occ_uic_wells.yaml": "/content/dam/ok/en/occ/documents/og/ogdatafiles/online-active-well-list.xlsx",
}


def record_all():
    """Record cassettes for all OK bulk files."""
    for cassette_name, url_path in FILES.items():
        cassette_path = os.path.join(CASSETTE_DIR, cassette_name)
        if os.path.exists(cassette_path):
            print(f"  Skipping {cassette_name} (already exists)")
            continue

        full_url = f"{BASE}{url_path}"
        print(f"  Recording {cassette_name} from {full_url}")

        try:
            with my_vcr.use_cassette(cassette_name):
                resp = requests.get(full_url, timeout=60, stream=True)
                # Read only first 10KB for CSV; full content for XLSX
                _ = resp.raw.read(10240) if url_path.endswith(".csv") else resp.content
                print(f"    Status: {resp.status_code}")
        except Exception as e:
            print(f"    ERROR: {e}")


if __name__ == "__main__":
    print("Recording OK OCC VCR cassettes...")
    record_all()
    print("Done.")
