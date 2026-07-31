"""Narration / audiobook post-pass (spec 031 Cluster J).

Behaviour-preserving extraction from ``pipeline/late_phases.py``: the narration-text
builder, the artifact-text validator (ElevenLabs tag / disallowed-pattern checks), and the
optional separate audiobook LLM post-pass reached only through injected ``dependencies``
callables (offline-drivable — no module-level SDK client). ``late_phases`` re-exports these
names so ``late_phases.<name>`` keeps resolving for the test namespace and the still-in
-``late_phases`` ``finalize_processing_success`` caller. No module-level mutable state; all
patterns are immutable compiled constants.
"""

import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

from docxaicorrector.generation._generation import strip_markdown_for_narration
from docxaicorrector.pipeline.text_call_support import _require_group_int, _resolve_text_call_target
from docxaicorrector.pipeline.contracts import LatePhaseStopped


_ELEVENLABS_TAG_PATTERN = re.compile(r"\[(?:thoughtful|curious|serious|sad|excited|annoyed|sarcastic|whispers|short pause|long pause|sighs|laughs|chuckles|exhales)\]")
_NARRATION_ANY_TAG_PATTERN = re.compile(r"\[[^\]\n]{1,40}\]")
_NARRATION_DISALLOWED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("internal_placeholder", re.compile(r"\[\[DOCX_[A-Za-z0-9_]+\]\]")),
    ("raw_url", re.compile(r"(?:https?://\S+|www\.\S+)", re.IGNORECASE)),
    ("doi", re.compile(r"\bdoi\s*[:/]?\s*10\.\d{4,9}/\S+", re.IGNORECASE)),
    ("isbn", re.compile(r"\bisbn\b", re.IGNORECASE)),
    ("arxiv", re.compile(r"\barxiv\b", re.IGNORECASE)),
    ("inline_citation", re.compile(r"\((?:ibid\.|там же|[A-ZА-ЯЁ][^()]{0,80}?,\s*(?:19|20)\d{2})[^()]*\)", re.IGNORECASE)),
    ("superscript_footnote", re.compile(r"[\u00B9\u00B2\u00B3\u2070-\u2079]")),
    ("markdown_heading", re.compile(r"^\s{0,3}#", re.MULTILINE)),
)


def _project_final_cleanup_narration_chunks(
    *,
    context: Any,
    final_generated_paragraph_registry: Sequence[object] | None,
) -> list[str]:
    if final_generated_paragraph_registry is None:
        raise RuntimeError("narration_cleanup_projection_unsafe:missing_final_registry")
    jobs = list(getattr(context, "jobs", ()) or ())
    projected: list[str] = []
    for raw_entry in final_generated_paragraph_registry:
        if not isinstance(raw_entry, Mapping):
            raise RuntimeError("narration_cleanup_projection_unsafe:invalid_registry_entry")
        text = str(raw_entry.get("text", "") or "").strip()
        source_block_indexes = raw_entry.get("reader_cleanup_source_block_indexes")
        if source_block_indexes is None:
            source_block_indexes = [raw_entry.get("block_index")]
        if (
            not isinstance(source_block_indexes, Sequence)
            or isinstance(source_block_indexes, (str, bytes, bytearray))
            or not source_block_indexes
        ):
            raise RuntimeError("narration_cleanup_projection_unsafe:incomplete_lineage")
        inclusion_flags: set[bool] = set()
        for block_index in source_block_indexes:
            if (
                isinstance(block_index, bool)
                or not isinstance(block_index, int)
                or block_index < 1
                or block_index > len(jobs)
            ):
                raise RuntimeError("narration_cleanup_projection_unsafe:incomplete_lineage")
            job = jobs[block_index - 1]
            inclusion_flags.add(
                bool(job.get("narration_include", True))
                if isinstance(job, Mapping)
                else bool(getattr(job, "narration_include", True))
            )
        if len(inclusion_flags) != 1:
            raise RuntimeError("narration_cleanup_projection_unsafe:mixed_join_boundary")
        # Blank blocks and form-only internal placeholders carry no narratable
        # content. They still need valid structural lineage, but they do not make
        # adjacent eligible final text unsafe and must not poison the whole
        # narration projection.
        if not strip_markdown_for_narration(text):
            continue
        if True in inclusion_flags:
            projected.append(text)
    return projected


