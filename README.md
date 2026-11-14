# ListenBrainz Autoposter

Posts your **ListenBrainz top 5 albums from last month** to **Bluesky and/or Mastodon**,
automatically, once a month (as soon as ListenBrainz has the data after the 15th) — run by **cron on any Linux box** (a home server, a Raspberry
Pi, a cheap VPS).

Inspired by [scrobble-blue](https://github.com/willmanduffy/scrobble-blue), but rebuilt around
ListenBrainz and a plain cron job instead of a Cloudflare Worker.

![Example image of top 5 albums](top5.png)

Also checkout my [ListenBrainz-widget](https://prcutler.github.io/listenbrainz-widget/index.html) to embed your top listens in a webpage or manually create an image you can share on the social media platform of your choice.

## How it works

- A cron job runs [`scripts/run.sh`](scripts/run.sh) **daily from the 16th to the 28th**, but it
  **posts only once a month**: the first run that finds last month's stats posts, and the rest
  exit quietly.
- It reads your **last completed calendar month** of listens from the public ListenBrainz
  statistics API (`range=month`).
- It draws a **1200×1200 image** of your top 5 albums (with cover art) using
  [Pillow](https://python-pillow.org/), then posts it with a short caption and accessible alt text.
- It's plain **Python** with one dependency (Pillow) — no Node.js and no headless browser.
- If the image render ever fails, it automatically falls back to a **text-only** post.

### Why the 16th–28th / why monthly instead of weekly?

This originally ran weekly (every Wednesday), reading ListenBrainz's `week` range. That fought their
[update schedule](https://listenbrainz.readthedocs.io/en/latest/general/data-update-intervals.html):
they only do a full stats reimport on the **1st and 15th of the month**. In June 2026 the `week`
range got stuck serving the same stale window for **8+ days** — `last_updated` on their API was
frozen the whole time, even though raw listens kept recording fine. No amount of schedule-shuffling
fixes a problem that's upstream, so the project moved to `range=month`, which only needs to flip over
once a month, right when ListenBrainz already does its full reimport. It originally posted on the
**4th**, then the **14th**, but those reimports keep running late: in July 2026 the 1st-of-month
reimport took ~12 days, and in November 2026 it still hadn't landed by the 14th.

Both reimports produce the same "last month" stats, so by the **16th** there have been two chances
for them to land. Neither is guaranteed to be on time, though, so instead of betting on one day the
job runs every day from the 16th to the 28th:

- Each run checks that the stats are actually for last month and **skips** (rather than posting
  stale data) if ListenBrainz hasn't caught up yet.
- After a successful post, the month is recorded per platform in `.autoposter-state.json`, so later
  runs that month do nothing. If one platform fails (say Mastodon is down), the next day's run
  retries just that one, without double-posting to the other.
- Stopping at the 28th keeps every run inside the same calendar month, so "last month" never
  changes underneath it.

### Why cron instead of GitHub Actions?

GitHub **disables scheduled workflows after 60 days with no repository activity**. A monthly job
in a repo that rarely changes trips that constantly, so the schedule now lives in cron on a machine
you control. The GitHub workflow is still there, but only as a **manual** fallback (Actions →
Run workflow) — it no longer runs on a schedule, so it can't double-post.

## Setup

### 1. Get credentials for at least one destination

You can post to **Bluesky, Mastodon, or both** — it posts to whichever you've configured.

**Bluesky:** Settings → **App Passwords → Add App Password**. Use this, not your real password (it's
revocable and works with MFA enabled).

**Mastodon:** your instance → **Preferences → Development → New Application**, with scopes
`write:statuses` and `write:media`, then copy the access token.

### 2. Install on your Linux box

Requires **Python 3.10+** and git. On Debian/Ubuntu you may also need `sudo apt install python3-venv`.

```bash
git clone https://github.com/<you>/listenbrainz-autoposter.git ~/listenbrainz-autoposter
cd ~/listenbrainz-autoposter
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env         # then fill it in
```

(If you'd rather skip the virtualenv, `sudo apt install python3-pil` works too — `scripts/run.sh`
falls back to the system `python3` when there's no `.venv`.)

| `.env` key | Value | Needed for |
|---|---|---|
| `LISTENBRAINZ_USERNAME` | your ListenBrainz username | always |
| `BSKY_USERNAME` | your Bluesky handle (e.g. `you.bsky.social`) | Bluesky |
| `BSKY_PASSWORD` | the app password from step 1 | Bluesky |
| `MASTODON_INSTANCE` | your instance URL (e.g. `https://mastodon.social`) | Mastodon |
| `MASTODON_TOKEN` | the access token from step 1 | Mastodon |

Leave a platform's values blank to skip it.

### 3. Test it

```bash
scripts/run.sh --dry-run
```

This prints the post, writes `./preview.png`, and sends nothing. Output is also appended to
`logs/YYYY-MM.log`.

### 4. Add the cron job

Run `crontab -e` and add:

```cron
# ListenBrainz autoposter — 15:00 daily on the 16th–28th; posts once per month
0 15 16-28 * * $HOME/listenbrainz-autoposter/scripts/run.sh >/dev/null 2>&1
```

Cron uses the machine's **local time zone** (check with `timedatectl`); adjust the hour if you
want it at a particular UTC time. Output goes to `logs/`, so cron's own mail is silenced above — drop
the `>/dev/null 2>&1` if your box has mail set up and you'd like a copy.

The script uses the project's `.venv` automatically, so cron's minimal `PATH` isn't a problem. To
use a different interpreter, set `PYTHON=/path/to/python` at the start of the cron line.

To post again for a month that's already been posted, run `scripts/run.sh --force`, or delete
`.autoposter-state.json`.

To check a run afterwards:

```bash
tail -n 40 ~/listenbrainz-autoposter/logs/$(date -u +%Y-%m).log
```

### Updating

```bash
cd ~/listenbrainz-autoposter && git pull && .venv/bin/pip install -r requirements.txt
```

## Running locally

Same as the Linux setup — it runs anywhere with Python 3.10+ (macOS included):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                       # fill in your details
.venv/bin/python -m autoposter --dry-run   # prints the post + writes ./preview.png, does NOT send it
.venv/bin/python -m autoposter             # actually posts
```

## What gets posted

A **1200×1200 image** of your top 5 albums with cover art, plus a short caption:

```
🎧 My top 5 artists on ListenBrainz last month (May 1 – May 31)

https://listenbrainz.org/user/<you>/
```

The full ranked list (album — artist — play count) goes into the image's **alt text** for
accessibility. The same caption + image is sent to every configured destination; the profile link is
rendered as a clickable link on both Bluesky (via facets) and Mastodon (auto-linkified).

### Text-only mode

Set `TEXT_ONLY=1` to skip the image and post the full ranked list as text instead. The renderer also
falls back to text automatically if drawing the image fails for any reason.

## Notes & ideas

- **Image size:** Bluesky caps image blobs at 1 MB. The card is saved as PNG, and if that exceeds
  the limit it's re-encoded as JPEG automatically.
- **Fonts:** the card uses Fraunces, Hanken Grotesk and DM Mono, bundled in `autoposter/fonts/`
  (SIL Open Font License). Album titles in scripts those fonts don't cover (e.g. CJK) will show
  placeholder boxes.
- **Top artists instead of albums?** ListenBrainz also exposes `/stats/user/{user}/artists`. Swap
  the endpoint in `autoposter/listenbrainz.py` and the wording in `autoposter/__main__.py` /
  `autoposter/image.py`.
- **Machine off for a few days?** Thanks to the daily 16th–28th window, a missed day just means it
  posts on the next one. If it misses the whole window, run `scripts/run.sh` by hand.

## Project layout

```
scripts/run.sh                      # cron entry point: loads .env, logs to logs/
autoposter/__main__.py              # orchestration + caption/alt text
autoposter/listenbrainz.py          # ListenBrainz stats fetch + cover-art URLs
autoposter/image.py                 # draws the 1200×1200 card with Pillow
autoposter/bluesky.py               # Bluesky login + post (with image embed)
autoposter/mastodon.py              # Mastodon media upload + status post
autoposter/fonts/                   # bundled card fonts (OFL)
.github/workflows/monthly-post.yml  # manual-only fallback on GitHub Actions
.env.example                        # config template
```
