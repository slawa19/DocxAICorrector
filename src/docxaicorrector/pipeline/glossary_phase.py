"""Spec 063 P2: the run glossary phase — one call, before the first block of a ``translate`` run.

The pure half (candidates by form, the request, the answer's contract) lives in
``text/glossary_pass.py``. This phase decides whether to run, makes the one call through the
run's own text client and model, writes the artifact, logs the outcome and hands the block
phase a context whose ``document_context_prompt`` carries the glossary section. That prompt
already reaches every block's system prompt of ``translate`` (``block_execution.py``,
``_build_prompt_source_text``), and nothing else: ``edit`` and ``audiobook`` never read it.

FAIL-OPEN. The glossary makes renderings consistent; without it the run is today's product.
Any failure is logged as WARNING, surfaced as a notice and recorded in the artifact, and the
run goes on with the context it had. No status of this phase touches delivery, the quality
gate or the acceptance verdict (Constitution VII, "no verifier as a gate").
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from docxaicorrector.core import constants
from docxaicorrector.core.model_accounting import STAGE_GLOSSARY_EXTRACTION, snapshot_run_model_accounting
from docxaicorrector.document.segments import (
    DEFAULT_GLOSSARY_PROMPT_MAX_CHARS,
    GlossaryTerm,
    render_glossary_prompt_section,
)
from docxaicorrector.pipeline.contracts import LatePhaseStopped
from docxaicorrector.runtime.artifact_retention import (
    RUN_GLOSSARIES_MAX_AGE_SECONDS,
    RUN_GLOSSARIES_MAX_COUNT,
    prune_artifact_dir,
)
from docxaicorrector.text.glossary_pass import (
    DEFAULT_GLOSSARY_CANDIDATE_LIMIT,
    DEFAULT_GLOSSARY_MAX_TERMS,
    RUN_GLOSSARY_SECTION_HEADER,
    GlossaryCandidate,
    GlossaryResponseError,
    build_glossary_request,
    domain_glossary_terms,
    extract_glossary_candidates,
    parse_glossary_response,
    request_candidates,
    select_glossary_source_units,
)


RUN_GLOSSARY_SCHEMA = "run_glossary/v1"
RUN_GLOSSARY_STATUS_NOT_APPLICABLE = "not_applicable"
RUN_GLOSSARY_STATUS_BUILT = "built"
RUN_GLOSSARY_STATUS_EMPTY = "empty"
RUN_GLOSSARY_STATUS_NO_CANDIDATES = "no_candidates"
RUN_GLOSSARY_STATUS_FAILED = "failed"
RUN_GLOSSARY_STATUS_STOPPED = "stopped"
RUN_GLOSSARY_NOTICE_KIND = "glossary"
RUN_GLOSSARY_BUILT_MESSAGE_KEY = "result.run_glossary_built"
RUN_GLOSSARY_FAILED_MESSAGE_KEY = "result.run_glossary_failed"
_ERROR_PREVIEW_CHARS = 120
_UNSAFE_STEM_CHARS_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def resolve_run_glossaries_dir() -> Path:
    """Read at call time, so a test (or ``DOCX_AI_RUN_DIR``) can move the family."""

    return Path(constants.RUN_GLOSSARIES_DIR)


def _int_setting(app_config: Mapping[str, object], key: str, default: int) -> int:
    value = app_config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def glossary_pass_applies(context: Any) -> bool:
    if str(getattr(context, "processing_operation", "") or "") != "translate":
        return False
    app_config = getattr(context, "app_config", None) or {}
    return bool(app_config.get("glossary_pass_enabled", False))


def build_run_glossary_notice(*, status: str, term_count: int) -> dict[str, object] | None:
    """The one result-screen notice the glossary may produce, or ``None`` (nothing to say)."""

    if status == RUN_GLOSSARY_STATUS_BUILT and term_count > 0:
        return {
            "kind": RUN_GLOSSARY_NOTICE_KIND,
            "level": "info",
            "message_key": RUN_GLOSSARY_BUILT_MESSAGE_KEY,
            "params": {"count": int(term_count)},
        }
    if status == RUN_GLOSSARY_STATUS_FAILED:
        return {
            "kind": RUN_GLOSSARY_NOTICE_KIND,
            "level": "warning",
            "message_key": RUN_GLOSSARY_FAILED_MESSAGE_KEY,
        }
    return None


def _stage_usage() -> dict[str, object]:
    try:
        stages = snapshot_run_model_accounting().get("stages") or {}
    except Exception:
        return {"prompt_tokens": None, "completion_tokens": None, "cost_usd": None}
    stage = stages.get(STAGE_GLOSSARY_EXTRACTION) if isinstance(stages, Mapping) else None
    if not isinstance(stage, Mapping):
        return {"prompt_tokens": None, "completion_tokens": None, "cost_usd": None}
    cost_known = int(stage.get("model_calls_without_cost", 0) or 0) == 0 and int(stage.get("model_call_count", 0) or 0) > 0
    usage_known = int(stage.get("model_calls_with_usage", 0) or 0) > 0
    return {
        "prompt_tokens": stage.get("prompt_tokens") if usage_known else None,
        "completion_tokens": stage.get("completion_tokens") if usage_known else None,
        "cost_usd": stage.get("cost_usd_reported_by_provider") if cost_known else None,
    }


def _artifact_stem(context: Any) -> str:
    for value in (getattr(context, "run_id", ""), getattr(context, "source_token", "")):
        stem = _UNSAFE_STEM_CHARS_RE.sub("_", str(value or "").strip())[:64]
        if stem:
            return stem
    return "run"


def _write_run_glossary_artifact(payload: Mapping[str, object], *, context: Any) -> str:
    target_dir = resolve_run_glossaries_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{_artifact_stem(context)}_{int(time.time() * 1000)}.json"
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    prune_artifact_dir(
        target_dir=target_dir,
        max_age_seconds=RUN_GLOSSARIES_MAX_AGE_SECONDS,
        max_count=RUN_GLOSSARIES_MAX_COUNT,
    )
    return str(path)


def _rendered_term_count(section: str) -> int:
    return sum(1 for line in section.splitlines() if line.startswith("- ") and line != "- ...")


def run_glossary_phase(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    request_text_completion_fn: Callable[..., str] | None = None,
) -> Any:
    """Build the run glossary and return the context the block phase should use."""

    if not glossary_pass_applies(context):
        return context
    try:
        return _run_glossary_phase(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            request_text_completion_fn=request_text_completion_fn,
        )
    except Exception as exc:  # pragma: no cover - the inner phase already catches its own failures
        _set_state(state, status=RUN_GLOSSARY_STATUS_FAILED, term_count=0)
        _log_failed(
            dependencies,
            context=context,
            model="",
            error_code=type(exc).__name__,
            error_message=str(exc),
            candidate_count=0,
            artifact_path=None,
        )
        return context


def _set_state(state: Any, *, status: str, term_count: int) -> None:
    try:
        state.run_glossary_status = status
        state.run_glossary_term_count = int(term_count)
    except Exception:
        pass


def _log_failed(
    dependencies: Any,
    *,
    context: Any,
    model: str,
    error_code: str,
    error_message: str,
    candidate_count: int,
    artifact_path: str | None,
) -> None:
    dependencies.log_event(
        logging.WARNING,
        "run_glossary_failed",
        "Глоссарий прогона не построен; перевод идёт без него.",
        filename=getattr(context, "uploaded_filename", ""),
        status=RUN_GLOSSARY_STATUS_FAILED,
        model=model,
        error_code=error_code,
        error_message=" ".join(str(error_message or "").split())[:_ERROR_PREVIEW_CHARS],
        candidate_count=candidate_count,
        artifact_path=artifact_path,
    )


def _run_glossary_phase(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    request_text_completion_fn: Callable[..., str] | None,
) -> Any:
    app_config: Mapping[str, object] = getattr(context, "app_config", None) or {}
    max_terms = max(0, _int_setting(app_config, "glossary_max_terms", DEFAULT_GLOSSARY_MAX_TERMS))
    prompt_max_chars = max(0, _int_setting(app_config, "glossary_prompt_max_chars", DEFAULT_GLOSSARY_PROMPT_MAX_CHARS))
    candidate_limit = max(0, _int_setting(app_config, "glossary_candidate_limit", DEFAULT_GLOSSARY_CANDIDATE_LIMIT))
    model = str(getattr(initialization, "text_model_id", "") or getattr(context, "model", "") or "")

    units = select_glossary_source_units(list(getattr(context, "jobs", ()) or ()), getattr(context, "source_paragraphs", None))
    candidates = extract_glossary_candidates(units, limit=candidate_limit)
    fixed_terms = domain_glossary_terms(
        source_text="\n\n".join(unit.text for unit in units),
        translation_domain=str(getattr(context, "translation_domain", "general") or "general"),
    )
    sent_candidates = request_candidates(candidates, fixed_terms)

    record: dict[str, object] = {
        "schema": RUN_GLOSSARY_SCHEMA,
        "run_id": str(getattr(context, "run_id", "") or ""),
        "source_token": str(getattr(context, "source_token", "") or ""),
        "filename": str(getattr(context, "uploaded_filename", "") or ""),
        "status": RUN_GLOSSARY_STATUS_NO_CANDIDATES,
        "model": model,
        "source_language": str(getattr(context, "source_language", "") or ""),
        "target_language": str(getattr(context, "target_language", "") or ""),
        "source_unit_count": len(units),
        "candidate_count": len(candidates),
        "request_candidate_count": len(sent_candidates),
        "domain_term_count": len(fixed_terms),
        "max_terms": max_terms,
        "prompt_max_chars": prompt_max_chars,
        "terms": [],
        "rejected_counts": {},
        "rendered_term_count": 0,
        "prompt_section_chars": 0,
        "usage": {"prompt_tokens": None, "completion_tokens": None, "cost_usd": None},
        "request_chars": 0,
        "candidates": [candidate.to_payload() for candidate in candidates],
        "error_code": None,
    }

    terms: tuple[GlossaryTerm, ...] = ()
    if not sent_candidates or max_terms <= 0:
        status = RUN_GLOSSARY_STATUS_NO_CANDIDATES
    elif dependencies.should_stop_processing(context.runtime):
        status = RUN_GLOSSARY_STATUS_STOPPED
    else:
        status, terms = _call_model(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            initialization=initialization,
            model=model,
            sent_candidates=sent_candidates,
            fixed_terms=fixed_terms,
            max_terms=max_terms,
            record=record,
            request_text_completion_fn=request_text_completion_fn,
        )

    section = ""
    if status == RUN_GLOSSARY_STATUS_BUILT:
        section = render_glossary_prompt_section(terms, header=RUN_GLOSSARY_SECTION_HEADER, max_chars=prompt_max_chars)
    record["status"] = status
    record["terms"] = [
        {"source_term": term.source_term, "target_term": term.target_term, "kind": term.kind, "note": term.note}
        for term in terms
    ]
    record["rendered_term_count"] = _rendered_term_count(section)
    record["prompt_section_chars"] = len(section)

    artifact_path: str | None = None
    if status != RUN_GLOSSARY_STATUS_STOPPED:
        try:
            artifact_path = _write_run_glossary_artifact(record, context=context)
        except Exception as exc:
            dependencies.log_event(
                logging.WARNING,
                "run_glossary_artifact_write_failed",
                "Не удалось сохранить артефакт глоссария прогона; глоссарий и прогон не затронуты.",
                filename=getattr(context, "uploaded_filename", ""),
                error_type=type(exc).__name__,
                error_message=" ".join(str(exc).split())[:_ERROR_PREVIEW_CHARS],
            )

    _set_state(state, status=status, term_count=len(terms) if status == RUN_GLOSSARY_STATUS_BUILT else 0)
    usage = record["usage"] if isinstance(record["usage"], Mapping) else {}
    if status == RUN_GLOSSARY_STATUS_FAILED:
        _log_failed(
            dependencies,
            context=context,
            model=model,
            error_code=str(record.get("error_code") or "unknown"),
            error_message=str(record.get("error_message") or ""),
            candidate_count=len(candidates),
            artifact_path=artifact_path,
        )
    elif status != RUN_GLOSSARY_STATUS_STOPPED:
        dependencies.log_event(
            logging.INFO,
            "run_glossary_built",
            "Глоссарий прогона построен по документу.",
            filename=getattr(context, "uploaded_filename", ""),
            status=status,
            model=model,
            candidate_count=len(candidates),
            request_candidate_count=len(sent_candidates),
            domain_term_count=len(fixed_terms),
            term_count=len(terms),
            rendered_term_count=record["rendered_term_count"],
            prompt_section_chars=record["prompt_section_chars"],
            rejected_counts=dict(record["rejected_counts"]) if isinstance(record["rejected_counts"], Mapping) else {},
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cost_usd=usage.get("cost_usd"),
            artifact_path=artifact_path,
        )

    if not section:
        return context
    existing_prompt = str(getattr(context, "document_context_prompt", "") or "").strip()
    combined_prompt = f"{existing_prompt}\n\n{section}" if existing_prompt else section
    return replace(context, document_context_prompt=combined_prompt)


def _call_model(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    initialization: Any,
    model: str,
    sent_candidates: tuple[GlossaryCandidate, ...],
    fixed_terms: tuple[GlossaryTerm, ...],
    max_terms: int,
    record: dict[str, object],
    request_text_completion_fn: Callable[..., str] | None,
) -> tuple[str, tuple[GlossaryTerm, ...]]:
    if request_text_completion_fn is None:
        from docxaicorrector.generation._generation import request_text_completion

        request_text_completion_fn = request_text_completion
    job_count = int(getattr(initialization, "job_count", 0) or 0)
    emitters.emit_status(
        context.runtime,
        stage="Глоссарий книги",
        detail=f"Закрепляю передачи терминов и имён книги: {len(sent_candidates)} кандидатов, один запрос к модели.",
        current_block=0,
        block_count=job_count,
        target_chars=0,
        context_chars=0,
        progress=0.0,
        is_running=True,
    )
    request = build_glossary_request(
        model=model,
        candidates=sent_candidates,
        fixed_terms=fixed_terms,
        source_language=str(getattr(context, "source_language", "") or ""),
        target_language=str(getattr(context, "target_language", "") or ""),
        max_terms=max_terms,
    )
    request_input = request.get("input")
    record["request_chars"] = sum(
        len(str(part.get("text", "")))
        for item in (request_input if isinstance(request_input, list) else [])
        if isinstance(item, Mapping)
        for part in (item.get("content") or [])
        if isinstance(part, Mapping)
    )
    client = getattr(initialization, "text_client", None) or getattr(initialization, "client", None)
    try:
        raw_text = request_text_completion_fn(
            client,
            request,
            usage_stage=STAGE_GLOSSARY_EXTRACTION,
            should_stop=lambda: bool(dependencies.should_stop_processing(context.runtime)),
        )
    except LatePhaseStopped:
        record["usage"] = _stage_usage()
        return RUN_GLOSSARY_STATUS_STOPPED, ()
    except Exception as exc:
        record["usage"] = _stage_usage()
        record["error_code"] = type(exc).__name__
        record["error_message"] = str(exc)[:_ERROR_PREVIEW_CHARS]
        return RUN_GLOSSARY_STATUS_FAILED, ()
    record["usage"] = _stage_usage()
    try:
        parsed = parse_glossary_response(raw_text, candidates=sent_candidates, max_terms=max_terms)
    except GlossaryResponseError as exc:
        record["error_code"] = exc.code
        record["error_message"] = str(exc)[:_ERROR_PREVIEW_CHARS]
        return RUN_GLOSSARY_STATUS_FAILED, ()
    record["rejected_counts"] = dict(parsed.rejected_counts)
    if not parsed.terms:
        return RUN_GLOSSARY_STATUS_EMPTY, ()
    return RUN_GLOSSARY_STATUS_BUILT, parsed.terms


__all__ = [
    "RUN_GLOSSARY_BUILT_MESSAGE_KEY",
    "RUN_GLOSSARY_FAILED_MESSAGE_KEY",
    "RUN_GLOSSARY_NOTICE_KIND",
    "build_run_glossary_notice",
    "glossary_pass_applies",
    "resolve_run_glossaries_dir",
    "run_glossary_phase",
]
