"""The history walk must terminate even when nothing is ever served.

Misses were only counted once a first snapshot had landed, so a window
with no data at all -- an outage, or a --meeting date that is not on the
schedule -- walked backwards without end.
"""

from datetime import date

import pytest

from cme_fedwatch import get_history
from cme_fedwatch.api import NoSettlementData


@pytest.fixture
def nothing_served(monkeypatch):
    import cme_fedwatch

    attempts = []

    def _get_settlements(trade_date=None):
        attempts.append(trade_date)
        raise NoSettlementData("no settlement data")

    monkeypatch.setattr(cme_fedwatch, "get_settlements", _get_settlements)
    monkeypatch.setattr(cme_fedwatch, "fetch_effr", lambda: 3.88)
    monkeypatch.setattr(cme_fedwatch, "fetch_target_range", lambda: (3.75, 4.00))
    monkeypatch.setattr(cme_fedwatch, "fetch_target_range_history", lambda start, end: {})
    return attempts


def test_gives_up_when_no_day_is_ever_served(nothing_served):
    result = get_history(days=5)
    assert result["available_days"] == 0
    assert result["history"] == []
    assert "note" in result
    # A bounded walk, not one request per business day back to the epoch.
    assert len(nothing_served) < 40


def test_a_meeting_not_on_the_schedule_does_not_walk_forever(history_offline):
    # 2026-10-29 is a day after the real meeting, so no snapshot ever
    # matches it however far back the walk goes.
    result = get_history("2026-10-29", days=5)
    assert result["available_days"] == 0
