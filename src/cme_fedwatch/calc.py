"""FedWatch probability calculation engine (CME methodology).

A 30-Day Fed Funds future prices the *average* EFFR over its delivery
month: ``A_t = 100 - P_t``. A month containing an FOMC meeting therefore
blends the rate before the decision with the rate after it::

    A_t = (N_t * S_t + M_t * E_t) / D_t

with ``D_t`` days in the month, ``N_t = d`` days at the pre-meeting rate
(CME counts the announcement day itself as pre-change) and
``M_t = D_t - d`` days at the post-meeting rate.

That is one equation in two unknowns, so the curve is bootstrapped from
months with *no* meeting, where the contract prices a single flat rate.
Such an anchor month ``q`` pins its neighbours::

    E[q-1] = A_q = S[q+1]

and the remaining meeting months are solved in reverse chronological
order, each one handing its start rate to the month before it
(``E[t-1] = S_t``). This continuity condition is the heart of the method:
a meeting's pre-rate is the *previous meeting's* post-rate, never the
previous calendar month's average -- those differ by a whole rate step
whenever that month contained a decision.

Each meeting then contributes ``x_t = (E_t - S_t) / 0.25`` expected 25bp
moves, split across the two adjacent whole numbers, and the per-meeting
distributions are convolved so a distant meeting can span several target
ranges.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Optional

from .fomc import FOMC_MEETINGS, _MONTH_NAMES, days_in_month, meeting_to_contract_code

_STEP = 0.25


def _month_key(year: int, month: int) -> str:
    return f"{_MONTH_NAMES[month]} {year % 100}"


def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def current_target_range(effr: float) -> tuple[float, float]:
    """Derive the current target range from the EFFR.

    Fallback for when FRED's target-range series is unavailable; the EFFR
    always trades inside the 25bp band, so flooring it recovers the band.

    Returns (lower, upper) in percentage points, e.g. (3.75, 4.00).
    """
    lower_bps = int(math.floor(effr * 100 / 25.0)) * 25
    return lower_bps / 100, (lower_bps + 25) / 100


def _implied_averages(settlements: list[dict]) -> dict[str, float]:
    """Map settlement month label -> implied average EFFR for that month."""
    return {s["month"]: 100.0 - s["settle"] for s in settlements}


def _solve_rate_curve(
    averages: dict[str, float],
    meeting_months: dict[tuple[int, int], date],
    months: list[tuple[int, int]],
    horizon_month: Optional[tuple[int, int]],
) -> tuple[dict, dict]:
    """Bootstrap per-meeting start and end rates from the ZQ curve.

    Returns (start, end) keyed by (year, month) for meeting months whose
    rates could be determined. Meeting months that never reach an anchor
    are simply absent.
    """
    start: dict[tuple[int, int], float] = {}
    end: dict[tuple[int, int], float] = {}

    def avg(ym: tuple[int, int]) -> Optional[float]:
        return averages.get(_month_key(*ym))

    # A month with no meeting prices a single flat rate, so it pins the end
    # of the month before it and the start of the month after it. Months
    # past the schedule horizon are NOT anchors: we cannot tell an actual
    # no-meeting month from one whose meeting we simply do not know yet,
    # and guessing there would silently produce wrong probabilities.
    for ym in months:
        if ym in meeting_months:
            continue
        if horizon_month is not None and ym > horizon_month:
            continue
        a = avg(ym)
        if a is None:
            continue
        prev, nxt = _prev_month(*ym), _next_month(*ym)
        if prev in meeting_months:
            end.setdefault(prev, a)
        if nxt in meeting_months:
            start.setdefault(nxt, a)

    # Propagate until the chain stops growing. Backward solving runs first
    # in each pass because CME gives it precedence: an anchor populates the
    # preceding month's end rate and calculations then proceed in reverse
    # chronological order. Forward solving fills what backward could not
    # reach, and both directions hand their result to the neighbouring
    # meeting month -- a rate solved either way is the next meeting's start
    # rate, so a single missing contract does not end the chain.
    changed = True
    while changed:
        changed = False

        for ym in reversed(months):
            if ym not in meeting_months or ym in start:
                continue
            a = avg(ym)
            if a is None:
                continue
            meeting = meeting_months[ym]
            D = days_in_month(meeting)
            N, M = meeting.day, D - meeting.day
            if M == 0:
                # The meeting is on the last day, so the contract averages
                # the pre-meeting rate alone and no end rate is needed.
                start[ym] = a
            elif ym in end:
                start[ym] = (D * a - M * end[ym]) / N
            else:
                continue
            prev = _prev_month(*ym)
            if prev in meeting_months:
                end.setdefault(prev, start[ym])
            changed = True

        for ym in months:
            if ym not in meeting_months or ym in end or ym not in start:
                continue
            a = avg(ym)
            if a is None:
                continue
            meeting = meeting_months[ym]
            D = days_in_month(meeting)
            N, M = meeting.day, D - meeting.day
            if M == 0:
                # Not priced by this contract; it has to come from an anchor.
                continue
            end[ym] = (D * a - N * start[ym]) / M
            nxt = _next_month(*ym)
            if nxt in meeting_months:
                start.setdefault(nxt, end[ym])
            changed = True

    return start, end


def _step_distribution(start_rate: float, end_rate: float) -> dict[int, float]:
    """Split expected 25bp moves across the two adjacent whole numbers."""
    moves = (end_rate - start_rate) / _STEP
    floor_m = math.floor(moves)
    frac = moves - floor_m
    return {floor_m: 1.0 - frac, floor_m + 1: frac}


def _convolve(cumulative: dict[int, float], step: dict[int, float]) -> dict[int, float]:
    """Combine a meeting's step distribution into the cumulative one.

    Nothing is pruned here. Branches too small to display individually
    still add up: eight meetings each pricing a 0.04% hike carry 0.3%
    between them, and dropping them per convolution loses that for good.
    Thinning happens once, on the displayed result.
    """
    out: dict[int, float] = {}
    for moves_so_far, p in cumulative.items():
        for moves, q in step.items():
            out[moves_so_far + moves] = out.get(moves_so_far + moves, 0.0) + p * q
    return out


def _range_label(lower_bps: int, upper_bps: int) -> str:
    return f"{lower_bps / 100:.2f}%-{upper_bps / 100:.2f}%"


def calculate(
    settlements: list[dict],
    meetings: list[date],
    current_range: tuple[float, float],
    horizon: Optional[date] = None,
    schedule: Optional[list[date]] = None,
) -> list[dict]:
    """Calculate FedWatch probabilities for each FOMC meeting.

    Args:
        settlements: Settlement dicts with 'month' and 'settle'.
        meetings: FOMC meeting dates to report, chronological.
        current_range: Current target range in percent, e.g. (3.75, 4.00).
        horizon: Last date the meeting schedule is known to be complete.
            Months beyond it are excluded from anchor detection.
        schedule: Every meeting date the anchor search should know about,
            past ones included. Anchors are months with no meeting, and
            `meetings` holds only the ones still ahead -- classifying from
            that alone would read the month of a meeting that has already
            happened as an anchor and reintroduce the very error this
            engine exists to avoid. Defaults to the built-in schedule.

    Returns:
        One dict per meeting with 'date', 'contract' and 'probabilities'
        keyed by target range label (e.g. '3.75%-4.00%'). Meetings whose
        rates could not be bootstrapped are omitted.
    """
    if not meetings:
        return []

    averages = _implied_averages(settlements)

    # 성진: 한 달에 FOMC가 두 번 있으면 이 맵이 하나를 덮어쓴다. 현대 일정에는
    # 없어서 지원하지 않는다 — 등장하면 앵커 연쇄를 월 단위가 아니라 회의 단위로
    # 다시 써야 한다.
    known = FOMC_MEETINGS if schedule is None else schedule
    meeting_months = {(m.year, m.month): m for m in known}
    meeting_months.update({(m.year, m.month): m for m in meetings})

    # One month either side of the meeting span: the month before the first
    # meeting can be the anchor that pins its start rate, and the month
    # after the last one can be the anchor that pins its end rate.
    months = []
    ym = _prev_month(meetings[0].year, meetings[0].month)
    last = _next_month(meetings[-1].year, meetings[-1].month)
    while ym <= last:
        months.append(ym)
        ym = _next_month(*ym)

    horizon_month = (horizon.year, horizon.month) if horizon else None
    start, end = _solve_rate_curve(averages, meeting_months, months, horizon_month)

    lower_bps = round(current_range[0] * 100)
    upper_bps = round(current_range[1] * 100)

    results = []
    cumulative = {0: 1.0}
    for meeting in meetings:
        ym = (meeting.year, meeting.month)
        if ym not in start or ym not in end:
            # No anchor reached this meeting; every later meeting depends on
            # it, so the chain ends here rather than resuming with a gap.
            break
        cumulative = _convolve(cumulative, _step_distribution(start[ym], end[ym]))
        probabilities = {
            _range_label(lower_bps + 25 * c, upper_bps + 25 * c): round(p * 100, 1)
            for c, p in sorted(cumulative.items())
            if round(p * 100, 1) > 0.0
        }
        results.append({
            "date": meeting.isoformat(),
            "contract": meeting_to_contract_code(meeting),
            "probabilities": probabilities,
        })

    return results
