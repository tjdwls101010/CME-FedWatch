"""CLI interface for cme-fedwatch."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import date, datetime
from typing import Optional


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def cmd_current(args: argparse.Namespace) -> None:
    """Show probabilities for all upcoming FOMC meetings."""
    from . import get_fedwatch

    trade_date = _parse_date(args.date) if args.date else None
    data = get_fedwatch(trade_date=trade_date, current_rate=args.rate)

    if args.json:
        print(json.dumps(data, indent=2))
        return

    if args.csv:
        _print_csv(data)
        return

    _print_table(data)


def cmd_next(args: argparse.Namespace) -> None:
    """Show probabilities for the next FOMC meeting only."""
    from . import get_fedwatch

    trade_date = _parse_date(args.date) if args.date else None
    data = get_fedwatch(trade_date=trade_date, current_rate=args.rate)

    if not data:
        print("No upcoming FOMC meetings found.")
        return

    result = [data[0]]

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if args.csv:
        _print_csv(result)
        return

    _print_table(result)


def cmd_settlements(args: argparse.Namespace) -> None:
    """Show raw settlement prices."""
    from .api import get_settlements

    trade_date = _parse_date(args.date) if args.date else None
    settlements = get_settlements(trade_date)

    if args.json:
        print(json.dumps(settlements, indent=2))
        return

    print(f"{'Month':<12} {'Settle':>10} {'Volume':>12} {'Open Int':>12}")
    print("-" * 48)
    for s in settlements:
        print(
            f"{s['month']:<12} {s['settle']:>10.4f} "
            f"{s['volume']:>12} {s['open_interest']:>12}"
        )


def _print_table(data: list[dict]) -> None:
    """Print a formatted probability table."""
    # Collect all target rate labels across all meetings
    all_rates = set()
    for meeting in data:
        all_rates.update(meeting["probabilities"].keys())

    if not all_rates:
        print("No data available.")
        return

    # Sort rate labels numerically
    sorted_rates = sorted(all_rates, key=lambda r: int(r.split("-")[0]))

    # Header
    header = f"{'Meeting':<14} {'Contract':<10}"
    for rate in sorted_rates:
        header += f" {rate:>10}"
    print(header)
    print("-" * len(header))

    # Rows
    for meeting in data:
        row = f"{meeting['date']:<14} {meeting['contract']:<10}"
        for rate in sorted_rates:
            prob = meeting["probabilities"].get(rate, 0.0)
            row += f" {prob:>9.1f}%"
        print(row)


def _print_csv(data: list[dict]) -> None:
    """Print results as CSV."""
    all_rates = set()
    for meeting in data:
        all_rates.update(meeting["probabilities"].keys())
    sorted_rates = sorted(all_rates, key=lambda r: int(r.split("-")[0]))

    writer = csv.writer(sys.stdout)
    writer.writerow(["date", "contract"] + sorted_rates)
    for meeting in data:
        row = [meeting["date"], meeting["contract"]]
        for rate in sorted_rates:
            row.append(meeting["probabilities"].get(rate, 0.0))
        writer.writerow(row)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="cme-fedwatch",
        description="CME FedWatch probability calculator",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    parser.add_argument(
        "--csv", action="store_true", help="Output as CSV"
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Trade date (YYYY-MM-DD). Defaults to most recent business day.",
    )
    parser.add_argument(
        "--rate", type=float, default=None,
        help="Current effective federal funds rate (e.g. 4.33)",
    )

    subparsers = parser.add_subparsers(dest="command")

    sub_current = subparsers.add_parser(
        "current", help="All upcoming FOMC meeting probabilities"
    )

    sub_next = subparsers.add_parser(
        "next", help="Next FOMC meeting probabilities only"
    )

    sub_settlements = subparsers.add_parser(
        "settlements", help="Raw settlement prices"
    )

    args = parser.parse_args(argv)

    # Propagate top-level flags to subcommands
    if not hasattr(args, "json"):
        args.json = False
    if not hasattr(args, "csv"):
        args.csv = False

    if args.command == "next":
        cmd_next(args)
    elif args.command == "settlements":
        cmd_settlements(args)
    else:
        # Default: show current (all meetings)
        cmd_current(args)


if __name__ == "__main__":
    main()
