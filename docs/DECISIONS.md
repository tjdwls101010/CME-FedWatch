# Decisions

Newest first. Each entry: `## YYYY-MM-DD — short title`, then 1–3 sentences (context + decision + why).

## 2026-06-07 — FOMC schedule stays hardcoded; expiry surfaced at runtime, refresh stays manual

The FOMC schedule lives in `FOMC_MEETINGS` (hardcoded, finite). Runtime scraping of Fed HTML was rejected — fragile, breaks the project's "no-scraping, works out of the box" promise, and the calc needs the exact announcement day which Fed publishes only as range text. Instead a runtime `schedule_status` field + CLI stderr warning surfaces expiry early, so a manual ~5-minute refresh (add the next year's 8 dates) suffices. A CI auto-updater was considered but **deferred**: with the warning in place, maintaining a fragile scraper isn't worth the cost — revisit only if fully unattended operation becomes a requirement.
