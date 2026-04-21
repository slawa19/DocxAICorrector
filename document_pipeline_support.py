import inspect
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from formatting_diagnostics_retention import write_formatting_diagnostics_artifact


def resolve_system_prompt(
    load_system_prompt: Any,
    *,
    operation: str,
    source_language: str,
    target_language: str,
) -> str:
    try:
        signature = inspect.signature(load_system_prompt)
    except (TypeError, ValueError):
        signature = None

    if signature is None:
        return load_system_prompt(
            operation=operation,
            source_language=source_language,
            target_language=target_language,
        )

    parameters = signature.parameters.values()
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return load_system_prompt(
            operation=operation,
            source_language=source_language,
            target_language=target_language,
        )

    parameter_names = {parameter.name for parameter in parameters}
    if {"operation", "source_language", "target_language"}.issubset(parameter_names):
        return load_system_prompt(
            operation=operation,
            source_language=source_language,
            target_language=target_language,
        )

    return load_system_prompt()


def extract_marker_diagnostics_code(exc: Exception) -> str | None:
    message = str(exc)
    marker_prefix = "paragraph_marker_validation_failed:"
    registry_prefix = "paragraph_marker_registry_mismatch:"
    if marker_prefix in message:
        return message.split(marker_prefix, 1)[1].strip() or "unknown_marker_validation_failure"
    if registry_prefix in message:
        return message.split(registry_prefix, 1)[1].strip() or "unknown_marker_registry_failure"
    return None


def write_marker_diagnostics_artifact(
    *,
    stage: str,
    uploaded_filename: str,
    block_index: int,
    block_count: int,
    error_code: str,
    target_text: str,
    context_before: str,
    context_after: str,
    paragraph_ids: Sequence[str] | None,
    diagnostics_dir: Path,
    processed_chunk: str | None = None,
) -> str | None:
    return write_formatting_diagnostics_artifact(
        stage=stage,
        filename_prefix=f"marker_block_{stage}_{block_index:03d}",
        diagnostics_dir=diagnostics_dir,
        diagnostics={
            "uploaded_filename": uploaded_filename,
            "block_index": block_index,
            "block_count": block_count,
            "error_code": error_code,
            "paragraph_ids": list(paragraph_ids or []),
            "target_text_preview": target_text[:1000],
            "context_before_preview": context_before[:600],
            "context_after_preview": context_after[:600],
            "processed_chunk_preview": (processed_chunk or "")[:1000],
        },
    )


def call_docx_restorer_with_optional_registry(
    restorer: Any,
    docx_bytes: bytes,
    paragraphs: Any,
    generated_paragraph_registry: Any,
) -> bytes:
    try:
        return restorer(
            docx_bytes,
            paragraphs,
            generated_paragraph_registry=generated_paragraph_registry,
        )
    except TypeError as exc:
        if "generated_paragraph_registry" not in str(exc):
            raise
        return restorer(docx_bytes, paragraphs)


def current_markdown(processed_chunks: Sequence[str]) -> str:
    return "\n\n".join(processed_chunks).strip()