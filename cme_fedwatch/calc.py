"""FedWatch probability calculation engine.

Each meeting's probability is computed independently using the previous
month's implied rate as the pre-meeting rate. For meetings in the last
3 days of the month, the next month's contract is used for the post-rate.

The probability is derived from the expected number of 25bp moves:
    expected_moves = (post_rate - pre_rate) / 0.25
Then distributed across the two adjacent integer outcomes.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Optional

from .fomc import (
    _MONTH_NAMES,
    days_in_month,
    meeting_to_contract_code,
    meeting_to_settlement_month,
)


def _target_range_label(lower_bps: int) -> str:
    return f"{lower_bps}-{lower_bps + 25}"


def _month_key(year: int, month: int) -> str:
    return f"{_MONTH_NAMES[month]} {year % 100}"


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def current_target_range(effr: float) -> tuple[float, float]:
    """Derive the current target range from the EFFR.

    Returns (lower, upper) in percentage points, e.g. (3.50, 3.75).
    """
    lower_bps = int(math.floor(effr * 100 / 25.0)) * 25
    return lower_bps / 100, (lower_bps + 25) / 100


def calculate(
    settlements: list[dict],
    meetings: list[date],
    current_rate: float,
) -> list[dict]:
    """Calculate FedWatch probabilities for each FOMC meeting.

    Args:
        settlements: Settlement dicts with 'month' and 'settle'.
        meetings: FOMC meeting dates.
        current_rate: Current EFFR (e.g. 3.64).
    """
    settle_map = {s["month"]: s["settle"] for s in settlements}
    current_lower, current_upper = current_target_range(current_rate)
    results = []

    for meeting in meetings:
        month_key = meeting_to_settlement_month(meeting)
        if month_key not in settle_map:
            continue

        settle_price = settle_map[month_key]
        implied_rate = 100.0 - settle_price

        d = meeting.day
        D = days_in_month(meeting)
        n_post = D - d + 1

        # Pre-meeting rate: previous month's implied or current EFFR
        py, pm = _prev_month(meeting.year, meeting.month)
        prev_key = _month_key(py, pm)
        pre_rate = (100.0 - settle_map[prev_key]) if prev_key in settle_map else current_rate

        # Post-meeting rate
        ny, nm = _next_month(meeting.year, meeting.month)
        next_key = _month_key(ny, nm)

        if n_post <= 3 and next_key in settle_map:
            post_rate = 100.0 - settle_map[next_key]
        else:
            n_pre = d - 1
            post_rate = (implied_rate * D - pre_rate * n_pre) / n_post if n_post > 0 else implied_rate

        # Compute probabilities with direction labels
        probabilities = _moves_to_probabilities(pre_rate, post_rate, current_lower)

        results.append({
            "date": meeting.isoformat(),
            "contract": meeting_to_contract_code(meeting),
            "probabilities": probabilities,
        })

    return results


def _moves_to_probabilities(
    pre_rate: float, post_rate: float, current_lower_pct: float
) -> dict[str, float]:
    """Convert pre/post rates to probability distribution."""
    pre_bps = pre_rate * 100
    pre_lower = int(math.floor(pre_bps / 25.0)) * 25

    expected_moves = (post_rate - pre_rate) / 0.25
    floor_m = math.floor(expected_moves)

    p_ceil = max(0.0, min(1.0, expected_moves - floor_m))
    p_floor = 1.0 - p_ceil

    target_floor = pre_lower + int(floor_m) * 25
    target_ceil = pre_lower + int(floor_m + 1) * 25

    probs: dict[str, float] = {}
    if p_floor > 0.001:
        probs[_target_range_label(target_floor)] = round(p_floor * 100, 1)
    if p_ceil > 0.001:
        probs[_target_range_label(target_ceil)] = round(p_ceil * 100, 1)

    return probs
