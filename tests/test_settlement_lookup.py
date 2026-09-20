"""Finding the most recent trade date that CME actually served.

CME answers 200 with ``empty: true`` for a date it has no settlement for --
weekends, US market holidays, and dates that have not happened yet in
Chicago. The lookup has to walk back past all three, because the caller's
local date can legitimately be a day ahead of the US trading date.
"""

from datetime import date

import pytest

from cme_fedwatch import api


@pytest.fixture
def cme(monkeypatch, raw_settlements_20260918):
    """Serve settlements for an explicit set of trade dates, and count calls."""
    calls = []

    def _serve(available):
        def _fetch(url, **kw):
            requested = url.split("tradeDate=")[1]
            calls.append(requested)
            if requested in available:
                return _Response({**raw_settlements_20260918, "tradeDate": requested})
            return _Response({"settlements": [], "tradeDate": requested, "empty": True})

        class _Session:
            def __init__(self, *a, **kw):
                pass

            get = staticmethod(_fetch)

        monkeypatch.setattr(api.requests, "Session", _Session)
        return calls

    return _serve


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _freeze_today(monkeypatch, today: date):
    class _Date(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(api, "date", _Date)


def test_walks_back_over_a_holiday_weekend(monkeypatch, cme):
    # Friday 2026-12-25 is a holiday and the 26th-27th are the weekend, so
    # the newest settlement is Thursday the 24th.
    cme({"12/24/2026"})
    _freeze_today(monkeypatch, date(2026, 12, 28))
    assert api.get_settlements().trade_date == date(2026, 12, 24)


def test_local_date_may_run_ahead_of_the_us_trading_date(monkeypatch, cme):
    # Monday morning in Seoul is still Sunday afternoon in Chicago, so
    # Monday has not settled anywhere and Friday is the newest day there is.
    # The walk must start at the local date and find that out, not assume it.
    calls = cme({"09/18/2026"})
    _freeze_today(monkeypatch, date(2026, 9, 21))
    assert api.get_settlements().trade_date == date(2026, 9, 18)
    assert calls[0] == "09/21/2026"
    # The intervening weekend costs no requests.
    assert calls == ["09/21/2026", "09/18/2026"]


def test_an_explicit_trade_date_is_not_silently_replaced(monkeypatch, cme):
    # Asking for a specific day that CME no longer serves must fail loudly;
    # returning a different day's numbers under that label would be worse.
    cme({"09/18/2026"})
    _freeze_today(monkeypatch, date(2026, 9, 20))
    with pytest.raises(LookupError, match="2026-06-18"):
        api.get_settlements(date(2026, 6, 18))


def test_exhausting_the_window_raises_rather_than_returning_nothing(monkeypatch, cme):
    cme(set())
    _freeze_today(monkeypatch, date(2026, 9, 20))
    with pytest.raises(LookupError):
        api.get_settlements()


def test_volume_and_open_interest_are_numbers(monkeypatch, cme):
    cme({"09/18/2026"})
    _freeze_today(monkeypatch, date(2026, 9, 18))
    row = api.get_settlements().rows[0]
    assert isinstance(row["volume"], int)
    assert isinstance(row["open_interest"], int)
