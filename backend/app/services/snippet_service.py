"""Build a client-safe PNG snippet of one 'Seen by AI' response.

Text is verbatim except competitor names, which are redacted to '[a competitor]'
so a client-facing card never advertises a rival. No LLM is used.
"""
import re
from io import BytesIO
from pathlib import Path

_MAX_EXCERPT_CHARS = 280
_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _redact(text: str, competitors: list[str]) -> str:
    for name in sorted([c for c in competitors if c], key=len, reverse=True):
        text = re.sub(re.escape(name), "[a competitor]", text, flags=re.IGNORECASE)
    return text


def build_excerpt(response_text: str, brand: str, competitors: list[str]) -> str | None:
    """Return the sentence containing the brand (redacted, truncated), or None."""
    if not response_text or brand.lower() not in response_text.lower():
        return None
    sentences = re.split(r"(?<=[.!?])\s+", response_text.strip())
    chosen = next((s for s in sentences if brand.lower() in s.lower()), None)
    if chosen is None:
        return None
    chosen = _redact(chosen.strip(), competitors)
    if len(chosen) > _MAX_EXCERPT_CHARS:
        chosen = chosen[: _MAX_EXCERPT_CHARS - 1].rstrip() + "…"
    return chosen


from PIL import Image, ImageDraw, ImageFont

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
            lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def render_snippet_png(platform_label: str, brand: str, excerpt: str) -> bytes:
    img = Image.new("RGB", (_W, _H), _BG)
    draw = ImageDraw.Draw(img)

    draw.text((80, 70), "SEEN BY AI", font=_font("Inter-Bold.ttf", 34), fill=_ACCENT)
    draw.text((80, 120), f"What {platform_label} said about {brand}", font=_font("Inter-Bold.ttf", 48), fill=_FG)

    body = _font("Inter-Regular.ttf", 40)
    y = 240
    for line in _wrap(draw, f"“{excerpt}”", body, _W - 160):
        draw.text((80, y), line, font=body, fill=_FG)
        y += 56

    draw.text((80, _H - 80), "Tracked by SeenBy", font=_font("Inter-Regular.ttf", 28), fill=(148, 163, 184))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
