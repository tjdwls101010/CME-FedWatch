"""CME Settlement API client."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Optional

from curl_cffi import requests


_CME_SETTLEMENTS_URL = (
    "https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements"
    "/305/FUT"
)


def _recent_business_day(d: date) -> date:
    """Roll back to the most recent weekday."""
    while d.weekday() >= 5:  # Saturday=5, Sunday=6
        d -= timedelta(days=1)
    return d


def fetch_settlements(trade_date: Optional[date] = None) -> dict:
    """Fetch 30-Day Federal Funds Futures settlement data from CME.

    Args:
        trade_date: The trade date to query. Defaults to the most recent
            business day.

    Returns:
        Raw JSON response from CME as a dict with keys:
        - settlements: list of per-contract dicts
        - tradeDate, updateTime, dsHeader, reportType, empty
    """
    if trade_date is None:
        trade_date = _recent_business_day(date.today() - timedelta(days=1))

    date_str = trade_date.strftime("%m/%d/%Y")
    session = requests.Session(impersonate="chrome")
    resp = session.get(f"{_CME_SETTLEMENTS_URL}?tradeDate={date_str}")
    resp.raise_for_status()
    data = resp.json()

    if data.get("empty"):
        # Try the previous business day
        prev = _recent_business_day(trade_date - timedelta(days=1))
        date_str = prev.strftime("%m/%d/%Y")
        resp = session.get(f"{_CME_SETTLEMENTS_URL}?tradeDate={date_str}")
        resp.raise_for_status()
        data = resp.json()

    return data


def get_settlements(trade_date: Optional[date] = None) -> list[dict]:
    """Return parsed settlement prices.

    Returns:
        List of dicts with keys: month, settle, volume, open_interest.
        Only includes contracts with valid settlement prices.
    """
    data = fetch_settlements(trade_date)
    results = []
    for s in data["settlements"]:
        if s["month"] == "Total":
            continue
        try:
            settle = float(s["settle"])
        except (ValueError, TypeError):
            continue
        results.append({
            "month": s["month"],
            "settle": settle,
            "volume": s.get("volume", "0").replace(",", ""),
            "open_interest": s.get("openInterest", "0").replace(",", ""),
        })
    return results
