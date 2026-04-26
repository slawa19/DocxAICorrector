import builtins
import re
from enum import StrEnum
from dataclasses import asdict, dataclass, field
from typing import Any, cast


_UNSET = object()


EXPLICIT_LIST_MARKER_PATTERN = re.compile(r"^(?:\s*[-*•]\s+|\s*\d+[\.)]\s+)")
EXPLICIT_HEADING_PATTERN = re.compile(r"^#{1,6}\s+")


class ImageMode(StrEnum):
    NO_CHANGE = "no_change"
    SAFE = "safe"
    SEMANTIC_REDRAW_DIRECT = "semantic_redraw_direct"
    SEMANTIC_REDRAW_STRUCTURED = "semantic_redraw_structured"
    COMPARE_ALL = "compare_all"


IMAGE_MODE_VALUES = tuple(mode.value for mode in ImageMode)
SEMANTIC_IMAGE_MODE_VALUES = (
    ImageMode.SEMANTIC_REDRAW_DIRECT.value,
    ImageMode.SEMANTIC_REDRAW_STRUCTURED.value,
)
DOCX_COMPARE_VARIANT_MODE_VALUES = (
    ImageMode.SAFE.value,
    ImageMode.SEMANTIC_REDRAW_DIRECT.value,
    ImageMode.SEMANTIC_REDRAW_STRUCTURED.value,
)
PARAGRAPH_BOUNDARY_NORMALIZATION_MODE_VALUES = ("off", "high_only", "high_and_medium")
PARAGRAPH_BOUNDARY_AI_REVIEW_MODE_VALUES = ("off", "review_only")
RELATION_NORMALIZATION_PROFILE_VALUES = ("phase2_default",)
RELATION_NORMALIZATION_KIND_VALUES = (
    "image_caption",
    "table_caption",
    "epigraph_attribution",
    "toc_region",
)
STRUCTURE_RECOGNITION_MIN_CONFIDENCE_VALUES = ("medium", "high")


@dataclass(frozen=True)
class RawParagraph:
    raw_index: int
    text: str
    style_name: str
    paragraph_properties_xml: str | None = None
    paragraph_alignment: str | None = None
    is_bold: bool = False
    is_italic: bool = False
    font_size_pt: float | None = None
    explicit_heading_level: int | None = None
    heading_level: int | None = None
    heading_source: str | None = None
    list_kind: str | None = None
    list_level: int = 0
    list_numbering_format: str | None = None
    list_num_id: str | None = None
    list_abstract_num_id: str | None = None
    list_num_xml: str | None = None
    list_abstract_num_xml: str | None = None
    role_hint: str = "body"
    source_xml_fingerprint: str | None = None
    origin_raw_indexes: tuple[int, ...] = ()
    origin_raw_texts: tuple[str, ...] = ()
    layout_origin: str = "paragraph"
    boundary_source: str = "raw"
    boundary_confidence: str = "explicit"
    boundary_rationale: str | None = None


@dataclass(frozen=True)
class RawTable:
    raw_index: int
    html_text: str
    asset_id: str


RawBlock = RawParagraph | RawTable


@dataclass(frozen=True)
class ParagraphBoundaryDecision:
    left_raw_index: int
    right_raw_index: int
    decision: str
    confidence: str
    reasons: tuple[str, ...]


@dataclass
class ParagraphBoundaryNormalizationReport:
    total_raw_paragraphs: int
    total_logical_paragraphs: int
    merged_group_count: int
    merged_raw_paragraph_count: int
    decisions: list[ParagraphBoundaryDecision] = field(default_factory=list)


@dataclass(frozen=True)
class ParagraphRelationDecision:
    relation_kind: str
    decision: str
    member_paragraph_ids: tuple[str, ...]
    anchor_asset_id: str | None = None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParagraphRelation:
    relation_id: str
    relation_kind: str
    member_paragraph_ids: tuple[str, ...]
    anchor_asset_id: str | None = None
    confidence: str = "high"
    rationale: tuple[str, ...] = ()


@dataclass
class RelationNormalizationReport:
    total_relations: int
    relation_counts: dict[str, int]
    rejected_candidate_count: int
    decisions: list[ParagraphRelationDecision] = field(default_factory=list)


@dataclass(frozen=True)
class LayoutArtifactCleanupDecision:
    original_source_index: int
    original_paragraph_id: str
    origin_raw_indexes: tuple[int, ...]
    text_preview: str
    action: str
    reason: str
    confidence: str
    normalized_text: str
    repeat_count: int = 1


@dataclass
class LayoutArtifactCleanupReport:
    original_paragraph_count: int
    cleaned_paragraph_count: int
    removed_paragraph_count: int
    removed_page_number_count: int
    removed_repeated_artifact_count: int
    removed_empty_or_whitespace_count: int
    decisions: list[LayoutArtifactCleanupDecision] = field(default_factory=list)
    cleanup_applied: bool = False
    skipped_reason: str | None = None
    error_code: str | None = None


