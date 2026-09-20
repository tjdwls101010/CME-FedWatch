"""Boundary behaviour of the rate-curve bootstrap.

These conditions -- a cut, a meeting on the last day of a month, a
schedule that runs out -- cannot be provoked through the public API
without fabricating both a schedule and a futures curve, so they are
exercised against ``calculate`` directly.
"""

from datetime import date

import pytest

from cme_fedwatch.calc import calculate

TARGET = (3.75, 4.00)


def _curve(**months) -> list[dict]:
    """Build settlement rows from {'OCT 26': implied_rate, ...}."""
    return [{"month": k, "settle": 100.0 - v} for k, v in months.items()]


def test_schedule_horizon_drops_meetings_instead_of_guessing(settlements_20260918):
    # Pulling the horizon back to December 2026 removes February 2027 as an
    # anchor candidate, which is what January 2027's chain depends on.
    meetings = [date(2026, 10, 28), date(2026, 12, 9), date(2027, 1, 27)]
    out = calculate(settlements_20260918, meetings, TARGET, horizon=date(2026, 12, 9))

    assert [r["date"] for r in out] == ["2026-10-28", "2026-12-09"]
    # The meetings that a valid anchor does reach are unaffected.
    assert out[0]["probabilities"] == pytest.approx({"375-400": 42.4, "400-425": 57.6}, abs=0.1)


def test_a_cut_is_labelled_below_the_current_range():
    # November has no meeting, so it anchors October's post-meeting rate at
    # 3.65%. October's own average is built backwards from a 3.88% start
    # held for 28 days: (28 * 3.88 + 3 * 3.65) / 31 = 3.857742. That is a
    # move of -0.92 steps, so most of the weight sits one range down.
    out = calculate(
        _curve(**{"OCT 26": 3.857742, "NOV 26": 3.65}),
        [date(2026, 10, 28)],
        TARGET,
    )
    probs = out[0]["probabilities"]
    assert max(probs, key=probs.get) == "350-375"
    assert probs["350-375"] == pytest.approx(92.0, abs=0.1)


def test_meeting_on_the_last_day_of_the_month_is_dropped_not_divided_by_zero():
    # A meeting on November 30 leaves zero post-meeting days in the November
    # contract, so that contract cannot price the outcome. October anchors
    # the start rate but December is itself a meeting month, so nothing
    # anchors the end rate either. The month must be dropped rather than
    # dividing by M == 0.
    out = calculate(
        _curve(**{"OCT 26": 3.88, "NOV 26": 3.90, "DEC 26": 4.1650}),
        [date(2026, 11, 30), date(2026, 12, 9)],
        TARGET,
    )
    assert out == []


def test_no_meetings_returns_empty():
    assert calculate([], [], TARGET) == []