def _build_narration_text(*, context: Any, dependencies: Any, emitters: Any, state: Any, final_generated_paragraph_registry: Sequence[object] | None = None) -> str | None:
    stop_predicate = getattr(dependencies, "should_stop_processing", None) if dependencies is not None else None
    if callable(stop_predicate) and stop_predicate(getattr(context, "runtime", None)):
        raise LatePhaseStopped()
    if context.processing_operation != "audiobook":
        if not _should_run_audiobook_postprocess(context=context):
            return None
        narration_chunks_override = None
        cleanup_policy = str(context.app_config.get("reader_cleanup_policy", "advisory") or "advisory").strip().lower()
        if context.processing_operation == "translate" and bool(context.app_config.get("reader_cleanup_enabled", False)) and cleanup_policy != "off":
            narration_chunks_override = _project_final_cleanup_narration_chunks(
                context=context,
                final_generated_paragraph_registry=final_generated_paragraph_registry,
            )
        return _run_audiobook_postprocess(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            narration_chunks_override=narration_chunks_override,
        )
    narration_source = "\n\n".join(_collect_narration_chunks(state=state))
    if not narration_source:
        return None
    return strip_markdown_for_narration(narration_source)


def _validate_narration_artifact_text(narration_text: str) -> None:
    violations = [name for name, pattern in _NARRATION_DISALLOWED_PATTERNS if pattern.search(narration_text)]
    disallowed_tags = sorted(
        {
            tag
            for tag in _NARRATION_ANY_TAG_PATTERN.findall(narration_text)
            if _ELEVENLABS_TAG_PATTERN.fullmatch(tag) is None
        }
    )
    if disallowed_tags:
        violations.append(f"disallowed_tags={','.join(disallowed_tags[:5])}")
    if violations:
        raise RuntimeError("narration_artifact_validation_failed:" + ";".join(violations))


def _should_run_audiobook_postprocess(*, context: Any) -> bool:
    return context.processing_operation in {"edit", "translate"} and bool(
        context.app_config.get("audiobook_postprocess_enabled", False)
    )


def _collect_narration_chunks(*, state: Any) -> list[str]:
    return [str(chunk).strip() for chunk in getattr(state, "narration_chunks", []) if str(chunk).strip()]


def _resolve_audiobook_postprocess_model(*, context: Any) -> str:
    configured_model = str(context.app_config.get("audiobook_model", "")).strip()
    return configured_model or context.model


def _resolve_audiobook_postprocess_chunk_size(*, context: Any) -> int:
    configured_chunk_size = context.app_config.get("chunk_size", 6000)
    try:
        return max(int(configured_chunk_size), 3000)
    except (TypeError, ValueError):
        return 6000


def _build_narration_postprocess_groups(*, narration_chunks: Sequence[str], chunk_size: int) -> list[dict[str, object]]:
    if not narration_chunks:
        return []

    groups: list[dict[str, object]] = []
    group_start = 0
    current_chunks: list[str] = []
    current_chars = 0

    for chunk_index, chunk in enumerate(narration_chunks):
        chunk_chars = len(chunk)
        separator_chars = 2 if current_chunks else 0
        if current_chunks and current_chars + separator_chars + chunk_chars > chunk_size:
            group_end = group_start + len(current_chunks) - 1
            groups.append(
                {
                    "group_index": len(groups) + 1,
                    "start_index": group_start,
                    "end_index": group_end,
                    "target_text": "\n\n".join(current_chunks),
                    "context_before": narration_chunks[group_start - 1] if group_start > 0 else "",
                    "context_after": narration_chunks[group_end + 1] if group_end + 1 < len(narration_chunks) else "",
                }
            )
            group_start = chunk_index
            current_chunks = [chunk]
            current_chars = chunk_chars
            continue

        current_chunks.append(chunk)
        current_chars += separator_chars + chunk_chars

    if current_chunks:
        group_end = group_start + len(current_chunks) - 1
        groups.append(
            {
                "group_index": len(groups) + 1,
                "start_index": group_start,
                "end_index": group_end,
                "target_text": "\n\n".join(current_chunks),
                "context_before": narration_chunks[group_start - 1] if group_start > 0 else "",
                "context_after": narration_chunks[group_end + 1] if group_end + 1 < len(narration_chunks) else "",
            }
        )

    return groups


