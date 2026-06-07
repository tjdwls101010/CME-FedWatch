"""Behavior tests for the FOMC schedule health check.

These tests are deterministic and network-free: schedule_status reads only
the hardcoded FOMC_MEETINGS list, so injecting from_date lets us exercise
every state without touching CME or FRED.
"""

from datetime import date

from cme_fedwatch.fomc import FOMC_MEETINGS, schedule_status


def test_status_ok_when_many_meetings_remain():
    # Mid-2026: a dozen hardcoded meetings still lie ahead.
    st = schedule_status(from_date=date(2026, 6, 7))
    assert st["state"] == "ok"
    assert st["remaining"] >= 4


def test_status_expiring_when_few_meetings_remain():
    # Late 2027: only the final hardcoded meeting (2027-12-08) is left.
    st = schedule_status(from_date=date(2027, 11, 1))
    assert st["state"] == "expiring"
    assert 0 < st["remaining"] <= 3


def test_status_expired_when_no_meetings_remain():
    # Past the last hardcoded meeting: the schedule has run out.
    st = schedule_status(from_date=date(2028, 1, 1))
    assert st["state"] == "expired"
    assert st["remaining"] == 0


def test_status_surfaces_last_known_meeting():
    # The last hardcoded date is reported so a maintainer knows the horizon.
    st = schedule_status(from_date=date(2026, 6, 7))
    assert st["last_known"] == FOMC_MEETINGS[-1].isoformat()
