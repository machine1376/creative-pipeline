"""
Image generation via OpenAI DALL-E 3.

Design decisions:
  - Mock mode produces realistic placeholder images without API calls,
    enabling local demos and CI runs without spending API quota.
  - DALL-E 3 native sizes are used (1024x1024, 1024x1792, 1792x1024) to
    maximize quality before the composition step upscales to final dimensions.
  - Each generation request is logged with its prompt for full auditability.
  - Errors are caught per-asset so one failure doesn't abort the full run.
"""

from __future__ import annotations

import io
import logging
import random
from typing import TYPE_CHECKING

import requests
from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from openai import OpenAI as OpenAIClient

from .models import AspectRatio

logger = logging.getLogger(__name__)


class ImageGenerationError(RuntimeError):
    """Raised when image generation fails unrecoverably."""


class ImageGenerator:
    def __init__(self, api_key: str | None = None, mock_mode: bool = False):
        self.mock_mode = mock_mode
        self._client: OpenAIClient | None = None

        if not mock_mode:
            if not api_key:
                raise ValueError(
                    "OPENAI_API_KEY is required when not running in mock mode. "
                    "Set the env var or pass --mock to use placeholder images."
                )
            # Lazy import so the package installs gracefully without openai in mock mode
            try:
                from openai import OpenAI  # noqa: PLC0415
                self._client = OpenAI(api_key=api_key)
            except ImportError as exc:
                raise ImportError(
                    "openai package is required for live generation. "
                    "Run: pip install openai"
                ) from exc

    def generate(
        self,
        prompt: str,
        product_name: str,
        aspect_ratio: AspectRatio,
    ) -> Image.Image:
        """
        Generate a hero image.
        In mock mode, returns a styled placeholder.
        In live mode, calls DALL-E 3 and decodes the returned image.
        """
        if self.mock_mode:
            logger.info("[MOCK] Generating placeholder for '%s' (%s)", product_name, aspect_ratio.key)
            return self._generate_mock(product_name, aspect_ratio)

        logger.info("Generating image for '%s' (%s) via DALL-E 3…", product_name, aspect_ratio.key)
        logger.debug("Prompt: %s", prompt)

        try:
            response = self._client.images.generate(  # type: ignore[union-attr]
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size=aspect_ratio.dalle_size_str,
                response_format="url",
                quality="standard",
            )
            image_url = response.data[0].url
            revised_prompt = response.data[0].revised_prompt
            if revised_prompt:
                logger.debug("DALL-E revised prompt: %s", revised_prompt)

            return self._fetch_image(image_url)

        except Exception as exc:  # noqa: BLE001
            detail = f"DALL-E 3 generation failed for '{product_name}': {exc}"
            err_lower = str(exc).lower()
            if "billing" in err_lower and "limit" in err_lower:
                detail += (
                    " | Fix: OpenAI → Settings → Billing — increase monthly budget or raise/remove "
                    "the hard usage limit (https://platform.openai.com/settings/organization/billing)."
                )
            elif "invalid_api_key" in err_lower or "incorrect api key" in err_lower:
                detail += " | Fix: set a valid OPENAI_API_KEY in .env or your shell."
            raise ImageGenerationError(detail) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_image(self, url: str) -> Image.Image:
        """Download the generated image from OpenAI's CDN."""
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")

    def _generate_mock(self, product_name: str, aspect_ratio: AspectRatio) -> Image.Image:
        """
        Create a visually distinct placeholder image for demo / testing.

        Each product gets a deterministic color palette so the same product
        always produces the same mock image (useful for reproducibility tests).
        """
        w, h = aspect_ratio.dalle_size

        # Deterministic color from product name hash
        seed = sum(ord(c) for c in product_name)
        rng = random.Random(seed)

        # Background gradient colors
        r1, g1, b1 = rng.randint(20, 80), rng.randint(20, 80), rng.randint(80, 160)
        r2, g2, b2 = rng.randint(80, 180), rng.randint(40, 120), rng.randint(20, 80)

        img = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)

        # Vertical gradient
        for y in range(h):
            t = y / h
            r = int(r1 + (r2 - r1) * t)
            g = int(g1 + (g2 - g1) * t)
            b = int(b1 + (b2 - b1) * t)
            draw.line([(0, y), (w, y)], fill=(r, g, b))

        # Decorative circles to simulate product
        cx, cy = w // 2, h // 3
        for i, radius in enumerate([200, 150, 100]):
            alpha = 60 + i * 30
            overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ov_draw = ImageDraw.Draw(overlay)
            ov_draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=(255, 255, 255, alpha),
            )
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(img)

        # Centered product label
        label = f"[ {product_name} ]"
        try:
            font = ImageFont.truetype(self._find_system_font(), 48)
        except Exception:  # noqa: BLE001
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), label, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text(
            ((w - text_w) // 2, cy - text_h // 2),
            label,
            fill=(255, 255, 255),
            font=font,
        )

        # "MOCK" badge
        draw.rectangle([0, 0, 120, 40], fill=(255, 80, 80))
        draw.text((8, 8), "MOCK", fill=(255, 255, 255), font=ImageFont.load_default())

        return img

    @staticmethod
    def _find_system_font() -> str:
        """Return the first available system font path."""
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
        from pathlib import Path  # noqa: PLC0415
        for p in candidates:
            if Path(p).exists():
                return p
        raise FileNotFoundError("No system font found")
