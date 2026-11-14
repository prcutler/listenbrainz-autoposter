"""Draws the 1200×1200 top-5 album card with Pillow (no browser needed).

This is a direct port of the old HTML/CSS card: same colours, fonts, sizes
and spacing. Everything is drawn at 2× and downscaled, which gives smooth
anti-aliased edges on the rounded corners and gradients.

Bluesky caps image blobs at 1,000,000 bytes, so if the PNG is too large it
is re-encoded as JPEG.
"""

import io
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .http import request

SIZE = 1200
S = 2                       # supersampling factor
MAX_BYTES = 976_000         # safely under Bluesky's 1 MB blob limit
FONTS = Path(__file__).parent / "fonts"

# Palette (from the original CSS custom properties)
CARD_BG = (31, 24, 42)
INK = (244, 238, 230)
INK_SOFT = (185, 174, 160)
INK_FAINT = (119, 110, 132)
ACCENT = (255, 174, 92)
ACCENT_2 = (255, 111, 145)
EDGE = (255, 255, 255, 15)  # rgba(255,255,255,.06)

PAD_X, PAD_Y = 96, 90
ART = 108


# ── fonts ────────────────────────────────────────────────────────────────

_font_cache = {}


def _font(family, size, weight=400):
    key = (family, size, weight)
    if key in _font_cache:
        return _font_cache[key]
    px = size * S
    if family == "mono":
        f = ImageFont.truetype(str(FONTS / ("DMMono-Medium.ttf" if weight >= 500
                                            else "DMMono-Regular.ttf")), px)
    elif family == "serif":
        f = ImageFont.truetype(str(FONTS / "Fraunces.ttf"), px)
        # Axes: opsz, wght, SOFT, WONK. Browsers set opsz = font size.
        f.set_variation_by_axes([min(max(size, 9), 144), weight, 0, 1])
    else:
        f = ImageFont.truetype(str(FONTS / "HankenGrotesk.ttf"), px)
        f.set_variation_by_axes([weight])
    _font_cache[key] = f
    return f


def _line_height(font, factor=None):
    """CSS line box height (in 2× px). factor=None means `line-height: normal`."""
    ascent, descent = font.getmetrics()
    return (ascent + descent) if factor is None else font.size * factor


def _baseline(font, top, box_h):
    """Baseline y for text whose line box starts at `top` with height `box_h`."""
    ascent, descent = font.getmetrics()
    return top + (box_h - (ascent + descent)) / 2 + ascent


def _spaced_width(text, font, spacing):
    return sum(font.getlength(ch) + spacing for ch in text)


