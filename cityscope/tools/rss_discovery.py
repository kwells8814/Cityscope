"""RSS feed auto-discovery.

Given a city (and a candidate publication website), automatically FIND its RSS
feed instead of hand-entering URLs. Strategy, in order:

  1. Try common feed paths on the site (/feed/, /rss/, /feed, /rss.xml, ...).
  2. Parse the site's homepage for <link rel="alternate" type="...rss/atom">.
  3. Verify each candidate actually returns parseable items with titles.

Only feeds that pass verification are returned, so you never save a dead URL.

This needs network access, so it runs on YOUR machine (or the server), not in
the build sandbox. It uses stdlib only (urllib + a tiny HTML scan); feedparser
is used if available for more robust verification.

USAGE (command line):
    python -m cityscope.tools.rss_discovery "Asheville" mountainx.com
    python -m cityscope.tools.rss_discovery --seed     # discover for all known cities

The --seed mode reads candidate publication domains from KNOWN_PUBLICATIONS
below, discovers + verifies feeds, and prints SQL you can run to populate the
city_feed table (or use --write to insert directly when DATABASE_URL is set).
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# Common locations publishers put their feed.
_COMMON_PATHS = [
    "/feed/", "/feed", "/rss/", "/rss", "/rss.xml", "/index.xml",
    "/feed/rss/", "/feeds/", "/atom.xml", "/?feed=rss2",
    "/events/feed/", "/calendar/feed/",
]

_FEED_LINK_RE = re.compile(
    r'<link[^>]+type=["\']application/(?:rss\+xml|atom\+xml)["\'][^>]*>',
    re.I,
)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)

_UA = "cityscope-feed-discovery/0.2 (+personal project)"


# A small, EXTENDABLE map of city -> candidate publication domain(s).
# These are guesses to *try*; discovery verifies them, so a wrong guess just
# gets skipped. Add cities/domains freely — that's the whole point.
KNOWN_PUBLICATIONS = {
    "austin":      ["austinchronicle.com", "do512.com"],
    "chicago":     ["chicagoreader.com", "do312.com"],
    "asheville":   ["mountainx.com", "mtnxhost.net"],
    "durham":      ["indyweek.com"],
    "portland":    ["wweek.com", "pdxpipeline.com"],   # Portland, OR
    "seattle":     ["thestranger.com", "everout.com"],
    "neworleans":  ["nola.com"],
    "pittsburgh":  ["pghcitypaper.com"],
    "savannah":    ["connectsavannah.com"],
    "boise":       ["boiseweekly.com"],
    "nashville":   ["nashvillescene.com"],
    "denver":      ["westword.com"],
    "phoenix":     ["phoenixnewtimes.com"],
    "dallas":      ["dallasobserver.com"],
    "houston":     ["houstonpress.com"],
    "miami":       ["miaminewtimes.com"],
    "minneapolis": ["citypages.com", "racketmn.com"],
    "sanfrancisco":["sfweekly.com", "48hills.org"],
    "losangeles":  ["laweekly.com"],
    "philadelphia":["phillyvoice.com"],
    "detroit":     ["metrotimes.com"],
    "cleveland":   ["clevescene.com"],
    "kansascity":  ["thepitchkc.com"],
    "sanantonio":  ["sacurrent.com"],
    "orlando":     ["orlandoweekly.com"],
    "tampa":       ["cltampa.com"],
    "richmond":    ["styleweekly.com"],
    "tucson":      ["tucsonweekly.com"],
    "memphis":     ["memphisflyer.com"],
    "lasvegas":    ["lasvegasweekly.com"],
    "sacramento":  ["sacramento.newsreview.com"],
    "saltlakecity":["cityweekly.net"],
    "spokane":     ["inlander.com"],
}


def _fetch(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _verify_feed(url):
    """Return item count if the URL is a real feed with items, else 0."""
    try:
        raw = _fetch(url)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return 0
    # robust path: feedparser if present
    try:
        import feedparser  # type: ignore
        parsed = feedparser.parse(raw)
        titled = [e for e in parsed.entries if e.get("title")]
        return len(titled)
    except ImportError:
        pass
    # stdlib fallback: count <item> or <entry> with a <title>
    text = raw.decode("utf-8", "ignore")
    items = re.findall(r"<(?:item|entry)\b", text, re.I)
    titles = re.findall(r"<title\b", text, re.I)
    # crude: need several items and at least as many titles
    return min(len(items), max(0, len(titles) - 1))


def _candidates_from_homepage(domain):
    """Scan a domain's homepage for declared feed <link> tags."""
    base = f"https://{domain}"
    try:
        html = _fetch(base).decode("utf-8", "ignore")
    except Exception:
        return []
    out = []
    for tag in _FEED_LINK_RE.findall(html):
        m = _HREF_RE.search(tag)
        if m:
            out.append(urllib.parse.urljoin(base, m.group(1)))
    return out


