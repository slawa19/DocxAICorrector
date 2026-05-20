from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = PROJECT_ROOT / ".run"
PRE_PROJECTION_DIR = RUN_DIR / "structure_maps_stage2_pre_projection"
PROVIDER_NATIVE_DIR = RUN_DIR / "structure_maps_stage2_provider_native"
RAW_WINDOW_DIR = RUN_DIR / "structure_maps_stage2_raw_window"
MANUAL_INVESTIGATION_ROOT = RUN_DIR / "manual_investigations" / "structure_drift"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_json_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _resolve_cache_key(explicit_cache_key: str | None) -> str:
    if explicit_cache_key:
        return explicit_cache_key
    candidates = sorted(PRE_PROJECTION_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No pre-projection artifacts found in {PRE_PROJECTION_DIR}")
    return candidates[0].stem


def _resolve_artifact_path(directory: Path, cache_key: str) -> Path:
    path = directory / f"{cache_key}.json"
    if not path.exists():
        raise FileNotFoundError(f"Expected artifact missing: {path}")
    return path


def _extract_provider_texts(provider_native_response: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    output_items = provider_native_response.get("output")
    if not isinstance(output_items, list):
        return texts
    for output_item in output_items:
        if not isinstance(output_item, dict):
            continue
        content_items = output_item.get("content")
        if not isinstance(content_items, list):
            continue
        for content_item in content_items:
            if not isinstance(content_item, dict):
                continue
            text_payload = content_item.get("text")
            if isinstance(text_payload, str):
                texts.append(text_payload)
                continue
            if not isinstance(text_payload, dict):
                continue
            value = text_payload.get("value")
            if isinstance(value, str):
                texts.append(value)
    return texts


def _coerce_native_payload_object(payload: object) -> object | None:
    if payload is None:
        return None
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except Exception:
            return payload
    return payload


def _extract_texts_from_native_payload(payload: object | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    return _extract_provider_texts(payload)


def _build_window_summary(
    *,
    pre_projection_window: dict[str, Any],
    provider_native_window: dict[str, Any],
    raw_window: dict[str, Any],
) -> dict[str, Any]:
    provider_native_response = provider_native_window.get("provider_native_response")
    provider_texts = _extract_provider_texts(provider_native_response if isinstance(provider_native_response, dict) else {})
    provider_joined_text = "\n\n".join(provider_texts)

    collected_texts_raw = raw_window.get("collected_texts")
    collected_texts = [item for item in collected_texts_raw if isinstance(item, str)] if isinstance(collected_texts_raw, list) else []
    collected_joined_text = "\n\n".join(collected_texts)
    raw_output_text = raw_window.get("raw_output_text") if isinstance(raw_window.get("raw_output_text"), str) else ""
    normalized_content = raw_window.get("normalized_content") if isinstance(raw_window.get("normalized_content"), str) else ""

    native_payload_object = _coerce_native_payload_object(pre_projection_window.get("native_serialized_payload"))
    native_payload_texts = _extract_texts_from_native_payload(native_payload_object)
    native_payload_joined_text = "\n\n".join(native_payload_texts)
    provider_reference_text = provider_texts[0] if provider_texts else provider_joined_text
    raw_reference_text = raw_output_text or collected_joined_text

    return {
        "current_window": pre_projection_window.get("current_window"),
        "attempt_source": pre_projection_window.get("attempt_source"),
        "fallback_depth": pre_projection_window.get("fallback_depth"),
        "descriptor_count": pre_projection_window.get("descriptor_count"),
        "total_tokens_used": pre_projection_window.get("total_tokens_used"),
        "serialization_strategy": pre_projection_window.get("serialization_strategy"),
        "native_serialized_hash": pre_projection_window.get("native_serialized_hash"),
        "native_serialized_char_count": pre_projection_window.get("native_serialized_char_count"),
        "provider_text_count": len(provider_texts),
        "provider_text_sha256": _sha256_text(provider_joined_text) if provider_joined_text else None,
        "raw_output_text_sha256": _sha256_text(raw_output_text) if raw_output_text else None,
        "collected_texts_sha256": _sha256_text(collected_joined_text) if collected_joined_text else None,
        "normalized_content_sha256": _sha256_text(normalized_content) if normalized_content else None,
        "provider_text_equals_raw_output_text": bool(provider_joined_text) and provider_joined_text == raw_output_text,
        "provider_text_equals_collected_texts": bool(provider_joined_text) and provider_joined_text == collected_joined_text,
        "raw_output_text_equals_normalized_content": bool(raw_output_text) and raw_output_text == normalized_content,
        "native_payload_text_count": len(native_payload_texts),
        "native_payload_text_sha256": _sha256_text(native_payload_joined_text) if native_payload_joined_text else None,
        "native_payload_matches_provider_text": bool(provider_joined_text)
        and provider_joined_text == native_payload_joined_text,
        "native_payload_matches_raw_output_text": bool(raw_reference_text)
        and raw_reference_text == native_payload_joined_text,
        "native_payload_contains_provider_text": (
            provider_reference_text in native_payload_texts if provider_reference_text else None
        ),
        "native_payload_contains_raw_output_text": (
            raw_reference_text in native_payload_texts if raw_reference_text else None
        ),
    }


def _render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Pre-Projection Drift Boundary Inspection",
        "",
        f"- Generated at: {summary['generated_at_utc']}",
        f"- Cache key: {summary['cache_key']}",
        f"- Decision: {summary['decision']}",
        "",
        "## Confirmed",
    ]
    lines.extend(f"- {item}" for item in summary["confirmed"])
    lines.append("")
    lines.append("## Partially Confirmed")
    lines.extend(f"- {item}" for item in summary["partially_confirmed"])
    lines.append("")
    lines.append("## Unconfirmed")
    lines.extend(f"- {item}" for item in summary["unconfirmed"])
    lines.append("")
    lines.append("## Source Artifacts")
    for name, value in summary["source_artifacts"].items():
        lines.append(f"- {name}: {value}")
    lines.append("")
    lines.append("## Bundle Artifacts")
    for name, value in summary["bundle_artifacts"].items():
        lines.append(f"- {name}: {value}")
    lines.append("")
    lines.append("## Window Checks")
    for window in summary["window_summaries"]:
        lines.append(f"- window={window['current_window']} strategy={window['serialization_strategy']} provider==raw={window['provider_text_equals_raw_output_text']} provider==collected={window['provider_text_equals_collected_texts']} native_matches_provider={window['native_payload_matches_provider_text']}")
    lines.append("")
    lines.append("## Immediate Outcome")
    if summary["decision"] == "current_saved_boundary_sufficient_for_now":
        lines.append("- Current saved evidence at the pre-projection boundary is sufficiently explicit for now; a deeper package below `to_json()` is not the immediate next package.")
    else:
        lines.append("- The current saved boundary is not explicit enough; a deeper transport-closest package below `to_json()` is justified as the immediate next package.")
    return "\n".join(lines) + "\n"


def inspect_pre_projection_drift_boundary(*, cache_key: str | None, label: str | None) -> dict[str, Any]:
    resolved_cache_key = _resolve_cache_key(cache_key)
    pre_projection_path = _resolve_artifact_path(PRE_PROJECTION_DIR, resolved_cache_key)
    provider_native_path = _resolve_artifact_path(PROVIDER_NATIVE_DIR, resolved_cache_key)
    raw_window_path = _resolve_artifact_path(RAW_WINDOW_DIR, resolved_cache_key)

    pre_projection_payload = _load_json(pre_projection_path)
    provider_native_payload = _load_json(provider_native_path)
    raw_window_payload = _load_json(raw_window_path)

    pre_projection_windows = pre_projection_payload.get("pre_projection_windows")
    provider_native_windows = provider_native_payload.get("provider_native_windows")
    raw_windows = raw_window_payload.get("raw_windows")
    if not isinstance(pre_projection_windows, list) or not isinstance(provider_native_windows, list) or not isinstance(raw_windows, list):
        raise ValueError("Expected window lists in saved Stage 2 artifacts")
    if not (len(pre_projection_windows) == len(provider_native_windows) == len(raw_windows)):
        raise ValueError("Saved Stage 2 artifact window counts do not match")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle_name = label or f"pre_projection_boundary_{timestamp}_{resolved_cache_key[:12]}"
    bundle_dir = MANUAL_INVESTIGATION_ROOT / bundle_name
    artifacts_dir = bundle_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=False)

    copied_pre_projection = artifacts_dir / f"pre_projection_{pre_projection_path.name}"
    copied_provider_native = artifacts_dir / f"provider_native_{provider_native_path.name}"
    copied_raw_window = artifacts_dir / f"raw_window_{raw_window_path.name}"
    shutil.copy2(pre_projection_path, copied_pre_projection)
    shutil.copy2(provider_native_path, copied_provider_native)
    shutil.copy2(raw_window_path, copied_raw_window)

    window_summaries = [
        _build_window_summary(
            pre_projection_window=pre_projection_window,
            provider_native_window=provider_native_window,
            raw_window=raw_window,
        )
        for pre_projection_window, provider_native_window, raw_window in zip(
            pre_projection_windows,
            provider_native_windows,
            raw_windows,
            strict=True,
        )
        if isinstance(pre_projection_window, dict)
        and isinstance(provider_native_window, dict)
        and isinstance(raw_window, dict)
    ]

    confirmed = [
        "Current saved Stage 2 pre-projection artifact exists and is persisted separately from later derived views.",
        "Current saved provider-native Stage 2 artifact exists and preserves projected response fields adjacent to the pre-projection payload.",
        "Current saved raw-window Stage 2 artifact exists and preserves the traversal/raw text consumed after the pre-projection boundary.",
    ]
    partially_confirmed = [
        "The saved boundary now makes the SDK-native `to_json()` serialization inspectable together with adjacent projected and traversal views.",
        "This bundle makes the current reviewer-safe boundary classification repeatable from saved artifacts without reopening fixture refresh or broader runtime work.",
    ]
    unconfirmed = [
        "True wire-level upstream/provider payload drift remains unconfirmed.",
        "Whether the earliest divergence comes from upstream variability or SDK `to_json()` serialization behavior remains unconfirmed.",
    ]

    alignment_ok = bool(window_summaries) and all(
        window["provider_text_equals_raw_output_text"]
        and window["provider_text_equals_collected_texts"]
        and window["raw_output_text_equals_normalized_content"]
        and window["native_payload_matches_provider_text"]
        for window in window_summaries
    )

    if alignment_ok:
        confirmed.append(
            "Within the saved bundle, provider-native text and raw-window traversal text are identical, and the same text is already present inside the saved SDK-native serialized payload."
        )
        decision = "current_saved_boundary_sufficient_for_now"
    else:
        partially_confirmed.append(
            "At least one saved window did not align provider-native, traversal, and serialized-payload views inside the current bundle."
        )
        decision = "deeper_transport_closest_package_required"

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "cache_key": resolved_cache_key,
        "decision": decision,
        "source_artifacts": {
            "pre_projection": str(pre_projection_path.relative_to(PROJECT_ROOT)),
            "provider_native": str(provider_native_path.relative_to(PROJECT_ROOT)),
            "raw_window": str(raw_window_path.relative_to(PROJECT_ROOT)),
        },
        "bundle_artifacts": {
            "bundle_dir": str(bundle_dir.relative_to(PROJECT_ROOT)),
            "summary_json": str((bundle_dir / "summary.json").relative_to(PROJECT_ROOT)),
            "summary_md": str((bundle_dir / "summary.md").relative_to(PROJECT_ROOT)),
            "copied_pre_projection": str(copied_pre_projection.relative_to(PROJECT_ROOT)),
            "copied_provider_native": str(copied_provider_native.relative_to(PROJECT_ROOT)),
            "copied_raw_window": str(copied_raw_window.relative_to(PROJECT_ROOT)),
        },
        "window_summaries": window_summaries,
        "confirmed": confirmed,
        "partially_confirmed": partially_confirmed,
        "unconfirmed": unconfirmed,
    }
    (bundle_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (bundle_dir / "summary.md").write_text(_render_summary_markdown(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect the saved pre-projection drift boundary and copy the current Stage 2 artifact triplet into a manual investigation bundle.")
    parser.add_argument("--cache-key", help="Explicit structure-recognition cache key to inspect. Defaults to the latest saved pre-projection artifact.")
    parser.add_argument("--label", help="Optional manual bundle label under .run/manual_investigations/structure_drift/.")
    args = parser.parse_args()

    summary = inspect_pre_projection_drift_boundary(cache_key=args.cache_key, label=args.label)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
