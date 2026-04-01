# Creative Automation Pipeline

A proof-of-concept tool that automates localized social ad creatives using GenAI.
Given a campaign brief (YAML or JSON), it produces image assets in three aspect
ratios (1:1, 9:16, 16:9), runs compliance checks, and writes a JSON run report.
Use the **CLI** (`main.py`) or the optional **Streamlit** UI (`streamlit_app.py`).

---

## Quick Start

```bash
# 1. Clone and install (use a virtualenv — required on many macOS/Homebrew Python setups)
git clone https://github.com/machine1376/creative-pipeline.git
cd creative-pipeline
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Run in mock mode (no API key — good first run)
python main.py --brief briefs/example_brief.yaml --mock

# 3. View outputs under outputs/<campaign_id>/
```

**Live mode** (DALL-E 3 — requires billing enabled on your OpenAI account):

```bash
cp .env.example .env          # set OPENAI_API_KEY=...
python main.py --brief briefs/example_brief.yaml
```

- **`main.py`** loads `.env` from the project root when `python-dotenv` is installed. If it is missing, set `export OPENAI_API_KEY=...` or use `.venv/bin/python` after `pip install -r requirements.txt` so dependencies resolve.
- Environment variables already set in the shell **override** values from `.env`.

**Web UI** (Streamlit — sample or upload brief, mock / force-regenerate, preview and download report):

```bash
streamlit run streamlit_app.py
```

Open the URL shown (typically `http://localhost:8501`). Run from the **project root** with the same venv activated.

---

## Environment & API keys

