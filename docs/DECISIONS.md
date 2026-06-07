# Decisions

Newest first. Each entry: `## YYYY-MM-DD — short title`, then 1–3 sentences (context + decision + why).

## 2026-06-07 — FOMC schedule stays hardcoded; freshness via CI, not runtime scraping

The FOMC schedule lives in `FOMC_MEETINGS` (hardcoded, finite). Rather than scrape Fed HTML at runtime — fragile, breaks the project's "no-scraping, works out of the box" promise, and the calc needs the exact announcement day which Fed publishes only as range text — freshness is delegated to a CI updater that opens a PR for human review. A runtime `schedule_status` field plus a CLI stderr warning is the safety net against silent expiry.
