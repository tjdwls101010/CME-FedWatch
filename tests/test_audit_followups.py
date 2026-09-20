"""Edge cases an independent audit flagged after 0.2.0 shipped."""

from datetime import date

import pytest

from cme_fedwatch import api
from cme_fedwatch.cli import _collect_all_rates


def test_rate_columns_sort_numerically_not_lexicographically():
    # "10.00%-10.25%" sorts before "9.50%-9.75%" as text, which would print
    # the table's columns out of order once rates reach double digits.
    rates = _collect_all_rates([
        {"probabilities": {"9.75%-10.00%": 1.0, "10.00%-10.25%": 2.0, "9.50%-9.75%": 3.0}}
    ])
    assert rates == ["9.50%-9.75%", "9.75%-10.00%", "10.00%-10.25%"]


def test_a_non_finite_settlement_price_is_rejected():
    # float("NaN") parses happily and then poisons every rate derived from
    # it, silently, rather than the row being skipped like other bad prices.
    rows = api._parse({
        "settlements": [
            {"month": "OCT 26", "settle": "NaN", "volume": "1", "openInterest": "1"},
            {"month": "NOV 26", "settle": "Infinity", "volume": "1", "openInterest": "1"},
            {"month": "DEC 26", "settle": "95.835", "volume": "1", "openInterest": "1"},
        ],
        "empty": False,
    })
    assert [r["month"] for r in rows] == ["DEC 26"]


def test_history_targets_the_meeting_that_was_upcoming_for_its_settlement(
    monkeypatch, raw_settlements_20260918
):
    # Anchoring on the local calendar instead of the settlement picks the
    # wrong meeting in the hours when the two disagree: at midnight in Seoul
    # on the 17th, Chicago is still mid-afternoon on the 16th and the newest
    # settlement CME serves is the 16th's -- a day on which the September
    # meeting had not happened yet. Reporting December's numbers under
    # September's settlement would be simply mislabelled.
    import json

    import cme_fedwatch
    from cme_fedwatch import get_history
    from cme_fedwatch.api import NoSettlementData, SettlementSet
    from conftest import FIXTURES

    served = {}
    for day in (14, 15, 16):
        with (FIXTURES / f"settlements_202609{day}.json").open() as fh:
            served[date(2026, 9, day)] = api._parse(json.load(fh))

    def _get_settlements(trade_date=None):
        if trade_date is None:
            trade_date = max(served)
        if trade_date not in served:
            raise NoSettlementData(f"no data for {trade_date}")
        return SettlementSet(trade_date, served[trade_date])

    monkeypatch.setattr(cme_fedwatch, "get_settlements", _get_settlements)
    monkeypatch.setattr(cme_fedwatch, "fetch_effr", lambda: 3.63)
    monkeypatch.setattr(cme_fedwatch, "fetch_target_range", lambda: (3.50, 3.75))
    monkeypatch.setattr(cme_fedwatch, "fetch_target_range_history", lambda start, end: {})

    class _Date(date):
        @classmethod
        def today(cls):
            return date(2026, 9, 17)

    monkeypatch.setattr(cme_fedwatch, "date", _Date)

    assert get_history(days=3)["meeting_date"] == "2026-09-16"
