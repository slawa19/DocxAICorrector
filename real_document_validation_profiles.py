from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "corpus_registry.toml"
_SUPPORTED_TIERS = {"extraction", "structural", "full"}
_SUPPORTED_STRUCTURAL_MODES = {"strict", "tolerant"}


@dataclass(frozen=True)
class DocumentProfile:
    id: str
    source_path: str
    artifact_prefix: str = "real_document_validation"
    output_basename: str | None = None
    structural_mode: str = "strict"
    min_paragraphs: int = 1
    has_headings: bool = False
    min_headings: int = 0
    has_numbered_lists: bool = False
    min_numbered_items: int = 0
    has_images: bool = False
    min_images: int = 0
    has_tables: bool = False
    min_tables: int = 0
    max_formatting_diagnostics: int = 0
    max_unmapped_source_paragraphs: int = 0
    max_unmapped_target_paragraphs: int = 0
    max_heading_level_drift: int = 1
    min_text_similarity: float = 0.98
    min_merged_groups: int = 0
    min_merged_raw_paragraphs: int = 0
    require_numbered_lists_preserved: bool = False
    require_nonempty_output: bool = True
    forbid_heading_only_collapse: bool = False
    default_run_profile: str | None = None
    tags: tuple[str, ...] = ()
    provenance: str = ""
    tolerance_reason: str | None = None

    def resolved_source_path(self, project_root: Path | None = None) -> Path:
        base_path = PROJECT_ROOT if project_root is None else project_root
        return (base_path / self.source_path).resolve()


@dataclass(frozen=True)
class RunProfile:
    id: str
    tier: str = "full"
    mode: str = "regression"
    model: str | None = None
    chunk_size: int | None = None
    max_retries: int | None = None
    image_mode: str | None = None
    enable_paragraph_markers: bool | None = None
    keep_all_image_variants: bool | None = None
    repeat_count: int = 1


@dataclass(frozen=True)
class ValidationRegistry:
    documents: tuple[DocumentProfile, ...]
    run_profiles: tuple[RunProfile, ...]

    def get_document_profile(self, profile_id: str) -> DocumentProfile:
        for profile in self.documents:
            if profile.id == profile_id:
                return profile
        raise KeyError(f"Unknown document profile: {profile_id}")

    def get_run_profile(self, profile_id: str) -> RunProfile:
        for profile in self.run_profiles:
            if profile.id == profile_id:
                return profile
        raise KeyError(f"Unknown run profile: {profile_id}")

    def resolve_run_profile(self, document_profile: DocumentProfile, run_profile_id: str | None = None) -> RunProfile:
        if run_profile_id:
            return self.get_run_profile(run_profile_id)
        if document_profile.default_run_profile:
            return self.get_run_profile(document_profile.default_run_profile)
        raise KeyError(f"Document profile {document_profile.id} does not declare default_run_profile")


@dataclass(frozen=True)
class ResolvedRuntimeConfig:
    model: str
    chunk_size: int
    max_retries: int
    image_mode: str
    enable_paragraph_markers: bool
    keep_all_image_variants: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "chunk_size": self.chunk_size,
            "max_retries": self.max_retries,
            "image_mode": self.image_mode,
            "enable_paragraph_markers": self.enable_paragraph_markers,
            "keep_all_image_variants": self.keep_all_image_variants,
        }


@dataclass(frozen=True)
class RuntimeResolution:
    effective: ResolvedRuntimeConfig
    ui_defaults: ResolvedRuntimeConfig
    overrides: dict[str, object]


@lru_cache(maxsize=1)
def load_validation_registry(registry_path: str | Path | None = None) -> ValidationRegistry:
    path = DEFAULT_REGISTRY_PATH if registry_path is None else Path(registry_path)
    payload = tomllib.loads(path.read_text(encoding="utf-8"))

    documents = tuple(_build_document_profile(item) for item in payload.get("documents", []))
    run_profiles = tuple(_build_run_profile(item) for item in payload.get("run_profiles", []))
    if not documents:
        raise RuntimeError(f"Validation registry has no documents: {path}")
    if not run_profiles:
        raise RuntimeError(f"Validation registry has no run profiles: {path}")
    return ValidationRegistry(documents=documents, run_profiles=run_profiles)


