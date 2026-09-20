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
    print(
        f"EFFR: {result['effr']:.2f}%  Target: {result['current_target']}"
        f"  Settlement: {result['trade_date']}"
    )
    print()
    if not meetings:
        print(
            "No meetings could be priced from this settlement. The built-in "
            "FOMC schedule may not reach far enough; see the warning below."
        )
        return

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

    print(f"EFFR: {result['effr']:.2f}%  Target: {result['current_target']}")
    print(f"Meeting: {result['meeting_date']}  Contract: {result['contract']}")
    print()

    if not history:
        print("No settlement data available for the requested window.")
        return

    sorted_rates = _collect_all_rates_from_history(history)
    header = f"{'':>12}"
    for r in sorted_rates:
        header += f"  {r:>14}"
    print(header)
    print("-" * len(header))

    for h in history:
        row = f"{h['trade_date']:>12}"
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


def _schedule_warning(status: Optional[dict]) -> Optional[str]:
    """Return a warning line for a non-ok schedule, else None.

    Pure: maps a schedule_status dict to a message so it can be tested
    without capturing stderr. The CLI prints the result to stderr.
    """
    state = (status or {}).get("state")
    if state == "expired":
        return (
            "⚠️  FOMC schedule has expired — no upcoming meetings in the "
            "built-in list. Update src/cme_fedwatch/fomc.py (FOMC_MEETINGS)."
        )
    if state == "expiring":
        return (
            f"⚠️  FOMC schedule is running low: {status.get('remaining')} "
            f"meeting(s) left (last: {status.get('last_known')}). "
            "Update FOMC_MEETINGS soon."
        )
    return None


def cmd_default(args: argparse.Namespace) -> None:
    from . import get_probabilities

    meeting = getattr(args, "meeting", None)
    date_str = getattr(args, "date", None)
    trade_date = _parse_date(date_str) if date_str else None
    rate = getattr(args, "rate", None)
    try:
        result = get_probabilities(meeting=meeting, trade_date=trade_date, current_rate=rate)
    except LookupError as exc:
        print(f"⚠️  {exc}", file=sys.stderr)
        raise SystemExit(1)

    if meeting not in (None, "next") and not result["meetings"]:
        priced = ", ".join(m["date"] for m in get_probabilities()["meetings"]) or "none"
        print(
            f"⚠️  {meeting} is not among the meetings this settlement prices. "
            f"Available: {priced}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
    elif getattr(args, "csv", False):
        _print_csv_meetings(result)
    else:
        _print_prob_table(result)

    if result.get("target_source") == "estimated":
        print(
            "⚠️  FRED's target-range series was unavailable; the range shown is "
            "estimated from the EFFR and may be one 25bp step off.",
            file=sys.stderr,
        )

    msg = _schedule_warning(result.get("schedule_status"))
    if msg:
        print(msg, file=sys.stderr)


def cmd_history(args: argparse.Namespace) -> None:
    from . import get_history

    if getattr(args, "date", None):
        print(
            "⚠️  history does not take --date; it always walks back from today. "
            "Use --days to choose how far.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    meeting = getattr(args, "meeting", None) or "next"
    days = getattr(args, "days", None) or 10
    rate = getattr(args, "rate", None)
    result = get_history(meeting=meeting, days=days, current_rate=rate)

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
    elif getattr(args, "csv", False):
        _print_csv_history(result)
    else:
        _print_history_table(result)

    if result.get("note"):
        print(f"ℹ️  {result['note']}", file=sys.stderr)

    msg = _schedule_warning(result.get("schedule_status"))
    if msg:
        print(msg, file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser.

    Global options are suppressed rather than defaulted, because argparse
    re-registers a parent's options on every subparser and a plain default
    there silently overwrites a value given before the subcommand --
    `cme-fedwatch --json next` would print a table. Callers read them with
    getattr and supply the default themselves.
    """
    parent = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
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
    hist.add_argument("--days", type=int, help="Business days (default: 10)")
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    args = build_parser().parse_args(argv)

    command = getattr(args, "command", None)
    if command == "all":
        args.meeting = None
        cmd_default(args)
    elif command == "next":
        args.meeting = "next"
        cmd_default(args)
    elif command == "history":
        cmd_history(args)
    else:
        if not getattr(args, "meeting", None):
            args.meeting = "next"
        cmd_default(args)


if __name__ == "__main__":
    main()
