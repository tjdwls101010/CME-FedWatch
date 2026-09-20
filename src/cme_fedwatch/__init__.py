"""cme-fedwatch: CME FedWatch probability calculator.

Usage:
    from cme_fedwatch import get_probabilities, get_history

    prob = get_probabilities()        # all meetings
    prob = get_probabilities("next")  # next meeting

    hist = get_history("next", days=10)  # how expectations changed
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .api import fetch_effr, fetch_target_range, get_settlements
from .calc import calculate
from .fomc import (
    FOMC_MEETINGS,
    get_upcoming_meetings,
    meeting_to_contract_code,
    schedule_horizon,
    schedule_status,
)

__version__ = "0.2.0"

# CME's free settlement feed retains roughly the last five business days, so
# a longer history is truncated rather than fetched. Stopping after this many
# consecutive misses ends the walk once it has fallen off that window, while
# still stepping over a holiday sitting inside it.
_MAX_CONSECUTIVE_MISSES = 3


def _target_label(lower: float, upper: float) -> str:
    return f"{lower:.2f}%-{upper:.2f}%"


def _current_range(current_rate: float) -> tuple[float, float]:
    try:
        return fetch_target_range()
    except Exception:
        # FRED's target-range series is unavailable; the EFFR always trades
        # inside the band, so flooring it recovers the same range.
        from .calc import current_target_range

        return current_target_range(current_rate)


def _to_percent_labels(probs: dict) -> dict:
    """Convert bps labels (e.g. '375-400') to percentage labels."""
    out = {}
    for label, value in probs.items():
        lo, hi = label.split("-")
        out[f"{int(lo) / 100:.2f}%-{int(hi) / 100:.2f}%"] = value
    return out


def get_probabilities(
    meeting: Optional[str] = None,
    trade_date: Optional[date] = None,
    current_rate: Optional[float] = None,
) -> dict:
    """Get FedWatch probabilities for FOMC meetings.

    Args:
        meeting: Filter to a specific meeting.
            - None: all upcoming meetings
            - "next": next meeting only
            - "YYYY-MM-DD": specific meeting date
        trade_date: Settlement date. Defaults to the newest one CME serves.
        current_rate: EFFR override. If None, fetched from FRED.

    Returns:
        Dict with rate context and a meetings list::

            {
                "effr": 3.88,
                "current_target": "3.75%-4.00%",
                "trade_date": "2026-09-18",
                "schedule_status": {...},
                "meetings": [{
                    "date": "2026-10-28",
                    "contract": "ZQV6",
                    "probabilities": {
                        "3.75%-4.00%": 42.4,
                        "4.00%-4.25%": 57.6,
                    }
                }]
            }

    Raises:
        LookupError: CME served no settlement data for the requested date.
    """
    if current_rate is None:
        current_rate = fetch_effr()
    lower, upper = _current_range(current_rate)

    settlements = get_settlements(trade_date)
    # Meetings are those upcoming as of the settlement, not as of the local
    # clock, so an explicit --date reports the meetings that day was pricing.
    meetings_list = get_upcoming_meetings(settlements.trade_date)
    raw = calculate(settlements.rows, meetings_list, (lower, upper), schedule_horizon())

    meetings_out = [
        {
            "date": r["date"],
            "contract": r["contract"],
            "probabilities": _to_percent_labels(r["probabilities"]),
        }
        for r in raw
    ]

    if meeting == "next":
        meetings_out = meetings_out[:1]
    elif meeting is not None:
        meetings_out = [m for m in meetings_out if m["date"] == meeting]

    return {
        "effr": current_rate,
        "current_target": _target_label(lower, upper),
        "trade_date": settlements.trade_date.isoformat(),
        "schedule_status": schedule_status(),
        "meetings": meetings_out,
    }


def _snapshot(
    trade_date: date,
    target_meeting: str,
    current_range: tuple[float, float],
) -> Optional[dict]:
    """Probabilities for one meeting as of one trade date, or None if unserved.

    Only a missing settlement is swallowed. A network or parsing failure
    propagates, so an outage cannot masquerade as a short history.
    """
    try:
        settlements = get_settlements(trade_date)
    except LookupError:
        return None

    meetings_list = get_upcoming_meetings(settlements.trade_date)
    for r in calculate(settlements.rows, meetings_list, current_range, schedule_horizon()):
        if r["date"] == target_meeting:
            return {
                "trade_date": trade_date.isoformat(),
                "probabilities": _to_percent_labels(r["probabilities"]),
            }
    return None


def get_history(
    meeting: Optional[str] = None,
    days: int = 10,
    current_rate: Optional[float] = None,
) -> dict:
    """Get how FedWatch probabilities changed over past business days.

    Args:
        meeting: "next" (default) or "YYYY-MM-DD".
        days: Business days of daily history to request.
        current_rate: EFFR override.

    Returns:
        Dict with the daily history and how much of the request it covers::

            {
                "effr": 3.88,
                "current_target": "3.75%-4.00%",
                "meeting_date": "2026-10-28",
                "contract": "ZQV6",
                "requested_days": 10,
                "available_days": 5,
                "note": "CME's free settlement feed served 5 of 10 ...",
                "history": [
                    {"trade_date": "2026-09-14", "probabilities": {...}},
                    ...
                ]
            }

        ``note`` is present only when fewer days were served than asked
        for. CME's free feed retains roughly the last five business days,
        so any longer request is truncated; missing days are omitted, never
        filled in.
    """
    if current_rate is None:
        current_rate = fetch_effr()
    lower, upper = _current_range(current_rate)

    meetings_list = get_upcoming_meetings()
    result = {
        "effr": current_rate,
        "current_target": _target_label(lower, upper),
        "schedule_status": schedule_status(),
        "meeting_date": None,
        "contract": None,
        "requested_days": days,
        "available_days": 0,
        "history": [],
    }
    if not meetings_list:
        return result

    target = (
        meetings_list[0].isoformat()
        if meeting in (None, "next")
        else meeting
    )

    history = []
    day = date.today()
    misses = 0
    while len(history) < days and misses < _MAX_CONSECUTIVE_MISSES:
        if day.weekday() < 5:
            snap = _snapshot(day, target, (lower, upper))
            if snap:
                history.append(snap)
                misses = 0
            elif history:
                misses += 1
        day -= timedelta(days=1)
    history.reverse()

    result["meeting_date"] = target
    result["contract"] = meeting_to_contract_code(date.fromisoformat(target))
    result["available_days"] = len(history)
    result["history"] = history
    if len(history) < days:
        result["note"] = (
            f"CME's free settlement feed served {len(history)} of the {days} "
            "business days requested; it retains roughly the last 5. "
            "Missing days are omitted, not estimated."
        )
    return result


# Convenience alias
get_fedwatch = get_probabilities