@dataclass
class ParagraphUnit:
    text: str
    role: str
    asset_id: str | None = None
    attached_to_asset_id: str | None = None
    paragraph_properties_xml: str | None = None
    paragraph_alignment: str | None = None
    heading_level: int | None = None
    heading_source: str | None = None
    list_kind: str | None = None
    list_level: int = 0
    list_numbering_format: str | None = None
    list_num_id: str | None = None
    list_abstract_num_id: str | None = None
    list_num_xml: str | None = None
    list_abstract_num_xml: str | None = None
    paragraph_id: str = ""
    source_index: int = -1
    structural_role: str = "body"
    role_confidence: str = "heuristic"
    style_name: str = ""
    is_bold: bool = False
    is_italic: bool = False
    font_size_pt: float | None = None
    origin_raw_indexes: list[int] = field(default_factory=list)
    origin_raw_texts: list[str] = field(default_factory=list)
    layout_origin: str = "paragraph"
    boundary_source: str = "raw"
    boundary_confidence: str = "explicit"
    boundary_rationale: str | None = None

    @property
    def rendered_text(self) -> str:
        if self.role == "heading" and self.heading_level is not None and not EXPLICIT_HEADING_PATTERN.match(self.text):
            level = min(max(self.heading_level, 1), 6)
            return f"{'#' * level} {self.text}"

        if self.structural_role in {"epigraph", "attribution", "dedication"}:
            lines = self.text.splitlines() or [self.text]
            if all(line.lstrip().startswith(">") for line in lines if line.strip()):
                return self.text
            return "\n".join(">" if not line.strip() else f"> {line}" for line in lines)

        if self.role != "list" or EXPLICIT_LIST_MARKER_PATTERN.match(self.text):
            return self.text

        indent = "  " * max(0, self.list_level)
        marker = "1." if self.list_kind == "ordered" else "-"
        return f"{indent}{marker} {self.text}"


@dataclass(frozen=True)
class ParagraphDescriptor:
    index: int
    text_preview: str
    text_length: int
    style_name: str
    is_bold: bool
    is_centered: bool
    is_all_caps: bool
    font_size_pt: float | None
    has_numbering: bool
    explicit_heading_level: int | None

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "i": self.index,
            "t": self.text_preview,
            "len": self.text_length,
            "s": self.style_name,
            "b": self.is_bold,
            "ctr": self.is_centered,
            "caps": self.is_all_caps,
            "pt": self.font_size_pt,
            "num": self.has_numbering,
            "hl": self.explicit_heading_level,
        }


@dataclass(frozen=True)
class ParagraphClassification:
    index: int
    role: str
    heading_level: int | None
    confidence: str
    rationale: str | None = None


@dataclass(frozen=True)
class StructureRecognitionSummary:
    ai_classified_count: int = 0
    ai_heading_count: int = 0
    ai_role_change_count: int = 0
    ai_heading_promotion_count: int = 0
    ai_heading_demotion_count: int = 0
    ai_structural_role_change_count: int = 0

    @classmethod
    def from_source(cls, source: object | None) -> "StructureRecognitionSummary":
        if isinstance(source, cls):
            return source
        return cls(
            ai_classified_count=int(getattr(source, "ai_classified_count", 0) or 0),
            ai_heading_count=int(getattr(source, "ai_heading_count", 0) or 0),
            ai_role_change_count=int(getattr(source, "ai_role_change_count", 0) or 0),
            ai_heading_promotion_count=int(getattr(source, "ai_heading_promotion_count", 0) or 0),
            ai_heading_demotion_count=int(getattr(source, "ai_heading_demotion_count", 0) or 0),
            ai_structural_role_change_count=int(getattr(source, "ai_structural_role_change_count", 0) or 0),
        )

    def as_progress_metrics(self, *, structure_map: "StructureMap | None" = None) -> dict[str, int]:
        metrics: dict[str, int] = {}
        if structure_map is not None:
            metrics["structure_window_count"] = structure_map.window_count
        if self.ai_classified_count:
            metrics["ai_classified"] = self.ai_classified_count
        if self.ai_heading_count:
            metrics["ai_headings"] = self.ai_heading_count
        if self.ai_role_change_count:
            metrics["ai_role_changes"] = self.ai_role_change_count
        if self.ai_heading_promotion_count:
            metrics["ai_heading_promotions"] = self.ai_heading_promotion_count
        if self.ai_heading_demotion_count:
            metrics["ai_heading_demotions"] = self.ai_heading_demotion_count
        if self.ai_structural_role_change_count:
            metrics["ai_structural_role_changes"] = self.ai_structural_role_change_count
        return metrics

    def as_preparation_summary_metrics(self) -> dict[str, int]:
        return {
            "ai_classified": self.ai_classified_count,
            "ai_headings": self.ai_heading_count,
            "ai_role_changes": self.ai_role_change_count,
            "ai_heading_promotions": self.ai_heading_promotion_count,
            "ai_heading_demotions": self.ai_heading_demotion_count,
            "ai_structural_role_changes": self.ai_structural_role_change_count,
        }


