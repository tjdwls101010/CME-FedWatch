"""The calculated probabilities must match CME's published FedWatch output.

Expected values are read off the CME FedWatch Tool on 2026-09-20, which was
showing the 09/18/2026 settlement (the 20th was a Sunday) -- the same
settlement the fixture holds. They are therefore an independent statement of
what the answer should be, not a restatement of what this code computes.
"""

import pytest

from cme_fedwatch import get_probabilities


def _probs(result, meeting_date):
    for m in result["meetings"]:
        if m["date"] == meeting_date:
            return m["probabilities"]
    raise AssertionError(f"{meeting_date} missing from {[m['date'] for m in result['meetings']]}")


def test_october_2026_matches_cme(offline):
    # CME FedWatch, 2026-09-20: 3.75-4.00% 42.4%, 4.00-4.25% 57.6%.
    probs = _probs(get_probabilities(), "2026-10-28")
    assert probs == pytest.approx({"3.75%-4.00%": 42.4, "4.00%-4.25%": 57.6}, abs=0.1)


def test_december_2026_spans_three_ranges(offline):
    # CME FedWatch, 2026-09-20: 3.75-4.00% 9.9%, 4.00-4.25% 46.0%,
    # 4.25-4.50% 44.1%. Three ranges because December's own two-outcome
    # split is convolved with October's -- a per-meeting calculation cannot
    # produce this shape at all.
    probs = _probs(get_probabilities(), "2026-12-09")
    assert probs == pytest.approx(
        {"3.75%-4.00%": 9.9, "4.00%-4.25%": 46.0, "4.25%-4.50%": 44.1}, abs=0.1
    )


def test_probabilities_sum_to_100(offline):
    for m in get_probabilities()["meetings"]:
        assert sum(m["probabilities"].values()) == pytest.approx(100.0, abs=0.3), m["date"]


def test_next_meeting_ranges_straddle_the_current_target(offline):
    # The guard that would have caught the shipped bug outright: 0.1.3 put
    # the next meeting at 4.50-5.00% while the target range was 3.75-4.00%.
    probs = _probs(get_probabilities("next"), "2026-10-28")
    assert "3.75%-4.00%" in probs
