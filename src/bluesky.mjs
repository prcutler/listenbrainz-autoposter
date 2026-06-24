// ─────────────────────────────────────────────────────────────────────────
// Bluesky (AT Protocol) wrapper.
//
// Uses an app password (Bluesky → Settings → App Passwords). We log in fresh
// on each run — at a monthly cadence there's no need to cache the session,
// so there's no equivalent of scrobble-blue's Cloudflare KV here.
// ─────────────────────────────────────────────────────────────────────────

import { AtpAgent, RichText } from "@atproto/api";

/**
 * Publish a post. URLs/mentions are auto-detected so they're clickable.
 * Optionally attaches a single image.
 *
 * @param {object}  opts
 * @param {string}  opts.identifier  Bluesky handle
 * @param {string}  opts.password    Bluesky app password
 * @param {string}  opts.text        post body
 * @param {object} [opts.image]      { buffer, mime, alt, width, height }
 * @returns {Promise<{uri: string, cid: string}>}
 */
export async function postToBluesky({ identifier, password, text, image }) {
  const agent = new AtpAgent({ service: "https://bsky.social" });
  await agent.login({ identifier, password });

  const rt = new RichText({ text });
  await rt.detectFacets(agent);

  let embed;
  if (image) {
    const { data } = await agent.uploadBlob(image.buffer, { encoding: image.mime });
    embed = {
      $type: "app.bsky.embed.images",
      images: [{
        image: data.blob,
        alt: image.alt || "",
        aspectRatio: { width: image.width || 1200, height: image.height || 1200 },
      }],
    };
  }

  return agent.post({
    text: rt.text,
    facets: rt.facets,
    embed,
    langs: ["en"],
    createdAt: new Date().toISOString(),
  });
}
