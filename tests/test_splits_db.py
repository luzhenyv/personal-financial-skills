"""Integration tests for pfs/splits.py against the live DB."""

import pytest
from datetime import date

from pfs.db.session import get_session
from pfs.services.splits import cumulative_split_factor, get_split_adjustor, load_splits_from_db


@pytest.fixture(scope="module")
def db():
    session = get_session()
    yield session
    session.close()


# ── load_splits_from_db ────────────────────────────────────────────────────────

class TestLoadSplitsFromDb:
    def test_nvda_returns_six_splits(self, db):
        splits = load_splits_from_db("NVDA", db)
        assert len(splits) == 6

    def test_avgo_returns_one_split(self, db):
        splits = load_splits_from_db("AVGO", db)
        assert len(splits) == 1
        assert splits[0] == {"date": "2024-07-15", "ratio": 10.0}

    def test_unknown_ticker_returns_empty(self, db):
        splits = load_splits_from_db("ZZZZ", db)
        assert splits == []

    def test_sorted_ascending(self, db):
        splits = load_splits_from_db("NVDA", db)
        dates = [s["date"] for s in splits]
        assert dates == sorted(dates)

    def test_dict_shape(self, db):
        splits = load_splits_from_db("NVDA", db)
        for s in splits:
            assert set(s.keys()) == {"date", "ratio"}
            assert isinstance(s["ratio"], float)


# ── cumulative_split_factor ────────────────────────────────────────────────────

class TestCumulativeSplitFactor:
    # NVDA splits: 2000-06-27 ×2, 2001-09-10 ×2, 2006-04-07 ×2,
    #              2007-09-11 ×1.5, 2021-07-20 ×4, 2024-06-10 ×10

    @pytest.fixture(autouse=True)
    def _splits(self, db):
        self.nvda = load_splits_from_db("NVDA", db)
        self.avgo = load_splits_from_db("AVGO", db)

    def test_nvda_fy2000_all_splits_after(self):
        # FYE Jan 2000 — all 6 splits follow
        factor = cumulative_split_factor(self.nvda, date(2000, 1, 31))
        assert factor == 2.0 * 2.0 * 2.0 * 1.5 * 4.0 * 10.0  # 240.0

    def test_nvda_fy2021_two_splits_after(self):
        # FYE Jan 2021 — July 2021 ×4 and June 2024 ×10 follow
        factor = cumulative_split_factor(self.nvda, date(2021, 1, 31))
        assert factor == 4.0 * 10.0  # 40.0

    def test_nvda_fy2024_one_split_after(self):
        # FYE Jan 2024 — only June 2024 ×10 follows
        factor = cumulative_split_factor(self.nvda, date(2024, 1, 31))
        assert factor == 10.0

    def test_nvda_fy2025_no_splits_after(self):
        # FYE Jan 2025 — no splits follow
        factor = cumulative_split_factor(self.nvda, date(2025, 1, 31))
        assert factor == 1.0

    def test_avgo_fy2023_split_after(self):
        # FYE Oct 2023 — July 2024 ×10 follows
        factor = cumulative_split_factor(self.avgo, date(2023, 10, 31))
        assert factor == 10.0

    def test_avgo_fy2024_no_split_after(self):
        # FYE Oct 2024 — split was July 2024, before FYE
        factor = cumulative_split_factor(self.avgo, date(2024, 10, 31))
        assert factor == 1.0

    def test_empty_splits_returns_one(self):
        assert cumulative_split_factor([], date(2024, 1, 31)) == 1.0


# ── get_split_adjustor ─────────────────────────────────────────────────────────

class TestGetSplitAdjustor:
    def test_nvda_fy2024_eps_divided_by_10(self, db):
        adjust = get_split_adjustor("NVDA", fiscal_year_end="0131", db=db)
        assert adjust(2024, 11.93) == round(11.93 / 10.0, 4)

    def test_nvda_fy2021_eps_divided_by_40(self, db):
        adjust = get_split_adjustor("NVDA", fiscal_year_end="0131", db=db)
        assert adjust(2021, 4.93) == round(4.93 / 40.0, 4)

    def test_nvda_fy2025_unchanged(self, db):
        adjust = get_split_adjustor("NVDA", fiscal_year_end="0131", db=db)
        assert adjust(2025, 2.99) == 2.99

    def test_none_passthrough(self, db):
        adjust = get_split_adjustor("NVDA", fiscal_year_end="0131", db=db)
        assert adjust(2024, None) is None

    def test_avgo_fy2023_eps_divided_by_10(self, db):
        adjust = get_split_adjustor("AVGO", fiscal_year_end="1031", db=db)
        assert adjust(2023, 42.50) == round(42.50 / 10.0, 4)

    def test_avgo_fy2024_unchanged(self, db):
        adjust = get_split_adjustor("AVGO", fiscal_year_end="1031", db=db)
        assert adjust(2024, 4.25) == 4.25

    def test_no_splits_ticker_unchanged(self, db):
        # ticker with no split history returns value as-is
        adjust = get_split_adjustor("ZZZZ", fiscal_year_end="1231", db=db)
        assert adjust(2023, 5.00) == 5.00

    def test_cache_reuses_computed_factor(self, db):
        adjust = get_split_adjustor("NVDA", fiscal_year_end="0131", db=db)
        # Call twice for same year — cache should return identical result
        r1 = adjust(2024, 11.93)
        r2 = adjust(2024, 11.93)
        assert r1 == r2

    def test_fye_defaults_to_dec31_when_none(self, db):
        # Without fiscal_year_end, falls back to Dec 31
        adjust = get_split_adjustor("NVDA", db=db)
        # FY2024 ends Dec 31 2024: June 2024 split is BEFORE that date → factor=1
        assert adjust(2024, 5.00) == 5.00
