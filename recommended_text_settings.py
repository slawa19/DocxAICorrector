from __future__ import annotations

from typing import TypedDict

from text_transform_assessment import TextTransformAssessment


TEXT_SETTINGS_FIELDS = (
    "processing_operation",
    "source_language",
    "target_language",
)


class RecommendedTextSettings(TypedDict):
    file_token: str
    processing_operation: str
    source_language: str
    target_language: str
    reason_summary: str | None


class ManualTextSettingsOverride(TypedDict):
    file_token: str
    processing_operation: bool
    source_language: bool
    target_language: bool


def build_empty_manual_text_settings_override(file_token: str) -> ManualTextSettingsOverride:
    return {
        "file_token": file_token,
        "processing_operation": False,
        "source_language": False,
        "target_language": False,
    }


def normalize_manual_text_settings_override(
    raw_state: object,
    *,
    file_token: str,
) -> ManualTextSettingsOverride:
    if not isinstance(raw_state, dict) or str(raw_state.get("file_token", "")) != file_token:
        return build_empty_manual_text_settings_override(file_token)
    return {
        "file_token": file_token,
        "processing_operation": bool(raw_state.get("processing_operation", False)),
        "source_language": bool(raw_state.get("source_language", False)),
        "target_language": bool(raw_state.get("target_language", False)),
    }


def normalize_recommendation_snapshot(
    raw_state: object,
    *,
    file_token: str,
) -> dict[str, str] | None:
    if not isinstance(raw_state, dict) or str(raw_state.get("file_token", "")) != file_token:
        return None
    processing_operation = str(raw_state.get("processing_operation", "")).strip()
    source_language = str(raw_state.get("source_language", "")).strip()
    target_language = str(raw_state.get("target_language", "")).strip()
    if not processing_operation or not source_language or not target_language:
        return None
    return {
        "file_token": file_token,
        "processing_operation": processing_operation,
        "source_language": source_language,
        "target_language": target_language,
    }


def mark_manual_overrides_from_baseline(
    manual_override: ManualTextSettingsOverride,
    *,
    current_settings: dict[str, str],
    baseline_settings: dict[str, str],
    source_visible: bool,
) -> ManualTextSettingsOverride:
    updated = dict(manual_override)
    if current_settings["processing_operation"] != baseline_settings["processing_operation"]:
        updated["processing_operation"] = True
    if current_settings["target_language"] != baseline_settings["target_language"]:
        updated["target_language"] = True
    if current_settings["source_language"] != baseline_settings["source_language"]:
        updated["source_language"] = True
    return updated  # type: ignore[return-value]


def mark_manual_overrides_from_recommendation(
    manual_override: ManualTextSettingsOverride,
    *,
    current_settings: dict[str, str],
    recommended_settings: RecommendedTextSettings,
    source_visible: bool,
) -> ManualTextSettingsOverride:
    updated = dict(manual_override)
    if current_settings["processing_operation"] != recommended_settings["processing_operation"]:
        updated["processing_operation"] = True
    if current_settings["target_language"] != recommended_settings["target_language"]:
        updated["target_language"] = True
    if current_settings["source_language"] != recommended_settings["source_language"]:
        updated["source_language"] = True
    return updated  # type: ignore[return-value]


def mark_manual_overrides_from_snapshot(
    manual_override: ManualTextSettingsOverride,
    *,
    current_settings: dict[str, str],
    applied_snapshot: dict[str, str] | None,
) -> ManualTextSettingsOverride:
    if applied_snapshot is None:
        return manual_override
    updated = dict(manual_override)
    if current_settings["processing_operation"] != applied_snapshot["processing_operation"]:
        updated["processing_operation"] = True
    if current_settings["target_language"] != applied_snapshot["target_language"]:
        updated["target_language"] = True
    if current_settings["source_language"] != applied_snapshot["source_language"]:
        updated["source_language"] = True
    return updated  # type: ignore[return-value]


def derive_recommended_text_settings(
    *,
    file_token: str,
    assessment: TextTransformAssessment,
    current_settings: dict[str, str],
) -> RecommendedTextSettings:
    current_operation = current_settings["processing_operation"]
    current_source = current_settings["source_language"]
    current_target = current_settings["target_language"]
    dominant_language = assessment["dominant_language"]
    target_language_script_match = assessment["target_language_script_match"]

    recommended_operation = current_operation
    reason_summary: str | None = None
    if dominant_language == current_target:
        recommended_operation = "edit"
        reason_summary = "text already looks like target-language content"
    elif target_language_script_match is False:
        recommended_operation = "translate"
        reason_summary = "text does not appear to match target-language content"

    recommended_source = current_source
    if recommended_operation == "translate":
        if dominant_language and dominant_language != current_target:
            recommended_source = dominant_language
        else:
            recommended_source = "auto"
            if reason_summary is None:
                reason_summary = "source language is ambiguous; auto is safer"

    return {
        "file_token": file_token,
        "processing_operation": recommended_operation,
        "source_language": recommended_source,
        "target_language": current_target,
        "reason_summary": reason_summary,
    }
