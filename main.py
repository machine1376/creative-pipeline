#!/usr/bin/env python3
"""
Creative Automation Pipeline — CLI entry point.

Usage examples:
  # Run in mock mode (no API key needed, great for demos):
  python main.py --brief briefs/example_brief.yaml --mock

  # Run with live DALL-E 3 (set OPENAI_API_KEY in .env or the environment):
  python main.py --brief briefs/example_brief.yaml

  # Custom output directory with verbose logging:
  python main.py --brief briefs/example_brief.yaml --mock --output-dir ./demo_output --verbose
"""

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="creative-pipeline",
        description="Creative Automation Pipeline — generate localized social ad creatives via GenAI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--brief",
        required=True,
        metavar="PATH",
        help="Path to campaign brief file (YAML or JSON).",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        metavar="DIR",
        help="Root directory for generated assets (default: outputs/).",
    )
    parser.add_argument(
        "--assets-dir",
        default="assets",
        metavar="DIR",
        help="Directory for input/cached assets (default: assets/).",
    )
    parser.add_argument(
        "--brand-guidelines",
        default="brand/guidelines.yaml",
        metavar="PATH",
        help="Path to brand guidelines YAML (default: brand/guidelines.yaml).",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use placeholder images instead of calling DALL-E 3 (no API key needed).",
    )
    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help="Ignore cached heroes at assets/{product_id}/hero.png and call DALL-E (or mock) again.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )

    args = parser.parse_args()

    # Deferred import so --help works even if dependencies aren't installed
    try:
        from src.pipeline import CreativePipeline
        from src.reporter import PipelineReporter
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("Fix: use this project's virtualenv, then install deps:")
        print("  source .venv/bin/activate && pip install -r requirements.txt")
        print("Or run without activating:  .venv/bin/python main.py ...")
        return 1

    _repo_root = Path(__file__).resolve().parent
    _env_file = _repo_root / ".env"
    try:
        from dotenv import load_dotenv
    except ImportError:
        if (
            _env_file.is_file()
            and not args.mock
            and not os.environ.get("OPENAI_API_KEY")
        ):
            print(
                "NOTE: Install python-dotenv to load .env (pip install -r requirements.txt). "
                "Until then, use: export OPENAI_API_KEY=...",
                file=sys.stderr,
            )
    else:
        load_dotenv(_env_file)

    reporter = PipelineReporter(verbose=args.verbose)

    pipeline = CreativePipeline(
        brief_path=args.brief,
        output_dir=args.output_dir,
        assets_dir=args.assets_dir,
        brand_guidelines_path=args.brand_guidelines,
        mock_mode=args.mock,
        force_regenerate_heroes=args.force_regenerate,
        reporter=reporter,
    )

    try:
        result = pipeline.run()
    except FileNotFoundError as exc:
        print(f"\nERROR: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: Pipeline failed — {exc}")
        return 1

    reporter.save_report(result, args.output_dir)

    output_root = (Path(args.output_dir) / result.campaign_id).resolve()
    if result.errors:
        print(
            f"\n⚠️  Finished with {len(result.errors)} error(s). "
            f"{result.total_assets} asset(s) written under: {output_root}"
        )
    else:
        print(f"\n✅  {result.total_assets} assets saved to: {output_root}")
    print(f"📊  Report: {output_root / 'pipeline_report.json'}")

    return 0 if not result.errors else 1


if __name__ == "__main__":
    sys.exit(main())