@dataclass
class StructureMap:
    classifications: dict[int, ParagraphClassification]
    model_used: str
    total_tokens_used: int
    processing_time_seconds: float
    window_count: int

    def get(self, index: int) -> ParagraphClassification | None:
        return self.classifications.get(index)

    @property
    def classified_count(self) -> int:
        return len(self.classifications)

    @property
    def heading_count(self) -> int:
        return sum(1 for classification in self.classifications.values() if classification.role == "heading")


@dataclass
class DocumentBlock:
    paragraphs: list["ParagraphUnit"]

    @property
    def text(self) -> str:
        return "\n\n".join(paragraph.rendered_text for paragraph in self.paragraphs)


@dataclass
class ImageAnalysisResult:
    image_type: str
    image_subtype: str | None
    contains_text: bool
    semantic_redraw_allowed: bool
    confidence: float
    structured_parse_confidence: float
    prompt_key: str
    render_strategy: str
    structure_summary: str
    extracted_labels: list[str]
    text_node_count: int | None = None
    extracted_text: str = ""
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ImageValidationResult:
    validation_passed: bool
    decision: str
    semantic_match_score: float
    text_match_score: float
    structure_match_score: float
    validator_confidence: float
    missing_labels: list[str]
    added_entities_detected: bool
    suspicious_reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ImagePipelineMetadata:
    source_mime_type: str | None = None
    rendered_mime_type: str | None = None
    source_width_emu: int | None = None
    source_height_emu: int | None = None
    strict_validation_decision: str | None = None
    strict_validation_passed: bool | None = None
    soft_accepted: bool = False
    placeholder_status: str | None = None
    preserve_all_variants_in_docx: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ImageVariantCandidate:
    mode: str
    bytes: builtins.bytes | None = None
    mime_type: str | None = None
    validation_result: "ImageValidationResult | dict[str, object] | None" = None
    validation_status: str = "pending"
    final_decision: str | None = None
    final_variant: str | None = None
    final_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "has_bytes": self.bytes is not None,
            "bytes_size": len(self.bytes) if isinstance(self.bytes, (bytes, bytearray)) else 0,
            "mime_type": self.mime_type,
            "validation_result": (
                self.validation_result.to_dict()
                if isinstance(self.validation_result, ImageValidationResult)
                else self.validation_result
            ),
            "validation_status": self.validation_status,
            "final_decision": self.final_decision,
            "final_variant": self.final_variant,
            "final_reason": self.final_reason,
        }


@dataclass
class ImageRuntimeAttemptState:
    redrawn_bytes: bytes | None = None
    redrawn_mime_type: str | None = None
    validation_result: "ImageValidationResult | dict[str, object] | None" = None
    validation_status: str = "pending"
    attempt_variants: list[ImageVariantCandidate | dict[str, object]] = field(default_factory=list)
    comparison_variants: dict[str, ImageVariantCandidate | dict[str, object]] = field(default_factory=dict)
    selected_compare_variant: str | None = None


@dataclass(frozen=True)
class ImageSourceIdentitySnapshot:
    image_id: str
    placeholder: str
    mime_type: str | None
    position_index: int
    width_emu: int | None = None
    height_emu: int | None = None
    source_mime_type: str | None = None
    source_width_emu: int | None = None
    source_height_emu: int | None = None
    source_forensics: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ImageRuntimeStateSnapshot:
    mode_requested: str | None
    analysis_result: ImageAnalysisResult | dict[str, object] | None
    prompt_key: str | None
    render_strategy: str | None
    safe_bytes_present: bool
    redrawn_bytes_present: bool
    redrawn_mime_type: str | None
    validation_result: ImageValidationResult | dict[str, object] | None
    validation_status: str
    attempt_variants: tuple[ImageVariantCandidate | dict[str, object], ...]
    comparison_variants: dict[str, ImageVariantCandidate | dict[str, object]]
    selected_compare_variant: str | None
    rendered_mime_type: str | None
    strict_validation_decision: str | None
    strict_validation_passed: bool | None
    soft_accepted: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "mode_requested": self.mode_requested,
            "analysis_result": self.analysis_result.to_dict() if isinstance(self.analysis_result, ImageAnalysisResult) else self.analysis_result,
            "prompt_key": self.prompt_key,
            "render_strategy": self.render_strategy,
            "safe_bytes_present": self.safe_bytes_present,
            "redrawn_bytes_present": self.redrawn_bytes_present,
            "redrawn_mime_type": self.redrawn_mime_type,
            "validation_result": self.validation_result.to_dict() if isinstance(self.validation_result, ImageValidationResult) else self.validation_result,
            "validation_status": self.validation_status,
            "attempt_variants": [
                variant.to_dict() if isinstance(variant, ImageVariantCandidate) else variant
                for variant in self.attempt_variants
            ],
            "comparison_variants": {
                key: variant.to_dict() if isinstance(variant, ImageVariantCandidate) else variant
                for key, variant in self.comparison_variants.items()
            },
            "selected_compare_variant": self.selected_compare_variant,
            "rendered_mime_type": self.rendered_mime_type,
            "strict_validation_decision": self.strict_validation_decision,
            "strict_validation_passed": self.strict_validation_passed,
            "soft_accepted": self.soft_accepted,
        }


