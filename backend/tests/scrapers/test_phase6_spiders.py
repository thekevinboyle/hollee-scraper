"""Tests for Phase 6 state spiders: TX, NM, ND, WY, AK, CA, LA."""

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from scrapy.http import Request, TextResponse

from og_scraper.scrapers.spiders.tx_spider import TexasRRCSpider
from og_scraper.scrapers.spiders.nm_spider import NewMexicoOCDSpider
from og_scraper.scrapers.spiders.nd_spider import NorthDakotaNDICSpider
from og_scraper.scrapers.spiders.wy_spider import WyomingWOGCCSpider
from og_scraper.scrapers.spiders.ak_spider import AlaskaAOGCCSpider
from og_scraper.scrapers.spiders.ca_spider import CaliforniaCalGEMSpider
from og_scraper.scrapers.spiders.la_spider import LouisianaSONRISSpider
from og_scraper.scrapers.items import WellItem, DocumentItem


def _make_response(url, body, meta=None):
    request = Request(url=url, meta=meta or {})
    return TextResponse(url=url, body=body.encode("utf-8"), encoding="utf-8", request=request)


def _make_arcgis_response(url, features, exceeded=False, meta=None):
    data = {"features": features, "exceededTransferLimit": exceeded}
    return _make_response(url, json.dumps(data), meta=meta or {"offset": 0})


# --- TX Spider ---

class TestTexasRRCSpider:
    def test_attributes(self):
        spider = TexasRRCSpider()
        assert spider.state_code == "TX"
        assert spider.name == "tx_rrc"

    def test_start_requests(self):
        spider = TexasRRCSpider()
        requests = list(spider.start_requests())
        assert len(requests) == 3  # wells, production, completions

    def test_start_requests_filter(self):
        spider = TexasRRCSpider(datasets="wells")
        requests = list(spider.start_requests())
        assert len(requests) == 1

    def test_parse_csv_wells(self):
        spider = TexasRRCSpider()
        csv_body = "API_NO,WELL_NAME,OPERATOR_NAME,COUNTY_NAME,LATITUDE,LONGITUDE,WELL_STATUS\n42501201300,Test Well,Test Op,HARRIS,29.76,-95.36,ACTIVE\n"
        response = _make_response(
            "https://mft.rrc.texas.gov/link/test",
            csv_body,
            meta={"dataset": {"name": "wells", "doc_type": "well_permit", "format": "csv"}},
        )
        items = list(spider.parse_csv(response))
        assert len(items) == 1
        assert isinstance(items[0], WellItem)
        assert items[0].state_code == "TX"
        assert items[0].well_name == "Test Well"

    def test_parse_csv_production(self):
        spider = TexasRRCSpider()
        csv_body = "API_NO,WELL_NAME,OPERATOR_NAME,OIL_BBL,GAS_MCF\n42501201300,Test Well,Test Op,1000,5000\n"
        response = _make_response(
            "https://mft.rrc.texas.gov/link/test",
            csv_body,
            meta={"dataset": {"name": "production", "doc_type": "production_report", "format": "csv"}},
        )
        items = list(spider.parse_csv(response))
        assert len(items) == 1
        assert isinstance(items[0], DocumentItem)
        assert items[0].doc_type == "production_report"

    def test_parse_csv_with_limit(self):
        spider = TexasRRCSpider(limit="1")
        csv_body = "API_NO,WELL_NAME\n42501201300,Well A\n42501201301,Well B\n"
        response = _make_response(
            "https://mft.rrc.texas.gov/link/test",
            csv_body,
            meta={"dataset": {"name": "wells", "doc_type": "well_permit", "format": "csv"}},
        )
        items = list(spider.parse_csv(response))
        assert len(items) == 1

    def test_empty_csv(self):
        spider = TexasRRCSpider()
        response = _make_response(
            "https://mft.rrc.texas.gov/link/test",
            "API_NO,WELL_NAME\n",
            meta={"dataset": {"name": "wells", "doc_type": "well_permit", "format": "csv"}},
        )
        items = list(spider.parse_csv(response))
        assert len(items) == 0


# --- NM Spider ---

class TestNewMexicoOCDSpider:
    def test_attributes(self):
        spider = NewMexicoOCDSpider()
        assert spider.state_code == "NM"

    def test_start_requests(self):
        spider = NewMexicoOCDSpider()
        requests = list(spider.start_requests())
        assert len(requests) == 1

    def test_parse_arcgis(self):
        spider = NewMexicoOCDSpider()
        features = [
            {"attributes": {"API_NUMBER": "30-015-12345", "WELL_NAME": "NM Well", "OPERATOR_NAME": "NM Op", "COUNTY": "LEA"},
             "geometry": {"x": -103.5, "y": 32.5}},
        ]
        response = _make_arcgis_response("https://gis.emnrd.nm.gov/test", features)
        items = list(spider.parse_results(response))
        assert len(items) == 1
        assert isinstance(items[0], WellItem)
        assert items[0].state_code == "NM"

    def test_pagination(self):
        spider = NewMexicoOCDSpider(batch_size="2")
        features = [
            {"attributes": {"API_NUMBER": f"30-015-{i:05d}", "WELL_NAME": f"W{i}"}, "geometry": {"x": -103, "y": 32}}
            for i in range(2)
        ]
        response = _make_arcgis_response("https://gis.emnrd.nm.gov/test", features, exceeded=True)
        results = list(spider.parse_results(response))
        wells = [r for r in results if isinstance(r, WellItem)]
        requests = [r for r in results if hasattr(r, "url")]
        assert len(wells) == 2
        assert len(requests) == 1  # pagination request