def _draw_spaced(draw, xy, text, font, fill, spacing):
    """Text with CSS-style letter-spacing (added after every character)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += font.getlength(ch) + spacing


def _ellipsize(text, font, max_w):
    if font.getlength(text) <= max_w:
        return text
    while text and font.getlength(text.rstrip() + "…") > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


# ── shapes & gradients ───────────────────────────────────────────────────

def _glow(color, alpha, center, radii, fade_at, size):
    """CSS radial-gradient(rx ry at cx cy, rgba(color,alpha), transparent fade_at)."""
    lo = 240  # compute a small alpha map, then upscale (it's a soft gradient)
    cx, cy = center[0] * lo, center[1] * lo
    rx, ry = radii[0] * lo, radii[1] * lo
    mask = Image.new("L", (lo, lo))
    px = mask.load()
    for y in range(lo):
        for x in range(lo):
            d = math.hypot((x + 0.5 - cx) / rx, (y + 0.5 - cy) / ry)
            px[x, y] = round(255 * alpha * max(0.0, 1 - d / fade_at))
    layer = Image.new("RGBA", (size, size), color + (0,))
    layer.putalpha(mask.resize((size, size), Image.BICUBIC))
    return layer


def _vertical_gradient(w, h, top, bottom):
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        grad.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return grad.resize((w, h))


def _diagonal_gradient(w, h, start, end):
    """CSS linear-gradient(135deg, start, end) for a square box."""
    small = 64
    img = Image.new("RGB", (small, small))
    for y in range(small):
        for x in range(small):
            t = (x + y) / (2 * (small - 1))
            img.putpixel((x, y), tuple(round(a + (b - a) * t) for a, b in zip(start, end)))
    return img.resize((w, h), Image.BICUBIC)


def _rounded_mask(w, h, r):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255)
    return m


def _draw_note(draw, box, fill):
    """Simple ♪ glyph (the card fonts don't include U+266A)."""
    x0, y0, x1, y1 = box
    w = x1 - x0
    head_w, head_h = w * 0.22, w * 0.16
    hx, hy = x0 + w * 0.36, y0 + w * 0.62
    draw.ellipse((hx - head_w / 2, hy - head_h / 2, hx + head_w / 2, hy + head_h / 2), fill=fill)
    stem_x = hx + head_w / 2 - S * 2
    draw.rectangle((stem_x, y0 + w * 0.30, stem_x + S * 2.5, hy), fill=fill)
    draw.polygon([(stem_x, y0 + w * 0.30), (stem_x + w * 0.18, y0 + w * 0.40),
                  (stem_x + w * 0.18, y0 + w * 0.46), (stem_x, y0 + w * 0.37)], fill=fill)


# ── cover art ────────────────────────────────────────────────────────────

def _fetch_cover(url):
    if not url:
        return None
    try:
        _, data = request(url, timeout=20)
        img = Image.open(io.BytesIO(data)).convert("RGB")
        return ImageOps.fit(img, (ART * S, ART * S), Image.LANCZOS)
    except Exception:
        return None


# ── the card ─────────────────────────────────────────────────────────────

def render_card(albums, range_label, username):
    """Return a 1200×1200 RGB PIL image."""
    W = SIZE * S
    with ThreadPoolExecutor(max_workers=5) as pool:
        covers = list(pool.map(_fetch_cover, [a.get("cover") for a in albums]))

    img = Image.new("RGBA", (W, W), CARD_BG + (255,))
    # Second CSS background layer sits under the first.
    img.alpha_composite(_glow(ACCENT_2, 0.13, (0.92, 1.0), (0.45, 0.40), 0.72, W))
    img.alpha_composite(_glow(ACCENT, 0.18, (0.12, 0.0), (0.55, 0.45), 0.70, W))

    overlay = Image.new("RGBA", (W, W), (0, 0, 0, 0))   # translucent rules
    draw = ImageDraw.Draw(img)
    odraw = ImageDraw.Draw(overlay)

    left, right = PAD_X * S, (SIZE - PAD_X) * S
    top, bottom = PAD_Y * S, (SIZE - PAD_Y) * S

    # Header: equaliser bars · title · range
    title_f = _font("mono", 24)
    range_f = _font("mono", 22)
    eq_h = 26 * S
    header_h = max(eq_h, _line_height(title_f), _line_height(range_f))
    eq_top = top + (header_h - eq_h) / 2
    x = left
    for frac in (0.40, 1.00, 0.60, 0.85, 0.50):
        bh = round(eq_h * frac)
        bar = _vertical_gradient(5 * S, bh, ACCENT, ACCENT_2)
        img.paste(bar, (round(x), round(eq_top + eq_h - bh)), _rounded_mask(5 * S, bh, 3 * S))
        x += 10 * S
    x += -5 * S + 20 * S  # last bar has no trailing gap; then header gap
    _draw_spaced(draw, (x, _baseline(title_f, top, header_h)),
                 "TOP 5 ALBUMS · LAST MONTH", title_f, ACCENT, 0.22 * 24 * S)
    if range_label:
        sp = 0.12 * 22 * S
        text = range_label.upper()
        _draw_spaced(draw, (right - _spaced_width(text, range_f, sp),
                            _baseline(range_f, top, header_h)), text, range_f, INK_FAINT, sp)

    # Rows
    rank_f = _font("serif", 60, 600)
    album_f = _font("serif", 40, 600)
    artist_f = _font("sans", 27, 500)
    count_f = _font("serif", 46, 600)
    plays_f = _font("mono", 18)
    plays_sp = 0.08 * 18 * S

    album_h = _line_height(album_f, 1.1)
    artist_h = _line_height(artist_f)
    meta_h = album_h + 6 * S + artist_h
    count_h = _line_height(count_f) + 2 * S + _line_height(plays_f)
    content_h = max(_line_height(rank_f), ART * S, meta_h, count_h)
    row_h = content_h + 44 * S

    y = top + header_h + 54 * S
    for i, (album, cover) in enumerate(zip(albums, covers)):
        cy = y + 22 * S                      # content top
        mid = cy + content_h / 2

        # rank
        rank_h = _line_height(rank_f)
        draw.text((left, _baseline(rank_f, mid - rank_h / 2, rank_h)),
                  f"{i + 1:02d}", font=rank_f, fill=ACCENT, anchor="ls")

        # cover art (or placeholder)
        ax, ay = left + 96 * S + 30 * S, round(mid - ART * S / 2)
        mask = _rounded_mask(ART * S, ART * S, 14 * S)
        if cover is not None:
            img.paste(cover, (ax, ay), mask)
        else:
            img.paste(_diagonal_gradient(ART * S, ART * S, (42, 35, 51), (26, 22, 34)),
                      (ax, ay), mask)
            _draw_note(draw, (ax, ay, ax + ART * S, ay + ART * S), INK_FAINT)

        # play count (right column)
        plays = str(album["plays"])
        count_w = max(count_f.getlength(plays), _spaced_width("PLAYS", plays_f, plays_sp))
        ctop = mid - count_h / 2
        num_h = _line_height(count_f)
        draw.text((right, _baseline(count_f, ctop, num_h)), plays,
                  font=count_f, fill=INK, anchor="rs")
        _draw_spaced(draw, (right - _spaced_width("PLAYS", plays_f, plays_sp),
                            _baseline(plays_f, ctop + num_h + 2 * S, _line_height(plays_f))),
                     "PLAYS", plays_f, INK_FAINT, plays_sp)

        # album + artist
        mx = ax + ART * S + 30 * S
        max_w = right - count_w - 30 * S - mx
        mtop = mid - meta_h / 2
        draw.text((mx, _baseline(album_f, mtop, album_h)),
                  _ellipsize(album["album"], album_f, max_w), font=album_f, fill=INK, anchor="ls")
        draw.text((mx, _baseline(artist_f, mtop + album_h + 6 * S, artist_h)),
                  _ellipsize(album["artist"], artist_f, max_w),
                  font=artist_f, fill=INK_SOFT, anchor="ls")

        y += row_h
        if i < len(albums) - 1:
            odraw.rectangle((left, y, right - 1, y + S - 1), fill=EDGE)
            y += S + 6 * S

    # Footer (pinned to the bottom)
    foot_f = _font("mono", 22)
    brand_f = _font("mono", 22, 500)
    foot_sp = 0.06 * 22 * S
    foot_h = _line_height(foot_f)
    foot_top = bottom - foot_h
    odraw.rectangle((left, foot_top - 30 * S - S, right - 1, foot_top - 30 * S - 1), fill=EDGE)
    base = _baseline(foot_f, foot_top, foot_h)
    _draw_spaced(draw, (left, base), username, foot_f, INK_FAINT, foot_sp)
    brand_w = _spaced_width("ListenBrainz", brand_f, foot_sp)
    via_w = _spaced_width("via ", foot_f, foot_sp)
    _draw_spaced(draw, (right - brand_w - via_w, base), "via ", foot_f, INK_FAINT, foot_sp)
    _draw_spaced(draw, (right - brand_w, base), "ListenBrainz", brand_f, INK_SOFT, foot_sp)

    img.alpha_composite(overlay)
    return img.convert("RGB").resize((SIZE, SIZE), Image.LANCZOS)


def render_image(albums, range_label, username):
    """Return {"data": bytes, "mime", "width", "height"}, under Bluesky's size cap."""
    card = render_card(albums, range_label, username)
    buf = io.BytesIO()
    card.save(buf, "PNG", optimize=True)
    mime = "image/png"
    if buf.tell() > MAX_BYTES:
        buf = io.BytesIO()
        card.save(buf, "JPEG", quality=88, optimize=True)
        mime = "image/jpeg"
    return {"data": buf.getvalue(), "mime": mime, "width": SIZE, "height": SIZE}
