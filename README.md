# ListenBrainz Autoposter

Posts your **ListenBrainz top 5 albums from last week** to **Bluesky and/or Mastodon**,
automatically, every Wednesday — running entirely on **GitHub Actions** (no Cloudflare, no server to
run).

Inspired by [scrobble-blue](https://github.com/willmanduffy/scrobble-blue), but rebuilt around
GitHub Actions + ListenBrainz instead of a Cloudflare Worker.

![Example image of top 5 weekly albums](top5.png)

Also checkout my [ListenBrainz-widget](https://prcutler.github.io/listenbrainz-widget/index.html) to embed your top listens in a webpage or manually create an image you can share on the social media platform of your choice.

## How it works

- A scheduled GitHub Actions workflow runs **every Wednesday at 15:00 UTC**.
- It reads your **last completed week** of listens from the public ListenBrainz statistics API
  (`range=week`).
- It renders a **1200×1200 image** of your top 5 albums (with cover art) using headless Chromium
  (Playwright), then posts it to Bluesky with a short caption and accessible alt text.
- If the image render ever fails, it automatically falls back to a **text-only** post.

### Why Wednesday / why "last week"?

ListenBrainz's `week` range is **last week's completed Monday–Sunday**, *not* a rolling 7 days.
Its stats are also batch-computed with a lag that can vary — on 2026-06-23 a Tuesday 15:07 UTC run
still got the week before last, only flipping over to the correct week later that same day. Running
on **Wednesday** instead gives a full extra day of buffer before posting.

## Setup

### 1. Get credentials for at least one destination

You can post to **Bluesky, Mastodon, or both** — it posts to whichever you've configured.

**Bluesky:** Settings → **App Passwords → Add App Password**. Use this, not your real password (it's
revocable and works with MFA enabled).

**Mastodon:** your instance → **Preferences → Development → New Application**, with scopes
`write:statuses` and `write:media`, then copy the access token.

### 2. Push this project to a GitHub repo

```bash
cd listenbrainz-autoposter
git init && git add . && git commit -m "Initial commit"
git remote add origin git@github.com:<you>/listenbrainz-autoposter.git
git push -u origin main
```

### 3. Add repository secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**. Add
`LISTENBRAINZ_USERNAME` plus the secrets for whichever destination(s) you want:

| Secret | Value | Needed for |
|---|---|---|
| `LISTENBRAINZ_USERNAME` | your ListenBrainz username (e.g. `silwenae`) | always |
| `BSKY_USERNAME` | your Bluesky handle (e.g. `you.bsky.social`) | Bluesky |
| `BSKY_PASSWORD` | the app password from step 1 | Bluesky |
| `MASTODON_INSTANCE` | your instance URL (e.g. `https://mastodon.social`) | Mastodon |
| `MASTODON_TOKEN` | the access token from step 1 | Mastodon |

Leave out the secrets for any platform you don't want to post to.

### 4. Test it

Go to the **Actions** tab → **Weekly ListenBrainz → Bluesky** → **Run workflow**, and tick
**dry run** to preview the post text in the logs without sending it. When you're happy, run it again
without dry run (or just wait for Wednesday).

## Running locally

Requires **Node.js 20.6+** (for `--env-file`).

```bash
cp .env.example .env                  # fill in your details
npm install
npx playwright install chromium       # one-time: download the browser
npm run dry-run                       # prints the post + writes ./preview.png, does NOT send it
npm run local                         # actually posts to Bluesky
```

`npm run dry-run` saves the rendered card to `./preview.png` (or `.jpg`) so you can eyeball the image
before posting for real.

## What gets posted

A **1200×1200 image** of your top 5 albums with cover art, plus a short caption:

```
🎧 My top 5 albums on ListenBrainz last week (May 25 – May 31)

https://listenbrainz.org/user/silwenae/
```

The full ranked list (album — artist — play count) goes into the image's **alt text** for
accessibility. The same caption + image is sent to every configured destination; the profile link is
rendered as a clickable link on both Bluesky (via facets) and Mastodon (auto-linkified).

### Text-only mode

Set `TEXT_ONLY=1` to skip the image and post the full ranked list as text instead. The renderer also
falls back to text automatically if Chromium fails for any reason.

## Notes & ideas

- **Image size:** Bluesky caps image blobs at 1 MB. The card is screenshotted as PNG, and if that
  exceeds the limit it's re-encoded as JPEG automatically.
- **Top artists instead of albums?** ListenBrainz also exposes `/stats/user/{user}/artists`. Swap
  the endpoint in `src/listenbrainz.mjs` and the wording in `src/index.mjs` / `src/template.mjs`.
- **GitHub Actions cron is best-effort** and can run a few minutes late — fine for a weekly job, but
  not suitable for minute-by-minute tasks.

## Project layout

```
.github/workflows/weekly-post.yml   # the Wednesday schedule + manual trigger
src/index.mjs                       # orchestration + caption/alt text
src/listenbrainz.mjs                # ListenBrainz stats fetch + cover-art URLs
src/template.mjs                    # the 1200×1200 HTML card
src/image.mjs                       # Playwright render → PNG/JPEG buffer
src/bluesky.mjs                     # Bluesky login + post (with image embed)
src/mastodon.mjs                    # Mastodon media upload + status post
.env.example                        # local config template
```
