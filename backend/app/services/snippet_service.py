"""Build a client-safe PNG snippet of one 'Seen by AI' response.

Text is verbatim except competitor names, which are redacted to '[a competitor]'
so a client-facing card never advertises a rival. No LLM is used.
"""
import re
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_MAX_EXCERPT_CHARS = 280
_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _redact(text: str, competitors: list[str]) -> str:
    for name in sorted([c for c in competitors if c], key=len, reverse=True):
        text = re.sub(re.escape(name), "[a competitor]", text, flags=re.IGNORECASE)
    return text


def _brand_pattern(brand: str) -> re.Pattern:
    """Whole-word, case-insensitive matcher so a short brand ('Ace') doesn't
    match inside a larger word ('Acme') and produce a misattributed card."""
    return re.compile(rf"\b{re.escape(brand)}\b", re.IGNORECASE)


def build_excerpt(response_text: str, brand: str, competitors: list[str]) -> str | None:
    """Return the sentence containing the brand (redacted, truncated), or None."""
    if not response_text:
        return None
    pattern = _brand_pattern(brand)
    if not pattern.search(response_text):
        return None
    sentences = re.split(r"(?<=[.!?])\s+", response_text.strip())
    chosen = next((s for s in sentences if pattern.search(s)), None)
    if chosen is None:
        return None
    chosen = _redact(chosen.strip(), competitors)
    if len(chosen) > _MAX_EXCERPT_CHARS:
        chosen = chosen[: _MAX_EXCERPT_CHARS - 1].rstrip() + "…"
    return chosen


_W, _H = 1200, 630
_BG = (15, 23, 42)
_FG = (241, 245, 249)
_ACCENT = (74, 222, 128)


def _font(name: str, size: int):
    path = _FONT_DIR / name
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_width):
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:  # avoid a blank leading line when the first word overflows
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


# Body text must stop above the watermark so the "Tracked by SeenBy" attribution
# is never occluded on a long (max-length) excerpt.
_BODY_TOP = 240
_LINE_HEIGHT = 56
_WATERMARK_Y = _H - 80
_BODY_MAX_Y = _WATERMARK_Y - 40


def render_snippet_png(platform_label: str, brand: str, excerpt: str) -> bytes:
    img = Image.new("RGB", (_W, _H), _BG)
    draw = ImageDraw.Draw(img)

    draw.text((80, 70), "SEEN BY AI", font=_font("Inter-Bold.ttf", 34), fill=_ACCENT)
    draw.text((80, 120), f"What {platform_label} said about {brand}", font=_font("Inter-Bold.ttf", 48), fill=_FG)

    body = _font("Inter-Regular.ttf", 40)
    y = _BODY_TOP
    for line in _wrap(draw, f"“{excerpt}”", body, _W - 160):
        if y + _LINE_HEIGHT > _BODY_MAX_Y:
            break  # don't draw over the watermark
        draw.text((80, y), line, font=body, fill=_FG)
        y += _LINE_HEIGHT

    draw.text((80, _WATERMARK_Y), "Tracked by SeenBy", font=_font("Inter-Regular.ttf", 28), fill=(148, 163, 184))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
