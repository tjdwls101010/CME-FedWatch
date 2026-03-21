"""FedWatch probability calculation engine.

Implements the CME FedWatch methodology:
1. Derive implied fed funds rate from futures settlement prices.
2. Back out the post-meeting rate using the day-weighted formula.
3. Distribute the implied rate across 25bp target-rate buckets.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Optional

from .fomc import days_in_month, meeting_to_settlement_month


def _target_range_label(lower_bps: int) -> str:
    """Format a target range label like '350-375'."""
    return f"{lower_bps}-{lower_bps + 25}"


def calculate(
    settlements: list[dict],
    meetings: list[date],
    current_rate: float,
) -> list[dict]:
    """Calculate FedWatch probabilities for each FOMC meeting.

    Args:
        settlements: List of settlement dicts from api.get_settlements().
            Each must have 'month' (e.g. "APR 26") and 'settle' (float).
        meetings: List of FOMC meeting dates to compute probabilities for.
        current_rate: The current effective federal funds rate (e.g. 4.33
            for the midpoint of 4.25-4.50 target range, or the actual EFFR).

    Returns:
        List of dicts, one per meeting:
        {
            "date": "2026-04-29",
            "contract": "ZQJ6",
            "probabilities": {"325-350": 0.0, "350-375": 93.8, ...},
        }
    """
    # Build a lookup: settlement month string → settle price
    settle_map: dict[str, float] = {}
    for s in settlements:
        settle_map[s["month"]] = s["settle"]

    pre_rate = current_rate
    results = []

    for meeting in meetings:
        month_key = meeting_to_settlement_month(meeting)
        if month_key not in settle_map:
            continue

        settle_price = settle_map[month_key]
        implied_rate = 100.0 - settle_price

        d = meeting.day  # day of month when meeting ends
        D = days_in_month(meeting)

        # Back out the post-meeting rate
        if D == d:
            # Meeting on the last day — implied rate IS the post-meeting rate
            post_rate = implied_rate
        else:
            post_rate = (implied_rate * D - pre_rate * (d - 1)) / (D - d + 1)

        # Distribute across 25bp buckets
        probabilities = _distribute_probability(post_rate)

        from .fomc import meeting_to_contract_code
        results.append({
            "date": meeting.isoformat(),
            "contract": meeting_to_contract_code(meeting),
            "probabilities": probabilities,
        })

        # Chain: this meeting's post-rate becomes next meeting's pre-rate
        pre_rate = post_rate

    return results


def _distribute_probability(rate: float) -> dict[str, float]:
    """Distribute an implied rate across 25bp target-rate buckets.

    The rate is expressed in percentage points (e.g. 3.65 for 3.65%).
    Target rates are in 25bp increments.

    Returns:
        Dict mapping target range labels to probabilities (0-100).
        E.g. {"350-375": 93.8, "375-400": 6.2}
    """
    # Convert rate to basis points for bucketing
    rate_bps = rate * 100  # e.g. 3.65% → 365 bps

    # Find the two adjacent 25bp buckets
    lower_bps = int(math.floor(rate_bps / 25.0)) * 25
    upper_bps = lower_bps + 25

    # Probability of being at the upper bucket
    if upper_bps == lower_bps:
        p_upper = 0.0
    else:
        p_upper = (rate_bps - lower_bps) / 25.0

    p_lower = 1.0 - p_upper

    probs: dict[str, float] = {}

    if p_lower > 0.001:
        probs[_target_range_label(lower_bps)] = round(p_lower * 100, 1)
    if p_upper > 0.001:
        probs[_target_range_label(upper_bps)] = round(p_upper * 100, 1)

    return probs
