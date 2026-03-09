from dataclasses import asdict, dataclass, field


@dataclass
class ParagraphUnit:
    text: str
    role: str


@dataclass
class DocumentBlock:
    paragraphs: list["ParagraphUnit"]

    @property
    def text(self) -> str:
        return "\n\n".join(paragraph.text for paragraph in self.paragraphs)


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

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


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
            "analysis_result": analysis_result.to_dict() if isinstance(analysis_result, ImageAnalysisResult) else analysis_result,
            "validation_result": (
                validation_result.to_dict()
                if isinstance(validation_result, ImageValidationResult)
                else validation_result
            ),
        }
