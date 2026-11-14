"""Entry point: fetch last month's top albums from ListenBrainz, render them
as an image, and post to Bluesky and/or Mastodon. Run with
`python -m autoposter` (cron uses scripts/run.sh).

Configure one or both destinations — it posts to whichever has credentials.

Env vars (also read from ./.env if present):
  LISTENBRAINZ_USERNAME   (required) whose public stats to read
  BSKY_USERNAME           Bluesky handle, e.g. you.bsky.social   ┐ enables
  BSKY_PASSWORD           Bluesky app password                   ┘ Bluesky
  MASTODON_INSTANCE       e.g. https://mastodon.social           ┐ enables
  MASTODON_TOKEN          Mastodon access token                  ┘ Mastodon
  TEXT_ONLY               (optional) "1" to skip the image and post text only
  DRY_RUN                 (optional) "1" to preview without posting
                          (writes the rendered image to ./preview.<ext>)

Post once per month: cron runs this daily for a stretch of days, because
ListenBrainz's stats can land days late. After a successful post, the
month is recorded per platform in .autoposter-state.json; later runs that
month skip platforms already done (and retry any that failed).
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .listenbrainz import format_range, get_top_albums


def load_env_file(path):
    """Minimal .env reader. Real environment variables win over the file."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def load_state(path):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return {}


def save_state(path, state):
    tmp = Path(f"{path}.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(path)


def previous_month():
    """"YYYY-MM" of last calendar month (UTC) — the month we're posting about."""
    first = expected_month_boundary()
    return f"{first.year - (first.month == 1)}-{(first.month - 2) % 12 + 1:02d}"


def graphemes(text):
    # Close enough for our caption (no combining sequences).
    return len(text)


def expected_month_boundary():
    """First day of the current month (UTC) — what `to` should be for "month"."""
    n = datetime.now(timezone.utc)
    return datetime(n.year, n.month, 1, tzinfo=timezone.utc)


def build_caption(count, range_label, lb_user):
    header = f"🎧 My top {count} artists on #ListenBrainz last month" + (
        f" ({range_label})" if range_label else "")
    with_link = f"{header}\n\nhttps://listenbrainz.org/user/{lb_user}/"
    return with_link if graphemes(with_link) <= 300 else header


def build_alt_text(albums, range_label):
    head = f"My top {len(albums)} artists on #ListenBrainz last month" + (
        f" ({range_label})" if range_label else "") + ":"
    lines = [f"{i + 1}. {a['album']} — {a['artist']} ({a['plays']} plays)"
             for i, a in enumerate(albums)]
    return "\n".join([head, *lines])


def main(argv=None):
    parser = argparse.ArgumentParser(prog="autoposter", description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="preview without posting")
    parser.add_argument("--env-file", default=".env", help="path to .env (default: ./.env)")
    parser.add_argument("--state-file", default=".autoposter-state.json",
                        help="where posted months are recorded (default: ./.autoposter-state.json)")
    parser.add_argument("--force", action="store_true",
                        help="post even if this month was already posted")
    args = parser.parse_args(argv)

    load_env_file(args.env_file)
    env = os.environ.get
    dry_run = args.dry_run or env("DRY_RUN") == "1"

    lb_user = env("LISTENBRAINZ_USERNAME")
    if not lb_user:
        print("✗ Missing required environment variable: LISTENBRAINZ_USERNAME", file=sys.stderr)
        return 1

    targets = []
    if env("BSKY_USERNAME") and env("BSKY_PASSWORD"):
        targets.append("bluesky")
    if env("MASTODON_INSTANCE") and env("MASTODON_TOKEN"):
        targets.append("mastodon")

    # Skip platforms that already have this month's post (cron runs daily).
    month = previous_month()
    state = load_state(args.state_file)
    if not dry_run and not args.force:
        done = [t for t in targets if state.get(t) == month]
        targets = [t for t in targets if t not in done]
        if done and not targets:
            print(f"→ Already posted {month} to {', '.join(done)} — nothing to do.")
            return 0
        if done:
            print(f"→ Already posted {month} to {', '.join(done)}; still to do: "
                  f"{', '.join(targets)}")

    print(f'→ Fetching last month\'s top albums for "{lb_user}"…', flush=True)
    stats = get_top_albums(lb_user, range_="month", count=5)
    albums, start, end = stats["albums"], stats["from"], stats["to"]

    if not albums:
        print("→ No listening data for last month — nothing to post. Done.")
        return 0

    expected = expected_month_boundary()
    if end and end < expected:
        got = f"{start:%Y-%m}" if start else f"data ending {end:%Y-%m-%d}"
        print(f'⚠ ListenBrainz\'s "month" stats are still for {got}, not {month} — '
              f"their stats engine hasn't caught up yet. "
              'Skipping this run rather than posting stale data as "last month".',
              file=sys.stderr)
        return 0

    range_label = format_range(start, end)
    text = build_caption(len(albums), range_label, lb_user)

    # Render the image (unless TEXT_ONLY); fall back to text-only on failure.
    image = None
    if env("TEXT_ONLY") != "1":
        try:
            from .image import render_image
            print("→ Rendering top 5 image…", flush=True)
            image = render_image(albums, range_label, lb_user)
            image["alt"] = build_alt_text(albums, range_label)
            print(f"  image ready ({image['mime']}, {len(image['data']) / 1024:.0f} KB)")
        except Exception as err:  # noqa: BLE001 — any render failure → text-only
            print(f"⚠ Image render failed — posting text only: {err}", file=sys.stderr)

    print("\n----- post preview -----\n" + text + "\n------------------------")
    if image:
        print(f"(with image + alt text, {image['width']}×{image['height']})")
    print(f"Destinations: {', '.join(targets) if targets else '(none configured)'}\n")

    if dry_run:
        if image:
            name = "preview.jpg" if image["mime"] == "image/jpeg" else "preview.png"
            Path(name).write_bytes(image["data"])
            print(f"→ dry run — wrote rendered image to ./{name}")
        print("→ dry run — skipping the actual post.")
        return 0

    if not targets:
        print("✗ No destinations configured. Set Bluesky and/or Mastodon credentials.",
              file=sys.stderr)
        return 1

    # Post to each target independently — one failing doesn't block the other.
    failed = False
    if "bluesky" in targets:
        from .bluesky import post_to_bluesky
        try:
            print("→ Posting to Bluesky…", flush=True)
            res = post_to_bluesky(identifier=env("BSKY_USERNAME"),
                                  password=env("BSKY_PASSWORD"), text=text, image=image)
            print(f"✓ Bluesky: {res['uri']}")
            state["bluesky"] = month
            save_state(args.state_file, state)
        except Exception as err:  # noqa: BLE001
            failed = True
            print(f"✗ Bluesky failed: {err}", file=sys.stderr)

    if "mastodon" in targets:
        from .mastodon import post_to_mastodon
        try:
            print("→ Posting to Mastodon…", flush=True)
            res = post_to_mastodon(instance=env("MASTODON_INSTANCE"),
                                   token=env("MASTODON_TOKEN"), text=text, image=image)
            print(f"✓ Mastodon: {res['url']}")
            state["mastodon"] = month
            save_state(args.state_file, state)
        except Exception as err:  # noqa: BLE001
            failed = True
            print(f"✗ Mastodon failed: {err}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as err:  # noqa: BLE001
        print(f"✗ Failed: {err}", file=sys.stderr)
        sys.exit(1)
