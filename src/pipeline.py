"""
Creative Automation Pipeline — main orchestrator.

Coordinates all pipeline stages in order:
  Brief parsing → Asset resolution → Image generation →
  Creative composition → Compliance check → Asset saving → Reporting

Design decisions:
  - Per-product errors are caught and logged without aborting the full run.
    A single bad product shouldn't block the rest of the campaign.
  - Asset caching happens before composition: the hero image is stored once,
    then composed into all three aspect ratios. This avoids 3× generation cost.
  - Output directory structure is:
      outputs/{campaign_id}/{product_id}/{ratio_key_sanitized}/final.png
    keeping outputs clearly organized and easy to browse.
  - The pipeline is a plain Python class with no global state, making it
    straightforward to unit-test or embed in a larger system.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from .asset_manager import AssetManager
from .brief_parser import BriefParser
from .compliance_checker import ComplianceChecker
from .creative_composer import CreativeComposer
from .image_generator import ImageGenerator, ImageGenerationError
from .models import (
    ASPECT_RATIOS,
    AssetResult,
    BrandGuidelines,
    CampaignBrief,
    ComplianceResult,
    PipelineResult,
    ProductBrief,
)
from .prompt_builder import PromptBuilder
from .reporter import PipelineReporter
from .theme_colors import resolve_product_theme_color

logger = logging.getLogger(__name__)


class CreativePipeline:
    def __init__(
        self,
        brief_path: str,
        output_dir: str = "outputs",
        assets_dir: str = "assets",
        brand_guidelines_path: Optional[str] = "brand/guidelines.yaml",
        mock_mode: bool = False,
        force_regenerate_heroes: bool = False,
        reporter: Optional[PipelineReporter] = None,
    ):
        self.brief_path = brief_path
        self.output_dir = Path(output_dir)
        self.mock_mode = mock_mode
        self.force_regenerate_heroes = force_regenerate_heroes
        self.reporter = reporter or PipelineReporter()

        # Instantiate pipeline components
        self.brief_parser = BriefParser()
        self.asset_manager = AssetManager(assets_dir)
        self.prompt_builder = PromptBuilder()
        self.image_generator = ImageGenerator(
            api_key=os.getenv("OPENAI_API_KEY"),
            mock_mode=mock_mode,
        )
        self.composer = CreativeComposer()
        self.compliance = ComplianceChecker()

        self.guidelines = self._load_guidelines(brand_guidelines_path)

    def run(self) -> PipelineResult:
        """Execute the full pipeline and return a structured result."""
        start = time.perf_counter()
        logger.info("═" * 55)
        logger.info("Creative Automation Pipeline — starting")
        logger.info("Brief: %s | Mock: %s", self.brief_path, self.mock_mode)
        logger.info("═" * 55)

        brief = self.brief_parser.parse(self.brief_path)
        logger.info(
            "Campaign '%s' | %d products | Region: %s",
            brief.campaign_id,
            len(brief.products),
            brief.target_region,
        )

        # Load logo once (shared across all products)
        logo = self._load_logo()

        asset_results: list[AssetResult] = []
        errors: list[str] = []

        for product in brief.products:
            logger.info("── Processing product: %s ──", product.name)
            try:
                results = self._process_product(brief, product, logo)
                asset_results.extend(results)
            except Exception as exc:  # noqa: BLE001
                msg = f"Failed to process '{product.name}': {exc}"
                logger.error(msg)
                errors.append(msg)

        elapsed = time.perf_counter() - start
        result = PipelineResult(
            campaign_id=brief.campaign_id,
            total_assets=len(asset_results),
            assets=asset_results,
            errors=errors,
            duration_seconds=elapsed,
            mock_mode=self.mock_mode,
        )

        self.reporter.print_summary(result)
        return result

    # ------------------------------------------------------------------
    # Per-product processing
    # ------------------------------------------------------------------

    def _process_product(
        self,
        brief: CampaignBrief,
        product: ProductBrief,
        logo: Optional[Image.Image],
    ) -> list[AssetResult]:
        # 1. Resolve hero image (cache → generate)
        hero, source = self._resolve_hero(brief, product)

        theme_color = resolve_product_theme_color(
            brand_primary=self.guidelines.primary_color,
            product_id=product.id,
            product_name=product.name,
            product_description=product.description,
            tagline=product.tagline,
            product_theme=product.product_theme,
            campaign_theme=brief.campaign_theme,
            theme_color_override=product.theme_color,
        )
        logger.debug("Theme overlay color for '%s': %s", product.id, theme_color)

        # 2. Compose + check for each aspect ratio
        results = []
        for ratio_key, aspect_ratio in ASPECT_RATIOS.items():
            logger.info("  Composing %s for %s…", ratio_key, product.name)

            creative = self.composer.compose(
                hero_image=hero,
                message=brief.campaign_message,
                product_name=product.name,
                aspect_ratio=aspect_ratio,
                brand_color=theme_color,
                tagline=product.tagline,
                logo=logo,
            )

            compliance_result = self.compliance.check(
                image=creative,
                campaign_message=brief.campaign_message,
                product_description=product.description,
                guidelines=self.guidelines,
                logo_was_applied=logo is not None,
                color_reference_hex=theme_color,
            )

            out_path = self._save_creative(creative, brief.campaign_id, product.id, ratio_key)

            results.append(
                AssetResult(
                    product_id=product.id,
                    product_name=product.name,
                    aspect_ratio=ratio_key,
                    output_path=str(out_path),
                    source=source,
                    compliance=compliance_result,
                )
            )

        return results

    def _resolve_hero(
        self, brief: CampaignBrief, product: ProductBrief
    ) -> tuple[Image.Image, str]:
        """
        Resolve a hero image for the product.
        Returns (image, source_label).
        """
        existing = self.asset_manager.resolve(
            product.id,
            product.asset_path,
            use_cache=not self.force_regenerate_heroes,
        )
        if existing:
            return existing, "existing_asset"

        # Build prompt and generate
        prompt = self.prompt_builder.build(
            product_name=product.name,
            product_description=product.description,
            target_region=brief.target_region,
            target_audience=brief.target_audience,
            campaign_theme=brief.campaign_theme,
        )

        try:
            # Generate using the 1:1 size as the canonical hero
            hero = self.image_generator.generate(
                prompt=prompt,
                product_name=product.name,
                aspect_ratio=ASPECT_RATIOS["1:1"],
            )
            source = "mock" if self.mock_mode else "generated"
            # Cache for future runs
            self.asset_manager.save_to_cache(product.id, hero)
            return hero, source

        except ImageGenerationError as exc:
            raise RuntimeError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Output saving
    # ------------------------------------------------------------------

    def _save_creative(
        self,
        image: Image.Image,
        campaign_id: str,
        product_id: str,
        ratio_key: str,
    ) -> Path:
        ratio_dir = ratio_key.replace(":", "_")
        out_dir = self.output_dir / campaign_id / product_id / ratio_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "final.png"
        # Upscale to final social media resolution
        target = ASPECT_RATIOS[ratio_key].size
        final = image.resize(target, Image.LANCZOS) if image.size != target else image
        final.save(out_path, format="PNG", optimize=True)
        logger.info("    Saved → %s", out_path)
        return out_path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_guidelines(self, path: Optional[str]) -> BrandGuidelines:
        if not path or not Path(path).exists():
            logger.info("No brand guidelines found at '%s' — using defaults.", path)
            return BrandGuidelines()

        import yaml  # noqa: PLC0415
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return BrandGuidelines(
            primary_color=data.get("primary_color", "#1a73e8"),
            secondary_color=data.get("secondary_color", "#ffffff"),
            accent_color=data.get("accent_color", "#fbbc04"),
            logo_path=data.get("logo_path"),
            prohibited_words=data.get("prohibited_words", []),
            required_disclaimer=data.get("required_disclaimer"),
        )

    def _load_logo(self) -> Optional[Image.Image]:
        if not self.guidelines.logo_path:
            return None
        logo_path = Path(self.guidelines.logo_path)
        if not logo_path.exists():
            logger.warning("Logo path configured but file not found: %s", logo_path)
            return None
        try:
            return Image.open(logo_path).convert("RGBA")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load logo: %s", exc)
            return None
