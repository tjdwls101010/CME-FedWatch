"""cme-fedwatch: CME FedWatch probability calculator.

Usage:
    from cme_fedwatch import get_fedwatch

    data = get_fedwatch()
    for meeting in data:
        print(meeting["date"], meeting["probabilities"])
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from .api import fetch_settlements, get_settlements
from .calc import calculate
from .fomc import (
    FOMC_MEETINGS,
    get_upcoming_meetings,
    meeting_to_contract_code,
)

__version__ = "0.1.0"

# Current effective federal funds rate (EFFR).
# This is the starting rate for the probability chain calculation.
# Update this when the Fed changes rates.
# As of March 2026: target range 4.25-4.50%, EFFR ≈ 4.33%
CURRENT_EFFR = 4.33


def get_fedwatch(
    trade_date: Optional[date] = None,
    current_rate: Optional[float] = None,
) -> list[dict]:
    """Get FedWatch probabilities for all upcoming FOMC meetings.

    Args:
        trade_date: Settlement date to use. Defaults to most recent
            business day.
        current_rate: Current effective federal funds rate. Defaults to
            the built-in CURRENT_EFFR value.

    Returns:
        List of dicts, one per meeting::

            [
                {
                    "date": "2026-04-29",
                    "contract": "ZQJ6",
                    "probabilities": {
                        "350-375": 93.8,
                        "375-400": 6.2,
                    }
                },
                ...
            ]
    """
    if current_rate is None:
        current_rate = CURRENT_EFFR

    settlements = get_settlements(trade_date)
    meetings = get_upcoming_meetings()
    return calculate(settlements, meetings, current_rate)
