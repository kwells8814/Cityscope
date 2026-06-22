# Getting Bluesky working reliably (free app password)

The app reads public Bluesky posts to surface real local chatter. It tries two
ways, in order:

1. **Authenticated** (if you set credentials) — reliable from a server.
2. **Public no-auth endpoint** (fallback) — works from a browser/home machine,
   but Bluesky sometimes returns empty results for unauthenticated requests
   coming from cloud servers like Render.

If your deployed app shows no Bluesky results, set up the free app password
below — it's the reliable path. This is NOT like Reddit: there's no approval, no
review, no developer portal. Just a free account and an app password.

## Steps

1. **Make a Bluesky account** (if you don't have one) at https://bsky.app — free.

2. **Create an App Password** (this is separate from your login password and can
   be revoked anytime, so the app never touches your real password):
   - In the Bluesky app/site: **Settings → Privacy and Security → App Passwords**
     (or go to https://bsky.app/settings/app-passwords).
   - Click **Add App Password**, give it a name like "cityscope", and copy the
     password it shows (looks like `xxxx-xxxx-xxxx-xxxx`). You only see it once.

3. **Add the two values to your deployment:**
   - On Render: your service → **Environment** tab → **Add Environment Variable**:
     - `BLUESKY_HANDLE` = your handle, e.g. `yourname.bsky.social`
     - `BLUESKY_APP_PASSWORD` = the `xxxx-xxxx-xxxx-xxxx` you copied
   - Save. Render redeploys automatically.

   - For local use: put the same two lines in your `.env` file.

4. **Verify:** open `/happenings?city=Chicago` and look at the Bluesky source's
   `detail.diag` — it should now say `"mode": "auth"` and `raw_total` above 0.

## Security notes

- An app password only grants API access and can be **revoked** anytime from the
  same settings page — it's designed exactly for this.
- Never put it in your public GitHub repo. It belongs in Render's Environment
  settings (or your local `.env`, which is git-ignored), not in the code.
