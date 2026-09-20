"""FOMC meeting schedule and contract mapping."""

from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Optional

FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"


# FOMC meeting end dates (the day the decision is announced).
# Source: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
FOMC_MEETINGS: list[date] = [
    # 2025
    date(2025, 1, 29),
    date(2025, 3, 19),
    date(2025, 5, 7),
    date(2025, 6, 18),
    date(2025, 7, 30),
    date(2025, 9, 17),
    date(2025, 10, 29),
    date(2025, 12, 10),
    # 2026
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 4, 29),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 10, 28),
    date(2026, 12, 9),
    # 2027
    date(2027, 1, 27),
    date(2027, 3, 17),
    date(2027, 4, 28),
    date(2027, 6, 9),
    date(2027, 7, 28),
    date(2027, 9, 15),
    date(2027, 10, 27),
    date(2027, 12, 8),
    # 2028
    date(2028, 1, 26),
]

# Month code mapping for Fed Funds Futures (ZQ)
_MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}

_MONTH_NAMES = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}


def get_upcoming_meetings(from_date: Optional[date] = None) -> list[date]:
    """Return FOMC meetings that haven't occurred yet."""
    if from_date is None:
        from_date = date.today()
    return [m for m in FOMC_MEETINGS if m >= from_date]


# Upcoming-meeting count at or below this triggers the 'expiring' warning.
_EXPIRING_THRESHOLD = 3


def schedule_status(from_date: Optional[date] = None) -> dict:
    """Report the health of the hardcoded FOMC schedule.

    FOMC_MEETINGS is a finite, hand-maintained list, so it eventually runs
    out. This surfaces how much runway is left, letting callers (and the CI
    updater) react before meetings silently disappear from results.

    Returns:
        Dict with:
            state: 'ok', 'expiring' (few meetings left), or 'expired' (none).
            remaining: number of upcoming meetings still in the schedule.
            last_known: ISO date of the last hardcoded meeting.
    """
    remaining = len(get_upcoming_meetings(from_date))
    if remaining == 0:
        state = "expired"
    elif remaining <= _EXPIRING_THRESHOLD:
        state = "expiring"
    else:
        state = "ok"
    return {
        "state": state,
        "remaining": remaining,
        "last_known": FOMC_MEETINGS[-1].isoformat(),
    }


def schedule_horizon() -> date:
    """Last meeting date the built-in schedule knows about.

    The probability engine bootstraps from months that have no FOMC
    meeting, so it must not look past this date: beyond it a month with no
    listed meeting is indistinguishable from one whose meeting simply has
    not been published yet, and treating it as an anchor would produce
    confidently wrong probabilities instead of a visible gap.
    """
    return FOMC_MEETINGS[-1]


def meeting_to_contract_code(meeting_date: date) -> str:
    """Map a meeting date to its Fed Funds Futures contract code.

    The contract that covers a meeting is the one expiring at the end of
    the meeting's month. E.g. a meeting on 2026-04-29 maps to ZQJ6
    (April 2026, code J, year digit 6).
    """
    code = _MONTH_CODES[meeting_date.month]
    year_digit = str(meeting_date.year % 10)
    return f"ZQ{code}{year_digit}"


def meeting_to_settlement_month(meeting_date: date) -> str:
    """Map a meeting date to the settlement month string.

    E.g. 2026-04-29 → "APR 26"
    """
    month_name = _MONTH_NAMES[meeting_date.month]
    year_short = str(meeting_date.year % 100)
    return f"{month_name} {year_short}"


def days_in_month(d: date) -> int:
    """Return the total number of days in the month of the given date."""
    return calendar.monthrange(d.year, d.month)[1]


_MONTH_NUMBERS = {name: n for n, name in enumerate(calendar.month_name) if name}
_MONTH_NUMBERS.update({name: n for n, name in enumerate(calendar.month_abbr) if name})

# The calendar page marks each meeting with two cells: a month (sometimes
# spanning two, e.g. "Apr/May") and a day range whose LAST day is the
# announcement date. Rows carrying a parenthetical note are not rate
# decisions -- an August 2025 row reads "22 (notation vote)".
_YEAR_HEADING = re.compile(r"(\d{4}) FOMC Meetings")
_MEETING_ROW = re.compile(
    r"fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>"
    r".{0,400}?fomc-meeting__date[^>]*>([^<]*)<",
    re.S,
)


def parse_fomc_calendar(html: str) -> list[date]:
    """Extract FOMC announcement dates from the Fed's calendar page HTML.

    Kept separate from the fetch so it can be exercised against a saved
    page. Raises ValueError if the page yields nothing, which is how a
    layout change surfaces instead of silently returning an empty list.
    """
    meetings: set[date] = set()
    headings = list(_YEAR_HEADING.finditer(html))
    for i, heading in enumerate(headings):
        year = int(heading.group(1))
        stop = headings[i + 1].start() if i + 1 < len(headings) else len(html)
        for month_cell, date_cell in _MEETING_ROW.findall(html[heading.end():stop]):
            if "(" in date_cell:
                continue
            days = re.findall(r"\d+", date_cell)
            if not days:
                continue
            day = int(days[-1])
            names = [n for n in month_cell.replace(".", "").strip().split("/") if n]
            try:
                months = [_MONTH_NUMBERS[n] for n in names]
            except KeyError:
                continue
            # A split-month row ends in the later month, which the day
            # numbers reveal: "Apr/May 30-1" announces on May 1.
            month = months[-1] if len(months) > 1 and day < int(days[0]) else months[0]
            meetings.add(date(year + 1 if month < months[0] else year, month, day))

    if not meetings:
        raise ValueError(f"No FOMC meetings found in calendar page ({FOMC_CALENDAR_URL})")
    return sorted(meetings)


def fetch_fomc_schedule() -> list[date]:
    """Fetch the FOMC schedule from federalreserve.gov, merged with the built-in list.

    Opt-in: nothing in the normal probability path calls this, so the
    package keeps working with no network beyond CME and FRED. The result
    is the UNION of the page and ``FOMC_MEETINGS`` -- the Fed publishes
    each year's calendar only once the prior year is under way, so the
    built-in list can legitimately reach further out than the page does.

    Raises whatever the request layer raises, or ValueError if the page
    cannot be parsed. Falling back silently would hide exactly the layout
    change this function exists to detect.
    """
    from curl_cffi import requests

    resp = requests.Session(impersonate="chrome").get(FOMC_CALENDAR_URL)
    resp.raise_for_status()
    return sorted(set(parse_fomc_calendar(resp.text)) | set(FOMC_MEETINGS))
