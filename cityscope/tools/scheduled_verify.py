"""Scheduled feed verification — designed to run as a cron job.

This is the "automated --verify" piece. Point a scheduler at it (Render Cron
Job, GitHub Actions on a schedule, or any cron) and it will check every feed
the app uses and report which are dead. Unlike the interactive rss_discovery
--verify, this is non-interactive and exits with a status code so a scheduler
can alert on failures.

USAGE:
    python -m cityscope.tools.scheduled_verify
    python -m cityscope.tools.scheduled_verify --json     # machine-readable

EXIT CODES:
    0 = all feeds healthy
    1 = one or more feeds dead (scheduler can treat as alert)

RENDER CRON SETUP (when ready to pay ~$1/mo for a cron service):
    Create a new "Cron Job" service on Render pointing at this repo, with:
      Command:  python -m cityscope.tools.scheduled_verify
      Schedule: 0 13 * * 1        (every Monday 1pm UTC, for example)
    Render emails you the logs; dead feeds show up there.

GITHUB ACTIONS ALTERNATIVE (free):
    A .github/workflows/verify.yml on a schedule can run this and open an issue
    on failure. See SCHEDULED_VERIFY.md for the workflow file.
"""

from __future__ import annotations

import sys
import json

sys.path.insert(0, ".")


def run(as_json: bool = False) -> int:
    from cityscope.tools.rss_discovery import _app_feeds, _verify_feed

    feeds = _app_feeds()
    healthy, dead = [], []
    for city_key, paper, url in feeds:
        try:
            n = _verify_feed(url)
        except Exception:
            n = 0
        (healthy if n >= 3 else dead).append(
            {"city": city_key, "paper": paper, "url": url, "items": n})

    result = {
        "checked": len(feeds),
        "healthy": len(healthy),
        "dead": len(dead),
        "dead_feeds": dead,
    }

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Checked {len(feeds)} feeds: {len(healthy)} healthy, {len(dead)} dead.")
        if dead:
            print("\nDEAD FEEDS — run per-city discovery to find new URLs:")
            for d in dead:
                print(f"  ✗ {d['city']}: {d['paper']} -> {d['url']}")
                domain = d["url"].split("/")[2] if "//" in d["url"] else d["url"]
                print(f"      fix: python -m cityscope.tools.rss_discovery "
                      f"\"{d['city'].title()}\" {domain}")
        else:
            print("All feeds healthy. ✓")

    # exit 1 if anything is dead, so a scheduler can alert
    return 1 if dead else 0


if __name__ == "__main__":
    as_json = "--json" in sys.argv
    sys.exit(run(as_json=as_json))
