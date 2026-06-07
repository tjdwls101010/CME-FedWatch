"""Behavior tests for the CLI schedule-expiry warning.

_schedule_warning is pure (status dict -> message or None), so the warning
behavior is verified without spawning the CLI or capturing stderr.
"""

from cme_fedwatch.cli import _schedule_warning


def test_warns_when_expired():
    msg = _schedule_warning({"state": "expired", "remaining": 0, "last_known": "2027-12-08"})
    assert msg is not None
    assert "expired" in msg.lower()


def test_warns_when_expiring_includes_remaining_and_last_known():
    msg = _schedule_warning({"state": "expiring", "remaining": 2, "last_known": "2027-12-08"})
    assert msg is not None
    assert "2" in msg
    assert "2027-12-08" in msg


def test_silent_when_ok():
    assert _schedule_warning({"state": "ok", "remaining": 13, "last_known": "2027-12-08"}) is None


def test_silent_when_status_missing():
    assert _schedule_warning(None) is None
