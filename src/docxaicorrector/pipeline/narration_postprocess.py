"""Narration / audiobook post-pass (spec 031 Cluster J).

Behaviour-preserving extraction from ``pipeline/late_phases.py``: the narration-text
builder, the artifact-text review pass (ElevenLabs tag / reference-marker checks), and the
optional separate audiobook LLM post-pass reached only through injected ``dependencies``
callables (offline-drivable — no module-level SDK client). ``late_phases`` re-exports these
names so ``late_phases.<name>`` keeps resolving for the test namespace and the still-in
-``late_phases`` ``finalize_processing_success`` caller. No module-level mutable state; all
patterns are immutable compiled constants.

**The artifact check is review DATA, not a verdict gate (spec 054 Finding 4, binding).**
It used to raise, and one match anywhere in a whole book's narration failed the standalone
``audiobook`` run outright — no artifact at all, after the entire LLM run was paid for.
Measured on 2026-08-04, four of the six patterns fired on ordinary prose: a parenthetical
``(Германия, 1923)`` reads as an inline citation, and the bare words ``ISBN`` / ``arXiv``
read as identifiers. Re-measured here over the four corpus books' imported narration text:
``inline_citation`` 4 / 65 / 178 / 191 hits per book. Constitution VII settles the shape of
the fix — a check whose residual is treated as a HARD failure "MUST emit the residual as
review data" — and it also forbids the name / city / publisher lists it would take to make
``inline_citation`` precise. So the check reports, the artifact ships, and a human decides.
The imprecision is now a spare line in a review log instead of a destroyed run.
"""

import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

from docxaicorrector.generation._generation import (
    strip_markdown_for_narration,
    strip_markdown_for_narration_with_stats,
)
from docxaicorrector.pipeline.text_call_support import _require_group_int, _resolve_text_call_target
from docxaicorrector.pipeline.contracts import LatePhaseStopped


# Space, ASCII hyphen and the Unicode dash block U+2010..U+2015 — the separators a printed
# ISBN is broken with. Form, not a literal: no per-book string enters the rule.
_ISBN_SEPARATOR = r"[ \t‐-―\-]"
_ELEVENLABS_TAG_PATTERN = re.compile(r"\[(?:thoughtful|curious|serious|sad|excited|annoyed|sarcastic|whispers|short pause|long pause|sighs|laughs|chuckles|exhales)\]")
_NARRATION_ANY_TAG_PATTERN = re.compile(r"\[[^\]\n]{1,40}\]")
_NARRATION_DISALLOWED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("internal_placeholder", re.compile(r"\[\[DOCX_[A-Za-z0-9_]+\]\]")),
    ("raw_url", re.compile(r"(?:https?://\S+|www\.\S+)", re.IGNORECASE)),
    ("doi", re.compile(r"\bdoi\s*[:/]?\s*10\.\d{4,9}/\S+", re.IGNORECASE)),
    # Keyed on the IDENTIFIER, the same form-based shape as ``doi`` above — not on the bare
    # word. ``\bisbn\b`` / ``\barxiv\b`` matched a book that merely TALKS about publishing
    # ("Издательство присвоило книге ISBN и отправило её в печать.", "Он опубликовал
    # препринт на arXiv…"), which is narratable prose and exactly what a listener wants
    # read out. What is not narratable is the number itself, so the number is what the
    # rules require: at least ten ISBN digits after the label, or a real arXiv id.
    # Measured 2026-08-04 over the four corpus books' imported narration text: the bare word
    # ``isbn`` hit 1 / 0 / 3 / 0 times per book and ``isbn_identifier`` hits 1 / 0 / 3 / 0 —
    # every real ISBN is still reported, and every hit is a genuine printed identifier
    # ("ISBN 978-1-60994-296-0"). ``arxiv`` never fired on this corpus in either form, so the
    # tightening cannot have lost signal there; the form mirrors ``doi``, which does fire (7
    # hits on Mazzucato) and is the same shape of rule.
    ("isbn_identifier", re.compile(r"\bisbn(?:-1[03])?\b[^\n\d]{0,8}\d(?:" + _ISBN_SEPARATOR + r"?\d){8,}" + _ISBN_SEPARATOR + r"?[\dXx]", re.IGNORECASE)),
    ("arxiv_identifier", re.compile(r"\barxiv\b\s*[:/]?\s*(?:\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7})", re.IGNORECASE)),
    ("inline_citation", re.compile(r"\((?:ibid\.|там же|[A-ZА-ЯЁ][^()]{0,80}?,\s*(?:19|20)\d{2})[^()]*\)", re.IGNORECASE)),
    # NO superscript-digit rule. A raised digit is not evidence of a footnote marker: the
    # PDF importer emits Unicode superscripts for every small raised digit welded to the
    # text before it, and a mathematical exponent ("x\u00B2", "m\u00B2") is welded exactly like a
    # reference ("\u2026Rome.\u2075", "as Smith notes\u00B9"). Telling them apart needs to understand the
    # formula, which this pipeline deliberately does not do. Removing reference markers is
    # the audiobook prompt's job (rule 1); a model that correctly KEEPS an exponent used to
    # fail this gate, which drops the optional narration on edit/translate and fails a
    # standalone audiobook run outright \u2014 losing the whole artifact over one glyph that TTS
    # would simply read as a number.
    ("markdown_heading", re.compile(r"^\s{0,3}#", re.MULTILINE)),
)
# A whole book's narration can match one rule hundreds of times (measured: 191 and 178
# ``inline_citation`` hits on two corpus books). The review record carries the COUNT plus a
# few truncated examples — enough to judge the class, small enough for a log line.
_NARRATION_REVIEW_SAMPLE_LIMIT = 3
_NARRATION_REVIEW_SAMPLE_CHARS = 120


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
        # Spec 054: a paragraph whose block took the source-text controlled fallback is not
        # narratable — the model's output was rejected and the block's own source text stands
        # in its place. The standalone ``audiobook`` operation never puts it in
        # ``state.narration_chunks``; this projection rebuilds the narration from the final
        # registry instead, so it has to honour the same decision or the two entry points
        # would diverge (anti-regression 3). The flag is written at the moment of the
        # fallback, in ``block_execution.append_controlled_fallback_registry_entries``.
        if bool(raw_entry.get("controlled_fallback_narration_excluded", False)):
            continue
        # Spec 056 E, same reasoning one level down: a paragraph the model returned nothing
        # for keeps its SOURCE text in the document but must not be read aloud. The
        # standalone ``audiobook`` operation drops it in ``block_execution`` before the
        # chunk is ever appended; this projection rebuilds the narration from the final
        # registry, so it has to honour the same decision or the two entry points diverge
        # (spec 054 anti-regression 3).
        if str(raw_entry.get("paragraph_status", "") or "") == "omitted":
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
    return _assemble_narration_recording_joins(narration_source, state=state)


