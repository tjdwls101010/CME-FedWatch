"""Cases an independent review reproduced against the first rewrite.

Each of these is a curve the methodology can solve, or a distribution it
defines, that the implementation got wrong.
"""

from datetime import date

import pytest

from cme_fedwatch.calc import calculate


def _curve(**months) -> list[dict]:
    return [{"month": k, "settle": 100.0 - v} for k, v in months.items()]


def test_a_forward_solved_rate_carries_to_the_next_meeting():
    # August anchors June and July backwards; February anchors March
    # forwards. March's solved end rate is April's start rate, so April
    # resolves too -- even though May has no quote at all.
    out = calculate(
        _curve(**{
            "JAN 26": 4.0,
            "FEB 26": 4.0,
            "MAR 26": (18 * 4.0 + 13 * 3.75) / 31,
            "APR 26": (29 * 3.75 + 1 * 3.50) / 30,
            "JUN 26": (17 * 3.50 + 13 * 3.25) / 30,
            "JUL 26": (29 * 3.25 + 2 * 3.00) / 31,
            "AUG 26": 3.0,
        }),
        [date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29),
         date(2026, 6, 17), date(2026, 7, 29)],
        (3.75, 4.00),
        horizon=date(2026, 8, 31),
        schedule=[date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29),
                  date(2026, 6, 17), date(2026, 7, 29)],
    )
    assert [r["date"] for r in out] == [
        "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
    ]


def test_an_anchor_before_the_first_meeting_is_used():
    # February has no meeting, so it pins March's start rate at 4.00%.
    # March's own average then gives its end rate. April is not needed.
    out = calculate(
        _curve(**{"FEB 26": 4.0, "MAR 26": (18 * 4.0 + 13 * 3.75) / 31}),
        [date(2026, 3, 18)],
        (4.00, 4.25),
        horizon=date(2026, 4, 30),
        schedule=[date(2026, 3, 18)],
    )
    assert out[0]["probabilities"] == pytest.approx({"3.75%-4.00%": 100.0}, abs=0.1)


def test_small_per_meeting_probabilities_accumulate_instead_of_being_pruned():
    # Eight meetings each pricing a 0.04% chance of a hike. Individually
    # every branch is below the display threshold; together they are 0.3%,
    # which must survive to the last meeting rather than being dropped at
    # each convolution.
    months = {"DEC 25": 4.0}
    meetings = []
    rate = 4.0
    for i, (label, month) in enumerate(
        [("JAN 26", 1), ("FEB 26", 2), ("MAR 26", 3), ("APR 26", 4),
         ("MAY 26", 5), ("JUN 26", 6), ("JUL 26", 7), ("AUG 26", 8)]
    ):
        meetings.append(date(2026, month, 15))
        end = rate + 0.0001
        days = (date(2026, month + 1, 1) - date(2026, month, 1)).days
        months[label] = (15 * rate + (days - 15) * end) / days
        rate = end
    months["SEP 26"] = rate
    out = calculate(
        _curve(**months), meetings, (3.75, 4.00),
        horizon=date(2026, 9, 30), schedule=meetings,
    )
    assert "4.00%-4.25%" in out[-1]["probabilities"]
    assert out[-1]["probabilities"]["4.00%-4.25%"] == pytest.approx(0.3, abs=0.05)


def test_a_cut_below_zero_is_not_silently_deleted():
    # At the zero lower bound the solver splits 50/50 between one cut and
    # no change. Dropping the negative label would publish half a
    # distribution as if it were whole.
    out = calculate(
        _curve(**{"APR 26": (29 * 0.25 + 0.125) / 30, "MAY 26": 0.125}),
        [date(2026, 4, 29)],
        (0.00, 0.25),
        horizon=date(2026, 5, 31),
        schedule=[date(2026, 4, 29)],
    )
    assert sum(out[0]["probabilities"].values()) == pytest.approx(100.0, abs=0.2)


def test_probabilities_still_sum_to_100_far_out(settlements_20260918):
    from cme_fedwatch.fomc import FOMC_MEETINGS, schedule_horizon

    meetings = [m for m in FOMC_MEETINGS if m >= date(2026, 10, 1)]
    for r in calculate(settlements_20260918, meetings, (3.75, 4.00), schedule_horizon()):
        assert sum(r["probabilities"].values()) == pytest.approx(100.0, abs=0.3), r["date"]
