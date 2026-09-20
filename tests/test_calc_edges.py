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


def test_a_month_past_the_schedule_horizon_is_not_treated_as_an_anchor(settlements_20260918):
    # October 2026's chain hangs entirely on November being a no-meeting
    # month. Past the horizon that is unknowable -- an unpublished meeting
    # looks exactly like no meeting -- so the engine must drop the meeting
    # rather than answer from a guess.
    meetings = [date(2026, 10, 28)]
    assert calculate(settlements_20260918, meetings, TARGET, horizon=date(2026, 10, 28)) == []

    # One month further out, November is inside the known schedule and the
    # same curve resolves.
    out = calculate(settlements_20260918, meetings, TARGET, horizon=date(2026, 11, 30))
    assert out[0]["probabilities"] == pytest.approx(
        {"3.75%-4.00%": 42.4, "4.00%-4.25%": 57.6}, abs=0.1
    )


def test_a_cut_is_labelled_below_the_current_range():
    # November has no meeting, so it anchors October's post-meeting rate at
    # 3.65%. October's own average is built backwards from a 3.88% start
    # held for 28 days: (28 * 3.88 + 3 * 3.65) / 31 = 3.857742. That is a
    # move of -0.92 steps, so most of the weight sits one range down.
    out = calculate(
        _curve(**{"OCT 26": 3.857742, "NOV 26": 3.65}),
        [date(2026, 10, 28)],
        TARGET,
        schedule=[date(2026, 10, 28)],
    )
    probs = out[0]["probabilities"]
    assert max(probs, key=probs.get) == "3.50%-3.75%"
    assert probs["3.50%-3.75%"] == pytest.approx(92.0, abs=0.1)


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
        schedule=[date(2026, 11, 30), date(2026, 12, 9)],
    )
    assert out == []


def test_no_meetings_returns_empty():
    assert calculate([], [], TARGET) == []
