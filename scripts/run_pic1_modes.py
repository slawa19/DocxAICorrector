import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping


ROOT_DIR = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT_DIR / "tests"
ARTIFACTS_DIR = TESTS_DIR / "artifacts" / "real_image_pipeline"
SOURCE_IMAGE = TESTS_DIR / "pic1_lietaer.jpg"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import get_client, get_model_role_value, load_app_config
from image_analysis import analyze_image
from image_generation import detect_image_mime_type, generate_image_candidate
from models import ImageAsset, get_image_variant_bytes
from processing_service import get_processing_service
from state import init_session_state


def _detect_extension(payload: bytes) -> str:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if payload.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if payload.startswith(b"BM"):
        return ".bmp"
    return ".bin"


def _int_setting(config: Mapping[str, object], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return default


def _float_setting(config: Mapping[str, object], key: str, default: float) -> float:
    value = config.get(key, default)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return default


def _build_reconstruction_render_config(config: Mapping[str, object]) -> dict[str, object]:
    return {
        "min_canvas_short_side_px": _int_setting(config, "reconstruction_min_canvas_short_side_px", 900),
        "target_min_font_px": _int_setting(config, "reconstruction_target_min_font_px", 18),
        "max_upscale_factor": _float_setting(config, "reconstruction_max_upscale_factor", 3.0),
        "background_sample_ratio": _float_setting(config, "reconstruction_background_sample_ratio", 0.04),
        "background_color_distance_threshold": _float_setting(
            config,
            "reconstruction_background_color_distance_threshold",
            48.0,
        ),
        "background_uniformity_threshold": _float_setting(
            config,
            "reconstruction_background_uniformity_threshold",
            10.0,
        ),
    }


def _write_artifact(base_name: str, payload: bytes) -> str:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = ARTIFACTS_DIR / f"{base_name}{_detect_extension(payload)}"
    output_path.write_bytes(payload)
    return str(output_path)


def main() -> None:
    init_session_state()
    config = load_app_config()
    client = get_client()
    processing_service = get_processing_service()
    image_bytes = SOURCE_IMAGE.read_bytes()

    analysis_started = time.perf_counter()
    analysis = analyze_image(image_bytes, model=get_model_role_value(config, "image_analysis"), client=client)
    analysis_elapsed = time.perf_counter() - analysis_started

    summary: dict[str, Any] = {
        "source": str(SOURCE_IMAGE),
        "analysis": {
            "image_type": analysis.image_type,
            "prompt_key": analysis.prompt_key,
            "render_strategy": analysis.render_strategy,
            "semantic_redraw_allowed": analysis.semantic_redraw_allowed,
            "analysis_elapsed_seconds": round(analysis_elapsed, 3),
        },
        "modes": {},
    }

    for mode in ["safe", "semantic_redraw_direct", "semantic_redraw_structured"]:
        started = time.perf_counter()
        candidate = generate_image_candidate(
            image_bytes,
            analysis,
            mode=mode,
            client=client,
            prefer_deterministic_reconstruction=bool(config.get("prefer_deterministic_reconstruction", True)),
            reconstruction_model=get_model_role_value(config, "image_reconstruction"),
            reconstruction_render_config=_build_reconstruction_render_config(config),
            model_config=config,
        )
        elapsed = time.perf_counter() - started
        summary["modes"][mode] = {
            "path": _write_artifact(f"pic1_lietaer_{mode}", candidate),
            "bytes_out": len(candidate),
            "mime_type": detect_image_mime_type(candidate),
            "generation_elapsed_seconds": round(elapsed, 3),
        }

    asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=image_bytes,
        mime_type=detect_image_mime_type(image_bytes),
        position_index=0,
    )
    compare_started = time.perf_counter()
    compare_assets = processing_service.process_document_images(
        image_assets=[asset],
        image_mode="compare_all",
        config=config,
        on_progress=lambda **kwargs: None,
        client=client,
    )
    compare_elapsed = time.perf_counter() - compare_started
    compare_asset = compare_assets[0]
    compare_variants: dict[str, object] = {}
    for variant_name, variant in compare_asset.comparison_variants.items():
        payload = get_image_variant_bytes(variant)
        if not payload:
            continue
        compare_variants[variant_name] = {
            "path": _write_artifact(f"pic1_lietaer_compare_all_{variant_name}", payload),
            "bytes_out": len(payload),
            "mime_type": detect_image_mime_type(payload),
        }

    summary["compare_all"] = {
        "generation_elapsed_seconds": round(compare_elapsed, 3),
        "selected_compare_variant": compare_asset.selected_compare_variant,
        "final_variant": compare_asset.final_variant,
        "final_decision": compare_asset.final_decision,
        "variants": compare_variants,
    }

    summary_path = ARTIFACTS_DIR / "pic1_lietaer_mode_comparison.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