def _run_audiobook_postprocess(*, context: Any, dependencies: Any, emitters: Any, state: Any, narration_chunks_override: Sequence[str] | None = None) -> str | None:
    narration_chunks = list(narration_chunks_override) if narration_chunks_override is not None else _collect_narration_chunks(state=state)
    stop_predicate = getattr(dependencies, "should_stop_processing", None)
    if not narration_chunks:
        return None

    system_prompt = dependencies.load_system_prompt(
        operation="audiobook",
        source_language=context.source_language,
        target_language=context.target_language,
        editorial_intensity=str(context.app_config.get("editorial_intensity_default", "literary")),
        prompt_variant="default",
    )
    model = _resolve_audiobook_postprocess_model(context=context)
    fallback_client = None
    if not callable(getattr(dependencies, "resolve_model_selector", None)) or not callable(
        getattr(dependencies, "get_client_for_model_selector", None)
    ):
        fallback_client = dependencies.get_client()
    client, model_id, model_selector, model_provider = _resolve_text_call_target(
        selector=model,
        context=context,
        dependencies=dependencies,
        fallback_client=fallback_client,
    )
    groups = _build_narration_postprocess_groups(
        narration_chunks=narration_chunks,
        chunk_size=_resolve_audiobook_postprocess_chunk_size(context=context),
    )

    emitters.emit_status(
        context.runtime,
        stage="Подготовка narration",
        detail="Запущен отдельный audiobook post-pass для текста ElevenLabs.",
        current_block=len(state.processed_chunks),
        block_count=max(len(state.processed_chunks), 1),
        target_chars=sum(len(chunk) for chunk in narration_chunks),
        context_chars=0,
        progress=1.0,
        is_running=True,
    )
    emitters.emit_activity(context.runtime, "Запущена отдельная подготовка narration text для ElevenLabs.")

    processed_groups: list[str] = []
    for group in groups:
        if callable(stop_predicate) and stop_predicate(context.runtime):
            raise LatePhaseStopped()
        target_text = str(group["target_text"])
        context_before = str(group["context_before"])
        context_after = str(group["context_after"])
        group_index = _require_group_int(group, "group_index")
        start_index = _require_group_int(group, "start_index")
        end_index = _require_group_int(group, "end_index")
        dependencies.log_event(
            logging.INFO,
            "audiobook_postprocess_chunk_started",
            "Запущен audiobook post-pass для narration chunk group.",
            filename=context.uploaded_filename,
            operation="audiobook",
            **{"pass": "postprocess"},
            model=model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            chunk_index=group_index,
            chunk_count=len(groups),
            target_chars=len(target_text),
            context_before_chars=len(context_before),
            context_after_chars=len(context_after),
            start_index=start_index,
            end_index=end_index,
        )
        processed_chunk = dependencies.generate_markdown_block(
            client=client,
            model=model_id,
            system_prompt=system_prompt,
            target_text=target_text,
            context_before=context_before,
            context_after=context_after,
            max_retries=context.max_retries,
            expected_paragraph_ids=None,
            marker_mode=False,
        )
        if callable(stop_predicate) and stop_predicate(context.runtime):
            raise LatePhaseStopped()
        processed_groups.append(processed_chunk)
        dependencies.log_event(
            logging.INFO,
            "audiobook_postprocess_chunk_completed",
            "Audiobook post-pass для narration chunk group завершён.",
            filename=context.uploaded_filename,
            operation="audiobook",
            **{"pass": "postprocess"},
            model=model,
            model_selector=model_selector,
            model_provider=model_provider,
            model_id=model_id,
            chunk_index=group_index,
            chunk_count=len(groups),
            output_chars=len(processed_chunk),
        )

    emitters.emit_activity(context.runtime, "Подготовка narration text для ElevenLabs завершена.")
    return strip_markdown_for_narration("\n\n".join(processed_groups))
