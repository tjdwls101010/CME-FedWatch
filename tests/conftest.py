"""Shared fixtures: real CME settlement data, no network.

The settlement fixture is the verbatim CME response for trade date
09/18/2026, so tests exercise the real parsing path and the real
calculation against prices that actually traded.
"""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Target range and EFFR in effect on 2026-09-18, after the 2026-09-16 FOMC
# raised the range by 25bp. Source: FOMC statement 2026-09-16; FRED EFFR.
TARGET_RANGE_20260918 = (3.75, 4.00)
EFFR_20260918 = 3.88


@pytest.fixture
def raw_settlements_20260918() -> dict:
    """Verbatim CME Settlements response for trade date 09/18/2026."""
    with (FIXTURES / "settlements_20260918.json").open() as fh:
        return json.load(fh)


@pytest.fixture
def settlements_20260918(raw_settlements_20260918, monkeypatch) -> list[dict]:
    """Settlement rows as the package's own parser produces them."""
    from cme_fedwatch import api

    monkeypatch.setattr(
        api, "fetch_settlements", lambda trade_date=None: raw_settlements_20260918
    )
    return api.get_settlements()


@pytest.fixture
def offline(monkeypatch, settlements_20260918):
    """Pin every network boundary to the 2026-09-18 state.

    Doubles sit only at the two external boundaries (CME, FRED); calc,
    fomc and the label conversion all run for real.
    """
    import cme_fedwatch

    monkeypatch.setattr(
        cme_fedwatch, "get_settlements", lambda trade_date=None: settlements_20260918
    )
    monkeypatch.setattr(cme_fedwatch, "fetch_target_range", lambda: TARGET_RANGE_20260918)
    monkeypatch.setattr(cme_fedwatch, "fetch_effr", lambda: EFFR_20260918)
