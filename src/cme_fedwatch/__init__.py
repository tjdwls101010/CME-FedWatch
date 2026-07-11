"""cme-fedwatch: CME FedWatch probability calculator.

Usage:
    from cme_fedwatch import get_probabilities, get_history

    prob = get_probabilities()        # all meetings
    prob = get_probabilities("next")  # next meeting

    hist = get_history("next", days=10)  # how expectations changed
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from .api import fetch_effr, fetch_target_range, get_settlements
from .calc import calculate
from .fomc import FOMC_MEETINGS, get_upcoming_meetings, schedule_status

__version__ = "0.1.3"


def _target_label(lower: float, upper: float) -> str:
    return f"{lower:.2f}%-{upper:.2f}%"


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
        trade_date: Settlement date. Defaults to most recent business day.
        current_rate: EFFR override. If None, fetched from FRED.

    Returns:
        Dict with current_rate info and meetings list::

            {
                "effr": 3.64,
                "current_target": "3.50%-3.75%",
                "meetings": [{
                    "date": "2026-04-29",
                    "contract": "ZQJ6",
                    "probabilities": {
                        "3.50%-3.75%": 84.0,
                        "3.75%-4.00%": 16.0,
                    }
                }]
            }
    """
    if current_rate is None:
        current_rate = fetch_effr()

    try:
        lower, upper = fetch_target_range()
    except Exception:
        # Fallback: derive from EFFR
        from .calc import current_target_range
        lower, upper = current_target_range(current_rate)

    settlements = get_settlements(trade_date)
    meetings_list = get_upcoming_meetings()
    raw = calculate(settlements, meetings_list, current_rate)

    # Convert bps labels to percentage labels
    meetings_out = []
    for r in raw:
        probs = {}
        for k, v in r["probabilities"].items():
            lo, hi = k.split("-")
            probs[f"{int(lo)/100:.2f}%-{int(hi)/100:.2f}%"] = v
        meetings_out.append({
            "date": r["date"],
            "contract": r["contract"],
            "probabilities": probs,
        })

    if meeting == "next":
        meetings_out = meetings_out[:1]
    elif meeting is not None:
        meetings_out = [m for m in meetings_out if m["date"] == meeting]

    return {
        "effr": current_rate,
        "current_target": _target_label(lower, upper),
        "schedule_status": schedule_status(),
        "meetings": meetings_out,
    }


def _snap_to_business_day(d: date) -> date:
    """Roll back to the nearest business day."""
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _fetch_snapshot(
    trade_date: date,
    target_meeting: str,
    meetings_list: list[date],
    current_rate: float,
    label: Optional[str] = None,
) -> Optional[dict]:
    """Fetch probability snapshot for a specific trade date."""
    try:
        settlements = get_settlements(trade_date)
        raw = calculate(settlements, meetings_list, current_rate)
        for r in raw:
            if r["date"] == target_meeting:
                probs = _convert_prob_labels(r["probabilities"])
                entry = {
                    "trade_date": trade_date.isoformat(),
                    "probabilities": probs,
                }
                if label:
                    entry["label"] = label
                return entry
    except Exception:
        return None


def _convert_prob_labels(probs: dict) -> dict:
    """Convert bps labels (e.g. '350-375') to percentage labels."""
    out = {}
    for k, v in probs.items():
        lo, hi = k.split("-")
        out[f"{int(lo)/100:.2f}%-{int(hi)/100:.2f}%"] = v
    return out


# Standard lookback periods: (label, approximate calendar days)
LOOKBACK_PERIODS = [
    ("1d", 1),
    ("1w", 7),
    ("1m", 30),
    ("3m", 91),
    ("6m", 182),
    ("1y", 365),
]


def get_history(
    meeting: Optional[str] = None,
    days: int = 10,
    current_rate: Optional[float] = None,
) -> dict:
    """Get how FedWatch probabilities changed over past N business days.

    Also includes standard lookback comparisons (1d, 1w, 1m, 3m, 6m, 1y).

    Args:
        meeting: "next" (default) or "YYYY-MM-DD".
        days: Business days of daily history.
        current_rate: EFFR override.

    Returns:
        Dict with daily history and lookback snapshots::

            {
                "effr": 3.64,
                "current_target": "3.50%-3.75%",
                "meeting_date": "2026-04-29",
                "contract": "ZQJ6",
                "history": [
                    {"trade_date": "2026-03-18", "probabilities": {...}},
                    ...
                ],
                "lookback": [
                    {"label": "1d", "trade_date": "2026-03-19", "probabilities": {...}},
                    {"label": "1w", "trade_date": "2026-03-13", "probabilities": {...}},
                    ...
                ]
            }
    """
    if current_rate is None:
        current_rate = fetch_effr()

    try:
        lower, upper = fetch_target_range()
    except Exception:
        from .calc import current_target_range
        lower, upper = current_target_range(current_rate)

    meetings_list = get_upcoming_meetings()
    empty = {"effr": current_rate, "current_target": _target_label(lower, upper),
             "schedule_status": schedule_status(),
             "meeting_date": None, "contract": None, "history": [], "lookback": []}
    if not meetings_list:
        return empty

    target = meetings_list[0].isoformat() if (meeting is None or meeting == "next") else meeting

    # Daily history
    history = []
    d = date.today() - timedelta(days=1)
    collected = 0
    while collected < days and d >= date.today() - timedelta(days=days * 2):
        if d.weekday() >= 5:
            d -= timedelta(days=1)
            continue
        snap = _fetch_snapshot(d, target, meetings_list, current_rate)
        if snap:
            history.append(snap)
            collected += 1
        d -= timedelta(days=1)
    history.reverse()

    # Lookback snapshots (1d, 1w, 1m, 3m, 6m, 1y)
    lookback = []
    today = date.today()
    for label, cal_days in LOOKBACK_PERIODS:
        ref_date = _snap_to_business_day(today - timedelta(days=cal_days))
        snap = _fetch_snapshot(ref_date, target, meetings_list, current_rate, label=label)
        if snap:
            lookback.append(snap)

    # Find contract code
    contract = None
    try:
        for r in calculate(get_settlements(), meetings_list, current_rate):
            if r["date"] == target:
                contract = r["contract"]
                break
    except Exception:
        pass

    return {
        "effr": current_rate,
        "current_target": _target_label(lower, upper),
        "schedule_status": schedule_status(),
        "meeting_date": target,
        "contract": contract,
        "history": history,
        "lookback": lookback,
    }


# Convenience alias
get_fedwatch = get_probabilities
