"""Tests for state configuration registry."""

import pytest

from og_scraper.scrapers.state_registry import (
    STATE_REGISTRY,
    get_state_config,
    get_all_states,
    get_states_by_tier,
    get_implemented_states,
)


class TestStateRegistry:
    def test_registry_has_10_states(self):
        assert len(STATE_REGISTRY) == 10

    def test_all_state_codes_present(self):
        expected = {"TX", "NM", "ND", "OK", "CO", "WY", "LA", "PA", "CA", "AK"}
        assert set(STATE_REGISTRY.keys()) == expected

    def test_get_state_config_valid(self):
        config = get_state_config("TX")
        assert config.code == "TX"
        assert config.name == "Texas"
        assert config.agency == "Railroad Commission of Texas (RRC)"
        assert config.rate_limit_seconds == 10.0

    def test_get_state_config_case_insensitive(self):
        config = get_state_config("tx")
        assert config.code == "TX"

    def test_get_state_config_invalid(self):
        with pytest.raises(KeyError, match="Unknown state code"):
            get_state_config("ZZ")

    def test_get_all_states(self):
        states = get_all_states()
        assert len(states) == 10

    def test_tier_1_has_5_states(self):
        tier1 = get_states_by_tier(1)
        assert len(tier1) == 5
        assert all(s.tier == 1 for s in tier1)

    def test_tier_2_has_5_states(self):
        tier2 = get_states_by_tier(2)
        assert len(tier2) == 5
        assert all(s.tier == 2 for s in tier2)

    def test_ok_is_implemented(self):
        """OK spider should be implemented after Task 4.3."""
        implemented = get_implemented_states()
        ok_states = [s for s in implemented if s.code == "OK"]
        assert len(ok_states) == 1
        assert ok_states[0].spider_class == "og_scraper.scrapers.spiders.ok_spider.OklahomaOCCSpider"

    def test_pa_is_easiest(self):
        """PA should have the lowest rate limit (easiest to scrape)."""
        pa = get_state_config("PA")
        assert pa.rate_limit_seconds == 3.0
        assert pa.requires_playwright is False
        assert pa.scrape_type == "bulk_download"

    def test_la_is_hardest(self):
        """LA should require Playwright and have high rate limit."""
        la = get_state_config("LA")
        assert la.rate_limit_seconds == 15.0
        assert la.requires_playwright is True
        assert la.scrape_type == "browser_form"
