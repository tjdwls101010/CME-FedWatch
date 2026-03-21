<div align="center">

<img src="https://logodownload.org/wp-content/uploads/2021/06/federal-reserve-logo-fed.png" width="140" alt="Federal Reserve">

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
    "effr": 3.64,
    "current_target": "3.50%-3.75%",
    "meetings": [{
        "date": "2026-04-29",
        "contract": "ZQJ6",
        "probabilities": {
            "3.50%-3.75%": 84.0,  # No change
            "3.75%-4.00%": 16.0   # 25bp hike
        }
    }]
}
```

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

# How expectations changed over the past 10 business days
# Includes 1d, 1w, 1m, 3m, 6m, 1y lookback comparisons
get_history("next", days=10)
```

---

## CLI

```bash
# Default: next meeting probabilities
$ cme-fedwatch

EFFR: 3.64%  Target: 3.50%-3.75%

     Meeting  Contract     3.50%-3.75%     3.75%-4.00%
------------------------------------------------------
  2026-04-29      ZQJ6           84.0%           16.0%
```

```bash
# All upcoming meetings
$ cme-fedwatch all

EFFR: 3.64%  Target: 3.50%-3.75%

     Meeting  Contract     3.25%-3.50%     3.50%-3.75%     3.75%-4.00%
----------------------------------------------------------------------
  2026-04-29      ZQJ6            0.0%           84.0%           16.0%
  2026-06-17      ZQM6            0.0%           95.7%            4.3%
  2026-07-29      ZQN6            0.0%           98.0%            2.0%
  2026-09-16      ZQU6            0.0%           88.0%           12.0%
  2026-10-28      ZQV6            0.0%           38.0%           62.0%
  2026-12-09      ZQZ6            8.1%           91.9%            0.0%
  ...
```

```bash
# Historical: how expectations evolved
$ cme-fedwatch history --days 5

EFFR: 3.64%  Target: 3.50%-3.75%
Meeting: 2026-04-29  Contract: ZQJ6

              3.50%-3.75%     3.75%-4.00%
-----------------------------------------
  2026-03-16       97.0%            3.0%
  2026-03-17       97.0%            3.0%
  2026-03-18      100.0%            0.0%
  2026-03-19       93.0%            7.0%
  2026-03-20       84.0%           16.0%

Lookback:
          1d          84.0%           16.0%
          1w          ...              ...
          1m          ...              ...
```

### All CLI Options

| Command | Description |
|---|---|
| `cme-fedwatch` | Next meeting probabilities |
| `cme-fedwatch all` | All upcoming meetings |
| `cme-fedwatch next` | Explicit next meeting |
| `cme-fedwatch history` | Probability changes over time |
| `cme-fedwatch history --days 20` | Last 20 business days |
| `cme-fedwatch --meeting 2026-10-28` | Specific meeting |
| `cme-fedwatch --json` | JSON output |
| `cme-fedwatch --csv` | CSV output |
| `cme-fedwatch --rate 4.33` | Override EFFR |

---

## API Reference

### `get_probabilities(meeting=None, trade_date=None, current_rate=None)`

Get rate-change probabilities for FOMC meetings.

| Parameter | Type | Description |
|---|---|---|
| `meeting` | `str` | `None` (all), `"next"`, or `"YYYY-MM-DD"` |
| `trade_date` | `date` | Settlement date (default: most recent) |
| `current_rate` | `float` | Override EFFR (default: fetched from FRED) |

**Returns** a dict with `effr`, `current_target`, and `meetings` list.

### `get_history(meeting=None, days=10, current_rate=None)`

Track how probabilities changed over time with standard lookback periods (1d, 1w, 1m, 3m, 6m, 1y).

| Parameter | Type | Description |
|---|---|---|
| `meeting` | `str` | `"next"` (default) or `"YYYY-MM-DD"` |
| `days` | `int` | Business days of daily history (default: 10) |
| `current_rate` | `float` | Override EFFR |

**Returns** a dict with `history` (daily) and `lookback` (1d/1w/1m/3m/6m/1y snapshots).

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

For each FOMC meeting, we derive the market-implied post-meeting fed funds rate from the futures settlement price, then compute the probability of each 25bp rate outcome:

```
implied_rate     = 100 - settlement_price
post_meeting_rate = (implied × D - pre_rate × (d-1)) / (D-d+1)
expected_moves   = (post_rate - pre_rate) / 0.25
```

Where `d` = meeting day, `D` = days in month, `pre_rate` = previous month's implied rate.

### Accuracy

Results are based on **daily settlement prices** (not live mid-prices), so they may differ from CME QuikStrike by a few percentage points — especially for meetings near the end of a month where the calculation is sensitive to small price differences. The directional signal (hike/cut/hold) is consistent.

---

## Reading the Output

The column headers show possible target rate ranges. Compare them to the **current target** displayed at the top:

```
EFFR: 3.64%  Target: 3.50%-3.75%        ← Current rate

     Meeting  Contract     3.25%-3.50%     3.50%-3.75%     3.75%-4.00%
                           ↑ 25bp CUT      ↑ NO CHANGE     ↑ 25bp HIKE
```

- **Column = current target** → probability of **no change**
- **Column > current target** → probability of **rate hike(s)**
- **Column < current target** → probability of **rate cut(s)**

---

## Disclaimer

This project is **not affiliated with CME Group, the Federal Reserve, or FRED**. Data is sourced from publicly available APIs. Probabilities are calculated using an approximation of the CME FedWatch methodology and may differ from official CME QuikStrike values.

This tool is for **informational and educational purposes only**. It is not financial advice.

---

## License

MIT
