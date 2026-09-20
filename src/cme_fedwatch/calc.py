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

from .fomc import _MONTH_NAMES, days_in_month, meeting_to_contract_code

# Outcomes below this probability are dropped rather than printed as 0.0%.
_PRUNE = 0.0005

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

    # Propagate in reverse chronological order, repeating until the chain
    # stops growing: each solved month pins the end of the month before it,
    # so consecutive meeting months resolve one per pass.
    changed = True
    while changed:
        changed = False
        for ym in reversed(months):
            if ym not in meeting_months or ym in start:
                continue
            a = avg(ym)
            if a is None or ym not in end:
                continue
            meeting = meeting_months[ym]
            D = days_in_month(meeting)
            N, M = meeting.day, D - meeting.day
            start[ym] = (D * a - M * end[ym]) / N
            prev = _prev_month(*ym)
            if prev in meeting_months:
                end.setdefault(prev, start[ym])
            changed = True

    # A meeting month whose start came from a preceding anchor can have its
    # end recovered the other way round. M == 0 (meeting on the last day of
    # the month) leaves the post-meeting rate unpriced by this contract.
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
            continue
        end[ym] = (D * a - N * start[ym]) / M

    return start, end


def _step_distribution(start_rate: float, end_rate: float) -> dict[int, float]:
    """Split expected 25bp moves across the two adjacent whole numbers."""
    moves = (end_rate - start_rate) / _STEP
    floor_m = math.floor(moves)
    frac = moves - floor_m
    return {floor_m: 1.0 - frac, floor_m + 1: frac}


def _convolve(cumulative: dict[int, float], step: dict[int, float]) -> dict[int, float]:
    out: dict[int, float] = {}
    for moves_so_far, p in cumulative.items():
        for moves, q in step.items():
            out[moves_so_far + moves] = out.get(moves_so_far + moves, 0.0) + p * q
    return {c: p for c, p in out.items() if p > _PRUNE}


def calculate(
    settlements: list[dict],
    meetings: list[date],
    current_range: tuple[float, float],
    horizon: Optional[date] = None,
) -> list[dict]:
    """Calculate FedWatch probabilities for each FOMC meeting.

    Args:
        settlements: Settlement dicts with 'month' and 'settle'.
        meetings: Upcoming FOMC meeting dates, chronological.
        current_range: Current target range in percent, e.g. (3.75, 4.00).
        horizon: Last date the meeting schedule is known to be complete.
            Months beyond it are excluded from anchor detection.

    Returns:
        One dict per meeting with 'date', 'contract' and 'probabilities'
        keyed by basis-point range label (e.g. '375-400'). Meetings whose
        rates could not be bootstrapped are omitted.
    """
    if not meetings:
        return []

    averages = _implied_averages(settlements)

    # 성진: 한 달에 FOMC가 두 번 있으면 이 맵이 하나를 덮어쓴다. 현대 일정에는
    # 없어서 지원하지 않는다 — 등장하면 앵커 연쇄를 월 단위가 아니라 회의 단위로
    # 다시 써야 한다.
    meeting_months = {(m.year, m.month): m for m in meetings}

    months = []
    ym = (meetings[0].year, meetings[0].month)
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
            f"{lower_bps + 25 * c}-{upper_bps + 25 * c}": round(p * 100, 1)
            for c, p in sorted(cumulative.items())
            # A negative target range is not a Fed outcome; it would also
            # make the bps label ambiguous to split on '-'.
            if round(p * 100, 1) > 0.0 and lower_bps + 25 * c >= 0
        }
        results.append({
            "date": meeting.isoformat(),
            "contract": meeting_to_contract_code(meeting),
            "probabilities": probabilities,
        })

    return results
