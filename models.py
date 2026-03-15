import builtins
import re
from enum import StrEnum
from dataclasses import asdict, dataclass, field


EXPLICIT_LIST_MARKER_PATTERN = re.compile(r"^(?:\s*[-*•—]\s+|\s*\d+[\.)]\s+)")
EXPLICIT_HEADING_PATTERN = re.compile(r"^#{1,6}\s+")


class ImageMode(StrEnum):
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


@dataclass
class ParagraphUnit:
    text: str
    role: str
    heading_level: int | None = None
    heading_source: str | None = None
    list_kind: str | None = None
    list_level: int = 0
    preserved_ppr_xml: tuple[str, ...] = field(default_factory=tuple)

    @property
    def rendered_text(self) -> str:
        if self.role == "heading" and self.heading_level is not None and not EXPLICIT_HEADING_PATTERN.match(self.text):
            level = min(max(self.heading_level, 1), 6)
            return f"{'#' * level} {self.text}"

        if self.role != "list" or EXPLICIT_LIST_MARKER_PATTERN.match(self.text):
            return self.text

        indent = "    " * max(0, self.list_level)
        marker = "1." if self.list_kind == "ordered" else "-"
        return f"{indent}{marker} {self.text}"


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
    mode_requested: str | None = None
    analysis_result: ImageAnalysisResult | dict[str, object] | None = None
    prompt_key: str | None = None
    render_strategy: str | None = None
    safe_bytes: bytes | None = None
    redrawn_bytes: bytes | None = None
    redrawn_mime_type: str | None = None
    metadata: ImagePipelineMetadata = field(default_factory=ImagePipelineMetadata)
    validation_result: ImageValidationResult | dict[str, object] | None = None
    validation_status: str = "pending"
    final_decision: str | None = None
    final_variant: str | None = None
    final_reason: str | None = None
    attempt_variants: list[ImageVariantCandidate | dict[str, object]] = field(default_factory=list)
    comparison_variants: dict[str, ImageVariantCandidate | dict[str, object]] = field(default_factory=dict)
    selected_compare_variant: str | None = None

    def __post_init__(self) -> None:
        self.sync_pipeline_metadata()

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

    def to_log_context(self) -> dict[str, object]:
        self.sync_pipeline_metadata()
        analysis_result = self.analysis_result
        validation_result = self.validation_result
        return {
            "image_id": self.image_id,
            "placeholder": self.placeholder,
            "mime_type": self.mime_type,
            "position_index": self.position_index,
            "width_emu": self.width_emu,
            "height_emu": self.height_emu,
            "mode_requested": self.mode_requested,
            "prompt_key": self.prompt_key,
            "render_strategy": self.render_strategy,
            "redrawn_mime_type": self.redrawn_mime_type,
            "metadata": self.metadata.to_dict(),
            "validation_status": self.validation_status,
            "final_decision": self.final_decision,
            "final_variant": self.final_variant,
            "final_reason": self.final_reason,
            "attempt_variants": [
                variant.to_dict() if isinstance(variant, ImageVariantCandidate) else variant
                for variant in self.attempt_variants
            ],
            "analysis_result": analysis_result.to_dict() if isinstance(analysis_result, ImageAnalysisResult) else analysis_result,
            "validation_result": (
                validation_result.to_dict()
                if isinstance(validation_result, ImageValidationResult)
                else validation_result
            ),
        }
