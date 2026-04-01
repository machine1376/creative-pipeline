"""
Resolve gradient / overlay accent colors from product and campaign themes.

Blends keyword-derived hues with the brand primary so creatives stay on-brand
while reflecting each product's character (water vs protein vs coffee, etc.).
"""

from __future__ import annotations

import colorsys
import re
from typing import Optional

# Longer phrases first so "ocean plastic" beats "ocean".
_THEME_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("ocean plastic", "#1a6b7c"),
    ("plant-based", "#2e7d4a"),
    ("mixed berry", "#8e4585"),
    ("ocean", "#1e88a8"),
    ("marine", "#1565c0"),
    ("hydration", "#26a69a"),
    ("water", "#1e88a8"),
    ("aqua", "#00838f"),
    ("blue", "#1976d2"),
    ("eco", "#2e7d32"),
    ("sustainable", "#388e3c"),
    ("organic", "#43a047"),
    ("forest", "#2e7d32"),
    ("green", "#388e3c"),
    ("protein", "#c67b4e"),
    ("vanilla", "#d4b896"),
    ("chocolate", "#5d4037"),
    ("berry", "#8e4585"),
    ("cocoa", "#6d4c41"),
    ("coffee", "#5d4037"),
    ("espresso", "#4e342e"),
    ("energy", "#ef6c00"),
    ("sun", "#f9a825"),
    ("citrus", "#f57f17"),
    ("outdoor", "#558b2f"),
    ("summer", "#f9a825"),
    ("skincare", "#c48b9f"),
    ("luxury", "#8d6e63"),
    ("cream", "#d7ccc8"),
    ("night", "#3949ab"),
    ("clean", "#78909c"),
)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip("#")
    if len(h) != 6 or not re.fullmatch(r"[0-9a-fA-F]+", h):
        raise ValueError(f"Invalid hex color: {hex_color!r}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _blend_hex(a: str, b: str, weight_b: float) -> str:
    """Linear blend in RGB; weight_b is how much of `b` to use (0..1)."""
    t = max(0.0, min(1.0, weight_b))
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    return _rgb_to_hex(
        int(ar * (1 - t) + br * t),
        int(ag * (1 - t) + bg * t),
        int(ab * (1 - t) + bb * t),
    )


def _fallback_accent(brand_primary: str, product_id: str) -> str:
    """Stable, distinct accent per product when no theme keyword matches."""
    h = hash(product_id) & 0xFFFFFFFF
    hue = (h % 360) / 360.0
    r_f, g_f, b_f = colorsys.hls_to_rgb(hue, 0.48, 0.52)
    wild = _rgb_to_hex(int(r_f * 255), int(g_f * 255), int(b_f * 255))
    return _blend_hex(brand_primary, wild, 0.38)


def _keyword_accent(text: str) -> Optional[str]:
    lower = text.lower()
    # Prefer longer / more specific keywords
    for keyword, hex_color in sorted(_THEME_KEYWORDS, key=lambda x: -len(x[0])):
        if keyword in lower:
            return hex_color
    return None


def resolve_product_theme_color(
    *,
    brand_primary: str,
    product_id: str,
    product_name: str,
    product_description: str,
    tagline: Optional[str],
    product_theme: Optional[str],
    campaign_theme: Optional[str],
    theme_color_override: Optional[str],
    theme_blend: float = 0.58,
) -> str:
    """
    Return a hex color for gradients/overlays for this product.

    Priority:
      1. Explicit ``theme_color_override`` from the brief (validated hex).
      2. Keyword match from combined theme text, blended with ``brand_primary``.
      3. Stable hue derived from ``product_id``, blended with ``brand_primary``.

    ``theme_blend`` controls how much the product theme contributes vs brand
    (0 = all brand primary, 1 = full theme keyword color).
    """
    if theme_color_override:
        try:
            rgb = _hex_to_rgb(theme_color_override)
            # Still blend slightly with brand so it never fully departs from identity
            return _blend_hex(brand_primary, _rgb_to_hex(*rgb), theme_blend)
        except ValueError:
            pass

    # Product-level text first so "summer sun" on the campaign doesn't override
    # a water bottle's aqua/ocean cues from the description.
    product_blob = " ".join(
        part
        for part in (
            product_name,
            product_description,
            tagline or "",
            product_theme or "",
        )
        if part
    )
    matched = _keyword_accent(product_blob)
    if matched:
        return _blend_hex(brand_primary, matched, theme_blend)

    if campaign_theme:
        matched = _keyword_accent(campaign_theme)
        if matched:
            return _blend_hex(brand_primary, matched, theme_blend)

    return _fallback_accent(brand_primary, product_id)