| Mode | What you need |
|------|----------------|
| `--mock` | Nothing — no network calls for image generation. |
| Live | `OPENAI_API_KEY` in `.env` or the environment; [OpenAI billing](https://platform.openai.com/settings/organization/billing) with a usable monthly budget / limit (image generation returns an error if a **hard billing limit** is hit). |

---

## CLI Reference

```
python main.py [OPTIONS]

Options:
  --brief PATH           Campaign brief file (YAML or JSON). Required.
  --output-dir DIR       Root output directory. Default: outputs/
  --assets-dir DIR       Input/cached assets directory. Default: assets/
  --brand-guidelines PATH  Brand guidelines YAML. Default: brand/guidelines.yaml
  --mock                 Use placeholder images (no API calls).
  --force-regenerate     Skip on-disk hero cache; call DALL-E (or mock) for new heroes.
  --verbose              Enable DEBUG-level logging.
```

---

## Example Input

**`briefs/example_brief.yaml`**

```yaml
campaign_id: summer_wellness_na
campaign_message: "Fuel your journey sustainably"
campaign_theme: "Clean energy, vibrant life, sun-drenched outdoor lifestyle"

target_region: North America
target_market: United States
target_audience: "Health-conscious millennials aged 25–35 who prioritize sustainability"
language: en

products:
  - id: eco_water_bottle
    name: "EcoFlow Bottle"
    description: >
      A 32oz sustainable water bottle made from 100% ocean-recycled plastic.
      Features double-wall vacuum insulation keeping drinks cold for 24 hours.
    tagline: "Hydrate. Sustain. Repeat."
    # Optional: steers overlay gradient tint (keywords + blend with brand primary)
    product_theme: "Cool hydration, ocean blues, fresh water"
    # asset_path: "assets/eco_water_bottle/hero.png"   # optional: skip generation

  - id: power_blend_protein
    name: "PowerBlend Protein"
    description: >
      Premium plant-based protein powder with 25g protein per serving.
      Available in Vanilla, Chocolate, and Mixed Berry flavors.
      NSF Certified for Sport.
    tagline: "Clean protein. Real performance."
    product_theme: "Plant energy, cocoa and berry tones, gym performance"
    # theme_color: "#8d4e2a"   # optional: explicit hex (still blended with brand)
```

Per-product fields: **`product_theme`** (free text) and optional **`theme_color`** (`#RRGGBB`) feed `src/theme_colors.py`. See `briefs/example_brief_eu.json` for the same idea in JSON.

---

## Example Output

```
outputs/
└── summer_wellness_na/
    ├── eco_water_bottle/
    │   ├── 1_1/    final.png   (1080×1080 — Instagram Feed)
    │   ├── 9_16/   final.png   (1080×1920 — Stories / Reels)
    │   └── 16_9/   final.png   (1920×1080 — Facebook / YouTube)
    ├── power_blend_protein/
    │   ├── 1_1/    final.png
    │   ├── 9_16/   final.png
    │   └── 16_9/   final.png
    └── pipeline_report.json
```

**`pipeline_report.json`** (excerpt):
```json
{
  "generated_at": "2025-06-01T14:32:10Z",
  "campaign_id": "summer_wellness_na",
  "duration_seconds": 18.4,
  "total_assets_generated": 6,
  "assets": [
    {
      "product_id": "eco_water_bottle",
      "aspect_ratio": "1:1",
      "output_path": "outputs/summer_wellness_na/eco_water_bottle/1_1/final.png",
      "source": "generated",
      "compliance": { "passed": true, "issues": [], "warnings": [] }
    }
  ]
}
```

---

## Architecture

```
main.py                     CLI entry point (argparse)
streamlit_app.py            Streamlit web UI (same pipeline, browser)
src/
  models.py                 Typed dataclasses: AspectRatio, CampaignBrief, etc.
  brief_parser.py           YAML/JSON brief → CampaignBrief (with validation)
  asset_manager.py          Asset cache resolution (reuse before generate)
  prompt_builder.py         Constructs DALL-E prompts from brief fields
  theme_colors.py           Per-product overlay tint from brief + brand primary
  image_generator.py        DALL-E 3 API + mock placeholder generator
  creative_composer.py      Pillow: cover-crop, gradient, blurred text halo, logo
  compliance_checker.py     Brand color analysis + prohibited word scan
  pipeline.py               Orchestrator — wires all stages together
  reporter.py               Structured logging + JSON report writer
brand/
  guidelines.yaml           Brand colors, logo path, prohibited words
briefs/
  example_brief.yaml        YAML example with 2 products
  example_brief_eu.json     JSON example (demonstrates format flexibility)
assets/                     Input assets + generation cache
outputs/                    Pipeline outputs (gitignored)
```

### Pipeline Flow

```
Campaign Brief (YAML/JSON)
        │
        ▼
  BriefParser.parse()
        │
        ▼
  For each product:
    AssetManager.resolve()
      ├── Brief asset_path → load (always; not bypassed by --force-regenerate)
      ├── Else assets/{product_id}/hero.png exists → load (skipped if --force-regenerate)
      └── Not found / cache skipped:
            PromptBuilder.build()
                  │
                  ▼
            ImageGenerator.generate()  ← DALL-E 3 or mock
                  │
                  ▼
            AssetManager.save_to_cache()
        │
        ▼
  For each aspect ratio (1:1 / 9:16 / 16:9):
    theme_colors.resolve_product_theme_color() → per-product overlay tint
        │
        ▼
    CreativeComposer.compose()
      ├── Cover crop to canvas
      ├── Brand-tinted gradient + dark scrim (readability)
      ├── Campaign message + product name (blurred halo + sharp fill)
      └── Logo placement (if configured)
        │
        ▼
    ComplianceChecker.check()
      ├── Palette vs resolved theme color (same tint as overlay)
      ├── Logo presence flag
      └── Prohibited word scan
        │
        ▼
    Save final.png → outputs/{campaign_id}/{product_id}/{ratio}/
        │
        ▼
  PipelineReporter.save_report() → pipeline_report.json
```

---

## Key Design Decisions

### 1. Asset-first, generate-second (cost optimization)
The `AssetManager` checks two tiers before calling DALL-E:
1. Explicit `asset_path` in the brief (for manually supplied brand assets).
2. Local cache at `assets/{product_id}/hero.png` (from a previous generation).

This prevents duplicate API calls across runs and enables incremental campaigns
where some products already have approved hero images.

To **force new hero images** on the next run (still one DALL-E call per product,
then recomposition into all aspect ratios), use `--force-regenerate`. That skips
tier 2 only; remove or change `asset_path` in the brief if you must bypass tier 1.

### 2. Single hero → three aspect ratios
Each product generates **one** hero image (at DALL-E's native resolution), then
`CreativeComposer` adapts it to all three formats. Generating three separate images
would triple API cost and produce inconsistent visuals.

**Overlay colors** (gradient tint behind copy) are resolved **per product** via
`src/theme_colors.py`: optional `theme_color` / `product_theme` in the brief, plus
keywords in the product’s name and description (e.g. ocean, berry, coffee), blended
with `primary_color` from `brand/guidelines.yaml`. Product text is matched before
`campaign_theme` so a seasonal campaign line does not override a product’s own cues.

### 3. DALL-E 3 native sizes
DALL-E 3 natively supports `1024×1024`, `1024×1792`, and `1792×1024`. The pipeline
uses the 1:1 native size as the canonical hero and upscales to standard social
dimensions (1080×1080, 1080×1920, 1920×1080) using Lanczos resampling, which
minimizes quality loss.

### 4. Cover-crop composition
Images are cropped using a "CSS `object-fit: cover`" approach — scale to fill,
then center-crop. This ensures no letterboxing on any platform. A future
enhancement could use saliency detection to avoid cropping the product focal point.

### 5. Compliance as a pipeline gate (not an afterthought)
Compliance runs on the **composed output**, not the raw hero image. This catches
issues introduced during rendering (e.g., brand color being obscured by the gradient).
Brand color matching uses k-means palette quantization for robustness.
The checker compares against the **same** per-product resolved theme color used in
the gradient overlay (not only the global `primary_color` in `brand/guidelines.yaml`).

### 6. Mock mode for cost-free testing
`--mock` produces deterministic, visually distinct placeholder images without any
API calls. Each product gets a consistent color palette (seeded by the product name
hash) so re-runs produce identical outputs — useful for reproducibility checks.

### 7. Separation of concerns
Each pipeline stage is a plain Python class with no shared global state. This makes
individual stages independently unit-testable and replaceable. For example, swapping
DALL-E for Stable Diffusion only requires changing `ImageGenerator`.

---

## Extending the Pipeline

| Extension | Where to change |
|---|---|
| Use Stable Diffusion instead of DALL-E | `src/image_generator.py` |
| Tune overlay colors / keyword map | `src/theme_colors.py` + brief `product_theme` / `theme_color` |
| Add multi-language text translation | `src/creative_composer.py` + translate `message` before rendering |
| Add a 4th aspect ratio | `src/models.py` → `ASPECT_RATIOS` |
| Push assets to S3/Azure Blob | `src/pipeline.py` → `_save_creative()` |
| Add approval workflow | `src/pipeline.py` → after compliance check |
| Refine prompt strategy | `src/prompt_builder.py` |
| Add more compliance rules | `src/compliance_checker.py` |
| Customize Streamlit UI | `streamlit_app.py` |

---

## Assumptions & Limitations

- **Image model**: DALL-E 3 via OpenAI API. Each product uses one generation
  credit (~$0.04 at standard quality). Failures such as **billing hard limit**
  or invalid keys surface as run errors; see `src/image_generator.py` for hints.
- **Hero → formats**: One square hero per product is cover-cropped to 9:16 and 16:9;
  off-center products can be cropped. Prompts emphasize a centered product subject.
- **Text rendering**: Uses available system fonts (DejaVu, Liberation, Helvetica).
  Copy uses a **blurred dark halo** under sharp fills, plus an optional dark scrim, for legibility on busy photos.
  For pixel-perfect brand typography, supply a `.ttf` file and update
  `_SYSTEM_FONTS_*` lists in `creative_composer.py`.
- **Brand color compliance**: Uses Euclidean RGB distance with tolerance 80
  (out of max 441). A production system would use CIEDE2000 for perceptual accuracy.
- **Multi-language**: Brief supports a `language` field, but translation of the
  campaign message is not implemented (the field is reserved for a future
  translation step using an LLM or translation API).
- **Storage**: Outputs are saved locally. S3/Azure/GCS integration is a straightforward
  extension via `boto3`, `azure-storage-blob`, or `google-cloud-storage`.
- **Approval workflow**: Not implemented. The compliance report JSON is the hook
  where a review/approval API call would be inserted.

---

## Troubleshooting

| Symptom | What to do |
|--------|------------|
| `No module named 'yaml'` (or other missing packages) | You are not using the project venv, or deps are not installed. Run: `python3 -m venv .venv && source .venv/bin/activate` then `pip install -r requirements.txt`. Use `python main.py ...` or `.venv/bin/python main.py` so the same interpreter sees PyYAML and the rest. |
| `externally-managed-environment` when running `pip install` | Do not install into the system/Homebrew Python. Create and use `.venv` as above. |
| `billing_hard_limit_reached` / DALL-E HTTP 400 from OpenAI | Your org hit a **hard spend cap**. In [OpenAI billing → limits](https://platform.openai.com/settings/organization/billing), raise the monthly budget or the hard limit, and ensure a valid payment method. |
| Invalid / refused API key | Set `OPENAI_API_KEY` in `.env` or export it; confirm the key is for the intended project. |
| `streamlit` command not found | Activate `.venv` first, or run `python -m streamlit run streamlit_app.py` from the project root. |
| UI runs but paths fail | Run Streamlit from the **repository root** so `briefs/`, `assets/`, and `outputs/` resolve correctly. |

---

## Requirements

- Python 3.11+
- `pip install -r requirements.txt` (includes Pillow, PyYAML, OpenAI, `python-dotenv`, Streamlit)
- OpenAI API key (live mode only; **not** required with `--mock` or the Streamlit mock default)

Use the project **virtualenv** when your system Python is “externally managed” (common on macOS with Homebrew): `python3 -m venv .venv && source .venv/bin/activate` then `pip install -r requirements.txt`.