@dataclass(frozen=True)
class ImageFinalSelectionSnapshot:
    final_decision: str | None
    final_variant: str | None
    final_reason: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ImageDeliveryInsertion:
    label: str | None
    bytes: builtins.bytes
    variant_key: str | None = None
    mime_type: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "variant_key": self.variant_key,
            "mime_type": self.mime_type,
            "has_bytes": bool(self.bytes),
            "bytes_size": len(self.bytes),
        }


@dataclass(frozen=True)
class ImageDeliveryPayload:
    delivery_kind: str
    final_bytes: builtins.bytes | None = None
    insertions: tuple[ImageDeliveryInsertion, ...] = ()
    selected_variant: str | None = None
    final_variant: str | None = None
    final_decision: str | None = None
    final_reason: str | None = None
    source_forensics: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "delivery_kind": self.delivery_kind,
            "has_final_bytes": self.final_bytes is not None,
            "final_bytes_size": len(self.final_bytes) if isinstance(self.final_bytes, (bytes, bytearray)) else 0,
            "selected_variant": self.selected_variant,
            "final_variant": self.final_variant,
            "final_decision": self.final_decision,
            "final_reason": self.final_reason,
            "insertions": [insertion.to_dict() for insertion in self.insertions],
            "source_forensics": dict(self.source_forensics),
        }


def get_image_variant_value(variant: "ImageVariantCandidate | dict[str, object] | None", field_name: str, default=None):
    if isinstance(variant, dict):
        return variant.get(field_name, default)
    if isinstance(variant, ImageVariantCandidate):
        return getattr(variant, field_name, default)
    return default


def get_image_variant_bytes(variant: "ImageVariantCandidate | dict[str, object] | None") -> bytes | None:
    payload = get_image_variant_value(variant, "bytes")
    if isinstance(payload, (bytes, bytearray)) and payload:
        return bytes(payload)
    return None


