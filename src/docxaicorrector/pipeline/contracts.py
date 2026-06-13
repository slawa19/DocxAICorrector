import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence, Sized
from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeAlias

from docxaicorrector.document.segments import DocumentSegment


PipelineResult: TypeAlias = Literal["succeeded", "failed", "stopped"]


class ParagraphLike(Protocol):
    role: str


class ImageAssetLike(Protocol):
    image_id: str

    def update_pipeline_metadata(self, **values: object) -> None: ...


class ProgressCallback(Protocol):
    def __call__(self, *, preview_title: str) -> None: ...


class FilenameResolver(Protocol):
    def __call__(self, uploaded_file: object) -> str: ...


class ClientFactory(Protocol):
    def __call__(self) -> object: ...


class ProviderClientFactory(Protocol):
    def __call__(self, provider_name: str) -> object: ...


class ModelSelectorClientFactory(Protocol):
    def __call__(self, selector: str, required_capability: str) -> object: ...


class ModelSelectorResolver(Protocol):
    def __call__(self, selector: str, required_capability: str | None = None) -> object: ...


class SystemPromptLoader(Protocol):
    def __call__(
        self,
        *,
        operation: str = "edit",
        source_language: str = "en",
        target_language: str = "ru",
        editorial_intensity: str = "literary",
        prompt_variant: str = "default",
        translation_domain: str = "general",
        source_text: str = "",
    ) -> str: ...


class EventLogger(Protocol):
    def __call__(self, level: int, event_id: str, message: str, **context: object) -> None: ...


class ErrorPresenter(Protocol):
    def __call__(self, code: str, exc: Exception, title: str, **context: object) -> str: ...


class StateEmitter(Protocol):
    def __call__(self, runtime: object, **values: object) -> None: ...


class FinalizeEmitter(Protocol):
    def __call__(self, runtime: object, stage: str, detail: str, progress: float, terminal_kind: str | None = None) -> None: ...


class ActivityEmitter(Protocol):
    def __call__(self, runtime: object, message: str) -> None: ...


class LogEmitter(Protocol):
    def __call__(self, runtime: object, **payload: object) -> None: ...


class StatusEmitter(Protocol):
    def __call__(self, runtime: object, **payload: object) -> None: ...


class StopPredicate(Protocol):
    def __call__(self, runtime: object) -> bool: ...


class MarkdownGenerator(Protocol):
    def __call__(
        self,
        *,
        client: object,
        model: str,
        system_prompt: str,
        target_text: str,
        context_before: str,
        context_after: str,
        max_retries: int,
        expected_paragraph_ids: Sequence[str] | None = None,
        marker_mode: bool = False,
    ) -> str: ...


class ImageProcessor(Protocol):
    def __call__(
        self,
        *,
        image_assets: Sequence[ImageAssetLike],
        image_mode: str,
        config: Mapping[str, object],
        on_progress: ProgressCallback,
        runtime: object,
        client: object,
    ) -> Iterable[ImageAssetLike] | None: ...


class PlaceholderInspector(Protocol):
    def __call__(self, markdown_text: str, image_assets: Sequence[ImageAssetLike]) -> Mapping[str, str]: ...


class MarkdownToDocxConverter(Protocol):
    def __call__(self, markdown_text: str) -> bytes: ...


class ParagraphPropertiesPreserver(Protocol):
    def __call__(
        self,
        docx_bytes: bytes,
        paragraphs: Sequence[ParagraphLike],
        generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
    ) -> bytes: ...


class ImageReinserter(Protocol):
    def __call__(self, docx_bytes: bytes, image_assets: Sequence[ImageAssetLike]) -> bytes: ...


class ResultArtifactWriter(Protocol):
    def __call__(
        self,
        *,
        source_name: str,
        markdown_text: str,
        docx_bytes: bytes,
        narration_text: str | None = None,
        quality_warning: Mapping[str, object] | None = None,
        assembly_mode: str | None = None,
        selected_segment_count: int | None = None,
        result_manifest: Mapping[str, object] | None = None,
    ) -> Mapping[str, str]: ...


