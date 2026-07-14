// ─────────────────────────────────────────────────────────────────────────
// Entry point: fetch last month's top albums from ListenBrainz, render them
// as an image, and post it to Bluesky. Runs monthly from GitHub Actions (see
// .github/workflows/monthly-post.yml).
//
// Configure one or both destinations — it posts to whichever has credentials.
//
// Env vars:
//   LISTENBRAINZ_USERNAME   (required) whose public stats to read
//   BSKY_USERNAME           Bluesky handle, e.g. you.bsky.social   ┐ enables
//   BSKY_PASSWORD           Bluesky app password                   ┘ Bluesky
//   MASTODON_INSTANCE       e.g. https://mastodon.social           ┐ enables
//   MASTODON_TOKEN          Mastodon access token                  ┘ Mastodon
//   TEXT_ONLY               (optional) "1" to skip the image and post text only
//   DRY_RUN                 (optional) "1" to preview without posting
//                           (writes the rendered image to ./preview.<ext>)
// ─────────────────────────────────────────────────────────────────────────

import { writeFile } from "node:fs/promises";
import { getTopAlbums, formatRange } from "./listenbrainz.mjs";
import { renderImage } from "./image.mjs";
import { postToBluesky } from "./bluesky.mjs";
import { postToMastodon } from "./mastodon.mjs";

const {
  LISTENBRAINZ_USERNAME,
  BSKY_USERNAME, BSKY_PASSWORD,
  MASTODON_INSTANCE, MASTODON_TOKEN,
  TEXT_ONLY, DRY_RUN,
} = process.env;

function required(name, value) {
  if (!value) {
    console.error(`✗ Missing required environment variable: ${name}`);
    process.exit(1);
  }
  return value;
}

const GRAPHEMES = text => [...new Intl.Segmenter().segment(text)].length;

// Returns the UTC timestamp for the first day of the current calendar month.
// The "month" stats range should return this exact date as its `to` value
// (last completed month ends at the start of the current month). If the
// returned `to` is earlier, ListenBrainz's stats engine hasn't caught up yet.
function expectedMonthBoundary() {
  const n = new Date();
  return new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), 1));
}

// Short caption that accompanies the image.
function buildCaption(count, range, lbUser) {
  const header = `🎧 My top ${count} artists on ListenBrainz last month` +
    (range ? ` (${range})` : "");
  const profile = `https://listenbrainz.org/user/${lbUser}/`;
  const withLink = `${header}\n\n${profile}`;
  return GRAPHEMES(withLink) <= 300 ? withLink : header;
}

// Accessible alt text describing the image contents.
function buildAltText(albums, range) {
  const lines = albums.map((a, i) => `${i + 1}. ${a.album} — ${a.artist} (${a.plays} plays)`);
  const head = `My top ${albums.length} artists on ListenBrainz last month` +
    (range ? ` (${range})` : "") + ":";
  return `${head}\n${lines.join("\n")}`;
}

async function main() {
  const lbUser = required("LISTENBRAINZ_USERNAME", LISTENBRAINZ_USERNAME);

  console.log(`→ Fetching last month's top albums for "${lbUser}"…`);
  const { albums, from, to } = await getTopAlbums(lbUser, { range: "month", count: 5 });

  if (!albums.length) {
    console.log("→ No listening data for last month — nothing to post. Done.");
    return;
  }

  const expected = expectedMonthBoundary();
  if (to && to < expected) {
    const got      = to.toISOString().slice(0, 7);   // e.g. "2026-06"
    const want     = expected.toISOString().slice(0, 7); // e.g. "2026-07"
    console.warn(
      `⚠ ListenBrainz's "month" stats are still showing ${got} instead of ${want} — ` +
      `their stats engine hasn't caught up yet. ` +
      `Skipping this run rather than posting stale data as "last month".`
    );
    return;
  }

  const range = formatRange(from, to);
  const text = buildCaption(albums.length, range, lbUser);

  // Render the image (unless TEXT_ONLY); fall back to text-only on failure.
  let image = null;
  if (TEXT_ONLY !== "1") {
    try {
      console.log("→ Rendering top 5 image…");
      const rendered = await renderImage({ albums, rangeLabel: range, username: lbUser });
      image = { ...rendered, alt: buildAltText(albums, range) };
      console.log(`  image ready (${rendered.mime}, ${(rendered.buffer.length / 1024).toFixed(0)} KB)`);
    } catch (err) {
      console.warn(`⚠ Image render failed — posting text only: ${err?.message || err}`);
    }
  }

  // Decide which platforms to post to, based on which creds are configured.
  const targets = [];
  if (BSKY_USERNAME && BSKY_PASSWORD) targets.push("bluesky");
  if (MASTODON_INSTANCE && MASTODON_TOKEN) targets.push("mastodon");

  console.log("\n----- post preview -----\n" + text + "\n------------------------");
  if (image) console.log(`(with image + alt text, ${image.width}×${image.height})`);
  console.log(`Destinations: ${targets.length ? targets.join(", ") : "(none configured)"}\n`);

  if (DRY_RUN === "1") {
    if (image) {
      const file = image.mime === "image/jpeg" ? "preview.jpg" : "preview.png";
      await writeFile(file, image.buffer);
      console.log(`→ DRY_RUN=1 — wrote rendered image to ./${file}`);
    }
    console.log("→ DRY_RUN=1 — skipping the actual post.");
    return;
  }

  if (!targets.length) {
    console.error("✗ No destinations configured. Set Bluesky and/or Mastodon credentials.");
    process.exit(1);
  }

  // Post to each target independently — one failing doesn't block the other.
  let failed = false;

  if (targets.includes("bluesky")) {
    try {
      console.log("→ Posting to Bluesky…");
      const { uri } = await postToBluesky({
        identifier: BSKY_USERNAME, password: BSKY_PASSWORD, text, image,
      });
      console.log(`✓ Bluesky: ${uri}`);
    } catch (err) {
      failed = true;
      console.error(`✗ Bluesky failed: ${err?.message || err}`);
    }
  }

  if (targets.includes("mastodon")) {
    try {
      console.log("→ Posting to Mastodon…");
      const { url } = await postToMastodon({
        instance: MASTODON_INSTANCE, token: MASTODON_TOKEN, text, image,
      });
      console.log(`✓ Mastodon: ${url}`);
    } catch (err) {
      failed = true;
      console.error(`✗ Mastodon failed: ${err?.message || err}`);
    }
  }

  if (failed) process.exit(1);
}

main().catch(err => {
  console.error("✗ Failed:", err?.message || err);
  process.exit(1);
});