@dataclass
class ImageAsset:
    image_id: str
    placeholder: str
    original_bytes: bytes
    mime_type: str | None
    position_index: int
    width_emu: int | None = None
    height_emu: int | None = None
    source_forensics: dict[str, object] = field(default_factory=dict)
    mode_requested: str | None = None
    analysis_result: ImageAnalysisResult | dict[str, object] | None = None
    prompt_key: str | None = None
    render_strategy: str | None = None
    safe_bytes: bytes | None = None
    redrawn_bytes: bytes | None = None
    redrawn_mime_type: str | None = None
    metadata: ImagePipelineMetadata = field(default_factory=ImagePipelineMetadata)
    runtime_attempt_state: ImageRuntimeAttemptState = field(default_factory=ImageRuntimeAttemptState)
    validation_result: ImageValidationResult | dict[str, object] | None = None
    validation_status: str = "pending"
    final_decision: str | None = None
    final_variant: str | None = None
    final_reason: str | None = None
    attempt_variants: list[ImageVariantCandidate | dict[str, object]] = field(default_factory=list)
    comparison_variants: dict[str, ImageVariantCandidate | dict[str, object]] = field(default_factory=dict)
    selected_compare_variant: str | None = None
    delivery_payload: ImageDeliveryPayload | None = None

    def __post_init__(self) -> None:
        self.sync_runtime_attempt_state_from_fields()
        self.sync_pipeline_metadata()
        self.sync_delivery_payload()

    def sync_runtime_attempt_state_from_fields(self) -> None:
        self.runtime_attempt_state.redrawn_bytes = self.redrawn_bytes
        self.runtime_attempt_state.redrawn_mime_type = self.redrawn_mime_type
        self.runtime_attempt_state.validation_result = self.validation_result
        self.runtime_attempt_state.validation_status = self.validation_status
        self.runtime_attempt_state.attempt_variants = list(self.attempt_variants)
        self.runtime_attempt_state.comparison_variants = dict(self.comparison_variants)
        self.runtime_attempt_state.selected_compare_variant = self.selected_compare_variant

    def _sync_fields_from_runtime_attempt_state(self) -> None:
        self.redrawn_bytes = self.runtime_attempt_state.redrawn_bytes
        self.redrawn_mime_type = self.runtime_attempt_state.redrawn_mime_type
        self.validation_result = self.runtime_attempt_state.validation_result
        self.validation_status = self.runtime_attempt_state.validation_status
        self.attempt_variants = list(self.runtime_attempt_state.attempt_variants)
        self.comparison_variants = dict(self.runtime_attempt_state.comparison_variants)
        self.selected_compare_variant = self.runtime_attempt_state.selected_compare_variant

    def sync_pipeline_metadata(self) -> None:
        if self.metadata.source_mime_type is None:
            self.metadata.source_mime_type = self.mime_type
        if self.metadata.source_width_emu is None:
            self.metadata.source_width_emu = self.width_emu
        if self.metadata.source_height_emu is None:
            self.metadata.source_height_emu = self.height_emu
        if self.redrawn_mime_type:
            self.metadata.rendered_mime_type = self.redrawn_mime_type

    def update_pipeline_metadata(self, **values) -> None:
        for key, value in values.items():
            if hasattr(self.metadata, key):
                setattr(self.metadata, key, value)
        self.sync_pipeline_metadata()
        self.sync_delivery_payload()

    def update_runtime_attempt_state(
        self,
        *,
        redrawn_bytes: bytes | None | Any = _UNSET,
        redrawn_mime_type: str | None | Any = _UNSET,
        validation_result: ImageValidationResult | dict[str, object] | None | Any = _UNSET,
        validation_status: str | Any = _UNSET,
        attempt_variants: list[ImageVariantCandidate | dict[str, object]] | Any = _UNSET,
        comparison_variants: dict[str, ImageVariantCandidate | dict[str, object]] | Any = _UNSET,
        selected_compare_variant: str | None | Any = _UNSET,
        clear_selected_compare_variant: bool = False,
    ) -> None:
        if redrawn_bytes is not _UNSET:
            self.runtime_attempt_state.redrawn_bytes = redrawn_bytes
        if redrawn_mime_type is not _UNSET:
            self.runtime_attempt_state.redrawn_mime_type = redrawn_mime_type
        if validation_result is not _UNSET:
            self.runtime_attempt_state.validation_result = validation_result
        if validation_status is not _UNSET:
            self.runtime_attempt_state.validation_status = validation_status
        if attempt_variants is not _UNSET:
            self.runtime_attempt_state.attempt_variants = list(attempt_variants)
        if comparison_variants is not _UNSET:
            self.runtime_attempt_state.comparison_variants = dict(comparison_variants)
        if clear_selected_compare_variant:
            self.runtime_attempt_state.selected_compare_variant = None
        elif selected_compare_variant is not _UNSET:
            self.runtime_attempt_state.selected_compare_variant = selected_compare_variant
        self._sync_fields_from_runtime_attempt_state()
        self.sync_pipeline_metadata()
        self.sync_delivery_payload()

    def sync_delivery_payload(self) -> None:
        self.delivery_payload = build_image_delivery_payload(self)

    def resolved_delivery_payload(self) -> ImageDeliveryPayload:
        if self.delivery_payload is None:
            self.sync_delivery_payload()
        return self.delivery_payload if self.delivery_payload is not None else build_image_delivery_payload(self)

    def source_identity_snapshot(self) -> ImageSourceIdentitySnapshot:
        self.sync_pipeline_metadata()
        return ImageSourceIdentitySnapshot(
            image_id=self.image_id,
            placeholder=self.placeholder,
            mime_type=self.mime_type,
            position_index=self.position_index,
            width_emu=self.width_emu,
            height_emu=self.height_emu,
            source_mime_type=self.metadata.source_mime_type,
            source_width_emu=self.metadata.source_width_emu,
            source_height_emu=self.metadata.source_height_emu,
            source_forensics=dict(self.source_forensics),
        )

    def runtime_state_snapshot(self) -> ImageRuntimeStateSnapshot:
        self.sync_runtime_attempt_state_from_fields()
        self.sync_pipeline_metadata()
        return ImageRuntimeStateSnapshot(
            mode_requested=self.mode_requested,
            analysis_result=self.analysis_result,
            prompt_key=self.prompt_key,
            render_strategy=self.render_strategy,
            safe_bytes_present=self.safe_bytes is not None,
            redrawn_bytes_present=self.runtime_attempt_state.redrawn_bytes is not None,
            redrawn_mime_type=self.runtime_attempt_state.redrawn_mime_type,
            validation_result=self.runtime_attempt_state.validation_result,
            validation_status=self.runtime_attempt_state.validation_status,
            attempt_variants=tuple(self.runtime_attempt_state.attempt_variants),
            comparison_variants=dict(self.runtime_attempt_state.comparison_variants),
            selected_compare_variant=self.runtime_attempt_state.selected_compare_variant,
            rendered_mime_type=self.metadata.rendered_mime_type,
            strict_validation_decision=self.metadata.strict_validation_decision,
            strict_validation_passed=self.metadata.strict_validation_passed,
            soft_accepted=self.metadata.soft_accepted,
        )

    def final_selection_snapshot(self) -> ImageFinalSelectionSnapshot:
        return ImageFinalSelectionSnapshot(
            final_decision=self.final_decision,
            final_variant=self.final_variant,
            final_reason=self.final_reason,
        )

    def reset_runtime_attempt_state(self) -> None:
        self.update_runtime_attempt_state(
            redrawn_bytes=None,
            redrawn_mime_type=None,
            validation_result=None,
            validation_status="pending",
            attempt_variants=[],
            comparison_variants={},
            selected_compare_variant=None,
            clear_selected_compare_variant=True,
        )
        self.update_pipeline_metadata(
            rendered_mime_type=None,
            strict_validation_decision=None,
            strict_validation_passed=None,
            soft_accepted=False,
        )

    def apply_final_selection_outcome(
        self,
        *,
        validation_status: str | None = None,
        final_decision: str | None = None,
        final_variant: str | None = None,
        final_reason: str | None = None,
        selected_compare_variant: str | None = None,
        clear_selected_compare_variant: bool = False,
        strict_validation_decision: str | None = None,
        strict_validation_passed: bool | None = None,
        soft_accepted: bool | None = None,
    ) -> None:
        self.final_decision = final_decision
        self.final_variant = final_variant
        self.final_reason = final_reason
        if validation_status is not None or clear_selected_compare_variant or selected_compare_variant is not None:
            self.update_runtime_attempt_state(
                validation_status=validation_status,
                selected_compare_variant=selected_compare_variant,
                clear_selected_compare_variant=clear_selected_compare_variant,
            )
        metadata_updates = {}
        if strict_validation_decision is not None:
            metadata_updates["strict_validation_decision"] = strict_validation_decision
        if strict_validation_passed is not None:
            metadata_updates["strict_validation_passed"] = strict_validation_passed
        if soft_accepted is not None:
            metadata_updates["soft_accepted"] = soft_accepted
        if metadata_updates:
            self.update_pipeline_metadata(**metadata_updates)
        self.sync_delivery_payload()

    def to_log_context(self) -> dict[str, object]:
        self.sync_pipeline_metadata()
        source_identity = self.source_identity_snapshot()
        runtime_state = self.runtime_state_snapshot()
        final_selection = self.final_selection_snapshot()
        return {
            "image_id": source_identity.image_id,
            "placeholder": source_identity.placeholder,
            "mime_type": source_identity.mime_type,
            "position_index": source_identity.position_index,
            "width_emu": source_identity.width_emu,
            "height_emu": source_identity.height_emu,
            "source_forensics": dict(source_identity.source_forensics),
            "mode_requested": runtime_state.mode_requested,
            "prompt_key": runtime_state.prompt_key,
            "render_strategy": runtime_state.render_strategy,
            "redrawn_mime_type": runtime_state.redrawn_mime_type,
            "metadata": self.metadata.to_dict(),
            "validation_status": runtime_state.validation_status,
            "final_decision": final_selection.final_decision,
            "final_variant": final_selection.final_variant,
            "final_reason": final_selection.final_reason,
            "delivery_payload": self.resolved_delivery_payload().to_dict(),
            "attempt_variants": [
                variant.to_dict() if isinstance(variant, ImageVariantCandidate) else variant
                for variant in runtime_state.attempt_variants
            ],
            "analysis_result": runtime_state.analysis_result.to_dict() if isinstance(runtime_state.analysis_result, ImageAnalysisResult) else runtime_state.analysis_result,
            "validation_result": (
                runtime_state.validation_result.to_dict()
                if isinstance(runtime_state.validation_result, ImageValidationResult)
                else runtime_state.validation_result
            ),
        }


