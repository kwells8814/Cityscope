# Get CityScope on your phone

This turns CityScope into a tappable icon on your home screen, backed by a real
server you can reach from anywhere. Two steps: **deploy the app**, then
**install it on your phone**.

The backend serves the frontend too, so you deploy *one thing* and get one URL.
It runs on sample data out of the box — no keys needed to get it on your phone.

---

## Part 1 — Deploy (pick ONE host)

You'll need a free GitHub account; push this folder to a new repo first:

```bash
cd cityscope-backend
git init && git add . && git commit -m "CityScope"
# create an empty repo on github.com, then:
git remote add origin https://github.com/<you>/cityscope.git
git push -u origin main
```

### Option A — Render (easiest, free tier)
1. Go to render.com, sign in with GitHub.
2. **New → Blueprint**, pick your repo. It reads `render.yaml` automatically.
3. Click **Apply**. Wait ~2–3 min for the build.
4. You get a URL like `https://cityscope.onrender.com`. That's your app.

(Free tier sleeps after inactivity; first load after idle takes ~30s. Fine for
personal use; upgrade for always-on.)

### Option B — Railway
1. railway.app → **New Project → Deploy from GitHub repo**.
2. It detects `railway.json` and builds. Open the generated domain.

### Option C — Fly.io (Docker, good free allowance)
1. Install the CLI: `curl -L https://fly.io/install.sh | sh`
2. `fly launch` (accepts `fly.toml`), then `fly deploy`.
3. `fly open` opens your URL.

### Verify
Open `https://<your-url>/health` — you should see JSON with `"status":"ok"`.
Open `https://<your-url>/` — the CityScope door with the **Tap in** button.
Because the frontend is served by the backend, it's automatically using the live
API (the page probes `/health` on load and switches to live mode).

---

## Part 2 — Install on your phone

Open your deployed URL in your phone's browser, then:

### iPhone (Safari — must be Safari, not Chrome)
1. Tap the **Share** button (square with an up-arrow).
2. Scroll down, tap **Add to Home Screen**.
3. Tap **Add**. A CityScope icon appears on your home screen.
4. Open it — it launches fullscreen, no browser bars, like a real app.

### Android (Chrome)
1. Tap the **⋮** menu (top right).
2. Tap **Install app** (or **Add to Home screen**).
3. Confirm. The icon lands on your home screen and in your app drawer.

That's it — you're using CityScope on your phone. GPS ("Use my location") will
prompt for location permission the first time.

---

## Part 3 — Make the data real (optional, later)

Out of the box it runs on sample data. Flip these in your host's **Environment
Variables** dashboard (no redeploy needed on most hosts beyond a restart):

| Variable | Effect | Needs |
|---|---|---|
| `CITYSCOPE_LIVE_RSS=true` | real local alt-weekly events | nothing |
| `CITYSCOPE_LIVE_GEOCODE=true` | real GPS → city (US Census) | nothing |
| `CITYSCOPE_LIVE_REDDIT=true` | real Reddit posts | Reddit keys ↓ |

For Reddit, also set `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`,
`REDDIT_USERNAME`. Create a **script** app at reddit.com/prefs/apps and request
API access (Reddit requires approval as of Nov 2025).

Start with RSS + geocode — they're real data with zero keys, so your first
"real" version costs nothing and needs no approvals.

---

## Updating the app later

Push to GitHub; Render/Railway auto-redeploy. The service worker is versioned
(`CACHE_VERSION` in `sw.js`) — bump it when you change frontend files so phones
pick up the new version instead of a stale cache.

## Troubleshooting

- **"Add to Home Screen" missing on iPhone:** you're not in Safari. iOS only
  allows PWA install from Safari.
- **Icon is generic / no fullscreen:** the manifest or icons didn't load. Open
  `https://<url>/manifest.webmanifest` and `.../icons/icon-192.png` directly to
  confirm they serve.
- **App shows sample data even when deployed:** the page couldn't reach
  `/health`. Check the deploy is running and `/health` returns 200.
- **Location button does nothing:** geolocation needs HTTPS. All the hosts above
  give you HTTPS automatically; `file://` and plain `http://` won't prompt.
