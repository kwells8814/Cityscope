# Reddit Data API — Access Application Draft
### (Personal / non-commercial use)

Fill in the [BRACKETED] parts before submitting. Everything else is written to
accurately describe a low-volume, non-commercial, read-only personal project —
the category Reddit's free tier is intended for.

Apply at: https://www.reddit.com/wiki/api  →  register an app at
https://www.reddit.com/prefs/apps (choose **script** type), and complete the
access request / Responsible Builder questionnaire Reddit presents.

---

## App registration (prefs/apps → "create app")

- **App type:** script
- **Name:** CityScope (personal)
- **Description:** Personal, non-commercial app that surfaces interesting local
  happenings in a chosen city by reading recent public posts from that city's
  public subreddits.
- **Redirect URI:** http://localhost:8000  *(required field; script apps don't
  use it meaningfully)*
- **About URL:** [leave blank, or your GitHub repo if public]

---

## Use-case description (for the access request)

**What the project is:**
CityScope is a personal hobby project I built to answer a simple question —
"what's actually going on in a given city right now?" — by reading recent public
posts from that city's public subreddits (e.g. r/[city]) and surfacing the ones
that describe real local events, hidden spots, and happenings. It is one of
several sources; the app also reads public local-newspaper RSS feeds.

**Commercial status:** Non-commercial. There is no revenue, no advertising, no
paywall, and no paid product. It is used by me and a small number of friends.

**Who uses it:** Me and a few friends — fewer than [NUMBER, e.g. 10] people.

**What data I access:** Read-only access to **public** post listings from public
subreddits — title, body text, score, comment count, timestamp, and permalink.
I do not access private subreddits, user-level data beyond the public author
name on a post, private messages, or any non-public content.

**What I do NOT do:** No posting, commenting, voting, messaging, or moderation
(read-only). No collection of user profiles or personal data. No attempt to
access deleted/removed content. No resale or redistribution of Reddit data.

**Request volume / frequency:** Low. A typical city lookup reads recent posts
("new"/"hot", limit ~50) from a handful of that city's subreddits. Results are
**cached** so repeated lookups of the same city do not re-fetch. Realistic
sustained volume is well under [e.g. a few hundred] requests per hour, far below
the 100 queries-per-minute free-tier limit. I implement conservative client-side
rate limiting (~50 QPM ceiling) and exponential backoff on 429 responses.

**Authentication:** OAuth 2.0 client-credentials flow with a registered script
app and a descriptive User-Agent in Reddit's required format
(`python:cityscope:<version> (by /u/[YOUR_USERNAME])`).

## Compliance & data handling

- **Public data only**, read-only, via the official OAuth API.
- **No persistent storage of Reddit content** beyond a short-lived in-memory /
  cache copy used to serve a request. If I later add a database, I will honor
  Reddit's deletion requirements: content removed or deleted on Reddit will be
  purged from any store (I will implement a purge path keyed on post IDs).
- **No user tracking or profiling.** I do not build profiles of Reddit users.
- **Attribution & links:** the app links back to the original Reddit post; it
  does not present Reddit content as its own.
- **Rate-limit respect:** descriptive User-Agent, OAuth, conservative pacing,
  backoff on 429, and caching to minimize load.
- I have read and will comply with the Reddit Data API Terms and the Responsible
  Builder Policy.

## Technical summary

- **Language/stack:** Python (FastAPI backend, stdlib HTTP client for Reddit).
- **Endpoints used:** `/subreddits/search` (to find a city's subreddits),
  `/r/{sub}/about` (size/activity), `/r/{sub}/new` and `/r/{sub}/hot` (recent
  public posts). All read-only GET requests.
- **Deployment:** [personal laptop / a small cloud instance — state whichever is
  true]. Single low-traffic instance.

---

## Contact

- **Reddit username:** /u/[YOUR_USERNAME]
- **Email:** [YOUR_EMAIL]
- **Name:** [YOUR_NAME]
