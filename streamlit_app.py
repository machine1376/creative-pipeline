"""
Creative Pipeline — web UI (Streamlit).

Run from the project root:
  streamlit run streamlit_app.py
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections import defaultdict
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass


def _list_builtin_briefs() -> list[Path]:
    briefs = REPO_ROOT / "briefs"
    if not briefs.is_dir():
        return []
    out: list[Path] = []
    for pattern in ("*.yaml", "*.yml", "*.json"):
        out.extend(sorted(briefs.glob(pattern)))
    return out


def _run_pipeline(
    brief_path: Path,
    *,
    output_dir: str,
    assets_dir: str,
    brand_guidelines: str,
    mock_mode: bool,
    force_regenerate: bool,
    verbose: bool,
):
    os.chdir(REPO_ROOT)
    from src.pipeline import CreativePipeline
    from src.reporter import PipelineReporter

    reporter = PipelineReporter(verbose=verbose)
    pipeline = CreativePipeline(
        brief_path=str(brief_path.resolve()),
        output_dir=output_dir,
        assets_dir=assets_dir,
        brand_guidelines_path=brand_guidelines,
        mock_mode=mock_mode,
        force_regenerate_heroes=force_regenerate,
        reporter=reporter,
    )
    result = pipeline.run()
    reporter.save_report(result, output_dir)
    return result


def _resolve_output_path(p: str) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def main() -> None:
    st.set_page_config(
        page_title="Creative Pipeline",
        page_icon="🎨",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _load_env()

    st.title("Creative automation pipeline")
    st.caption("Generate social ad creatives (1:1, 9:16, 16:9) from a campaign brief — mock or DALL·E 3.")

    with st.sidebar:
        st.header("Run options")
        mock = st.checkbox("Mock mode (no API calls)", value=True, help="Placeholder heroes — no OpenAI billing.")
        force_regenerate = st.checkbox(
            "Force regenerate heroes",
            value=False,
            help="Ignore cached assets/*/hero.png and regenerate heroes.",
        )
        verbose = st.checkbox("Verbose logging", value=False)
        st.divider()
        output_dir = st.text_input("Output directory", value="outputs")
        assets_dir = st.text_input("Assets directory", value="assets")
        brand_guidelines = st.text_input("Brand guidelines", value="brand/guidelines.yaml")

        has_key = bool(os.environ.get("OPENAI_API_KEY"))
        if not mock:
            if has_key:
                st.success("OPENAI_API_KEY is set")
            else:
                st.warning("Set OPENAI_API_KEY in `.env` or the environment for live mode.")

    st.subheader("Campaign brief")
    builtin = _list_builtin_briefs()
    mode = st.radio(
        "Brief source",
        ["Choose a sample brief", "Upload YAML or JSON"],
        horizontal=True,
    )

    brief_path: Path | None = None
    if mode == "Choose a sample brief":
        if not builtin:
            st.error("No briefs found under `briefs/`.")
        else:
            labels = {str(p.relative_to(REPO_ROOT)): p for p in builtin}
            choice = st.selectbox("Sample brief", list(labels.keys()))
            brief_path = labels[choice]
    else:
        up = st.file_uploader("Brief file", type=["yaml", "yml", "json"])
        if up is not None:
            suffix = Path(up.name).suffix.lower()
            if suffix not in {".yaml", ".yml", ".json"}:
                st.error("Upload a .yaml, .yml, or .json brief.")
            else:
                sig = f"{up.name}:{len(up.getbuffer())}"
                if st.session_state.get("_brief_sig") != sig:
                    old = st.session_state.get("_brief_tmp_path")
                    if old and Path(old).exists():
                        try:
                            os.unlink(old)
                        except OSError:
                            pass
                    tmp = tempfile.NamedTemporaryFile(
                        delete=False, suffix=suffix, prefix="uploaded_brief_"
                    )
                    tmp.write(up.getbuffer())
                    tmp.close()
                    st.session_state["_brief_tmp_path"] = tmp.name
                    st.session_state["_brief_sig"] = sig
                brief_path = Path(st.session_state["_brief_tmp_path"])

    run = st.button("Run pipeline", type="primary", disabled=brief_path is None)

    if run and brief_path is not None:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        with st.spinner("Running pipeline…"):
            try:
                result = _run_pipeline(
                    brief_path,
                    output_dir=output_dir,
                    assets_dir=assets_dir,
                    brand_guidelines=brand_guidelines,
                    mock_mode=mock,
                    force_regenerate=force_regenerate,
                    verbose=verbose,
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Pipeline failed: {exc}")
                st.session_state.pop("last_result", None)
            else:
                st.session_state["last_result"] = result
                st.session_state["last_output_dir"] = output_dir

    result = st.session_state.get("last_result")
    out_dir = st.session_state.get("last_output_dir", output_dir)
    if result is not None:
        st.divider()
        out_root = _resolve_output_path(out_dir) / result.campaign_id
        if result.errors:
            st.warning(f"Completed with {len(result.errors)} error(s).")
            for e in result.errors:
                st.text(e)
        else:
            st.success(
                f"**{result.campaign_id}** — {result.total_assets} assets in {result.duration_seconds:.1f}s "
                f"({'mock' if result.mock_mode else 'live'})"
            )

        c1, c2, c3 = st.columns(3)
        c1.metric("Assets", result.total_assets)
        c2.metric("Mode", "Mock" if result.mock_mode else "Live")
        c3.metric("Campaign", result.campaign_id)

        report_path = out_root / "pipeline_report.json"
        if report_path.is_file():
            with open(report_path, encoding="utf-8") as f:
                st.download_button(
                    "Download pipeline_report.json",
                    data=f.read(),
                    file_name="pipeline_report.json",
                    mime="application/json",
                )

        st.subheader("Creatives")
        by_product: dict[str, list] = defaultdict(list)
        for a in result.assets:
            by_product[a.product_id].append(a)

        for pid, assets in sorted(by_product.items()):
            name = assets[0].product_name if assets else pid
            st.markdown(f"**{name}** · `{pid}`")
            order = {"1:1": 0, "9:16": 1, "16:9": 2}
            assets.sort(key=lambda x: order.get(x.aspect_ratio, 9))
            cols = st.columns(len(assets))
            for col, a in zip(cols, assets):
                p = _resolve_output_path(a.output_path)
                if p.is_file():
                    col.image(str(p), caption=a.aspect_ratio, use_container_width=True)
                else:
                    col.caption(f"{a.aspect_ratio} — file not found: {p}")

    st.divider()
    st.caption(f"Project root: `{REPO_ROOT}` · Outputs: `{_resolve_output_path(out_dir)}`")


if __name__ == "__main__":
    main()
