"""Shared fixtures: real CME settlement data, no network.

The settlement fixture is the verbatim CME response for trade date
09/18/2026, so tests exercise the real parsing path and the real
calculation against prices that actually traded.
"""

import json
from datetime import date
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Target range and EFFR in effect on 2026-09-18, after the 2026-09-16 FOMC
# raised the range by 25bp. Source: FOMC statement 2026-09-16; FRED EFFR.
TRADE_DATE_20260918 = date(2026, 9, 18)
TARGET_RANGE_20260918 = (3.75, 4.00)
EFFR_20260918 = 3.88


@pytest.fixture
def raw_settlements_20260918() -> dict:
    """Verbatim CME Settlements response for trade date 09/18/2026."""
    with (FIXTURES / "settlements_20260918.json").open() as fh:
        return json.load(fh)


@pytest.fixture
def settlements_20260918(raw_settlements_20260918) -> list[dict]:
    """Settlement rows as the package's own parser produces them."""
    from cme_fedwatch import api

    return api._parse(raw_settlements_20260918)


@pytest.fixture
def offline(monkeypatch, settlements_20260918):
    """Pin every network boundary to the 2026-09-18 state.

    Doubles sit only at the two external boundaries (CME, FRED); calc,
    fomc and the label conversion all run for real.
    """
    import cme_fedwatch
    from cme_fedwatch.api import NoSettlementData, SettlementSet

    monkeypatch.setattr(
        cme_fedwatch,
        "get_settlements",
        lambda trade_date=None: SettlementSet(TRADE_DATE_20260918, settlements_20260918),
    )
    monkeypatch.setattr(cme_fedwatch, "fetch_target_range", lambda: TARGET_RANGE_20260918)
    monkeypatch.setattr(cme_fedwatch, "fetch_effr", lambda: EFFR_20260918)
    monkeypatch.setattr(
        cme_fedwatch,
        "fetch_target_range_history",
        lambda start, end: {TRADE_DATE_20260918: TARGET_RANGE_20260918},
    )


@pytest.fixture
def history_offline(monkeypatch):
    """Serve the 2026-09-14..18 settlement week and that week's FRED ranges.

    The walk starts from 2026-09-19, a Friday, so the five business days
    the fixture holds are exactly what CME still served on 2026-09-20.
    """
    import cme_fedwatch
    from cme_fedwatch import api
    from cme_fedwatch.api import NoSettlementData, SettlementSet

    served = {}
    for day in range(14, 19):
        with (FIXTURES / f"settlements_202609{day}.json").open() as fh:
            served[date(2026, 9, day)] = api._parse(json.load(fh))

    def _get_settlements(trade_date=None):
        if trade_date is None:
            trade_date = max(served)
        if trade_date not in served:
            raise NoSettlementData(f"no settlement data for {trade_date.isoformat()}")
        return SettlementSet(trade_date, served[trade_date])

    # DFEDTARL / DFEDTARU as FRED served them for September 2026.
    with (FIXTURES / "fred_target_range_202609.json").open() as fh:
        csv_by_series = json.load(fh)

    def _parse_csv(text):
        out = {}
        for line in text.strip().split("\n")[1:]:
            day, value = line.split(",")
            if value not in (".", ""):
                out[date.fromisoformat(day)] = float(value)
        return out

    lower = _parse_csv(csv_by_series["DFEDTARL"])
    upper = _parse_csv(csv_by_series["DFEDTARU"])

    monkeypatch.setattr(cme_fedwatch, "get_settlements", _get_settlements)
    monkeypatch.setattr(cme_fedwatch, "fetch_effr", lambda: EFFR_20260918)
    monkeypatch.setattr(cme_fedwatch, "fetch_target_range", lambda: TARGET_RANGE_20260918)
    monkeypatch.setattr(
        cme_fedwatch,
        "fetch_target_range_history",
        lambda start, end: {d: (lower[d], upper[d]) for d in lower.keys() & upper.keys()},
    )

    class _Date(date):
        @classmethod
        def today(cls):
            return date(2026, 9, 19)

    monkeypatch.setattr(cme_fedwatch, "date", _Date)