def resolve_runtime_resolution(app_config, run_profile: RunProfile) -> RuntimeResolution:
    ui_defaults = ResolvedRuntimeConfig(
        model=str(app_config.default_model),
        chunk_size=int(app_config.chunk_size),
        max_retries=int(app_config.max_retries),
        image_mode=str(app_config.image_mode_default),
        enable_paragraph_markers=bool(app_config.enable_paragraph_markers),
        keep_all_image_variants=bool(app_config.keep_all_image_variants),
    )
    effective = ResolvedRuntimeConfig(
        model=run_profile.model or ui_defaults.model,
        chunk_size=run_profile.chunk_size if run_profile.chunk_size is not None else ui_defaults.chunk_size,
        max_retries=run_profile.max_retries if run_profile.max_retries is not None else ui_defaults.max_retries,
        image_mode=run_profile.image_mode or ui_defaults.image_mode,
        enable_paragraph_markers=(
            run_profile.enable_paragraph_markers
            if run_profile.enable_paragraph_markers is not None
            else ui_defaults.enable_paragraph_markers
        ),
        keep_all_image_variants=(
            run_profile.keep_all_image_variants
            if run_profile.keep_all_image_variants is not None
            else ui_defaults.keep_all_image_variants
        ),
    )
    explicit_profile_overrides = {
        "model": run_profile.model,
        "chunk_size": run_profile.chunk_size,
        "max_retries": run_profile.max_retries,
        "image_mode": run_profile.image_mode,
        "enable_paragraph_markers": run_profile.enable_paragraph_markers,
        "keep_all_image_variants": run_profile.keep_all_image_variants,
    }
    overrides: dict[str, object] = {
        key: value for key, value in explicit_profile_overrides.items() if value is not None
    }
    for key, default_value in ui_defaults.to_dict().items():
        effective_value = effective.to_dict()[key]
        if effective_value != default_value:
            overrides[key] = effective_value
    return RuntimeResolution(effective=effective, ui_defaults=ui_defaults, overrides=overrides)


def apply_runtime_resolution_to_app_config(app_config, resolution: RuntimeResolution) -> dict[str, object]:
    app_config_dict = app_config.to_dict()
    app_config_dict.update(resolution.effective.to_dict())
    return app_config_dict


