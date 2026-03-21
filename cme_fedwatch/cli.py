"""CLI interface for cme-fedwatch."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime
from typing import Optional


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _collect_all_rates(meetings: list[dict]) -> list[str]:
    rates = set()
    for m in meetings:
        rates.update(m["probabilities"].keys())
    return sorted(rates)


def _print_prob_table(result: dict) -> None:
    meetings = result["meetings"]
    if not meetings:
        print("No data.")
        return

    print(f"EFFR: {result['effr']:.2f}%  Target: {result['current_target']}")
    print()

    sorted_rates = _collect_all_rates(meetings)
    header = f"{'Meeting':>12}  {'Contract':>8}"
    for r in sorted_rates:
        header += f"  {r:>14}"
    print(header)
    print("-" * len(header))

    for m in meetings:
        row = f"{m['date']:>12}  {m['contract']:>8}"
        for r in sorted_rates:
            p = m["probabilities"].get(r, 0.0)
            row += f"  {p:>13.1f}%"
        print(row)


def _print_history_table(result: dict) -> None:
    history = result.get("history", [])
    lookback = result.get("lookback", [])
    all_entries = history + lookback

    if not all_entries:
        print("No data.")
        return

    print(f"EFFR: {result['effr']:.2f}%  Target: {result['current_target']}")
    print(f"Meeting: {result['meeting_date']}  Contract: {result['contract']}")
    print()

    sorted_rates = _collect_all_rates_from_history(all_entries)
    header = f"{'':>12}"
    for r in sorted_rates:
        header += f"  {r:>14}"
    print(header)
    print("-" * len(header))

    # Daily history
    if history:
        for h in history:
            row = f"{h['trade_date']:>12}"
            for r in sorted_rates:
                p = h["probabilities"].get(r, 0.0)
                row += f"  {p:>13.1f}%"
            print(row)

    # Lookback comparison
    if lookback:
        print()
        print("Lookback:")
        for h in lookback:
            label = h.get("label", h["trade_date"])
            row = f"{label:>12}"
            for r in sorted_rates:
                p = h["probabilities"].get(r, 0.0)
                row += f"  {p:>13.1f}%"
            print(row)


def _collect_all_rates_from_history(history: list[dict]) -> list[str]:
    rates = set()
    for h in history:
        rates.update(h["probabilities"].keys())
    return sorted(rates)


def _print_csv_meetings(result: dict) -> None:
    meetings = result["meetings"]
    sorted_rates = _collect_all_rates(meetings)
    writer = csv.writer(sys.stdout)
    writer.writerow(["date", "contract"] + sorted_rates)
    for m in meetings:
        row = [m["date"], m["contract"]]
        for r in sorted_rates:
            row.append(m["probabilities"].get(r, 0.0))
        writer.writerow(row)


def _print_csv_history(result: dict) -> None:
    history = result["history"]
    sorted_rates = _collect_all_rates_from_history(history)
    writer = csv.writer(sys.stdout)
    writer.writerow(["trade_date"] + sorted_rates)
    for h in history:
        row = [h["trade_date"]]
        for r in sorted_rates:
            row.append(h["probabilities"].get(r, 0.0))
        writer.writerow(row)


def cmd_default(args: argparse.Namespace) -> None:
    from . import get_probabilities

    meeting = getattr(args, "meeting", None)
    trade_date = _parse_date(args.date) if args.date else None
    rate = getattr(args, "rate", None)
    result = get_probabilities(meeting=meeting, trade_date=trade_date, current_rate=rate)

    if args.json:
        print(json.dumps(result, indent=2))
    elif args.csv:
        _print_csv_meetings(result)
    else:
        _print_prob_table(result)


def cmd_history(args: argparse.Namespace) -> None:
    from . import get_history

    meeting = getattr(args, "meeting", None) or "next"
    days = getattr(args, "days", 10)
    rate = getattr(args, "rate", None)
    result = get_history(meeting=meeting, days=days, current_rate=rate)

    if args.json:
        print(json.dumps(result, indent=2))
    elif args.csv:
        _print_csv_history(result)
    else:
        _print_history_table(result)


def main(argv: Optional[list[str]] = None) -> None:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", action="store_true", help="JSON output")
    parent.add_argument("--csv", action="store_true", help="CSV output")
    parent.add_argument("--date", help="Trade date (YYYY-MM-DD)")
    parent.add_argument("--rate", type=float, help="Override EFFR")
    parent.add_argument("--meeting", help="Meeting: 'next' or YYYY-MM-DD")

    parser = argparse.ArgumentParser(
        prog="cme-fedwatch",
        description="CME FedWatch probability calculator",
        parents=[parent],
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("all", help="All upcoming meetings", parents=[parent])
    sub.add_parser("next", help="Next meeting only", parents=[parent])

    hist = sub.add_parser("history", help="Probability changes over time", parents=[parent])
    hist.add_argument("--days", type=int, default=10, help="Business days (default: 10)")

    args = parser.parse_args(argv)

    if args.command == "all":
        args.meeting = None
        cmd_default(args)
    elif args.command == "next":
        args.meeting = "next"
        cmd_default(args)
    elif args.command == "history":
        cmd_history(args)
    else:
        if not args.meeting:
            args.meeting = "next"
        cmd_default(args)


if __name__ == "__main__":
    main()
