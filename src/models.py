"""
Domain models for the Creative Automation Pipeline.

Design decision: Using dataclasses over dicts for type safety and IDE support.
Separating models from logic makes each layer independently testable.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class AspectRatioKey(str, Enum):
    SQUARE = "1:1"
    PORTRAIT = "9:16"
    LANDSCAPE = "16:9"


@dataclass(frozen=True)
class AspectRatio:
    """
    Immutable value object representing a target canvas size.

    Native DALL-E 3 sizes are used where possible to minimize quality loss from
    resizing:
        1:1  -> 1024x1024 (native)
        9:16 -> 1024x1792 (native)
        16:9 -> 1792x1024 (native)

    Final output is then upscaled to standard social media resolutions with
    Lanczos resampling.
    """

    key: str
    width: int
    height: int
    platform: str
    dalle_width: int
    dalle_height: int

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def dalle_size(self) -> tuple[int, int]:
        return (self.dalle_width, self.dalle_height)

    @property
    def dalle_size_str(self) -> str:
        return f"{self.dalle_width}x{self.dalle_height}"


ASPECT_RATIOS: dict[str, AspectRatio] = {
    "1:1": AspectRatio(
        key="1:1",
        width=1080,
        height=1080,
        platform="Instagram Feed / Facebook",
        dalle_width=1024,
        dalle_height=1024,
    ),
    "9:16": AspectRatio(
        key="9:16",
        width=1080,
        height=1920,
        platform="Instagram Stories / Reels / TikTok",
        dalle_width=1024,
        dalle_height=1792,
    ),
    "16:9": AspectRatio(
        key="16:9",
        width=1920,
        height=1080,
        platform="Facebook / YouTube / LinkedIn",
        dalle_width=1792,
        dalle_height=1024,
    ),
}


@dataclass
class ProductBrief:
    id: str
    name: str
    description: str
    tagline: Optional[str] = None
    asset_path: Optional[str] = None  # Pre-existing asset; skips generation if set
    # Optional: short theme phrase for color derivation (keywords like water, berry, eco).
    product_theme: Optional[str] = None
    # Optional: explicit #RRGGBB; still blended slightly with brand primary for cohesion.
    theme_color: Optional[str] = None


@dataclass
class CampaignBrief:
    campaign_id: str
    products: list[ProductBrief]
    target_region: str
    target_market: str
    target_audience: str
    campaign_message: str
    language: str = "en"
    campaign_theme: Optional[str] = None


@dataclass
class BrandGuidelines:
    primary_color: str = "#1a73e8"
    secondary_color: str = "#ffffff"
    accent_color: str = "#fbbc04"
    logo_path: Optional[str] = None
    prohibited_words: list[str] = field(default_factory=list)
    required_disclaimer: Optional[str] = None


@dataclass
class ComplianceResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "issues": self.issues,
            "warnings": self.warnings,
        }


@dataclass
class AssetResult:
    product_id: str
    product_name: str
    aspect_ratio: str
    output_path: str
    source: str  # "existing_asset" | "generated" | "mock"
    compliance: ComplianceResult
    generation_prompt: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "aspect_ratio": self.aspect_ratio,
            "output_path": self.output_path,
            "source": self.source,
            "compliance": self.compliance.to_dict(),
            "generation_prompt": self.generation_prompt,
        }


@dataclass
class PipelineResult:
    campaign_id: str
    total_assets: int
    assets: list[AssetResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    mock_mode: bool = False
