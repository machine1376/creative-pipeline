"""
Asset manager: resolve hero images for each product.

Resolution order (cost-optimized):
  1. Brief specifies an explicit asset_path → use it directly.
  2. Asset cache contains a previously generated image → reuse it.
  3. No asset found → caller must generate via GenAI.

Design decision: Separating asset resolution from generation keeps the
pipeline stages loosely coupled. The generator only runs when genuinely
necessary, reducing API cost and latency.

Cache convention:
  assets/{product_id}/hero.png
"""

import logging
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
HERO_FILENAME = "hero.png"


class AssetManager:
    def __init__(self, assets_dir: str = "assets"):
        self.assets_dir = Path(assets_dir)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def resolve(
        self,
        product_id: str,
        asset_path: Optional[str],
        *,
        use_cache: bool = True,
    ) -> Optional[Image.Image]:
        """
        Try to load a hero image for the given product.
        Returns None if no asset is available (triggers generation).

        When use_cache is False, skips the on-disk cache (assets/{id}/hero.png)
        so the pipeline can call DALL-E again; brief asset_path is still honored.
        """
        # Priority 1: explicit path from brief
        if asset_path:
            img = self._load(Path(asset_path), source_label="brief asset_path")
            if img:
                return img

        # Priority 2: asset cache
        if not use_cache:
            logger.info("Hero cache skipped for '%s' — will generate.", product_id)
            return None

        cached_path = self._cache_path(product_id)
        if cached_path.exists():
            img = self._load(cached_path, source_label="asset cache")
            if img:
                return img

        logger.info("No asset found for '%s' — will generate.", product_id)
        return None

    def save_to_cache(self, product_id: str, image: Image.Image) -> Path:
        """Persist a generated image to the asset cache."""
        cache_path = self._cache_path(product_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(cache_path, format="PNG")
        logger.debug("Cached hero image: %s", cache_path)
        return cache_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _cache_path(self, product_id: str) -> Path:
        return self.assets_dir / product_id / HERO_FILENAME

    def _load(self, path: Path, source_label: str) -> Optional[Image.Image]:
        if not path.exists():
            logger.debug("Asset not found at %s (%s)", path, source_label)
            return None

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            logger.warning(
                "Unsupported asset format '%s' for %s — skipping.",
                path.suffix,
                source_label,
            )
            return None

        try:
            img = Image.open(path).convert("RGB")
            logger.info("Loaded asset from %s (%s): %s", source_label, img.size, path)
            return img
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load asset at %s: %s", path, exc)
            return None
