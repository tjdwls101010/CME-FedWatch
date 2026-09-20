<div align="center">

<img src="https://github.com/tjdwls101010/tjdwls101010/blob/main/Images/CME%20Fedwatch.png?raw=true" width="240" alt="CME FedWatch">

# CME FedWatch Tracker

**Unofficial CME FedWatch — FOMC rate-change probabilities in one line of Python.**

The only open-source FedWatch that **actually works out of the box**. No data prep, no API keys, no Selenium.

[![PyPI](https://img.shields.io/pypi/v/cme-fedwatch)](https://pypi.org/project/cme-fedwatch/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](#)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](#)
[![Data](https://img.shields.io/badge/data-CME%20%2B%20FRED-orange)](#)

[Installation](#installation) · [Quick Start](#quick-start) · [CLI](#cli) · [API Reference](#api-reference) · [How It Works](#how-it-works)

</div>

---

## Why This Project?

The CME FedWatch Tool is the gold standard for gauging market expectations of Fed rate changes. **But accessing the data programmatically is painful:**

| Existing approach | Problem |
|---|---|
| [CME Website](https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html) | Manual, no API, embedded in QuikStrike iframe |
| [pyfedwatch](https://github.com/ARahimiQuant/pyfedwatch) | You must supply your own futures data — the library doesn't fetch anything |
| Selenium scrapers | Slow (~60s), fragile, requires browser + driver |
| CME DataMine API | Paid, enterprise-only |

**This project solves all of that.** One `pip install`, zero config:

```python
from cme_fedwatch import get_probabilities

data = get_probabilities("next")
print(data)
```
```python
{
    "effr": 3.88,
    "current_target": "3.75%-4.00%",
    "target_source": "fred",
    "trade_date": "2026-09-18",
    "meetings": [{
        "date": "2026-10-28",
        "contract": "ZQV6",
        "probabilities": {
            "3.75%-4.00%": 42.4,  # No change
            "4.00%-4.25%": 57.6   # 25bp hike
        }
    }]
}
```

Those are the CME FedWatch Tool's own numbers for that settlement, to the first decimal.

**Data sources — all official, all free:**
- Settlement prices from **CME Group**
- EFFR & target rate from **FRED** (Federal Reserve Bank of St. Louis)
- FOMC schedule from the **Federal Reserve**

---

## Installation

```bash
pip install cme-fedwatch
```

Requires Python 3.9+. Single dependency: [`curl_cffi`](https://github.com/lexiforest/curl_cffi).

---

## Quick Start

```python
from cme_fedwatch import get_probabilities, get_history

# Next FOMC meeting
get_probabilities("next")

# All upcoming meetings
get_probabilities()

# Specific meeting
get_probabilities("2026-10-28")

# How expectations changed over recent business days.
# CME's free settlement feed retains only about the last 5 business days,
# so a longer request comes back truncated and says so.
get_history("next", days=10)
```

---

## CLI

```bash
# Default: next meeting probabilities
$ cme-fedwatch

EFFR: 3.88%  Target: 3.75%-4.00%  Settlement: 2026-09-18

     Meeting  Contract     3.75%-4.00%     4.00%-4.25%
------------------------------------------------------
  2026-10-28      ZQV6           42.4%           57.6%
```

```bash
# All upcoming meetings
$ cme-fedwatch all

EFFR: 3.88%  Target: 3.75%-4.00%  Settlement: 2026-09-18

     Meeting  Contract     3.75%-4.00%     4.00%-4.25%     4.25%-4.50%     4.50%-4.75%
--------------------------------------------------------------------------------------
  2026-10-28      ZQV6           42.4%           57.6%            0.0%            0.0%
  2026-12-09      ZQZ6            9.9%           46.0%           44.1%            0.0%
  2027-01-27      ZQF7            5.8%           31.1%           44.9%           18.2%
  2027-03-17      ZQH7            2.0%           14.4%           35.8%           35.8%
  ...
```

> Later meetings span more ranges than earlier ones. That is the method working:
> each meeting contributes a two-outcome split and those splits are convolved, so
> uncertainty compounds the further out you look. The real table is wider than
> shown here.

```bash
# Historical: how expectations evolved over recent business days
$ cme-fedwatch history --days 5

EFFR: 3.88%  Target: 3.75%-4.00%
Meeting: 2026-10-28  Contract: ZQV6

                 3.50%-3.75%     3.75%-4.00%     4.00%-4.25%     4.25%-4.50%
----------------------------------------------------------------------------
  2026-09-14            3.8%           53.0%           43.2%            0.0%
  2026-09-15            2.8%           53.1%           44.0%            0.0%
  2026-09-16            0.0%           49.4%           48.8%            1.8%
  2026-09-17            0.0%           44.6%           55.4%            0.0%
  2026-09-18            0.0%           42.4%           57.6%            0.0%
```

> Each row is labelled against the target range in effect **on its own trade
> date**. The 2026-09-16 FOMC raised the range effective the 17th, which is why
> the earlier rows sit one step lower. Labelling every row with today's range
> would invent a 25bp repricing that never happened.

> Asking for more days than CME serves prints a note on stderr rather than a
> short table with no explanation:
>
> ```
> ℹ️  CME's free settlement feed served 5 of the 10 business days requested;
>    it retains roughly the last 5. Missing days are omitted, not estimated.
> ```

### All CLI Options

| Command | Description |
|---|---|
| `cme-fedwatch` | Next meeting probabilities |
| `cme-fedwatch all` | All upcoming meetings |
| `cme-fedwatch next` | Explicit next meeting |
| `cme-fedwatch history` | Probability changes over time |
| `cme-fedwatch history --days 20` | Request 20 business days (CME serves ~5) |
| `cme-fedwatch --meeting 2026-10-28` | Specific meeting |
| `cme-fedwatch --date 2026-09-17` | Price against an older settlement |
| `cme-fedwatch --json` | JSON output |
| `cme-fedwatch --csv` | CSV output |
| `cme-fedwatch --rate 4.33` | Override EFFR |

Global options work on either side of the subcommand: `cme-fedwatch --json next` and `cme-fedwatch next --json` are the same command. `history` does not accept `--date` — it always walks back from today — and rejects it rather than ignoring it. Asking for a meeting that is not on the schedule exits non-zero and lists the ones that are.

---

## API Reference

### `get_probabilities(meeting=None, trade_date=None, current_rate=None)`

Get rate-change probabilities for FOMC meetings.

| Parameter | Type | Description |
|---|---|---|
| `meeting` | `str` | `None` (all), `"next"`, or `"YYYY-MM-DD"` |
| `trade_date` | `date` | Settlement date (default: most recent) |
| `current_rate` | `float` | Override EFFR (default: fetched from FRED) |

**Returns** a dict with `effr`, `current_target`, `target_source`, `trade_date`, `schedule_status`, and a `meetings` list.

`trade_date` is the settlement the numbers came from. With no `trade_date` argument the library walks back from today to the newest day CME actually serves, stepping over weekends, US market holidays, and the case where your local date is already a day ahead of the US trading date. An explicit `trade_date` CME does not serve raises `NoSettlementData` rather than quietly substituting a neighbouring day.

`target_source` is `"fred"` when the target range came from FRED's published series, or `"estimated"` when FRED was unreachable and the range had to be derived from the EFFR — which can be one 25bp step off when the EFFR sits at or above the range ceiling, as it did in September 2019. The CLI warns when it is estimated.

`schedule_status` reports the health of the built-in FOMC schedule (hardcoded and finite): `{"state": "ok" | "expiring" | "expired", "remaining": <int>, "last_known": "<YYYY-MM-DD>"}`. The CLI prints a warning to stderr when the state is not `ok`, so a silently-expired schedule can't go unnoticed.

### `get_history(meeting=None, days=10, current_rate=None)`

Track how probabilities changed over recent business days.

| Parameter | Type | Description |
|---|---|---|
| `meeting` | `str` | `"next"` (default) or `"YYYY-MM-DD"` |
| `days` | `int` | Requested business days of daily history (default: 10) |
| `current_rate` | `float` | Override EFFR |

**Returns** a dict with `history`, `requested_days`, `available_days`, the same `schedule_status`, and a `note` present only when fewer days were served than asked for. Each row is labelled against the target range in effect on its own trade date.

> **Data availability.** CME's free settlement feed retains roughly the last 5 business days. `history` therefore returns at most ~5 daily rows regardless of `days`; `available_days` says how many you got and `note` says why. Missing days are omitted, never estimated. For full historical futures data, CME DataMine (paid) is the only official source.

### `fetch_fomc_schedule()`

Fetch the FOMC schedule from federalreserve.gov and return it **merged** with the built-in list.

Opt-in: nothing in the normal probability path calls it, so the package still works with no network beyond CME and FRED. It is a union rather than a replacement because the Fed publishes each year's calendar only once the prior year is under way, so the built-in list can legitimately reach further out than the page does. It raises rather than falling back silently — a silent fallback would hide exactly the layout change the function exists to detect.

---

## How It Works

### Data Pipeline

```
FRED API ──→ Current EFFR + Target Rate (official Fed data)
CME API  ──→ 30-Day Fed Funds Futures settlements (product 305)
               ↓
         FedWatch Calculation Engine
               ↓
         Per-meeting rate-change probabilities
```

### Calculation

This follows CME's published FedWatch methodology rather than approximating it.

A ZQ contract prices the **average** EFFR over its delivery month, so `A = 100 - settlement`. A month containing an FOMC meeting blends the rate before the decision with the rate after it:

```
A_t = (N_t · S_t + M_t · E_t) / D_t
```

where `D` is days in the month, `N = d` days at the pre-meeting rate (CME counts the announcement day itself as pre-change) and `M = D - d` days at the post-meeting rate. That is one equation in two unknowns, so the curve is bootstrapped from months with **no** meeting, where the contract prices a single flat rate:

```
E[q-1] = A_q = S[q+1]          for an anchor month q
S_t    = (D·A_t - M·E_t) / N   solving a meeting month
E[t-1] = S_t                   continuity
```

The continuity condition is the heart of it: **a meeting's pre-rate is the previous meeting's post-rate, not the previous calendar month's average.** Those differ by a whole rate step whenever that month contained a decision.

Each meeting then contributes `x_t = (E_t - S_t) / 0.25` expected 25bp moves, split across the two adjacent whole numbers, and the per-meeting distributions are **convolved**:

```
P_j = P_{j-1} * q_j
```

which is why a distant meeting spans several target ranges. Labels are the current target range shifted by the cumulative number of moves.

### Accuracy

Results are computed from **daily settlement prices**, not live mid-prices, so they reproduce what CME FedWatch showed for that settlement rather than what it shows intraday. Against CME's published output for the 2026-09-18 settlement:

| Meeting | CME FedWatch | This library |
|---|---|---|
| 2026-10-28 | 42.4% / 57.6% | 42.4% / 57.6% |
| 2026-12-09 | 9.9% / 46.0% / 44.1% | 9.9% / 46.0% / 44.1% |

The regression suite pins those numbers against a saved copy of that settlement, so the engine cannot drift away from them unnoticed.

**Known limits.** The built-in FOMC schedule is finite, and the engine will not look past it: a month beyond the last known meeting could have an unpublished meeting, and treating it as an anchor would produce confidently wrong numbers, so affected meetings are dropped instead. Two meetings in the same calendar month are not supported (the modern schedule has none).

## Reading the Output

The column headers show possible target rate ranges. Compare them to the **current target** displayed at the top:

```
EFFR: 3.88%  Target: 3.75%-4.00%        ← Current rate

     Meeting  Contract     3.50%-3.75%     3.75%-4.00%     4.00%-4.25%
                           ↑ 25bp CUT      ↑ NO CHANGE     ↑ 25bp HIKE
```

- **Column = current target** → probability of **no change**
- **Column > current target** → probability of **rate hike(s)**
- **Column < current target** → probability of **rate cut(s)**

---

## Disclaimer

This project is **not affiliated with CME Group, the Federal Reserve, or FRED**. Data is sourced from publicly available APIs. Probabilities follow CME's published FedWatch methodology and are pinned against its output in the test suite, but this is an independent implementation and may differ from official CME QuikStrike values — not least because it uses daily settlements rather than live prices.

This tool is for **informational and educational purposes only**. It is not financial advice.

---

## License

MIT