def clone_image_variant_candidate(variant: "ImageVariantCandidate | dict[str, object] | None"):
    if isinstance(variant, ImageVariantCandidate):
        return ImageVariantCandidate(
            mode=variant.mode,
            bytes=bytes(variant.bytes) if isinstance(variant.bytes, (bytes, bytearray)) else variant.bytes,
            mime_type=variant.mime_type,
            validation_result=(
                variant.validation_result.to_dict()
                if isinstance(variant.validation_result, ImageValidationResult)
                else _clone_validation_payload(variant.validation_result)
                if hasattr(variant.validation_result, "__dataclass_fields__")
                else dict(variant.validation_result)
                if isinstance(variant.validation_result, dict)
                else variant.validation_result
            ),
            validation_status=variant.validation_status,
            final_decision=variant.final_decision,
            final_variant=variant.final_variant,
            final_reason=variant.final_reason,
        )
    if isinstance(variant, dict):
        cloned_variant = dict(variant)
        validation_result = cloned_variant.get("validation_result")
        if isinstance(validation_result, ImageValidationResult):
            cloned_variant["validation_result"] = validation_result.to_dict()
        elif hasattr(validation_result, "__dataclass_fields__"):
            cloned_variant["validation_result"] = _clone_validation_payload(validation_result)
        elif isinstance(validation_result, dict):
            cloned_variant["validation_result"] = dict(validation_result)
        return cloned_variant
    return variant


