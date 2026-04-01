"""
Creative composer: resizes hero images and overlays campaign messaging.

Composition strategy per format:
  - 1:1  (Square):   Bottom-third gradient overlay, text left-aligned.
  - 9:16 (Portrait): Bottom-quarter gradient, larger headline for mobile legibility.
  - 16:9 (Landscape): Left-panel semi-transparent overlay so copy doesn't compete
                       with the product visual on the right.

Design decisions:
  - "Cover" crop (CSS background-size: cover equivalent) fills the canvas without
    letterboxing, matching how real social platforms display images.
  - Gradient overlay is brand-color tinted to tie text background to brand identity
    without obscuring the hero image entirely.
  - Text is wrapped and sized relative to canvas width so it adapts automatically
    to different aspect ratios without hardcoded pixel offsets.
  - Copy uses a blurred dark halo (stroke on an RGBA layer + GaussianBlur) under
    sharp white fills for legibility without a crisp outline.
  - Logo placement is top-right with padding proportional to canvas width, which
    keeps it consistent across formats.
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .models import AspectRatio, ASPECT_RATIOS

logger = logging.getLogger(__name__)


class CreativeComposer:
    # Font size as a fraction of canvas width
    _HEADLINE_SCALE = 0.055
    _BODY_SCALE = 0.030
    # Soft halo behind text: stroke drawn on a layer, then blurred
    _TEXT_HALO_BLUR_RADIUS = 1.85
    _TEXT_HALO_STROKE_SCALE = 1.4

    def compose(
        self,
        hero_image: Image.Image,
        message: str,
        product_name: str,
        aspect_ratio: AspectRatio,
        brand_color: str = "#1a73e8",
        tagline: Optional[str] = None,
        logo: Optional[Image.Image] = None,
    ) -> Image.Image:
        """
        Produce a final campaign creative at the target aspect ratio.

        Steps:
          1. Cover-crop hero to canvas dimensions.
          2. Apply brand-tinted gradient overlay.
          3. Render product name + campaign message.
          4. Optionally place logo.
        """
        # Step 1 – fit hero to canvas
        canvas = self._cover_crop(hero_image, aspect_ratio.size)

        # Step 2 – gradient overlay
        canvas = self._add_gradient(canvas, aspect_ratio.key, brand_color)

        # Step 3 – text
        canvas = self._render_text(canvas, product_name, message, tagline, aspect_ratio)

        # Step 4 – logo
        if logo:
            canvas = self._place_logo(canvas, logo)

        return canvas

    # ------------------------------------------------------------------
    # Cover crop
    # ------------------------------------------------------------------

    def _cover_crop(self, image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
        """
        Scale image to fill target_size (no letterboxing) then center-crop.
        Equivalent to CSS `object-fit: cover`.
        """
        tw, th = target_size
        sw, sh = image.size

        scale = max(tw / sw, th / sh)
        nw, nh = int(sw * scale), int(sh * scale)
        resized = image.resize((nw, nh), Image.LANCZOS)

        left = (nw - tw) // 2
        top = (nh - th) // 2
        return resized.crop((left, top, left + tw, top + th))

    # ------------------------------------------------------------------
    # Gradient overlay
    # ------------------------------------------------------------------

    def _add_gradient(
        self, image: Image.Image, ratio_key: str, brand_color: str
    ) -> Image.Image:
        """
        Add a semi-transparent gradient tinted with the brand color.
        Landscape format gets a left-side panel; all others get a bottom gradient.
        """
        w, h = image.size
        r, g, b = _hex_to_rgb(brand_color)
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if ratio_key == "16:9":
            # Left-panel gradient (40% of width)
            panel_w = int(w * 0.42)
            for x in range(panel_w):
                alpha = int(218 * (1 - x / panel_w))
                draw.line([(x, 0), (x, h)], fill=(r, g, b, alpha))
        else:
            # Bottom gradient (covers bottom ~48%)
            start_y = int(h * 0.52)
            for y in range(start_y, h):
                alpha = int(222 * (y - start_y) / (h - start_y))
                draw.line([(0, y), (w, y)], fill=(r, g, b, alpha))

        composite = Image.alpha_composite(image.convert("RGBA"), overlay)
        composite = self._add_dark_readability_scrim(composite, ratio_key)
        return composite.convert("RGB")

    def _add_dark_readability_scrim(self, rgba_image: Image.Image, ratio_key: str) -> Image.Image:
        """Add a neutral dark layer so white text stays legible on busy heroes."""
        w, h = rgba_image.size
        dark = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dark)

        if ratio_key == "16:9":
            panel_w = int(w * 0.46)
            for x in range(panel_w):
                a = int(52 * (1.0 - x / max(panel_w, 1)) ** 0.9)
                dd.line([(x, 0), (x, h)], fill=(0, 0, 0, a))
        else:
            start_y = int(h * 0.50)
            for y in range(start_y, h):
                t = (y - start_y) / max(h - start_y, 1)
                a = int(72 * (t**1.12))
                dd.line([(0, y), (w, y)], fill=(0, 0, 0, min(a, 78)))

        return Image.alpha_composite(rgba_image, dark)

    # ------------------------------------------------------------------
    # Text rendering
    # ------------------------------------------------------------------

    def _render_text(
        self,
        image: Image.Image,
        product_name: str,
        message: str,
        tagline: Optional[str],
        aspect_ratio: AspectRatio,
    ) -> Image.Image:
        w, h = image.size

        headline_size = max(28, int(w * self._HEADLINE_SCALE))
        body_size = max(18, int(w * self._BODY_SCALE))

        headline_font = _load_font(headline_size, bold=True)
        body_font = _load_font(body_size, bold=False)

        padding = int(w * 0.06)

        if aspect_ratio.key == "16:9":
            x = padding
            y0 = int(h * 0.25)
            max_chars = 18
        else:
            x = padding
            y0 = int(h * 0.57)
            max_chars = 22 if aspect_ratio.key == "9:16" else 20

        sw_body = max(1, min(3, body_size // 10))
        sw_head = max(1, min(4, headline_size // 14))

        base = image.convert("RGBA")
        halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dh = ImageDraw.Draw(halo)
        y = y0

        # Pass 1 — dark strokes on halo layer (blurred next)
        _draw_stroke_for_blur(
            dh,
            (x, y),
            product_name.upper(),
            body_font,
            max(2, int(sw_body * self._TEXT_HALO_STROKE_SCALE)),
        )
        y += body_size + int(body_size * 0.5)

        for line in textwrap.wrap(message, width=max_chars):
            _draw_stroke_for_blur(
                dh,
                (x, y),
                line,
                headline_font,
                max(2, int(sw_head * self._TEXT_HALO_STROKE_SCALE)),
            )
            y += headline_size + int(headline_size * 0.15)

        if tagline:
            y += int(body_size * 0.4)
            _draw_stroke_for_blur(
                dh,
                (x, y),
                tagline,
                body_font,
                max(2, int(sw_body * self._TEXT_HALO_STROKE_SCALE)),
            )

        halo = halo.filter(ImageFilter.GaussianBlur(radius=self._TEXT_HALO_BLUR_RADIUS))
        composed = Image.alpha_composite(base, halo)
        draw = ImageDraw.Draw(composed)

        # Pass 2 — sharp fills (no hard stroke)
        y = y0
        draw.text((x, y), product_name.upper(), font=body_font, fill=(255, 255, 255))
        y += body_size + int(body_size * 0.5)

        for line in textwrap.wrap(message, width=max_chars):
            draw.text((x, y), line, font=headline_font, fill=(255, 255, 255))
            y += headline_size + int(headline_size * 0.15)

        if tagline:
            y += int(body_size * 0.4)
            draw.text((x, y), tagline, font=body_font, fill=(245, 248, 255))

        return composed.convert("RGB")

    # ------------------------------------------------------------------
    # Logo placement
    # ------------------------------------------------------------------

    def _place_logo(self, image: Image.Image, logo: Image.Image) -> Image.Image:
        """Place brand logo in the top-right corner, sized to ~8% of canvas width."""
        w, h = image.size
        padding = int(w * 0.04)
        logo_w = int(w * 0.08)
        scale = logo_w / logo.width
        logo_h = int(logo.height * scale)
        logo_r = logo.resize((logo_w, logo_h), Image.LANCZOS)

        x, y = w - logo_w - padding, padding

        if logo_r.mode == "RGBA":
            base = image.convert("RGBA")
            base.paste(logo_r, (x, y), logo_r)
            return base.convert("RGB")
        image.paste(logo_r, (x, y))
        return image


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_FONT_CACHE: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}

_SYSTEM_FONTS_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
]
_SYSTEM_FONTS_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arial.ttf",
]


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    candidates = _SYSTEM_FONTS_BOLD if bold else _SYSTEM_FONTS_REGULAR
    for path in candidates:
        if Path(path).exists():
            try:
                font = ImageFont.truetype(path, size)
                _FONT_CACHE[key] = font
                return font
            except Exception:  # noqa: BLE001
                continue

    logger.warning("No TrueType font found at size %d — using default bitmap font.", size)
    return ImageFont.load_default()


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _draw_stroke_for_blur(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    stroke_width: int,
) -> None:
    """
    Draw only the glyph outline on an RGBA layer; inner fill stays transparent
    so GaussianBlur produces a soft halo (no crisp ring).
    """
    draw.text(
        xy,
        text,
        font=font,
        fill=(0, 0, 0, 0),
        stroke_width=stroke_width,
        stroke_fill=(18, 18, 22, 235),
    )
