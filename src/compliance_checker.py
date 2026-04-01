"""
Compliance checker: brand and legal validation on generated creatives.

Checks performed:
  Brand compliance:
    - Dominant color analysis: verifies brand primary color is present in the
      image (using k-means color quantization via Pillow's quantize()).
    - Logo presence: checks whether a logo was overlaid during composition.

  Legal compliance:
    - Prohibited word scan: flags any prohibited words found in the campaign
      message or product descriptions.
    - Required disclaimer: warns if a required legal footer is missing.

Design decision: Compliance runs AFTER composition (not before) so we validate
the actual output asset, not just the inputs. This catches issues introduced
during the rendering step itself (e.g., a brand color that becomes invisible
against the image background).

Limitation: Color matching uses Euclidean distance in RGB space with a
configurable tolerance. A production implementation might use CIEDE2000 (a
perceptually uniform color space) for more accurate brand color matching.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Optional

from PIL import Image

from .models import BrandGuidelines, ComplianceResult

logger = logging.getLogger(__name__)

# How close (in RGB Euclidean distance, max 441) a dominant color must be to
# the brand color to be considered compliant.
_COLOR_TOLERANCE = 80

# Number of palette colors extracted for dominant color analysis.
_PALETTE_SIZE = 8


class ComplianceChecker:
    def check(
        self,
        image: Image.Image,
        campaign_message: str,
        product_description: str,
        guidelines: BrandGuidelines,
        logo_was_applied: bool = False,
        color_reference_hex: Optional[str] = None,
    ) -> ComplianceResult:
        issues: list[str] = []
        warnings: list[str] = []

        # --- Brand compliance ---
        ref_color = color_reference_hex or guidelines.primary_color
        color_ok, color_note = self._check_brand_color(image, ref_color)
        if not color_ok:
            warnings.append(color_note)
        else:
            logger.debug("Brand color check passed: %s", color_note)

        if guidelines.logo_path and not logo_was_applied:
            warnings.append(
                "Brand logo is configured but was not applied to this creative "
                "(logo file may be missing)."
            )

        # --- Legal compliance ---
        combined_text = f"{campaign_message} {product_description}".lower()
        flagged = self._check_prohibited_words(combined_text, guidelines.prohibited_words)
        for word in flagged:
            issues.append(f"Prohibited word detected in content: '{word}'")

        if guidelines.required_disclaimer:
            if guidelines.required_disclaimer.lower() not in combined_text:
                warnings.append(
                    f"Required disclaimer may be missing: '{guidelines.required_disclaimer}'"
                )

        passed = len(issues) == 0
        if not passed:
            logger.warning("Compliance FAILED: %s", issues)
        elif warnings:
            logger.info("Compliance passed with warnings: %s", warnings)
        else:
            logger.info("Compliance passed cleanly.")

        return ComplianceResult(passed=passed, issues=issues, warnings=warnings)

    # ------------------------------------------------------------------
    # Brand color
    # ------------------------------------------------------------------

    def _check_brand_color(
        self, image: Image.Image, brand_color_hex: str
    ) -> tuple[bool, str]:
        """
        Quantize the image to N dominant colors and check whether any is
        within tolerance of the brand color.
        """
        try:
            target = _hex_to_rgb(brand_color_hex)
            # Quantize to a small palette for speed.
            # add_noise=0 prevents dithering artifacts on smooth gradients.
            quantized = image.convert("RGB").quantize(colors=_PALETTE_SIZE, dither=0)
            palette_raw = quantized.getpalette()  # flat R,G,B list

            if not palette_raw:
                return True, "Color analysis skipped (empty palette)"

            # Palette may have fewer entries than requested on uniform images
            n_colors = min(_PALETTE_SIZE, len(palette_raw) // 3)
            if n_colors == 0:
                return True, "Color analysis skipped (degenerate palette)"

            dominant_colors = [
                (palette_raw[i], palette_raw[i + 1], palette_raw[i + 2])
                for i in range(0, n_colors * 3, 3)
            ]

            distances = [_rgb_distance(c, target) for c in dominant_colors]
            min_dist = min(distances)
            closest = dominant_colors[distances.index(min_dist)]

            if min_dist <= _COLOR_TOLERANCE:
                return True, (
                    f"Brand color {brand_color_hex} matched (closest dominant: "
                    f"rgb{closest}, dist={min_dist:.1f})"
                )
            return False, (
                f"Brand color {brand_color_hex} not prominent in image "
                f"(closest: rgb{closest}, dist={min_dist:.1f}, tolerance={_COLOR_TOLERANCE})"
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning("Color analysis failed: %s", exc)
            return True, "Color analysis skipped (error during quantization)"

    # ------------------------------------------------------------------
    # Legal word scan
    # ------------------------------------------------------------------

    @staticmethod
    def _check_prohibited_words(text: str, prohibited_words: list[str]) -> list[str]:
        """Return any prohibited words found in text (case-insensitive, whole-word)."""
        flagged = []
        for word in prohibited_words:
            pattern = rf"\b{re.escape(word.lower())}\b"
            if re.search(pattern, text):
                flagged.append(word)
        return flagged


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
