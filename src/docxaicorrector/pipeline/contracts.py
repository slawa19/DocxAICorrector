import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence, Sized
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, TypeAlias

from docxaicorrector.document.segments import DocumentSegment


PipelineResult: TypeAlias = Literal["succeeded", "failed", "stopped"]


class LatePhaseStopped(BaseException):
    """Internal cooperative-cancellation signal not consumed by advisory handlers."""


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
        block_index: int | None = None,
        should_stop: Callable[[], bool] | None = None,
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
        processing_operation: str = "",
        target_language: str = "",
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
        model_accounting: Mapping[str, object] | None = None,
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
    emit_log: LogEmitter
    emit_status: StatusEmitter


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


@dataclass
class ProcessingState:
    processed_chunks: list[str] = field(default_factory=list)
    # Spec 063 P2: the run glossary's outcome, for the result-screen notice only; the glossary
    # itself lives in the block prompt and in its ``.run/run_glossaries/`` artifact.
    run_glossary_status: str = "not_applicable"
    run_glossary_term_count: int = 0
    narration_chunks: list[str] = field(default_factory=list)
    excluded_narration_block_count: int = 0
    # Blocks kept OUT of the narration for a reason the document layer could not know:
    # the model's output was rejected and the controlled fallback delivered the block's own
    # SOURCE text instead (``pipeline/block_execution.py``). The DOCX keeps that source —
    # a human reading a document sees an untranslated paragraph and fixes it — but nothing
    # stands between the narration artifact and the listener, so it does not go to audio.
    # Counted separately from ``excluded_narration_block_count`` (the document-layer
    # ``narration_include`` decision) because the two answer different questions and the
    # spec-054 exclusion measurements are keyed on the latter.
    narration_excluded_source_fallback_block_count: int = 0
    narration_excluded_source_fallback_chars: int = 0
    # Spec 056 E, the same loss one level down: individual PARAGRAPHS the model returned
    # nothing for. Their source stands in the DOCX and is kept out of the narration. The
    # characters are counted, not only the paragraphs, because spec 054's metric is the
    # share of source-language CHARACTERS in the artifact and a paragraph count cannot be
    # compared against it — one omitted paragraph stood for 1 378 characters on the
    # 2026-08-04 run.
    narration_excluded_omitted_paragraph_count: int = 0
    narration_excluded_omitted_chars: int = 0
    # 2026-08-09: the two families above, ADDRESSABLY. A quantity without a place is still a
    # hunt — the recorded 20260809T_059_audio_money run published "8 paragraphs, 4 455
    # characters" against a 512 458-character book — so each excluded paragraph keeps its
    # ``{paragraph_id, text}``. The blocks family is counted in BLOCKS and addressed in
    # PARAGRAPHS: the reader searches the DOCX for a passage, never for a block index. Both
    # lists are written where the exclusion is DECIDED (``block_execution``), because only
    # there is it known that the block was headed for the narration at all — re-deriving them
    # at finalization would sweep in the 59 blocks the document layer had already excluded on
    # that run. Read once, by ``quality_gate.build_narration_exclusion_facts``.
    narration_excluded_source_fallback_paragraphs: list[dict[str, str]] = field(
        default_factory=list
    )
    narration_excluded_omitted_paragraphs: list[dict[str, str]] = field(default_factory=list)
    # Spec 054, 2026-08-06: paragraph boundaries the assembly closed because the sentence
    # ran ON across them — 81 of the 83 measured on the four-book corpus arrive that way
    # from IMPORT, where a PDF line wrap became a paragraph break. Nothing is added or lost,
    # only a ``\n\n`` becomes a space, so this is the one narration counter that reports a
    # REPAIR rather than a loss. It is published all the same, and a zero is the statement
    # "this run found no sentence running across a paragraph break".
    narration_joined_sentence_continuation_count: int = 0
    # Spec 061 FR-017 (narrowed): audiobook post-pass groups whose answer came back with
    # FEWER paragraphs than were sent, and how many paragraphs short they were in total.
    # The answer is delivered and marked for review
    # (``narration_postprocess._record_postprocess_paragraph_shortfall``); these feed the
    # ``ui_audiobook_artifact_saved`` record and the result notice. Zero is a statement.
    narration_postprocess_paragraph_shortfall_group_count: int = 0
    narration_postprocess_paragraph_shortfall_paragraph_count: int = 0
    # Spec 059 FR-A8, revised 2026-08-09: one entry per DELIVERED block that shipped prose in
    # the source language, each entry a list of ``{paragraph_id, text}`` for the block's prose
    # paragraphs. It exists because the alarm channel cannot see this class any other way:
    # ``quality_gate.build_source_text_delivery_facts`` reads the delivered block's
    # per-paragraph record, and on such a block every paragraph is ``accepted`` — the model
    # answered, its answer simply WAS its input. Written by
    # ``block_execution._announce_untranslated_prose_delivery``, read once at finalization.
    untranslated_prose_delivered_paragraphs: list[list[dict[str, str]]] = field(default_factory=list)
    generated_paragraph_registry: list[dict[str, object]] = field(default_factory=list)
    segment_outputs: dict[str, list[str]] = field(default_factory=dict)
    completed_segment_ids: set[str] = field(default_factory=set)
    failed_segment_ids: set[str] = field(default_factory=set)
    system_prompt: str | None = None
    toc_system_prompt: str | None = None
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
    # Deferred builds use the immutable ProcessingContext ownership when re-collecting.
    diagnostics_dir: Path | None = None


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
    # Spec 059 A-II: one document REGION per paragraph, parallel to ``paragraph_ids`` and to
    # ``structural_roles``. This is what lets the failure-decision table tell apparatus from
    # prose INSIDE one block: ``narration_include`` below is a single bool for the whole
    # block, so on a mixed block it could not. ``None`` means the producer resolved no
    # regions -- only ``document.semantic_blocks.build_editing_jobs`` produces them, so
    # absence means a caller outside document preparation, and the consumer
    # (``block_execution.payload_contains_prose``) reads it as prose rather than as apparatus.
    paragraph_regions: list[str] | None = None
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