def _assemble_narration_recording_joins(narration_source: str, *, state: Any) -> str:
    """Assemble the narration and record how many sentence continuations were rejoined.

    Both narration entry points come through here — the standalone ``audiobook`` operation
    and the optional post-pass on translate/edit — so the counter means the same thing on
    each, exactly as the exclusion counters beside it do (anti-regression 3 of spec 054).
    """

    narration_text, joined_count = strip_markdown_for_narration_with_stats(narration_source)
    if state is not None:
        state.narration_joined_sentence_continuation_count = int(
            getattr(state, "narration_joined_sentence_continuation_count", 0) or 0
        ) + joined_count
    return narration_text


def _collect_narration_artifact_review_findings(narration_text: str) -> list[dict[str, object]]:
    """Report what the finished narration still carries, as review DATA for a human.

    Replaces ``_validate_narration_artifact_text``, which raised. Returns one entry per rule
    that matched — rule name, how many times, and up to
    ``_NARRATION_REVIEW_SAMPLE_LIMIT`` truncated samples so the reader can judge the match
    without the log carrying the model payload (LOGGING_AND_ARTIFACT_RETENTION §1.5).
    An empty list means nothing to review; it is never an error either way.
    """
    findings: list[dict[str, object]] = []
    for name, pattern in _NARRATION_DISALLOWED_PATTERNS:
        matches = [match.group(0) for match in pattern.finditer(narration_text)]
        if not matches:
            continue
        findings.append(
            {
                "rule": name,
                "match_count": len(matches),
                "samples": [
                    _truncate_narration_review_sample(match)
                    for match in matches[:_NARRATION_REVIEW_SAMPLE_LIMIT]
                ],
            }
        )
    disallowed_tags = sorted(
        {
            tag
            for tag in _NARRATION_ANY_TAG_PATTERN.findall(narration_text)
            if _ELEVENLABS_TAG_PATTERN.fullmatch(tag) is None
        }
    )
    if disallowed_tags:
        findings.append(
            {
                "rule": "disallowed_tags",
                "match_count": len(disallowed_tags),
                "samples": [
                    _truncate_narration_review_sample(tag)
                    for tag in disallowed_tags[:_NARRATION_REVIEW_SAMPLE_LIMIT]
                ],
            }
        )
    return findings


def _truncate_narration_review_sample(sample: str) -> str:
    collapsed = " ".join(str(sample).split())
    if len(collapsed) <= _NARRATION_REVIEW_SAMPLE_CHARS:
        return collapsed
    return collapsed[:_NARRATION_REVIEW_SAMPLE_CHARS] + "…"


def _summarize_narration_review_findings(
    findings: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Flatten review findings into the counters every observable surface publishes."""
    rules = [str(finding.get("rule", "")) for finding in findings]
    match_count = 0
    for finding in findings:
        raw_count = finding.get("match_count", 0)
        match_count += raw_count if isinstance(raw_count, int) and not isinstance(raw_count, bool) else 0
    return {
        "review_finding_count": len(findings),
        "review_match_count": match_count,
        "review_rules": rules,
    }


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
    return _assemble_narration_recording_joins(
        "\n\n".join(processed_groups), state=state
    )
