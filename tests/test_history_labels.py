"""History rows must be labelled against the target range of their own day.

The 2026-09-16 FOMC raised the range from 3.50-3.75% to 3.75-4.00%,
effective the 17th. A snapshot taken on the 14th therefore describes
outcomes relative to 3.50-3.75%. Labelling it with today's range would
invent a 25bp jump on the 17th that the market never priced -- only the
baseline moved.

Target ranges here come from FRED's DFEDTARL/DFEDTARU daily series, saved
verbatim in the fixture, not from anything this package computes.
"""

from datetime import date

import pytest

from cme_fedwatch import get_history


def test_pre_hike_rows_use_the_pre_hike_range(history_offline):
    rows = {h["trade_date"]: h["probabilities"] for h in get_history(days=5)["history"]}

    before = rows["2026-09-14"]
    assert "3.50%-3.75%" in before
    assert "4.25%-4.50%" not in before

    after = rows["2026-09-18"]
    assert "3.75%-4.00%" in after
    assert "3.50%-3.75%" not in after


def test_the_hike_does_not_show_up_as_a_repricing(history_offline):
    # Both days price roughly a 57/43 split over two adjacent ranges; what
    # changes between them is which ranges those are, not the market's view.
    rows = {h["trade_date"]: h["probabilities"] for h in get_history(days=5)["history"]}
    assert max(rows["2026-09-14"].values()) == pytest.approx(53.0, abs=1.0)
    assert max(rows["2026-09-18"].values()) == pytest.approx(57.6, abs=1.0)


def test_reports_how_much_of_the_request_was_served(history_offline):
    result = get_history(days=10)
    assert result["requested_days"] == 10
    assert result["available_days"] == 5
    assert "5 of the 10" in result["note"]
    assert "lookback" not in result


def test_no_note_when_the_request_is_fully_served(history_offline):
    result = get_history(days=5)
    assert result["available_days"] == 5
    assert "note" not in result
