"""CME Settlement API and FRED rate client."""

from __future__ import annotations

from datetime import date, timedelta
from typing import NamedTuple, Optional

from curl_cffi import requests


_CME_SETTLEMENTS_URL = (
    "https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements"
    "/305/FUT"
)

_FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# How far back to look for the newest settled trade date. CME answers 200
# with `empty: true` for weekends, US market holidays and dates that have
# not traded yet, and the caller's local date can be a day ahead of the US
# trading date, so the walk has to clear a holiday-plus-weekend cluster
# starting one day early.
_LOOKBACK_DAYS = 10


class SettlementSet(NamedTuple):
    """Settlement rows together with the trade date they actually came from."""

    trade_date: date
    rows: list[dict]


def _fetch_fred_series(series_id: str) -> float:
    """Fetch the latest value of a FRED series."""
    session = requests.Session(impersonate="chrome")
    end = date.today()
    # Wide enough to clear a long holiday shutdown; the series is daily and
    # the parse takes the last populated row regardless.
    start = end - timedelta(days=30)
    resp = session.get(
        _FRED_URL,
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
        (lower, upper) in percentage points, e.g. (3.75, 4.00).
    """
    return _fetch_fred_series("DFEDTARL"), _fetch_fred_series("DFEDTARU")


def fetch_settlements(trade_date: date) -> dict:
    """Fetch the raw 30-Day Federal Funds Futures settlement response for one day."""
    session = requests.Session(impersonate="chrome")
    resp = session.get(
        f"{_CME_SETTLEMENTS_URL}?tradeDate={trade_date.strftime('%m/%d/%Y')}"
    )
    resp.raise_for_status()
    return resp.json()


def _has_data(payload: dict) -> bool:
    return not payload.get("empty") and bool(payload.get("settlements"))


def _parse(payload: dict) -> list[dict]:
    """Return parsed settlement prices.

    Rows with a non-numeric settle (and the 'Total' summary row) are
    skipped; they carry no price to imply a rate from.
    """
    rows = []
    for s in payload["settlements"]:
        if s["month"] == "Total":
            continue
        try:
            settle = float(s["settle"])
        except (ValueError, TypeError):
            continue
        rows.append({
            "month": s["month"],
            "settle": settle,
            "volume": _as_int(s.get("volume")),
            "open_interest": _as_int(s.get("openInterest")),
        })
    return rows


def _as_int(value: Optional[str]) -> int:
    try:
        return int(str(value or "0").replace(",", ""))
    except ValueError:
        return 0


def get_settlements(trade_date: Optional[date] = None) -> SettlementSet:
    """Return settlement prices and the trade date they came from.

    Args:
        trade_date: An exact trade date. If CME does not serve that day,
            this raises rather than substituting a neighbouring day -- the
            caller asked for a specific day's numbers. Defaults to None,
            which walks back from today to the newest day CME does serve.

    Raises:
        LookupError: No settlement data within the lookback window. CME's
            free feed keeps only about the last five business days, so this
            is the expected outcome for any older date.
    """
    if trade_date is not None:
        payload = fetch_settlements(trade_date)
        if not _has_data(payload):
            raise LookupError(
                f"CME served no settlement data for {trade_date.isoformat()}. "
                "The free feed retains roughly the last 5 business days."
            )
        return SettlementSet(trade_date, _parse(payload))

    day = date.today()
    for _ in range(_LOOKBACK_DAYS):
        if day.weekday() < 5:
            payload = fetch_settlements(day)
            if _has_data(payload):
                return SettlementSet(day, _parse(payload))
        day -= timedelta(days=1)

    raise LookupError(
        f"No CME settlement data in the {_LOOKBACK_DAYS} days to {date.today().isoformat()}."
    )