def _build_document_profile(payload: Any) -> DocumentProfile:
    if not isinstance(payload, dict):
        raise RuntimeError(f"Document profile must be a table, got: {type(payload).__name__}")
    structural_mode = str(payload.get("structural_mode", "strict"))
    if structural_mode not in _SUPPORTED_STRUCTURAL_MODES:
        raise RuntimeError(f"Unsupported structural_mode: {structural_mode}")
    has_headings = _coerce_bool(payload, "has_headings", False)
    has_numbered_lists = _coerce_bool(payload, "has_numbered_lists", False)
    has_images = _coerce_bool(payload, "has_images", False)
    has_tables = _coerce_bool(payload, "has_tables", False)
    profile = DocumentProfile(
        id=_require_str(payload, "id"),
        source_path=_require_str(payload, "source_path"),
        artifact_prefix=_require_str(payload, "artifact_prefix", default="real_document_validation"),
        output_basename=_optional_str(payload, "output_basename"),
        structural_mode=structural_mode,
        min_paragraphs=_coerce_int(payload, "min_paragraphs", 1),
        has_headings=has_headings,
        min_headings=_coerce_int(payload, "min_headings", 1 if has_headings else 0),
        has_numbered_lists=has_numbered_lists,
        min_numbered_items=_coerce_int(payload, "min_numbered_items", 1 if has_numbered_lists else 0),
        has_images=has_images,
        min_images=_coerce_int(payload, "min_images", 1 if has_images else 0),
        has_tables=has_tables,
        min_tables=_coerce_int(payload, "min_tables", 1 if has_tables else 0),
        max_formatting_diagnostics=_coerce_int(payload, "max_formatting_diagnostics", 0),
        max_unmapped_source_paragraphs=_coerce_int(payload, "max_unmapped_source_paragraphs", 0),
        max_unmapped_target_paragraphs=_coerce_int(payload, "max_unmapped_target_paragraphs", 0),
        max_heading_level_drift=_coerce_int(payload, "max_heading_level_drift", 1),
        min_text_similarity=_coerce_float(payload, "min_text_similarity", 0.98),
        min_merged_groups=_coerce_int(payload, "min_merged_groups", 0),
        min_merged_raw_paragraphs=_coerce_int(payload, "min_merged_raw_paragraphs", 0),
        require_numbered_lists_preserved=_coerce_bool(payload, "require_numbered_lists_preserved", has_numbered_lists),
        require_nonempty_output=_coerce_bool(payload, "require_nonempty_output", True),
        forbid_heading_only_collapse=_coerce_bool(payload, "forbid_heading_only_collapse", False),
        default_run_profile=_optional_str(payload, "default_run_profile"),
        tags=tuple(_coerce_str_list(payload, "tags")),
        provenance=_require_str(payload, "provenance", default=""),
        tolerance_reason=_optional_str(payload, "tolerance_reason"),
    )
    if profile.structural_mode == "tolerant" and not profile.tolerance_reason:
        raise RuntimeError(f"Tolerant profile {profile.id} requires tolerance_reason")
    return profile


def _build_run_profile(payload: Any) -> RunProfile:
    if not isinstance(payload, dict):
        raise RuntimeError(f"Run profile must be a table, got: {type(payload).__name__}")
    tier = _require_str(payload, "tier", default="full")
    if tier not in _SUPPORTED_TIERS:
        raise RuntimeError(f"Unsupported validation tier: {tier}")
    repeat_count = _coerce_int(payload, "repeat_count", 1)
    if repeat_count < 1:
        raise RuntimeError(f"Run profile repeat_count must be >= 1, got {repeat_count}")
    return RunProfile(
        id=_require_str(payload, "id"),
        tier=tier,
        mode=_require_str(payload, "mode", default="regression"),
        model=_optional_str(payload, "model"),
        chunk_size=_optional_int(payload, "chunk_size"),
        max_retries=_optional_int(payload, "max_retries"),
        image_mode=_optional_str(payload, "image_mode"),
        enable_paragraph_markers=_optional_bool(payload, "enable_paragraph_markers"),
        keep_all_image_variants=_optional_bool(payload, "keep_all_image_variants"),
        repeat_count=repeat_count,
    )


def _require_str(payload: dict[str, Any], key: str, *, default: str | None = None) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Registry field {key} must be a non-empty string")
    return value.strip()


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Registry field {key} must be a non-empty string when provided")
    return value.strip()


def _coerce_int(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    if not isinstance(value, int):
        raise RuntimeError(f"Registry field {key} must be an integer")
    return value


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise RuntimeError(f"Registry field {key} must be an integer when provided")
    return value


def _coerce_float(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    if not isinstance(value, (int, float)):
        raise RuntimeError(f"Registry field {key} must be numeric")
    return float(value)


def _coerce_bool(payload: dict[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise RuntimeError(f"Registry field {key} must be a boolean")
    return value


def _optional_bool(payload: dict[str, Any], key: str) -> bool | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise RuntimeError(f"Registry field {key} must be a boolean when provided")
    return value


def _coerce_str_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RuntimeError(f"Registry field {key} must be a list of strings")
    return [item.strip() for item in value if item.strip()]
