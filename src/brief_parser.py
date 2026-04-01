"""
Campaign brief parser.

Supports YAML and JSON input formats. Validates structure before returning
a typed CampaignBrief object, surfacing clear errors early in the pipeline
rather than letting bad data propagate.

Design decision: Parser raises on invalid input rather than silently skipping
fields. In a production system you want loud failures at ingestion time, not
silent failures at render time.
"""

import json
from pathlib import Path

import yaml

from .models import CampaignBrief, ProductBrief


SUPPORTED_FORMATS = {".yaml", ".yml", ".json"}


class BriefValidationError(ValueError):
    """Raised when a campaign brief fails validation."""


class BriefParser:
    def parse(self, brief_path: str | Path) -> CampaignBrief:
        """Load and validate a campaign brief from disk."""
        path = Path(brief_path)

        if not path.exists():
            raise FileNotFoundError(f"Brief not found: {brief_path}")

        if path.suffix not in SUPPORTED_FORMATS:
            raise BriefValidationError(
                f"Unsupported format '{path.suffix}'. Accepted: {sorted(SUPPORTED_FORMATS)}"
            )

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) if path.suffix in {".yaml", ".yml"} else json.load(f)

        return self._build(data)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build(self, data: dict) -> CampaignBrief:
        self._validate_top_level(data)

        products = [self._build_product(i, p) for i, p in enumerate(data["products"])]

        return CampaignBrief(
            campaign_id=data["campaign_id"],
            products=products,
            target_region=data["target_region"],
            target_market=data["target_market"],
            target_audience=data["target_audience"],
            campaign_message=data["campaign_message"],
            language=data.get("language", "en"),
            campaign_theme=data.get("campaign_theme"),
        )

    def _validate_top_level(self, data: dict) -> None:
        required = [
            "campaign_id",
            "products",
            "target_region",
            "target_market",
            "target_audience",
            "campaign_message",
        ]
        missing = [k for k in required if k not in data]
        if missing:
            raise BriefValidationError(f"Brief missing required fields: {missing}")

        if not isinstance(data["products"], list) or len(data["products"]) < 2:
            raise BriefValidationError(
                "Brief must include at least 2 products (got "
                f"{len(data.get('products', []))})"
            )

    def _build_product(self, index: int, p: dict) -> ProductBrief:
        for field in ("name", "description"):
            if field not in p:
                raise BriefValidationError(
                    f"Product at index {index} is missing required field '{field}'"
                )

        product_id = p.get("id") or p["name"].lower().replace(" ", "_")

        return ProductBrief(
            id=product_id,
            name=p["name"],
            description=p["description"],
            tagline=p.get("tagline"),
            asset_path=p.get("asset_path"),
            product_theme=p.get("product_theme"),
            theme_color=p.get("theme_color"),
        )
