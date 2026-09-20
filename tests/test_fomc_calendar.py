"""Parsing the Fed's published FOMC calendar.

The fixture is the federalreserve.gov calendar page as served on
2026-09-20. Expected dates come from that page as rendered for a reader,
not from this parser's output.
"""

from datetime import date
from pathlib import Path

import pytest

from cme_fedwatch.fomc import FOMC_MEETINGS, parse_fomc_calendar

FIXTURE = Path(__file__).parent / "fixtures" / "fomccalendars_20260920.html"

# Announcement days (the last day of each meeting) for the years the page
# had published as of 2026-09-20.
EXPECTED_2027 = [
    date(2027, 1, 27), date(2027, 3, 17), date(2027, 4, 28), date(2027, 6, 9),
    date(2027, 7, 28), date(2027, 9, 15), date(2027, 10, 27), date(2027, 12, 8),
]


@pytest.fixture
def calendar_html() -> str:
    return FIXTURE.read_text()


def test_parses_the_announcement_day_of_each_2027_meeting(calendar_html):
    parsed = parse_fomc_calendar(calendar_html)
    assert [d for d in parsed if d.year == 2027] == EXPECTED_2027


def test_skips_notation_votes(calendar_html):
    # The page lists "August 22 (notation vote)" for 2025; it is not a
    # scheduled rate decision and must not enter the schedule.
    assert date(2025, 8, 22) not in parse_fomc_calendar(calendar_html)


def test_agrees_with_the_built_in_schedule_where_they_overlap(calendar_html):
    parsed = set(parse_fomc_calendar(calendar_html))
    overlap = [d for d in FOMC_MEETINGS if date(2025, 1, 1) <= d <= date(2027, 12, 31)]
    assert set(overlap) == {d for d in parsed if date(2025, 1, 1) <= d <= date(2027, 12, 31)}


def test_rejects_a_page_it_cannot_parse():
    with pytest.raises(ValueError, match="No FOMC meetings"):
        parse_fomc_calendar("<html><body>redesigned</body></html>")


def test_fetch_merges_rather_than_replaces(calendar_html, monkeypatch):
    # The Fed publishes a year's calendar only once the prior year is under
    # way, so the built-in list reaches further out than the page: on
    # 2026-09-20 the page stopped at 2027-12-08 while FOMC_MEETINGS already
    # held 2028-01-26. Replacing instead of merging would lose it.
    import curl_cffi.requests

    class _Response:
        text = calendar_html

        def raise_for_status(self):
            return None

    class _Session:
        def __init__(self, *a, **kw):
            pass

        def get(self, url):
            return _Response()

    monkeypatch.setattr(curl_cffi.requests, "Session", _Session)

    from cme_fedwatch.fomc import fetch_fomc_schedule

    merged = fetch_fomc_schedule()
    assert date(2028, 1, 26) in merged
    assert set(FOMC_MEETINGS) <= set(merged)
    assert merged == sorted(set(merged))