class SegmentResultRegistryWriter(Protocol):
    def __call__(
        self,
        *,
        records: Sequence[Mapping[str, object]],
    ) -> Mapping[str, str]: ...


class JobResultRegistryWriter(Protocol):
    def __call__(
        self,
        *,
        records: Sequence[Mapping[str, object]],
    ) -> Mapping[str, str]: ...


class ProcessingJobs(Sized, Protocol):
    def __iter__(self) -> Iterator[Mapping[str, object]]: ...


def _noop_segment_result_registry_writer(*, records: Sequence[Mapping[str, object]]) -> Mapping[str, str]:
    return {}


def _noop_job_result_registry_writer(*, records: Sequence[Mapping[str, object]]) -> Mapping[str, str]:
    return {}


@dataclass(frozen=True)
class ProcessingDependencies:
    resolve_uploaded_filename: FilenameResolver
    get_client: ClientFactory
    ensure_pandoc_available: Callable[[], None]
    load_system_prompt: SystemPromptLoader
    log_event: EventLogger
    present_error: ErrorPresenter
    should_stop_processing: StopPredicate
    generate_markdown_block: MarkdownGenerator
    process_document_images: ImageProcessor
    inspect_placeholder_integrity: PlaceholderInspector
    convert_markdown_to_docx_bytes: MarkdownToDocxConverter
    preserve_source_paragraph_properties: ParagraphPropertiesPreserver
    reinsert_inline_images: ImageReinserter
    write_ui_result_artifacts: ResultArtifactWriter
    write_segment_result_registry: SegmentResultRegistryWriter = _noop_segment_result_registry_writer
    write_job_result_registry: JobResultRegistryWriter = _noop_job_result_registry_writer
    get_provider_client: ProviderClientFactory | None = None
    get_client_for_model_selector: ModelSelectorClientFactory | None = None
    resolve_model_selector: ModelSelectorResolver | None = None


@dataclass(frozen=True)
class ProcessingEmitters:
    emit_state: StateEmitter
    emit_finalize: FinalizeEmitter
    emit_activity: ActivityEmitter
    emit_log: LogEmitter
    emit_status: StatusEmitter


@dataclass(frozen=True)
class SegmentSelection:
    selected_segment_ids: tuple[str, ...]
    include_descendants: bool = True
    include_front_matter: bool = False
    include_toc: bool = False
    output_mode: str = "selected_only"


@dataclass(frozen=True)
class ProcessingContext:
    uploaded_file: object
    uploaded_filename: str
    source_token: str
    run_id: str
    jobs: ProcessingJobs
    selected_segment_ids: Sequence[str] | None
    document_segments: Sequence[DocumentSegment]
    segment_selection_mode: str
    output_mode: str
    include_front_matter: bool
    include_toc: bool
    source_paragraphs: Sequence[ParagraphLike] | None
    image_assets: Sequence[ImageAssetLike]
    image_mode: str
    app_config: Mapping[str, object]
    model: str
    max_retries: int
    processing_operation: str
    source_language: str
    target_language: str
    translation_domain: str
    translation_domain_instructions: str
    on_progress: ProgressCallback
    runtime: object
    prepared_source_key: str = ""
    structure_fingerprint: str = ""
    model_selector: str = ""
    canonical_model_selector: str | None = None
    model_provider: str | None = None
    model_id: str | None = None
    document_context_prompt: str = ""
    segment_selection: SegmentSelection | None = None
    document_map: object | None = None
    document_topology_projection: object | None = None


@dataclass
class ProcessingState:
    processed_chunks: list[str] = field(default_factory=list)
    narration_chunks: list[str] = field(default_factory=list)
    excluded_narration_block_count: int = 0
    generated_paragraph_registry: list[dict[str, object]] = field(default_factory=list)
    segment_outputs: dict[str, list[str]] = field(default_factory=dict)
    completed_segment_ids: set[str] = field(default_factory=set)
    failed_segment_ids: set[str] = field(default_factory=set)
    system_prompt: str | None = None
    toc_system_prompt: str | None = None
    second_pass_system_prompt: str | None = None
    started_at: float = field(default_factory=time.perf_counter)


