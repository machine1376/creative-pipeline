"""
Prompt engineering for hero image generation.

Design decision: Prompt construction is isolated in its own module so it can
be unit-tested, iterated on, and swapped without touching the generation logic.
This is especially important for image gen where prompt quality directly
determines output quality.

Key strategies applied:
  - Negative framing ("no text, no logos") prevents DALL-E from hallucinating
    typography that conflicts with our composition step.
  - Regional context anchors the visual aesthetic to the target market.
  - Style anchors produce consistent, ad-quality outputs across products.
  - Audience framing shifts lighting, setting, and mood appropriately.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Tuned style suffix for commercial-quality ad images.
# "No text" is critical: text overlays are handled in the composition step,
# so DALL-E rendering its own text would create visual conflicts.
_STYLE_SUFFIX = (
    "professional product photography, clean composition, "
    "studio-quality lighting, sharp focus, high resolution, "
    "commercial advertisement aesthetic. "
    "No text, no typography, no logos, no watermarks."
)

_REGIONAL_MOODS: dict[str, str] = {
    "north america": "modern urban lifestyle setting, diverse and aspirational",
    "united states": "contemporary American lifestyle, bright and optimistic",
    "europe": "sophisticated minimalist European aesthetic, understated luxury",
    "latin america": "vibrant warm tones, culturally rich, energetic atmosphere",
    "asia": "clean minimalist composition, modern and tech-forward",
    "asia pacific": "clean minimalist composition, modern and tech-forward",
    "middle east": "premium luxurious feel, opulent warm tones",
    "africa": "bold vibrant colors, authentic and contemporary",
    "global": "universally appealing, clean and neutral backdrop",
}

_AUDIENCE_MOODS: dict[str, str] = {
    "millennial": "aspirational lifestyle, authenticity, experience-driven",
    "gen z": "bold, unapologetic, digital-native aesthetic",
    "gen x": "practical sophistication, quality-focused",
    "boomer": "trustworthy, premium, classic elegance",
    "professional": "executive setting, polished and confident",
    "parent": "warm, family-oriented, safe and nurturing",
    "athlete": "dynamic motion, high energy, peak performance",
    "health": "clean, fresh, vitality-focused",
}


class PromptBuilder:
    def build(
        self,
        product_name: str,
        product_description: str,
        target_region: str,
        target_audience: str,
        campaign_theme: Optional[str] = None,
    ) -> str:
        """
        Construct a DALL-E prompt optimized for ad-quality hero images.
        Returns the prompt string and logs it for auditability.
        """
        regional_mood = self._match(target_region.lower(), _REGIONAL_MOODS, "globally appealing setting")
        audience_mood = self._match(target_audience.lower(), _AUDIENCE_MOODS, "broad consumer appeal")

        parts = [
            f"Hero product image for '{product_name}': {product_description}",
            "The physical product must be the single dominant subject: large in frame, centered, "
            "fully visible (not cropped at edges), sharp and recognizable — not a tiny prop in a busy scene.",
            f"Visual mood: {regional_mood}",
            f"Audience feel: {audience_mood}",
        ]

        if campaign_theme:
            parts.append(f"Campaign theme: {campaign_theme}")

        parts.append(_STYLE_SUFFIX)

        prompt = " | ".join(parts)
        logger.debug("Built prompt for '%s': %s", product_name, prompt)
        return prompt

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _match(text: str, lookup: dict[str, str], default: str) -> str:
        """Fuzzy match text against lookup keys."""
        for key, value in lookup.items():
            if key in text:
                return value
        return default
