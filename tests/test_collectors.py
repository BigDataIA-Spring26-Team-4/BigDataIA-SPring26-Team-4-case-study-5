"""Tests for CS3 data collectors — Glassdoor culture and board governance."""

import pytest
from decimal import Decimal
from app.pipelines.glassdoor_collector import GlassdoorCultureCollector
from app.pipelines.board_analyzer import BoardCompositionAnalyzer


class TestGlassdoorCollector:
    def setup_method(self):
        self.collector = GlassdoorCultureCollector(data_dir="data/glassdoor")

    def test_load_cached_nvda(self):
        reviews = self.collector._load_cached("NVDA")
        assert len(reviews) > 0
        assert all(r.rating > 0 for r in reviews)

    def test_analyze_nvda_culture(self):
        reviews = self.collector._load_cached("NVDA")
        signal = self.collector.analyze_reviews("test-id", "NVDA", reviews)
        assert signal.review_count == len(reviews)
        assert Decimal("0") <= signal.overall_score <= Decimal("100")
        assert Decimal("0") <= signal.innovation_score <= Decimal("100")
        assert signal.confidence > Decimal("0")

    def test_analyze_dg_culture(self):
        reviews = self.collector._load_cached("DG")
        signal = self.collector.analyze_reviews("test-id", "DG", reviews)
        assert signal.overall_score < Decimal("50")

    def test_empty_reviews(self):
        signal = self.collector.analyze_reviews("test-id", "UNKNOWN", [])
        assert signal.overall_score == Decimal("50")
        assert signal.confidence == Decimal("0.3")

    @pytest.mark.parametrize("ticker", ["NVDA", "JPM", "WMT", "GE", "DG"])
    def test_all_companies_cached(self, ticker):
        reviews = self.collector._load_cached(ticker)
        assert len(reviews) > 0, f"No cached reviews for {ticker}"
        signal = self.collector.analyze_reviews("test-id", ticker, reviews)
        assert Decimal("0") <= signal.overall_score <= Decimal("100")

    def test_fetch_falls_back_to_cache(self):
        """With no API keys, fetch_reviews should fall back to cached data."""
        # Use a collector with no API keys to force cache fallback
        # (avoids overwriting production cache with smaller limit)
        no_api_collector = GlassdoorCultureCollector(
            wextractor_token=None, rapidapi_key=None, data_dir="data/glassdoor"
        )
        no_api_collector.wextractor_token = None
        no_api_collector.rapidapi_key = None
        reviews = no_api_collector.fetch_reviews("NVDA", limit=10)
        assert len(reviews) > 0


class TestBoardAnalyzer:
    def setup_method(self):
        self.analyzer = BoardCompositionAnalyzer(data_dir="data/board")

    def test_load_cached_nvda(self):
        members, committees, strategy = self.analyzer._load_cached("NVDA")
        assert len(members) > 0
        assert len(committees) > 0

    def test_analyze_nvda_governance(self):
        members, committees, strategy = self.analyzer._load_cached("NVDA")
        signal = self.analyzer.analyze_board("test-id", "NVDA", members, committees, strategy)
        assert signal.governance_score > Decimal("50")
        assert signal.has_ai_expertise is True
        assert signal.has_tech_committee is True

    def test_analyze_dg_governance(self):
        members, committees, strategy = self.analyzer._load_cached("DG")
        signal = self.analyzer.analyze_board("test-id", "DG", members, committees, strategy)
        # DG has no tech committee, no AI expertise, no data officer, no AI strategy
        assert signal.has_ai_expertise is False
        assert signal.has_data_officer is False
        assert signal.has_ai_in_strategy is False
        assert signal.governance_score <= Decimal("40")

    def test_score_capped_at_100(self):
        members, committees, strategy = self.analyzer._load_cached("JPM")
        signal = self.analyzer.analyze_board("test-id", "JPM", members, committees, strategy)
        assert Decimal("20") <= signal.governance_score <= Decimal("100")
        assert Decimal("0") <= signal.confidence <= Decimal("1")

    def test_empty_board(self):
        signal = self.analyzer.analyze_board("test-id", "UNKNOWN", [], [], "")
        assert signal.governance_score == Decimal("20")
        assert signal.confidence == Decimal("0.3")

    @pytest.mark.parametrize("ticker", ["NVDA", "JPM", "WMT", "GE", "DG"])
    def test_all_companies_cached(self, ticker):
        members, committees, strategy = self.analyzer._load_cached(ticker)
        assert len(members) > 0, f"No cached board data for {ticker}"
        signal = self.analyzer.analyze_board("test-id", ticker, members, committees, strategy)
        assert Decimal("20") <= signal.governance_score <= Decimal("100")

    def test_fetch_falls_back_to_cache(self):
        """With no API key, fetch_board_data should fall back to cached data."""
        members, committees, strategy = self.analyzer.fetch_board_data("NVDA")
        assert len(members) > 0