@dataclass(frozen=True)
class ProcessingInitialization:
    client: object
    job_count: int
    segment_ids_by_job: tuple[str | None, ...] = ()
    segment_titles_by_id: dict[str, str] = field(default_factory=dict)
    segment_job_totals: dict[str, int] = field(default_factory=dict)
    text_client: object | None = None
    text_model_id: str | None = None
    openai_client: object | None = None


@dataclass(frozen=True)
class ImageProcessingPhaseResult:
    processed_image_assets: list[ImageAssetLike]
    placeholder_integrity: Mapping[str, str]


@dataclass(frozen=True)
class DocxBuildPhaseResult:
    docx_bytes: bytes | None
    final_markdown: str
    latest_result_notice: dict[str, str] | None
    formatting_diagnostics_artifacts: list[str] = field(default_factory=list)
    pre_cleanup_formatting_baseline: Mapping[str, object] | None = None
    assembly_entries: list[Mapping[str, object]] = field(default_factory=list)
    result_manifest: Mapping[str, object] | None = None
    processed_image_assets: list[ImageAssetLike] = field(default_factory=list)
    base_docx_builder: Callable[[], bytes] | None = None


@dataclass(frozen=True)
class BlockExecutionPayload:
    job_kind: str
    target_chars: int
    context_chars: int
    target_text: str
    target_text_with_markers: str
    paragraph_ids: list[str] | None
    context_before: str
    context_after: str
    structural_roles: list[str] | None = None
    narration_include: bool = True
    toc_dominant: bool = False
    toc_paragraph_count: int = 0
    paragraph_count: int = 0


@dataclass(frozen=True)
class ProcessingRunComponents:
    dependencies: ProcessingDependencies
    emitters: ProcessingEmitters
    context: ProcessingContext


def build_processing_dependencies(
    *,
    resolve_uploaded_filename: FilenameResolver,
    get_client: ClientFactory,
    get_provider_client: ProviderClientFactory | None = None,
    get_client_for_model_selector: ModelSelectorClientFactory | None = None,
    resolve_model_selector: ModelSelectorResolver | None = None,
    ensure_pandoc_available: Callable[[], None],
    load_system_prompt: SystemPromptLoader,
    log_event: EventLogger,
    present_error: ErrorPresenter,
    should_stop_processing: StopPredicate,
    generate_markdown_block: MarkdownGenerator,
    process_document_images: ImageProcessor,
    inspect_placeholder_integrity: PlaceholderInspector,
    convert_markdown_to_docx_bytes: MarkdownToDocxConverter,
    preserve_source_paragraph_properties: ParagraphPropertiesPreserver,
    reinsert_inline_images: ImageReinserter,
    write_ui_result_artifacts: ResultArtifactWriter,
    write_segment_result_registry: SegmentResultRegistryWriter,
    write_job_result_registry: JobResultRegistryWriter = _noop_job_result_registry_writer,
) -> ProcessingDependencies:
    return ProcessingDependencies(
        resolve_uploaded_filename=resolve_uploaded_filename,
        get_client=get_client,
        get_provider_client=get_provider_client,
        get_client_for_model_selector=get_client_for_model_selector,
        resolve_model_selector=resolve_model_selector,
        ensure_pandoc_available=ensure_pandoc_available,
        load_system_prompt=load_system_prompt,
        log_event=log_event,
        present_error=present_error,
        should_stop_processing=should_stop_processing,
        generate_markdown_block=generate_markdown_block,
        process_document_images=process_document_images,
        inspect_placeholder_integrity=inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=preserve_source_paragraph_properties,
        reinsert_inline_images=reinsert_inline_images,
        write_ui_result_artifacts=write_ui_result_artifacts,
        write_segment_result_registry=write_segment_result_registry,
        write_job_result_registry=write_job_result_registry,
    )