def _clone_validation_payload(value):
    if isinstance(value, ImageValidationResult):
        return value.to_dict()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def _clone_analysis_payload(value):
    if isinstance(value, ImageAnalysisResult):
        return value.to_dict()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def clone_prepared_image_asset(asset):
    if not isinstance(asset, ImageAsset):
        return asset
    asset.sync_runtime_attempt_state_from_fields()
    metadata = asset.metadata if isinstance(asset.metadata, ImagePipelineMetadata) else ImagePipelineMetadata()
    return ImageAsset(
        image_id=asset.image_id,
        placeholder=asset.placeholder,
        original_bytes=bytes(asset.original_bytes),
        mime_type=asset.mime_type,
        position_index=asset.position_index,
        width_emu=asset.width_emu,
        height_emu=asset.height_emu,
        source_forensics=dict(asset.source_forensics),
        mode_requested=asset.mode_requested,
        analysis_result=_clone_analysis_payload(asset.analysis_result),
        prompt_key=asset.prompt_key,
        render_strategy=asset.render_strategy,
        safe_bytes=bytes(asset.safe_bytes) if isinstance(asset.safe_bytes, (bytes, bytearray)) else asset.safe_bytes,
        redrawn_bytes=bytes(asset.redrawn_bytes) if isinstance(asset.redrawn_bytes, (bytes, bytearray)) else asset.redrawn_bytes,
        redrawn_mime_type=asset.redrawn_mime_type,
        metadata=ImagePipelineMetadata(
            source_mime_type=metadata.source_mime_type,
            rendered_mime_type=metadata.rendered_mime_type,
            source_width_emu=metadata.source_width_emu,
            source_height_emu=metadata.source_height_emu,
            strict_validation_decision=metadata.strict_validation_decision,
            strict_validation_passed=metadata.strict_validation_passed,
            soft_accepted=metadata.soft_accepted,
            placeholder_status=metadata.placeholder_status,
            preserve_all_variants_in_docx=metadata.preserve_all_variants_in_docx,
        ),
        runtime_attempt_state=ImageRuntimeAttemptState(
            redrawn_bytes=bytes(asset.runtime_attempt_state.redrawn_bytes) if isinstance(asset.runtime_attempt_state.redrawn_bytes, (bytes, bytearray)) else asset.runtime_attempt_state.redrawn_bytes,
            redrawn_mime_type=asset.runtime_attempt_state.redrawn_mime_type,
            validation_result=_clone_validation_payload(asset.runtime_attempt_state.validation_result),
            validation_status=asset.runtime_attempt_state.validation_status,
            attempt_variants=cast(
                list[ImageVariantCandidate | dict[str, object]],
                [clone_image_variant_candidate(variant) for variant in asset.runtime_attempt_state.attempt_variants if variant is not None],
            ),
            comparison_variants=cast(
                dict[str, ImageVariantCandidate | dict[str, object]],
                {key: clone_image_variant_candidate(variant) for key, variant in asset.runtime_attempt_state.comparison_variants.items() if variant is not None},
            ),
            selected_compare_variant=asset.runtime_attempt_state.selected_compare_variant,
        ),
        validation_result=_clone_validation_payload(asset.validation_result),
        validation_status=asset.validation_status,
        final_decision=asset.final_decision,
        final_variant=asset.final_variant,
        final_reason=asset.final_reason,
        attempt_variants=cast(
            list[ImageVariantCandidate | dict[str, object]],
            [clone_image_variant_candidate(variant) for variant in asset.attempt_variants if variant is not None],
        ),
        comparison_variants=cast(
            dict[str, ImageVariantCandidate | dict[str, object]],
            {key: clone_image_variant_candidate(variant) for key, variant in asset.comparison_variants.items() if variant is not None},
        ),
        selected_compare_variant=asset.selected_compare_variant,
        delivery_payload=(
            ImageDeliveryPayload(
                delivery_kind=asset.delivery_payload.delivery_kind,
                final_bytes=(
                    bytes(asset.delivery_payload.final_bytes)
                    if isinstance(asset.delivery_payload.final_bytes, (bytes, bytearray))
                    else asset.delivery_payload.final_bytes
                ),
                insertions=tuple(
                    ImageDeliveryInsertion(
                        label=insertion.label,
                        bytes=bytes(insertion.bytes),
                        variant_key=insertion.variant_key,
                        mime_type=insertion.mime_type,
                    )
                    for insertion in asset.delivery_payload.insertions
                ),
                selected_variant=asset.delivery_payload.selected_variant,
                final_variant=asset.delivery_payload.final_variant,
                final_decision=asset.delivery_payload.final_decision,
                final_reason=asset.delivery_payload.final_reason,
                source_forensics=dict(asset.delivery_payload.source_forensics),
            )
            if isinstance(asset.delivery_payload, ImageDeliveryPayload)
            else None
        ),
    )


