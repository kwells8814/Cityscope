# Keeping feeds healthy automatically

Feeds move and die over time — it's the nature of RSS. Three layers keep this
from ever "randomly dropping a city" on you, from zero-effort to scheduled.

## Layer 1 — Self-healing (already on, free, automatic)

The app tracks each feed's health in memory. If a feed fails repeatedly it's
marked "cooling" and skipped on most requests (so it never slows the app),
but retried once every ~30 min so it heals automatically if it recovers.

Crucially: **a dead feed never drops a whole city.** Each city's feeds are
fetched independently with error isolation — a dead feed is skipped and the
city's other feeds still work. A city only goes empty if ALL its feeds die.

Glance at what's cooling any time:

    GET /feed-health

Returns the feeds currently failing and how long since each last succeeded.

## Layer 2 — Scheduled verification (opt-in)

Run a non-interactive check of every feed on a schedule. Two ways:

### Option A — GitHub Actions (FREE)
A workflow is included at `.github/workflows/verify-feeds.yml`. It runs weekly
(Mondays 13:00 UTC), and if any feed is dead it:
  - fails the job (visible in the Actions tab), and
  - opens a GitHub issue listing the dead feeds.
No setup beyond pushing the repo to GitHub. Adjust the `cron:` line to change
the schedule. This is the recommended free option.

### Option B — Render Cron Job (~$1/mo)
Create a new "Cron Job" service on Render pointing at this repo:
  - Command:  `python -m cityscope.tools.scheduled_verify`
  - Schedule: `0 13 * * 1`  (Mondays 1pm UTC)
Render emails you the logs; dead feeds appear there.

## Layer 3 — Fixing a moved feed (manual, rare)

When a feed is reported dead, it's usually MOVED, not gone. Find its new URL:

    python -m cityscope.tools.rss_discovery "Portland" wweek.com

The tool reads the site's homepage to find the current feed. Paste the URL it
reports into `cityscope/db/repository.py`. (Some feeds move to custom hosts the
tool can't auto-find — those need a manual look, but they're rare.)

## Why fixing isn't fully automated

Detecting dead feeds is safe to automate. *Fixing* them isn't: finding the new
URL sometimes fails (custom hosts, no homepage feed link), and a bad auto-swap
could silently feed wrong content. So detection is automatic; the fix stays a
quick informed human step.