# --- ND Spider ---

class TestNorthDakotaSpider:
    def test_attributes(self):
        spider = NorthDakotaNDICSpider()
        assert spider.state_code == "ND"

    def test_start_requests(self):
        spider = NorthDakotaNDICSpider()
        requests = list(spider.start_requests())
        assert len(requests) == 2  # daily_activity + monthly_production

    def test_parse_production_index(self):
        spider = NorthDakotaNDICSpider()
        html = '<html><body><a href="/oilgas/mpr/jan2024.pdf">Jan 2024</a><a href="/oilgas/mpr/feb2024.csv">Feb 2024</a></body></html>'
        response = _make_response(
            "https://www.dmr.nd.gov/oilgas/mpr/",
            html,
            meta={"endpoint": {"name": "monthly_production", "url": "", "doc_type": "production_report"}},
        )
        items = list(spider.parse_page(response))
        assert len(items) == 2
        assert all(isinstance(i, DocumentItem) for i in items)


# --- WY Spider ---

class TestWyomingSpider:
    def test_attributes(self):
        spider = WyomingWOGCCSpider()
        assert spider.state_code == "WY"

    def test_parse_arcgis(self):
        spider = WyomingWOGCCSpider()
        features = [
            {"attributes": {"API_NUMBER": "49-013-12345", "WELL_NAME": "WY Well", "OPERATOR": "WY Op", "COUNTY": "NATRONA"},
             "geometry": {"x": -106.3, "y": 42.8}},
        ]
        response = _make_arcgis_response("https://services1.arcgis.com/test", features)
        items = list(spider.parse_results(response))
        assert len(items) == 1
        assert items[0].state_code == "WY"


# --- AK Spider ---

class TestAlaskaSpider:
    def test_attributes(self):
        spider = AlaskaAOGCCSpider()
        assert spider.state_code == "AK"

    def test_parse_arcgis(self):
        spider = AlaskaAOGCCSpider()
        features = [
            {"attributes": {"API_NUMBER": "50-999-12345", "WELL_NAME": "AK Well", "OPERATOR": "AK Op", "AREA": "Cook Inlet"},
             "geometry": {"x": -151.0, "y": 61.2}},
        ]
        response = _make_arcgis_response("https://services.arcgis.com/test", features)
        items = list(spider.parse_results(response))
        assert len(items) == 1
        assert items[0].county == "Cook Inlet"


# --- CA Spider ---

class TestCaliforniaSpider:
    def test_attributes(self):
        spider = CaliforniaCalGEMSpider()
        assert spider.state_code == "CA"

    def test_parse_arcgis_with_3857(self):
        spider = CaliforniaCalGEMSpider()
        features = [
            {"attributes": {"APINumber": "04-019-12345", "WellName": "CA Well", "OperatorName": "CA Op", "CountyName": "Kern"},
             "geometry": {"x": -13250000, "y": 4250000}},  # EPSG:3857 coords
        ]
        response = _make_arcgis_response("https://gis.conservation.ca.gov/test", features)
        items = list(spider.parse_results(response))
        assert len(items) == 1
        assert items[0].state_code == "CA"
        assert items[0].latitude is not None
        assert items[0].longitude is not None
        # Should be roughly in California
        assert 30 < items[0].latitude < 42
        assert -125 < items[0].longitude < -114

    def test_convert_3857_to_4326(self):
        lat, lon = CaliforniaCalGEMSpider._convert_3857_to_4326(-13250000, 4250000)
        assert 30 < lat < 42
        assert -125 < lon < -114


# --- LA Spider ---

class TestLouisianaSpider:
    def test_attributes(self):
        spider = LouisianaSONRISSpider()
        assert spider.state_code == "LA"

    def test_parse_arcgis(self):
        spider = LouisianaSONRISSpider()
        features = [
            {"attributes": {"API_NUMBER": "17-033-12345", "WELL_NAME": "LA Well", "OPERATOR": "LA Op",
                           "PARISH": "Caddo", "WELL_SERIAL_NUM": "123456"},
             "geometry": {"x": -93.7, "y": 32.5}},
        ]
        response = _make_arcgis_response("https://services5.arcgis.com/test", features)
        items = list(spider.parse_arcgis_results(response))
        assert len(items) == 1
        assert items[0].county == "Caddo"  # parish stored as county
        assert items[0].metadata["serial_number"] == "123456"

    def test_circuit_breaker(self):
        spider = LouisianaSONRISSpider()
        spider._failures = 3
        spider._circuit_open = True
        features = [{"attributes": {"API_NUMBER": "17-001-00001"}, "geometry": {"x": -90, "y": 30}}]
        response = _make_arcgis_response("https://test.com", features)
        items = list(spider.parse_arcgis_results(response))
        assert len(items) == 0  # circuit open, no items

    def test_failure_resets_on_success(self):
        spider = LouisianaSONRISSpider()
        spider._failures = 2
        features = [{"attributes": {"API_NUMBER": "17-001-00001", "WELL_NAME": "W"}, "geometry": {"x": -90, "y": 30}}]
        response = _make_arcgis_response("https://test.com", features)
        list(spider.parse_arcgis_results(response))
        assert spider._failures == 0


# --- State Registry ---

class TestAllStatesImplemented:
    def test_all_10_states_have_spiders(self):
        from og_scraper.scrapers.state_registry import STATE_REGISTRY
        for code, config in STATE_REGISTRY.items():
            assert config.spider_class is not None, f"State {code} has no spider_class"

    def test_implemented_count(self):
        from og_scraper.scrapers.state_registry import get_implemented_states
        implemented = get_implemented_states()
        assert len(implemented) == 10