def build_image_delivery_payload(asset: ImageAsset) -> ImageDeliveryPayload:
    compare_insertions = _resolve_compare_delivery_insertions(asset)
    if compare_insertions:
        return ImageDeliveryPayload(
            delivery_kind="compare_all_variants",
            final_bytes=_resolve_final_image_bytes_from_asset(asset),
            insertions=compare_insertions,
            selected_variant=asset.selected_compare_variant,
            final_variant=asset.final_variant,
            final_decision=asset.final_decision,
            final_reason=asset.final_reason,
            source_forensics=dict(asset.source_forensics),
        )

    manual_review_insertions = _resolve_manual_review_delivery_insertions(asset)
    if manual_review_insertions:
        return ImageDeliveryPayload(
            delivery_kind="manual_review_variants",
            final_bytes=_resolve_final_image_bytes_from_asset(asset),
            insertions=manual_review_insertions,
            selected_variant=asset.selected_compare_variant,
            final_variant=asset.final_variant,
            final_decision=asset.final_decision,
            final_reason=asset.final_reason,
            source_forensics=dict(asset.source_forensics),
        )

    return ImageDeliveryPayload(
        delivery_kind="final_selection",
        final_bytes=_resolve_final_image_bytes_from_asset(asset),
        selected_variant=asset.selected_compare_variant,
        final_variant=asset.final_variant,
        final_decision=asset.final_decision,
        final_reason=asset.final_reason,
        source_forensics=dict(asset.source_forensics),
    )


def _resolve_compare_delivery_insertions(asset: ImageAsset) -> tuple[ImageDeliveryInsertion, ...]:
    if getattr(asset, "validation_status", None) != "compared" or not getattr(asset, "comparison_variants", None):
        return ()
    insertions: list[ImageDeliveryInsertion] = []
    for mode in DOCX_COMPARE_VARIANT_MODE_VALUES:
        variant = asset.comparison_variants.get(mode)
        variant_bytes = get_image_variant_bytes(variant)
        if variant_bytes:
            insertions.append(
                ImageDeliveryInsertion(
                    label=(
                        "Вариант 1: Просто улучшить"
                        if mode == ImageMode.SAFE.value
                        else "Вариант 2: Креативная AI-перерисовка"
                        if mode == ImageMode.SEMANTIC_REDRAW_DIRECT.value
                        else "Вариант 3: Структурная AI-перерисовка"
                    ),
                    bytes=variant_bytes,
                    variant_key=mode,
                    mime_type=cast(str | None, get_image_variant_value(variant, "mime_type")),
                )
            )
    return tuple(insertions)


def _resolve_manual_review_delivery_insertions(asset: ImageAsset) -> tuple[ImageDeliveryInsertion, ...]:
    if not bool(getattr(getattr(asset, "metadata", None), "preserve_all_variants_in_docx", False)):
        return ()
    insertions: list[ImageDeliveryInsertion] = []
    if asset.safe_bytes:
        insertions.append(
            ImageDeliveryInsertion(
                label="safe",
                bytes=bytes(asset.safe_bytes),
                variant_key=ImageMode.SAFE.value,
                mime_type=asset.mime_type,
            )
        )
    for variant in list(getattr(asset, "attempt_variants", []))[:2]:
        variant_label = str(get_image_variant_value(variant, "mode", "")).strip() or None
        variant_bytes = get_image_variant_bytes(variant)
        if variant_label and variant_bytes:
            insertions.append(
                ImageDeliveryInsertion(
                    label=variant_label,
                    bytes=variant_bytes,
                    variant_key=variant_label,
                    mime_type=cast(str | None, get_image_variant_value(variant, "mime_type")),
                )
            )
    return tuple(insertions)


def _resolve_final_image_bytes_from_asset(asset: ImageAsset) -> bytes:
    if asset.selected_compare_variant:
        if asset.selected_compare_variant == "original":
            return asset.original_bytes
        selected_variant = asset.comparison_variants.get(asset.selected_compare_variant)
        selected_bytes = get_image_variant_bytes(selected_variant)
        if selected_bytes:
            return selected_bytes
    if asset.final_variant == "redrawn" and asset.redrawn_bytes:
        return bytes(asset.redrawn_bytes)
    if asset.final_variant == "safe" and asset.safe_bytes:
        return bytes(asset.safe_bytes)
    return bytes(asset.original_bytes)