def discover_feed(domain):
    """
    Find the best working feed URL for a publication domain.
    Returns (url, item_count) or (None, 0).
    """
    base = f"https://{domain}"
    tried = []

    # 1. declared <link> feeds (most reliable)
    for url in _candidates_from_homepage(domain):
        tried.append(url)
        n = _verify_feed(url)
        if n >= 3:
            return url, n

    # 2. common paths
    for path in _COMMON_PATHS:
        url = base + path
        if url in tried:
            continue
        n = _verify_feed(url)
        if n >= 3:
            return url, n

    return None, 0


def discover_for_city(city_key, domains=None):
    """Try each candidate domain for a city; return the first working feed."""
    domains = domains or KNOWN_PUBLICATIONS.get(city_key, [])
    for domain in domains:
        url, n = discover_feed(domain)
        if url:
            paper = _guess_paper_name(domain)
            return {"city_key": city_key, "paper": paper, "feed_url": url, "items": n}
    return None


def _guess_paper_name(domain):
    # turn "mountainx.com" -> "Mountainx"; user can rename later
    base = domain.split("//")[-1].split("/")[0]
    base = base.replace("www.", "").split(".")[0]
    return base.replace("-", " ").title()


def _sql_for(result):
    p = result["paper"].replace("'", "''")
    u = result["feed_url"].replace("'", "''")
    k = result["city_key"].replace("'", "''")
    return (f"INSERT INTO city_feed (city_key, paper, feed_url, active) "
            f"VALUES ('{k}', '{p}', '{u}', true) "
            f"ON CONFLICT (city_key, feed_url) DO UPDATE SET active=true;")


def main(argv):
    write = "--write" in argv
    argv = [a for a in argv if a != "--write"]

    if argv and argv[0] == "--seed":
        results = []
        for city_key in KNOWN_PUBLICATIONS:
            print(f"discovering {city_key}...", file=sys.stderr)
            r = discover_for_city(city_key)
            if r:
                print(f"  ✓ {r['paper']} -> {r['feed_url']} ({r['items']} items)",
                      file=sys.stderr)
                results.append(r)
            else:
                print(f"  ✗ no working feed found", file=sys.stderr)
        print(f"\n-- {len(results)} feeds discovered --")
        for r in results:
            print(_sql_for(r))
        if write:
            _write_results(results)
        return

    if len(argv) >= 1:
        city = argv[0].strip().lower().replace(" ", "")
        domains = argv[1:] if len(argv) > 1 else None
        r = discover_for_city(city, domains)
        if r:
            print(f"FOUND: {r['paper']} -> {r['feed_url']} ({r['items']} items)")
            print(_sql_for(r))
            if write:
                _write_results([r])
        else:
            print("No working feed found. Try passing the publication domain, e.g.:")
            print(f'  python -m cityscope.tools.rss_discovery "{argv[0]}" examplepaper.com')
        return

    print(__doc__)


def _write_results(results):
    """Insert verified feeds straight into the DB (needs DATABASE_URL)."""
    try:
        from ..db.engine import db_enabled, session_scope, init_engine, get_engine
        from ..db.models import Base, CityFeed
    except Exception as exc:
        print(f"(DB write skipped: {exc})", file=sys.stderr)
        return
    if not db_enabled():
        print("(DB write skipped: DATABASE_URL not set)", file=sys.stderr)
        return
    init_engine()
    Base.metadata.create_all(get_engine())
    with session_scope() as s:
        for r in results:
            exists = (s.query(CityFeed)
                      .filter(CityFeed.city_key == r["city_key"],
                              CityFeed.feed_url == r["feed_url"]).first())
            if not exists:
                s.add(CityFeed(city_key=r["city_key"], paper=r["paper"],
                               feed_url=r["feed_url"], active=True))
    print(f"wrote {len(results)} feeds to the database.", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
