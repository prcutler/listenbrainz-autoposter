// ─────────────────────────────────────────────────────────────────────────
// Builds the 1200×1200 HTML card that gets screenshotted into the post image.
// Rendered by real headless Chromium (Playwright), so gradients, web fonts and
// cross-origin cover art all "just work" — no html-to-image workarounds needed.
// ─────────────────────────────────────────────────────────────────────────

const esc = s => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

export function buildHtml({ albums, rangeLabel, username }) {
  const rows = albums.map((a, i) => {
    const rank = String(i + 1).padStart(2, "0");
    const img = a.cover
      ? `<img src="${esc(a.cover)}" alt="" onerror="this.remove()">`
      : "";
    return `
      <div class="row">
        <div class="rank">${rank}</div>
        <div class="art"><span class="art-fallback">&#9834;</span>${img}</div>
        <div class="meta">
          <div class="album">${esc(a.album)}</div>
          <div class="artist">${esc(a.artist)}</div>
        </div>
        <div class="count"><strong>${esc(a.plays)}</strong><span>plays</span></div>
      </div>`;
  }).join("");

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Fraunces:ital,opsz,wght@0,9..144,500;0,9..144,600&family=Hanken+Grotesk:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root{
    --card-bg:#1f182a; --ink:#f4eee6; --ink-soft:#b9aea0; --ink-faint:#776e84;
    --accent:#ffae5c; --accent-2:#ff6f91; --edge:rgba(255,255,255,.06);
  }
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:1200px;height:1200px}
  body{font-family:"Hanken Grotesk",sans-serif}

  #card{
    width:1200px;height:1200px;overflow:hidden;position:relative;
    padding:90px 96px;display:flex;flex-direction:column;
    background:
      radial-gradient(55% 45% at 12% 0%, rgba(255,174,92,.18), rgba(31,24,42,0) 70%),
      radial-gradient(45% 40% at 92% 100%, rgba(255,111,145,.13), rgba(31,24,42,0) 72%),
      var(--card-bg);
    color:var(--ink);
  }

  .header{display:flex;align-items:center;gap:20px;margin-bottom:54px}
  .eq{display:inline-flex;align-items:flex-end;gap:5px;height:26px}
  .eq span{width:5px;border-radius:3px;background:linear-gradient(var(--accent),var(--accent-2))}
  .eq span:nth-child(1){height:40%}.eq span:nth-child(2){height:100%}
  .eq span:nth-child(3){height:60%}.eq span:nth-child(4){height:85%}
  .eq span:nth-child(5){height:50%}
  .title{font-family:"DM Mono",monospace;font-size:24px;letter-spacing:.22em;
    text-transform:uppercase;color:var(--accent)}
  .range{margin-left:auto;font-family:"DM Mono",monospace;font-size:22px;
    letter-spacing:.12em;text-transform:uppercase;color:var(--ink-faint)}

  .list{display:flex;flex-direction:column;gap:6px;flex:1}
  .row{display:flex;align-items:center;gap:30px;padding:22px 0;
    border-bottom:1px solid var(--edge)}
  .row:last-child{border-bottom:none}
  .rank{font-family:"Fraunces",serif;font-weight:600;font-size:60px;
    color:var(--accent);width:96px;flex-shrink:0;font-variant-numeric:tabular-nums}
  .art{position:relative;width:108px;height:108px;border-radius:14px;flex-shrink:0;
    overflow:hidden;background:linear-gradient(135deg,#2a2333,#1a1622)}
  .art img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
  .art-fallback{position:absolute;inset:0;display:flex;align-items:center;
    justify-content:center;font-size:44px;color:var(--ink-faint)}
  .meta{min-width:0;flex:1}
  .album{font-family:"Fraunces",serif;font-weight:600;font-size:40px;line-height:1.1;
    color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .artist{font-size:27px;font-weight:500;color:var(--ink-soft);margin-top:6px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .count{text-align:right;flex-shrink:0;display:flex;flex-direction:column;align-items:flex-end}
  .count strong{font-family:"Fraunces",serif;font-weight:600;font-size:46px;color:var(--ink)}
  .count span{font-family:"DM Mono",monospace;font-size:18px;letter-spacing:.08em;
    text-transform:uppercase;color:var(--ink-faint);margin-top:2px}

  .footer{display:flex;align-items:center;margin-top:48px;padding-top:30px;
    border-top:1px solid var(--edge);font-family:"DM Mono",monospace;font-size:22px;
    letter-spacing:.06em;color:var(--ink-faint)}
  .footer .brand{margin-left:auto}
  .footer .brand b{color:var(--ink-soft);font-weight:500}
</style></head>
<body>
  <div id="card">
    <div class="header">
      <span class="eq"><span></span><span></span><span></span><span></span><span></span></span>
      <span class="title">Top 5 Albums · Last Week</span>
      ${rangeLabel ? `<span class="range">${esc(rangeLabel)}</span>` : ""}
    </div>
    <div class="list">${rows}</div>
    <div class="footer">
      <span>${esc(username)}</span>
      <span class="brand">via <b>ListenBrainz</b></span>
    </div>
  </div>
</body></html>`;
}
