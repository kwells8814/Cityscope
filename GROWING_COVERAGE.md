# Growing city coverage

Two independent ways to add real data for more cities. They don't depend on each
other — do either or both.

## A. Auto-discover newspaper RSS feeds (no keys, works today)

Instead of hand-entering feed URLs (which go stale), let the discovery tool
*find and verify* them. It tries common feed paths + reads each site's declared
feed links, and only keeps feeds that actually return articles.

**One city:**
```
py -m cityscope.tools.rss_discovery "Nashville" nashvillescene.com
```
It prints the working feed URL (or says none found) and a ready-to-run SQL line.

**All known cities at once:**
```
py -m cityscope.tools.rss_discovery --seed
```
This walks a built-in list of ~30 cities' alt-weekly domains, discovers each
feed, and prints SQL for the ones that work.

**Write straight to the database** (when DATABASE_URL is set):
```
py -m cityscope.tools.rss_discovery --seed --write
```

**To add a city not in the list:** just pass its paper's domain — you can find a
city's alt-weekly by searching "[city] alternative weekly" or "[city] events
newspaper". Example:
```
py -m cityscope.tools.rss_discovery "Boulder" boulderweekly.com
```

Editing the `KNOWN_PUBLICATIONS` dict in `cityscope/tools/rss_discovery.py` adds
domains to the `--seed` batch permanently.

### Without a database
If you're not running Postgres yet, the feed map lives in
`cityscope/db/repository.py` (`_FALLBACK_FEEDS`). The discovery tool prints the
paper name + URL; paste new entries there in the same format:
```python
"nashville": ("Nashville Scene", "https://www.nashvillescene.com/feed/"),
```
Then restart the app.

## B. Bluesky (real people, no keys, no approval)

Bluesky is the "boots on the ground" source — real people posting informal,
timely local chatter, the texture Reddit used to provide. Unlike Reddit, it's
genuinely open: no developer portal, no API key, no approval process. The app
uses Bluesky's PUBLIC search endpoint, which needs no authentication at all.

Turn it on by setting `CITYSCOPE_LIVE_BLUESKY=true` (already enabled in the
Render deploy config). No keys to obtain, nothing to apply for. The app searches
public posts mentioning the city + event terms and runs them through the same
classifier as every other source.

This is the practical answer to Reddit's locked-down API: same kind of content,
zero friction.

## C. Reddit (effectively closed as of 2026)

Reddit disabled self-serve app creation in late 2025 (the "Responsible Builder
Policy"), leaving the prefs/apps page in a broken state that returns errors. For
now, Reddit is not a viable source. The code path remains (set the REDDIT_* vars
and `CITYSCOPE_LIVE_REDDIT=true` if access ever opens up), but don't count on it.
Bluesky (above) is the replacement.

## Reality check on coverage

- **RSS** gives you cities that have an alt-weekly with a working feed — mostly
  mid-to-large US cities. Small towns often won't have one.
- **Reddit** (if approved) fills the gap, since almost every city has a sub.
- The autocomplete suggests 321 cities, but a city only shows real results once
  it has at least one working source. That's expected — coverage grows as you
  add feeds / enable Reddit.
