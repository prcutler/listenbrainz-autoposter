// ─────────────────────────────────────────────────────────────────────────
// Renders the album card to a PNG (or JPEG) buffer using headless Chromium.
//
// Bluesky caps image blobs at 1,000,000 bytes. We screenshot as PNG and, if
// that's too large, fall back to JPEG so the upload always succeeds.
// ─────────────────────────────────────────────────────────────────────────

import { chromium } from "playwright";
import { buildHtml } from "./template.mjs";

const MAX_BYTES = 976_000; // safely under Bluesky's 1MB blob limit

export async function renderImage({ albums, rangeLabel, username }) {
  const html = buildHtml({ albums, rangeLabel, username });

  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({
      viewport: { width: 1200, height: 1200 },
      deviceScaleFactor: 1,
    });

    await page.setContent(html, { waitUntil: "networkidle" });

    // Make sure fonts and all cover images have finished loading.
    await page.evaluate(async () => {
      if (document.fonts && document.fonts.ready) await document.fonts.ready;
      await Promise.all(
        [...document.images].map(img =>
          img.complete ? null : new Promise(res => { img.onload = img.onerror = res; })
        )
      );
    });

    const card = await page.$("#card");

    let buffer = await card.screenshot({ type: "png" });
    let mime = "image/png";
    if (buffer.length > MAX_BYTES) {
      buffer = await card.screenshot({ type: "jpeg", quality: 88 });
      mime = "image/jpeg";
    }

    return { buffer, mime, width: 1200, height: 1200 };
  } finally {
    await browser.close();
  }
}
