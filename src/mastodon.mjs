// ─────────────────────────────────────────────────────────────────────────
// Mastodon wrapper (plain REST API, no SDK needed).
//
// Auth: an access token from your instance → Preferences → Development →
// New Application (scopes: write:statuses, write:media).
//
// Posting with an image is two steps: upload the media, then create a status
// referencing it. Mastodon auto-linkifies URLs in the status text, so unlike
// Bluesky there are no facets to build.
// ─────────────────────────────────────────────────────────────────────────

const safeText = async res => { try { return await res.text(); } catch { return ""; } };

/**
 * Publish a status, optionally with one image.
 * @param {object}  opts
 * @param {string}  opts.instance  base URL, e.g. https://mastodon.social
 * @param {string}  opts.token     access token
 * @param {string}  opts.text      status body
 * @param {object} [opts.image]    { buffer, mime, alt }
 * @returns {Promise<{url: string, id: string}>}
 */
export async function postToMastodon({ instance, token, text, image }) {
  const base = instance.replace(/\/+$/, "");
  const auth = { Authorization: `Bearer ${token}` };

  let mediaIds = [];
  if (image) {
    const filename = image.mime === "image/jpeg" ? "top5.jpg" : "top5.png";
    const form = new FormData();
    form.append("file", new Blob([image.buffer], { type: image.mime }), filename);
    if (image.alt) form.append("description", image.alt);

    const res = await fetch(`${base}/api/v2/media`, { method: "POST", headers: auth, body: form });
    if (!res.ok) throw new Error(`media upload failed: HTTP ${res.status} ${await safeText(res)}`);

    let media = await res.json();
    // 202 = accepted but still processing; poll until it's ready.
    if (res.status === 202) media = await waitForMedia(base, auth, media.id);
    mediaIds = [media.id];
  }

  const res = await fetch(`${base}/api/v1/statuses`, {
    method: "POST",
    headers: { ...auth, "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({
      status: text,
      media_ids: mediaIds,
      language: "en",
      visibility: "public",
    }),
  });
  if (!res.ok) throw new Error(`status post failed: HTTP ${res.status} ${await safeText(res)}`);

  const data = await res.json();
  return { url: data.url, id: data.id };
}

// Poll a media attachment until processing finishes (200) or we give up.
async function waitForMedia(base, auth, id, { tries = 30, delayMs = 1000 } = {}) {
  for (let i = 0; i < tries; i++) {
    await new Promise(r => setTimeout(r, delayMs));
    const res = await fetch(`${base}/api/v1/media/${id}`, { headers: auth });
    if (res.status === 200) return res.json();         // ready
    if (res.status === 206) continue;                  // still processing
    throw new Error(`media processing failed: HTTP ${res.status}`);
  }
  throw new Error("media processing timed out");
}
