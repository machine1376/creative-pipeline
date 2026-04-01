"""
Pipeline reporter: structured logging and run report generation.

Produces a JSON report alongside the generated assets so runs are
fully auditable (which products were processed, which assets were reused
vs generated, compliance results, timing, etc.).

Design decision: Separating reporting from pipeline logic means the reporter
can be swapped for a different sink (e.g., pushing to an analytics API or
writing to a database) without touching the pipeline itself.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from .models import PipelineResult


def configure_logging(verbose: bool = False) -> None:
    """Set up structured console logging for the pipeline."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logging.basicConfig(level=level, handlers=[handler], force=True)


class PipelineReporter:
    def __init__(self, verbose: bool = False):
        configure_logging(verbose)
        self.logger = logging.getLogger("reporter")

    def save_report(self, result: PipelineResult, output_dir: str) -> Path:
        """Write a JSON summary of the pipeline run to the output directory."""
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "campaign_id": result.campaign_id,
            "mock_mode": result.mock_mode,
            "duration_seconds": round(result.duration_seconds, 2),
            "total_assets_generated": result.total_assets,
            "errors": result.errors,
            "assets": [a.to_dict() for a in result.assets],
            "summary": self._build_summary(result),
        }

        out_path = Path(output_dir) / result.campaign_id / "pipeline_report.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        self.logger.info("Report saved: %s", out_path)
        return out_path

    def print_summary(self, result: PipelineResult) -> None:
        summary = self._build_summary(result)
        print("\n" + "─" * 60)
        print(f"  Campaign: {result.campaign_id}")
        print(f"  Mode:     {'MOCK' if result.mock_mode else 'LIVE'}")
        print(f"  Assets:   {result.total_assets} generated in {result.duration_seconds:.1f}s")
        print(f"  Reused:   {summary['reused_assets']}")
        print(f"  Compliance: {summary['compliance_passed']} passed, "
              f"{summary['compliance_failed']} failed")
        if result.errors:
            print(f"  Errors:   {len(result.errors)}")
            for e in result.errors:
                print(f"    ✗ {e}")
        print("─" * 60 + "\n")

    @staticmethod
    def _build_summary(result: PipelineResult) -> dict:
        reused = sum(1 for a in result.assets if a.source == "existing_asset")
        passed = sum(1 for a in result.assets if a.compliance.passed)
        failed = sum(1 for a in result.assets if not a.compliance.passed)
        return {
            "reused_assets": reused,
            "generated_assets": result.total_assets - reused,
            "compliance_passed": passed,
            "compliance_failed": failed,
        }
