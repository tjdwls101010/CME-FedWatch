"""CME Settlement API and NY Fed EFFR client."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from curl_cffi import requests


_CME_SETTLEMENTS_URL = (
    "https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements"
    "/305/FUT"
)

_FRED_EFFR_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def _recent_business_day(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _fetch_fred_series(series_id: str) -> float:
    """Fetch the latest value of a FRED series."""
    session = requests.Session(impersonate="chrome")
    end = date.today()
    start = end - timedelta(days=10)
    resp = session.get(
        _FRED_EFFR_URL,
        params={"id": series_id, "cosd": start.isoformat(), "coed": end.isoformat()},
    )
    resp.raise_for_status()
    for line in reversed(resp.text.strip().split("\n")[1:]):
        parts = line.split(",")
        if len(parts) == 2 and parts[1] not in (".", ""):
            return float(parts[1])
    raise ValueError(f"Could not fetch {series_id} from FRED")


def fetch_effr() -> float:
    """Fetch the latest effective federal funds rate from FRED."""
    return _fetch_fred_series("EFFR")


def fetch_target_range() -> tuple[float, float]:
    """Fetch the current FOMC target rate range from FRED.

    Returns:
        (lower, upper) in percentage points, e.g. (3.50, 3.75).
    """
    lower = _fetch_fred_series("DFEDTARL")
    upper = _fetch_fred_series("DFEDTARU")
    return lower, upper


def fetch_settlements(trade_date: Optional[date] = None) -> dict:
    """Fetch 30-Day Federal Funds Futures settlement data from CME.

    Args:
        trade_date: The trade date to query. Defaults to the most recent
            business day.

    Returns:
        Raw JSON response dict from CME.
    """
    if trade_date is None:
        trade_date = _recent_business_day(date.today() - timedelta(days=1))

    date_str = trade_date.strftime("%m/%d/%Y")
    session = requests.Session(impersonate="chrome")
    resp = session.get(f"{_CME_SETTLEMENTS_URL}?tradeDate={date_str}")
    resp.raise_for_status()
    data = resp.json()

    if data.get("empty"):
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
