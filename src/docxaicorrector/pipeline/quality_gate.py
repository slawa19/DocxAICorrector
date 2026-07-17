"""Document-level translation quality-gate decisioning (spec 031, Step 8 / Cluster F).

Behaviour-preserving extraction from ``pipeline/late_phases.py``: the quality-gate
serializers, leaf detectors, threshold/hygiene helpers, formatting-review-item builders,
the acceptance-verdict wrappers, and the ``_build_translation_quality_report`` hub plus
its authority/warning helpers. ``late_phases`` re-exports every name here so
``late_phases.<name>`` keeps resolving for the test namespace and the still-in-``late_phases``
callers (``finalize_processing_success``). No module-level mutable state; pure CPU (no LLM).

Monkeypatch / compat seam (F15 — the contract is *this module*):
    The detector/serializer/collector leaves live in the ``quality_gate_serializers`` and
    ``quality_gate_text_detectors`` satellites (and in ``output_validation`` /
    ``formatting_coverage``), but they are imported *into this module's namespace* above and
    every gate function invokes them by bare name. Name resolution therefore happens against
    THIS module's globals at call time, so the single documented patch point is
    ``quality_gate.<name>`` — patching it there lands for the whole gate, even when the
    ``_build_translation_quality_report`` hub is reached through the ``late_phases.<name>``
    re-export (the hub still *executes* in this namespace). Patch here, NOT at ``late_phases``
    (that re-export binding is a copy and would be a stale no-op for the hub's own callees).

    Caveat — transitive calls INSIDE a satellite: when one satellite leaf calls another
    (e.g. ``_is_untranslated_body_text`` calls ``_is_bibliography_or_url_dominant_text`` and
    ``_latin_letter_ratio`` from within ``quality_gate_text_detectors``), that inner call
    resolves against the *satellite's* globals, so patching ``quality_gate.<inner_leaf>`` does
    NOT reach it. Patch the outermost leaf this module invokes directly (``_is_untranslated_
    body_text``), or patch the satellite module itself, to override transitive behaviour.

TODO (F15): ``_resolve_acceptance_output_artifacts`` reaches the PRIVATE
``docxaicorrector.validation.structural._build_output_artifacts``. Promoting it to a public
wrapper is out of this module's scope (would edit ``validation/structural.py``); left as a
documented private-access seam until that module exposes a public entry point.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from docxaicorrector.processing.preparation import humanize_quality_gate_reasons
from docxaicorrector.validation.acceptance import build_acceptance_verdict
from docxaicorrector.validation.formatting_coverage import (
    classify_heading_demotions,
    resolve_role_aware_formatting_unmapped_source_summary,
    resolve_role_aware_formatting_unmapped_target_summary,
)
from docxaicorrector.validation.quality_gate_audit import quality_gate_audit_classifications_payload
from docxaicorrector.pipeline.output_validation import (
    build_generated_paragraph_registry_from_entries,
    collect_bullet_heading_samples,
    collect_recovered_heading_entries,
    collect_false_fragment_heading_samples,
    collect_false_fragment_heading_samples_from_entries,
    collect_list_fragment_regression_samples,
    collect_mixed_script_samples,
    collect_paragraph_break_samples,
    collect_page_placeholder_heading_concat_samples,
    collect_residual_bullet_glyph_samples,
    has_toc_body_concat_markdown,
)
from docxaicorrector.pipeline.formatting_diagnostics_feedback import (
    _load_formatting_diagnostics_payloads,
)
from docxaicorrector.pipeline.runtime_display_markdown import (
    _BULLET_MARKDOWN_HEADING_PATTERN,
    _DOCX_INTERNAL_PLACEHOLDER_PATTERN,
    _REVIEW_ANCHOR_HEADING_MARKER_PATTERN,
    _normalize_final_markdown_for_display_hygiene_reporting,
    _normalize_final_markdown_for_quality_gate,
)
from docxaicorrector.pipeline.quality_gate_serializers import (  # noqa: F401
    _serialize_assembly_decisions,
    _serialize_quality_samples,
    _serialize_paragraph_break_samples,
    _serialize_recovered_heading_entries,
    _serialize_untranslated_structural_sample,
    _serialize_role_loss_sample,
    _serialize_heading_demotion_sample,
)
from docxaicorrector.pipeline.quality_gate_text_detectors import (  # noqa: F401
    _STANDALONE_NUMERIC_CONTINUATION_PATTERN,
    _UNTRANSLATED_BODY_MIN_CHARS,
    _UNTRANSLATED_BODY_MIN_LATIN_WORDS,
    _UNTRANSLATED_BODY_FAIL_MIN_CHARS,
    _UNTRANSLATED_BODY_FAIL_RATIO,
    _LATIN_LETTER_PATTERN,
    _LATIN_WORD_PATTERN,
    _CYRILLIC_LETTER_PATTERN,
    _MARKDOWN_STRUCTURAL_PREFIX_PATTERN,
    _URL_OR_DOMAIN_PATTERN,
    _BIBLIOGRAPHY_LIKE_PATTERN,
    _strip_structural_markdown_prefix,
    _is_untranslated_structural_text,
    _latin_letter_ratio,
    _is_bibliography_or_url_dominant_text,
    _is_untranslated_body_text,
    _is_standalone_numeric_continuation_sample,
    _REFERENCES_BIB_MARKER_PATTERN,
    _MULTI_FOOTNOTE_MARKER_PATTERN,
    _is_citation_form_list_fragment_sample,
)


def _format_translation_quality_gate_failure_message(gate_reasons: Sequence[str]) -> str:
    reasons = humanize_quality_gate_reasons(gate_reasons)
    base = "Итоговый перевод не прошёл document-level quality gate."
    if not reasons:
        return f"{base} (translation_quality_gate_failed)"
    return f"{base} (translation_quality_gate_failed) Причины: {', '.join(reasons)}."


def _resolve_translation_quality_gate_policy(*, context: Any) -> str:
    configured = str(context.app_config.get("translation_output_quality_gate_policy", "")).strip().lower()
    if configured in {"strict", "advisory"}:
        return configured
    if context.processing_operation == "translate":
        return "strict"
    return "advisory"


def _count_bullet_markdown_headings(markdown_text: str) -> int:
    return len(_BULLET_MARKDOWN_HEADING_PATTERN.findall(markdown_text or ""))


def _has_toc_body_concat_markdown(markdown_text: str) -> bool:
    return has_toc_body_concat_markdown(markdown_text)


def _apply_quality_gate_reason(
    *,
    quality_status: str,
    gate_reasons: list[str],
    policy: str,
    reason: str,
) -> str:
    if policy == "strict":
        quality_status = "fail"
    elif quality_status != "fail":
        quality_status = "warn"
    gate_reasons.append(reason)
    return quality_status


def _apply_quality_review_reason(
    *,
    quality_status: str,
    gate_reasons: list[str],
    reason: str,
) -> str:
    if quality_status != "fail":
        quality_status = "warn"
    gate_reasons.append(reason)
    return quality_status


# spec 018: the document-level translation quality gate hard-fails (blocking red)
# ONLY for genuinely NON-DELIVERABLE output. An empty/unopenable DOCX is guarded
# separately by ``_validate_nonempty_docx_bytes_or_fail``; the quality-report
# gate_reasons catastrophic enough to block delivery of an otherwise-usable document
# are wholesale-untranslated BODY above the catastrophic threshold and a
# caption→heading structural conflict (spec 042 P1-B: a figure/table caption promoted
# to a heading corrupts the document outline — non-deliverable). Every other
# fail-driver (role_loss, heading_demotion, false_fragment, list_fragment, unmapped
# source, toc_body_concat, mixed_script, residual_bullet, …) is a fix/review-severity
# formatting discrepancy: the document IS delivered and the verdict is downgraded to
# ``warn`` (review-DATA). This keys on the reason TOKEN (severity), never on document
# content, so there are no per-book literals (Constitution VII).
_FATAL_DOCUMENT_GATE_REASONS: frozenset[str] = frozenset(
    {"untranslated_body_text_above_threshold", "caption_heading_conflict"}
)


def _resolve_document_delivery_verdict(
    *,
    quality_status: str,
    gate_reasons: Sequence[str],
) -> str:
    """Resolve the DOCUMENT-level delivery verdict on top of the per-reason gate status.

    The per-reason gate logic still computes ``fail`` for any strict-policy
    formatting discrepancy; this resolves the delivery verdict for the whole
    document. A ``fail`` is preserved only when a genuinely-fatal reason is present
    (``_FATAL_DOCUMENT_GATE_REASONS``). Otherwise the run is deliverable and a
    review-grade ``fail`` is downgraded to ``warn`` so the flagged-but-usable
    document is presented as "completed, needs review" rather than blocked
    (spec 018). ``pass``/``warn`` verdicts are returned unchanged. All gate_reasons
    and review-items are preserved verbatim — only the verdict severity moves.
    """
    if any(reason in _FATAL_DOCUMENT_GATE_REASONS for reason in gate_reasons):
        return "fail"
    if quality_status == "fail":
        return "warn"
    return quality_status


def _has_source_backed_entry_authority(assembly_entries: Sequence[object]) -> bool:
    return any(
        bool(getattr(entry, "from_registry", False)) and not bool(getattr(entry, "used_fallback", False))
        for entry in assembly_entries
    )


def _resolve_false_fragment_heading_gate_samples(
    *,
    raw_samples: Sequence[object],
    entry_samples: Sequence[object],
    source_backed_entry_authority: bool,
) -> tuple[list[object], str]:
    if source_backed_entry_authority:
        return list(entry_samples), "entry_assembly"
    return list(raw_samples), "legacy_markdown"


def _resolve_list_fragment_regression_gate_samples(
    *,
    raw_samples: Sequence[object],
    final_markdown: str,
    assembly_entries: Sequence[object],
    source_backed_entry_authority: bool,
    topology_projection_supported: bool,
) -> tuple[list[object], str]:
    if source_backed_entry_authority and topology_projection_supported:
        return [], "topology_projection"
    if source_backed_entry_authority and assembly_entries:
        entry_by_line = _build_source_backed_entry_by_markdown_line(
            final_markdown=final_markdown,
            assembly_entries=assembly_entries,
        )
        source_backed_list_texts = _build_source_backed_list_entry_texts(assembly_entries)
        unresolved_samples = [
            sample
            for sample in raw_samples
            if not _is_source_backed_list_sample(
                sample=sample,
                entry_by_line=entry_by_line,
                source_backed_list_texts=source_backed_list_texts,
            )
        ]
        # FR-001/FR-002 (Constitution VII, "no source signal, no repair"): a carry-over
        # sample survives to the gate only if it has SOURCE LIST CONTEXT — its resolved
        # assembly entry, or the immediately preceding / following entry, is a source-backed
        # list entry. A prose paragraph that merely ends in a trailing ordinal (a
        # cross-reference / year / citation) has a body entry and body/heading neighbours, so
        # it is dropped, not hard-failed. Keying on the source-declared list_kind — never on
        # the text shape — means no signal ⇒ accept.
        entry_index_by_line = _build_source_backed_entry_index_by_markdown_line(
            final_markdown=final_markdown,
            assembly_entries=assembly_entries,
        )
        contextual_samples = [
            sample
            for sample in unresolved_samples
            if _sample_has_source_list_context(
                sample=sample,
                entry_index_by_line=entry_index_by_line,
                assembly_entries=assembly_entries,
            )
        ]
        return contextual_samples, "entry_assembly"
    return list(raw_samples), "legacy_markdown"


def _build_source_backed_entry_by_markdown_line(
    *,
    final_markdown: str,
    assembly_entries: Sequence[object],
) -> dict[int, object]:
    entry_by_nonempty_line_index: dict[int, object] = {}
    for index, entry in enumerate(assembly_entries, start=1):
        entry_by_nonempty_line_index[index] = entry

    entry_by_line: dict[int, object] = {}
    nonempty_index = 0
    for line_number, raw_line in enumerate(final_markdown.splitlines(), start=1):
        if not raw_line.strip():
            continue
        nonempty_index += 1
        entry = entry_by_nonempty_line_index.get(nonempty_index)
        if entry is not None:
            entry_by_line[line_number] = entry
    return entry_by_line


def _build_source_backed_entry_index_by_markdown_line(
    *,
    final_markdown: str,
    assembly_entries: Sequence[object],
) -> dict[int, int]:
    """Map each non-empty markdown line to its 0-based position in ``assembly_entries``
    (the same non-empty-line ordinal alignment ``_build_source_backed_entry_by_markdown_line``
    relies on). The index lets a sample's entry look at its k-1 / k+1 document neighbours."""
    entry_count = len(assembly_entries)
    entry_index_by_line: dict[int, int] = {}
    nonempty_index = 0
    for line_number, raw_line in enumerate(final_markdown.splitlines(), start=1):
        if not raw_line.strip():
            continue
        entry_position = nonempty_index
        nonempty_index += 1
        if entry_position < entry_count:
            entry_index_by_line[line_number] = entry_position
    return entry_index_by_line


def _sample_has_source_list_context(
    *,
    sample: object,
    entry_index_by_line: Mapping[int, int],
    assembly_entries: Sequence[object],
) -> bool:
    """True iff the sample's resolved assembly entry — or the immediately preceding /
    following entry — is a source-backed list entry (FR-001). An unresolvable line (no
    ``line``, or a line past the entry sequence) yields no list-context signal, so the
    sample is dropped (FR-002)."""
    line = getattr(sample, "line", None)
    if not isinstance(line, int):
        return False
    index = entry_index_by_line.get(line)
    if index is None:
        return False
    entry_count = len(assembly_entries)
    for neighbour_index in (index - 1, index, index + 1):
        if 0 <= neighbour_index < entry_count and _is_source_backed_list_entry(
            assembly_entries[neighbour_index]
        ):
            return True
    return False


def _normalize_list_fragment_sample_text(text: str) -> str:
    text = re.sub(r"^\s*[-*]\s+", "", text.strip())
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _is_source_backed_list_entry(entry: object) -> bool:
    return (
        bool(getattr(entry, "from_registry", False))
        and not bool(getattr(entry, "used_fallback", False))
        and str(getattr(entry, "list_kind", "") or "").strip().lower() in {"ordered", "unordered", "list"}
    )


def _build_source_backed_list_entry_texts(assembly_entries: Sequence[object]) -> set[str]:
    return {
        normalized
        for entry in assembly_entries
        if _is_source_backed_list_entry(entry)
        for normalized in [_normalize_list_fragment_sample_text(str(getattr(entry, "text", "") or ""))]
        if normalized
    }


def _is_source_backed_list_sample(
    *,
    sample: object,
    entry_by_line: Mapping[int, object],
    source_backed_list_texts: set[str],
) -> bool:
    sample_text = str(getattr(sample, "text", "") or "").split(" || ", maxsplit=1)[0]
    normalized_sample_text = _normalize_list_fragment_sample_text(sample_text)
    if normalized_sample_text and normalized_sample_text in source_backed_list_texts:
        return True

    line = getattr(sample, "line", None)
    if not isinstance(line, int):
        return False
    entry = entry_by_line.get(line)
    if entry is None:
        return False
    return _is_source_backed_list_entry(entry)


_ROLE_AWARE_UNMAPPED_SOURCE_REVIEW_RATIO = 0.01
_ROLE_LOSS_MANUAL_REVIEW_MAX_COUNT = 10
_ROLE_LOSS_MANUAL_REVIEW_MAX_RATIO = 0.05
_LEGACY_HYGIENE_MANUAL_REVIEW_MAX_COUNT = 10
_LEGACY_HYGIENE_MANUAL_REVIEW_MAX_RATIO = 0.01


@dataclass(frozen=True)
class _HygieneGateSpec:
    review_reason: str
    fail_reason: str
    label: str
    severity: str = "review"
    threshold: Literal["legacy", "role_loss"] = "legacy"
    empty_label: str | None = None


@dataclass(frozen=True)
class _UntranslatedStructuralSample:
    line: int | None
    text: str
    reason: str
    role: str | None = None
    structural_role: str | None = None
    paragraph_id: str | None = None
    char_count: int = 0


_HYGIENE_GATE_SPECS: dict[str, _HygieneGateSpec] = {
    "role_loss": _HygieneGateSpec(
        review_reason="role_loss_review_required",
        fail_reason="role_loss_above_manual_review_threshold",
        label="Структурный абзац стал обычным текстом",
        severity="fix",
        threshold="role_loss",
        empty_label="Структурные абзацы требуют ручной правки",
    ),
    "heading_demotion": _HygieneGateSpec(
        review_reason="heading_demotion_review_required",
        fail_reason="heading_demotion_above_manual_review_threshold",
        label="Заголовок стал обычным текстом или списком",
        severity="fix",
        threshold="role_loss",
        empty_label="Заголовки требуют ручной правки",
    ),
    "bullet_heading": _HygieneGateSpec(
        review_reason="bullet_marker_headings_review_required",
        fail_reason="bullet_marker_headings_present",
        label="Маркер списка попал в заголовок",
        severity="fix",
    ),
    "false_fragment": _HygieneGateSpec(
        review_reason="false_fragment_headings_review_required",
        fail_reason="false_fragment_headings_present",
        label="Фрагмент текста выглядит как ложный заголовок",
        severity="fix",
    ),
    "residual_bullet": _HygieneGateSpec(
        review_reason="residual_bullet_glyphs_review_required",
        fail_reason="residual_bullet_glyphs_present",
        label="Остался лишний маркер списка",
    ),
    "mixed_script": _HygieneGateSpec(
        review_reason="mixed_script_terms_review_required",
        fail_reason="mixed_script_terms_present",
        label="Слово содержит символы из разных алфавитов",
    ),
}


def _collect_untranslated_structural_samples(
    *,
    final_markdown: str,
    assembly_entries: Sequence[object],
) -> list[_UntranslatedStructuralSample]:
    if not assembly_entries:
        return []
    nonempty_line_numbers = [
        line_number
        for line_number, raw_line in enumerate(final_markdown.splitlines(), start=1)
        if raw_line.strip()
    ]
    samples: list[_UntranslatedStructuralSample] = []
    for index, entry in enumerate(assembly_entries):
        role = str(getattr(entry, "role", "") or "").strip().lower()
        structural_role = str(getattr(entry, "structural_role", "") or "").strip().lower()
        if role not in {"heading", "caption"} and structural_role not in {"heading", "caption"}:
            continue
        if bool(getattr(entry, "controlled_fallback", False)):
            continue
        text = str(getattr(entry, "text", "") or "").strip()
        if not _is_untranslated_structural_text(text):
            continue
        samples.append(
            _UntranslatedStructuralSample(
                line=nonempty_line_numbers[index] if index < len(nonempty_line_numbers) else None,
                text=text,
                reason="untranslated_structural_text",
                role=role or None,
                structural_role=structural_role or None,
                paragraph_id=str(getattr(entry, "paragraph_id", "") or "") or None,
                char_count=len(_strip_structural_markdown_prefix(text)),
            )
        )
    return samples


def _collect_untranslated_body_samples(
    *,
    final_markdown: str,
    assembly_entries: Sequence[object],
) -> list[_UntranslatedStructuralSample]:
    if not assembly_entries:
        return []
    nonempty_line_numbers = [
        line_number
        for line_number, raw_line in enumerate(final_markdown.splitlines(), start=1)
        if raw_line.strip()
    ]
    samples: list[_UntranslatedStructuralSample] = []
    for index, entry in enumerate(assembly_entries):
        role = str(getattr(entry, "role", "") or "").strip().lower()
        structural_role = str(getattr(entry, "structural_role", "") or "").strip().lower()
        if role in {"heading", "caption"} or structural_role in {"heading", "caption"}:
            continue
        if bool(getattr(entry, "controlled_fallback", False)):
            continue
        text = str(getattr(entry, "text", "") or "").strip()
        if not _is_untranslated_body_text(text):
            continue
        samples.append(
            _UntranslatedStructuralSample(
                line=nonempty_line_numbers[index] if index < len(nonempty_line_numbers) else None,
                text=text,
                reason="untranslated_body_text",
                role=role or None,
                structural_role=structural_role or None,
                paragraph_id=str(getattr(entry, "paragraph_id", "") or "") or None,
                char_count=len(_strip_structural_markdown_prefix(text)),
            )
        )
    return samples


def _is_reviewable_list_fragment_residue(
    *,
    samples: Sequence[object],
    gate_source: str,
) -> bool:
    if gate_source != "entry_assembly":
        return False
    if not samples:
        return False
    # Partition the residue: form-credited citation residue (standalone footnote / page
    # numbers such as "18." or "1491.", and citation-form notes lines) vs. real body-text
    # list fragments (broken bullets / list items). A single non-creditable body fragment
    # hard-fails; a residue that is ENTIRELY citation-form routes to soft review, regardless
    # of count, so footnote / page / bibliography residue cannot tip an otherwise-good book
    # into an acceptance hard-fail (1‑A references crediting extended from bare numbers to
    # full notes/bibliography lines).
    non_creditable_residue = [
        sample
        for sample in samples
        if not _is_citation_form_list_fragment_sample(sample)
    ]
    if non_creditable_residue:
        return False
    return True


def _sanitize_review_anchor_text(value: object) -> str:
    """Turn a raw preview into a user-locatable anchor: drop internal
    `[[DOCX_PARA_…]]` / `[[DOCX_IMAGE_…]]` placeholders (FR-004), strip a leading
    markdown heading marker, and collapse whitespace/newlines."""
    text = _DOCX_INTERNAL_PLACEHOLDER_PATTERN.sub(" ", str(value or ""))
    text = " ".join(text.split())
    return _REVIEW_ANCHOR_HEADING_MARKER_PATTERN.sub("", text)


def _review_anchor_visible_char_count(text: str) -> int:
    return sum(1 for char in text if not char.isspace())


# Sample reasons whose role was genuinely LOST (heading/list → body), for which the
# manual action is to reapply the source Word style (FR-005).
_ROLE_LOSS_SAMPLE_REASONS = frozenset(
    {"content_survived_but_format_role_lost", "content_survived_but_heading_demoted"}
)


def _review_item_word_style(
    *,
    role: str | None,
    structural_role: str | None,
    heading_level: int | None,
) -> str | None:
    """Pure role→Word-style map (Constitution VII): the concrete manual action for a
    demoted structural paragraph. No word lists, no per-book literals — only the
    source-declared role/level decide the style name."""
    if heading_level is not None and heading_level >= 1:
        return f"Заголовок {heading_level}"
    normalized_role = (role or "").strip().lower()
    normalized_structural = (structural_role or "").strip().lower()
    if normalized_role == "heading" or normalized_structural == "heading":
        return "Заголовок"
    return None


def _build_formatting_review_item(
    *,
    reason: str,
    label: str,
    sample: Mapping[str, object] | None = None,
    count: int = 1,
    severity: str = "review",
) -> dict[str, object]:
    item: dict[str, object] = {
        "reason": reason,
        "label": label,
        "count": count,
        "severity": severity,
    }
    if sample:
        sample_dict = dict(sample)
        # FR-004: internal ids must never reach the user-facing anchor.
        anchor_text = _sanitize_review_anchor_text(sample_dict.get("text"))
        sample_dict["text"] = anchor_text
        if "source_text" in sample_dict:
            sample_dict["source_text"] = _sanitize_review_anchor_text(sample_dict.get("source_text"))
        # FR-006: an anchor with fewer than 3 locatable characters (e.g. "$", "", "###")
        # cannot be searched for. Mark it so the renderer counts it instead of printing an
        # empty «» row. No anchor is invented (Constitution VII, "No source signal…").
        if _review_anchor_visible_char_count(anchor_text) < 3:
            sample_dict["anchor_usable"] = False
        # FR-005: a role_loss / heading-demotion item carries the concrete manual action —
        # the Word style to REAPPLY — derived purely from the source role/level. Gated on the
        # role-loss reason so an item whose role survived (e.g. an untranslated heading) is not
        # told to restyle a paragraph that already has the right style.
        if sample_dict.get("reason") in _ROLE_LOSS_SAMPLE_REASONS:
            raw_level = sample_dict.get("heading_level")
            heading_level = raw_level if isinstance(raw_level, int) and not isinstance(raw_level, bool) else None
            raw_role = sample_dict.get("role")
            raw_structural = sample_dict.get("structural_role")
            action_style = _review_item_word_style(
                role=str(raw_role) if isinstance(raw_role, str) else None,
                structural_role=str(raw_structural) if isinstance(raw_structural, str) else None,
                heading_level=heading_level,
            )
            if action_style is not None:
                item["action_style"] = action_style
        item["sample"] = sample_dict
    return item


def _emit_mapping_text_quality_defect_items(
    *,
    formatting_review_items: list[dict[str, object]],
    mapping_text_quality: Mapping[str, object] | None,
    limit: int = 8,
) -> None:
    # A "bad pair" means a translated paragraph landed against the wrong source paragraph
    # (source/target text barely overlap). That is a content defect, not a formatting nit,
    # so it is surfaced with severity "defect" ([КРИТ]). Rendered samples are capped like
    # the other gates; the true total rides on aggregate_count of the first item.
    if not isinstance(mapping_text_quality, Mapping):
        return
    try:
        # bad_pair_count is an int count in the mapping-text-quality payload when present.
        bad_pair_count = int(cast(int, mapping_text_quality.get("bad_pair_count") or 0))
    except (TypeError, ValueError):
        bad_pair_count = 0
    if bad_pair_count <= 0:
        return
    raw_samples = mapping_text_quality.get("samples")
    samples: list[Mapping[str, object]] = []
    if isinstance(raw_samples, Sequence) and not isinstance(raw_samples, (str, bytes)):
        samples = [sample for sample in raw_samples if isinstance(sample, Mapping)][:limit]
    label = "Перевод встал не к тому исходному абзацу"
    if not samples:
        formatting_review_items.append(
            _build_formatting_review_item(
                reason="mapping_text_quality_bad_pair",
                label=label,
                count=bad_pair_count,
                severity="defect",
            )
        )
        return
    use_aggregate = bad_pair_count > len(samples)
    for sample_index, sample in enumerate(samples):
        item = _build_formatting_review_item(
            reason="mapping_text_quality_bad_pair",
            label=label,
            sample={
                "text": sample.get("target_text_preview"),
                "source_text": sample.get("source_text_preview"),
                "reason": "mapping_text_quality_bad_pair",
            },
            count=0 if use_aggregate else 1,
            severity="defect",
        )
        if sample_index == 0 and use_aggregate:
            item["aggregate_count"] = bad_pair_count
        formatting_review_items.append(item)


def _formatting_review_required_count(items: Sequence[Mapping[str, object]]) -> int:
    count = 0
    for item in items:
        try:
            value = item.get("aggregate_count") if "aggregate_count" in item else item.get("count", 1)
            count += max(0, int(value))
        except (TypeError, ValueError):
            count += 1
    return count


def _effective_formatting_coverage_diagnostics(payload: Mapping[str, object]) -> Mapping[str, object]:
    residual = payload.get("unmapped_source_residual_diagnostics")
    if not isinstance(residual, Mapping):
        return {}
    effective = residual.get("effective_formatting_coverage_diagnostics")
    if not isinstance(effective, Mapping):
        return {}
    return effective


def _effective_formatting_coverage_counts(payload: Mapping[str, object]) -> Mapping[str, object]:
    counts = _effective_formatting_coverage_diagnostics(payload).get("counts")
    return counts if isinstance(counts, Mapping) else {}


def _effective_formatting_coverage_samples_by_class(
    payload: Mapping[str, object],
    *,
    coverage_class: str,
    limit: int = 8,
) -> list[Mapping[str, object]]:
    residual = payload.get("unmapped_source_residual_diagnostics")
    if not isinstance(residual, Mapping):
        return []
    samples = residual.get("samples")
    if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
        return []
    selected: list[Mapping[str, object]] = []
    for sample in samples:
        if not isinstance(sample, Mapping):
            continue
        if str(sample.get("effective_formatting_coverage_class") or "") != coverage_class:
            continue
        selected.append(sample)
        if len(selected) >= limit:
            break
    return selected


def _controlled_fallback_review_samples(payload: Mapping[str, object], *, limit: int = 8) -> tuple[int, list[dict[str, object]]]:
    residual = payload.get("unmapped_target_residual_diagnostics")
    if not isinstance(residual, Mapping):
        return 0, []
    count = 0
    try:
        count = int(residual.get("controlled_fallback_creditable_count") or 0)
    except (TypeError, ValueError):
        count = 0
    counts = residual.get("counts")
    if count <= 0 and isinstance(counts, Mapping):
        try:
            count = int(counts.get("controlled_fallback_covered") or 0)
        except (TypeError, ValueError):
            count = 0
    rows = residual.get("residual_rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        rows = residual.get("samples")
    samples: list[dict[str, object]] = []
    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            if row.get("residual_class") != "controlled_fallback_covered":
                continue
            samples.append(
                {
                    "text": row.get("target_text_preview"),
                    "reason": "controlled_fallback_covered",
                    "controlled_fallback_kind": row.get("controlled_fallback_kind"),
                    "controlled_fallback_block_index": row.get("controlled_fallback_block_index"),
                }
            )
            if len(samples) >= limit:
                break
    return max(count, len(samples)), samples


def _emit_controlled_fallback_review_items(
    *,
    quality_status: str,
    gate_reasons: list[str],
    formatting_review_items: list[dict[str, object]],
    count: int,
    samples: Sequence[Mapping[str, object]],
) -> str:
    if count <= 0:
        return quality_status
    quality_status = _apply_quality_review_reason(
        quality_status=quality_status,
        gate_reasons=gate_reasons,
        reason="controlled_fallback_blocks_review_required",
    )
    if samples:
        use_aggregate = count > len(samples)
        for sample_index, sample in enumerate(samples):
            item = _build_formatting_review_item(
                reason="controlled_fallback_blocks_review_required",
                label="Блок сохранён через controlled fallback",
                sample=sample,
                count=0 if use_aggregate else 1,
            )
            if sample_index == 0 and use_aggregate:
                item["aggregate_count"] = count
            formatting_review_items.append(item)
    else:
        formatting_review_items.append(
            _build_formatting_review_item(
                reason="controlled_fallback_blocks_review_required",
                label="Блоки сохранены через controlled fallback",
                count=count,
            )
        )
    return quality_status


def _is_reviewable_role_aware_unmapped_source_residue(
    *,
    count: int,
    source_total: object,
    basis: str,
    coverage_counts: Mapping[str, object],
) -> bool:
    if count <= 0 or basis != "role_aware_formatting_coverage":
        return False
    try:
        role_loss_count = int(coverage_counts.get("content_survived_but_format_role_lost") or 0)
    except (TypeError, ValueError):
        role_loss_count = 0
    if role_loss_count > 0:
        return False
    if not isinstance(source_total, int) or source_total <= 0:
        return False
    return (count / source_total) <= _ROLE_AWARE_UNMAPPED_SOURCE_REVIEW_RATIO


def _is_role_loss_within_manual_review_threshold(
    *,
    role_loss_count: int,
    source_total: object,
) -> bool:
    if role_loss_count <= 0:
        return False
    if role_loss_count > _ROLE_LOSS_MANUAL_REVIEW_MAX_COUNT:
        return False
    if not isinstance(source_total, int) or source_total <= 0:
        return True
    return (role_loss_count / source_total) <= _ROLE_LOSS_MANUAL_REVIEW_MAX_RATIO


def _is_legacy_hygiene_within_manual_review_threshold(
    *,
    count: int,
    source_total: object,
) -> bool:
    if count <= 0:
        return False
    if count > _LEGACY_HYGIENE_MANUAL_REVIEW_MAX_COUNT:
        return False
    if not isinstance(source_total, int) or source_total <= 0:
        return True
    return (count / source_total) <= _LEGACY_HYGIENE_MANUAL_REVIEW_MAX_RATIO


def _apply_manual_review_or_fail(
    *,
    quality_status: str,
    gate_reasons: list[str],
    policy: str,
    reason: str,
    fail_reason: str,
    count: int,
    source_total: object,
    threshold_fn: Callable[[int, object], bool] | None = None,
) -> tuple[str, str]:
    if policy != "strict":
        quality_status = _apply_quality_review_reason(
            quality_status=quality_status,
            gate_reasons=gate_reasons,
            reason=reason,
        )
        return quality_status, reason
    within_manual_review = (
        threshold_fn(count, source_total)
        if threshold_fn is not None
        else _is_legacy_hygiene_within_manual_review_threshold(count=count, source_total=source_total)
    )
    if within_manual_review:
        quality_status = _apply_quality_review_reason(
            quality_status=quality_status,
            gate_reasons=gate_reasons,
            reason=reason,
        )
        return quality_status, reason
    quality_status = "fail"
    gate_reasons.append(fail_reason)
    return quality_status, fail_reason


def _hygiene_threshold_fn(spec: _HygieneGateSpec) -> Callable[[int, object], bool]:
    if spec.threshold == "role_loss":
        return lambda count, source_total: _is_role_loss_within_manual_review_threshold(
            role_loss_count=count,
            source_total=source_total,
        )
    return lambda count, source_total: _is_legacy_hygiene_within_manual_review_threshold(
        count=count,
        source_total=source_total,
    )


def _emit_unmapped_source_discrepancy_review_items(
    *,
    formatting_review_items: list[dict[str, object]],
    basis: str,
    role_loss_count: int,
    role_loss_samples: Sequence[object],
    unmapped_source_count: int,
) -> None:
    """Policy-independent DATA emission for unmapped-source discrepancies.

    Emits role_loss / unmapped review-items so the UI has these discrepancies
    even under advisory (where the pass/fail STATUS stays policy-scaled and is
    applied by the caller). The item shapes mirror the strict path's
    ``_emit_hygiene_gate`` output; only the DATA — not the verdict severity — is
    made policy-independent (GATE_TRUSTWORTHINESS refactor, Task B).
    """
    if basis == "role_aware_formatting_coverage" and role_loss_count > 0:
        spec = _HYGIENE_GATE_SPECS["role_loss"]
        serialized_samples = [
            dict(_serialize_role_loss_sample(cast(Mapping[str, object], sample)))
            for sample in list(role_loss_samples)[:8]
        ]
        if serialized_samples:
            use_aggregate = role_loss_count > len(serialized_samples)
            for sample_index, sample in enumerate(serialized_samples):
                item = _build_formatting_review_item(
                    reason=spec.review_reason,
                    label=spec.label,
                    sample=sample,
                    count=0 if use_aggregate else 1,
                    severity=spec.severity,
                )
                if sample_index == 0 and use_aggregate:
                    item["aggregate_count"] = role_loss_count
                formatting_review_items.append(item)
        else:
            formatting_review_items.append(
                _build_formatting_review_item(
                    reason=spec.review_reason,
                    label=spec.empty_label or spec.label,
                    count=role_loss_count,
                    severity=spec.severity,
                )
            )
    else:
        formatting_review_items.append(
            _build_formatting_review_item(
                reason="unmapped_source_paragraphs_review_required",
                label="Абзацы без явного соответствия оригиналу",
                count=unmapped_source_count,
            )
        )


def _emit_unmapped_target_discrepancy_review_items(
    *,
    formatting_review_items: list[dict[str, object]],
    has_role_aware_summary: bool,
    retained_samples: Sequence[object],
    retained_count: int,
    effective_unmapped_target_count: int,
) -> None:
    """Policy-independent DATA emission for unmapped-TARGET discrepancies (spec 011).

    Target counterpart of ``_emit_unmapped_source_discrepancy_review_items``: itemizes the
    genuinely-unmapped target paragraphs (the passthrough classifier's ``retained`` residue,
    threaded out via ``retained_target_samples``) so the UI's unmapped-target ``[ПРОВЕРКА]``
    row lists WHICH paragraphs are unmapped, not just a count. Emitted under both strict and
    advisory — this is review-DATA (spec 010 keeps target coverage NOT-APPLICABLE in
    production); it appends review-items only and touches no acceptance check / verdict.

    The ``has_role_aware_summary`` discriminator mirrors the source emitter's
    ``basis == role_aware`` branch:
      * summary present → itemize the retained residue (zero retained ⇒ nothing to review —
        the anti-vacuum guarantee: a credited passthrough paragraph is never emitted);
      * summary absent (no target-split accounting) → a single count-only item carrying the
        effective count (FR-004), never silence when that count is positive.
    """
    reason = "unmapped_target_paragraphs_review_required"
    label = "Абзацы перевода без явного соответствия оригиналу"
    if has_role_aware_summary:
        samples = [sample for sample in list(retained_samples)[:8] if isinstance(sample, Mapping)]
        if not samples:
            # Zero retained unmapped target paragraphs — nothing to review (SC-002a).
            return
        # Mirror the source emitter's capping invariant: the first item carries the true
        # retained total when the sample list is capped below it.
        use_aggregate = retained_count > len(samples)
        for sample_index, sample in enumerate(samples):
            text = str(sample.get("text_preview") or "")
            item = _build_formatting_review_item(
                reason=reason,
                label=label,
                sample={"line": None, "text": text, "reason": reason},
                count=0 if use_aggregate else 1,
                severity="review",
            )
            if sample_index == 0 and use_aggregate:
                item["aggregate_count"] = retained_count
            formatting_review_items.append(item)
    elif effective_unmapped_target_count > 0:
        # FR-004: no role-aware target summary (no target-split accounting) — fall back to a
        # single count-only item, never silence.
        formatting_review_items.append(
            _build_formatting_review_item(
                reason=reason,
                label=label,
                count=effective_unmapped_target_count,
                severity="review",
            )
        )


def _emit_hygiene_gate(
    *,
    quality_status: str,
    gate_reasons: list[str],
    formatting_review_items: list[dict[str, object]],
    policy: str,
    spec: _HygieneGateSpec,
    count: int,
    source_total: object,
    samples: Sequence[object],
    sample_serializer: Callable[[object], Mapping[str, object]] | None = None,
) -> tuple[str, str]:
    quality_status, emitted_reason = _apply_manual_review_or_fail(
        quality_status=quality_status,
        gate_reasons=gate_reasons,
        policy=policy,
        reason=spec.review_reason,
        fail_reason=spec.fail_reason,
        count=count,
        source_total=source_total,
        threshold_fn=_hygiene_threshold_fn(spec),
    )
    serialized_samples = (
        [dict(sample_serializer(sample)) for sample in samples[:8]]
        if sample_serializer is not None
        else _serialize_quality_samples(samples)
    )
    if serialized_samples:
        use_aggregate = count > len(serialized_samples)
        for sample_index, sample in enumerate(serialized_samples):
            item = _build_formatting_review_item(
                reason=emitted_reason,
                label=spec.label,
                sample=sample,
                count=0 if use_aggregate else 1,
                severity=spec.severity,
            )
            if sample_index == 0 and use_aggregate:
                item["aggregate_count"] = count
            formatting_review_items.append(item)
    else:
        formatting_review_items.append(
            _build_formatting_review_item(
                reason=emitted_reason,
                label=spec.empty_label or spec.label,
                count=count,
                severity=spec.severity,
            )
        )
    return quality_status, emitted_reason


_ACCEPTANCE_MAX_UNMAPPED_SOURCE_CONFIG_KEY = "acceptance_max_unmapped_source_paragraphs"
_ACCEPTANCE_MAX_UNMAPPED_TARGET_CONFIG_KEY = "acceptance_max_unmapped_target_paragraphs"
_ACCEPTANCE_REQUIRE_NO_TOC_BODY_CONCAT_CONFIG_KEY = "acceptance_require_no_toc_body_concat"


def build_report_acceptance_verdict(
    report: Mapping[str, object],
    *,
    mismatch_threshold: int | None = None,
    unmapped_target_threshold: int | None = None,
    require_no_toc_body_concat: bool = False,
) -> dict[str, object]:
    """Assemble the acceptance verdict for a report context via the shared module.

    Production-side counterpart to the harness' ``evaluate_lietaer_acceptance``:
    both delegate to ``docxaicorrector.validation.acceptance.build_acceptance_verdict``
    so the UI/advisory path binds to the same shared verdict shape.

    Parity of *code*, not of *evaluated checks*: production and the harness do not
    judge the same set of checks, because production genuinely lacks some of the
    harness' inputs, and it must not fake them (Constitution VII, spec FR-002):

    - The harness owns both the source and output DOCX bytes, so it injects the
      source<->output structural comparison. Production has no source DOCX (the user
      uploads an arbitrary document), so no ``structural_checks_builder`` is passed
      and ``structural_comparison_available`` is emitted NOT-APPLICABLE.
    - The harness receives a per-book loss budget from the test corpus registry;
      production has no such budget (``mismatch_threshold`` / ``unmapped_target_threshold``
      arrive as ``None`` when unconfigured), so the threshold checks are emitted
      NOT-APPLICABLE while still carrying the measured ``actual``.
    - ``output_docx_openable`` (and ``no_placeholder_markup``) reflect the real
      ``output_artifacts`` when the DOCX bytes exist at finalization; when the
      delivered DOCX has not been built yet they are NOT-APPLICABLE, never a guess.

    What both CAN evaluate in common (pipeline success, reader-cleanup stage,
    display-hygiene, translation-quality residue) is judged identically.
    """
    return build_acceptance_verdict(
        report,
        mismatch_threshold=mismatch_threshold,
        unmapped_target_threshold=unmapped_target_threshold,
        require_no_toc_body_concat=require_no_toc_body_concat,
        structural_checks_builder=None,
    )


def _resolve_acceptance_thresholds(context: Any) -> tuple[int | None, int | None, bool]:
    app_config = getattr(context, "app_config", {}) or {}

    def _cfg_int_or_none(key: str) -> int | None:
        # An absent config key means the threshold is UNCONFIGURED (production has
        # no per-book loss budget), which the shared verdict renders NOT-APPLICABLE.
        # These keys are absent from config.toml and set nowhere in production today,
        # so this returns ``None`` there; the harness supplies real per-book integers
        # instead. NOTE: unmapped coverage is ADVISORY review data (specs 038/039,
        # Constitution VII) — it never gates, at any threshold. The caption→heading
        # structural conflict does gate DELIVERY, but UNCONDITIONALLY (whenever the
        # conflict count > 0), NOT via any threshold resolved here: spec 042 P1-B routes
        # the conflict into ``quality_status="fail"`` + a ``caption_heading_conflict``
        # gate_reason in ``_build_translation_quality_report`` (fatal token, see
        # ``_FATAL_DOCUMENT_GATE_REASONS``), which blocks primary-artifact publication in
        # ``late_phases``. The acceptance verdict's independent
        # ``caption_heading_conflict_absent`` check remains the auditable record.
        if key not in app_config:
            return None
        value = app_config.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    return (
        _cfg_int_or_none(_ACCEPTANCE_MAX_UNMAPPED_SOURCE_CONFIG_KEY),
        _cfg_int_or_none(_ACCEPTANCE_MAX_UNMAPPED_TARGET_CONFIG_KEY),
        bool(app_config.get(_ACCEPTANCE_REQUIRE_NO_TOC_BODY_CONCAT_CONFIG_KEY, False)),
    )


def _build_report_context_for_acceptance(
    *,
    context: Any,
    quality_report: Mapping[str, object],
    formatting_diagnostics_payloads: Sequence[Mapping[str, object]],
    output_artifacts: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "result": "succeeded",
        "runtime_config": {
            "effective": {"processing_operation": getattr(context, "processing_operation", "")}
        },
        "translation_quality_report": dict(quality_report),
        "formatting_diagnostics": [dict(payload) for payload in formatting_diagnostics_payloads],
        # Real output artifacts when the DOCX bytes exist at this point; an empty
        # mapping otherwise, which the shared verdict renders as a NOT-APPLICABLE
        # ``output_docx_openable`` rather than a guessed pass (spec FR-001).
        "output_artifacts": dict(output_artifacts) if output_artifacts else {},
        "runtime": {},
        "reader_cleanup_evidence": {},
        "preparation_diagnostic_snapshot": {},
    }


def _resolve_acceptance_output_artifacts(
    *,
    docx_phase: Mapping[str, object],
    runtime_display_markdown: str,
) -> dict[str, object] | None:
    """Compute the acceptance ``output_artifacts`` from already-built DOCX bytes.

    Returns ``None`` when the DOCX bytes are not present yet — the base build is
    deferred until reader cleanup on the common production path — so the caller
    can leave ``output_docx_openable`` NOT-APPLICABLE instead of forcing an early
    build or guessing. The builder callback is deliberately NOT invoked here.
    """
    docx_bytes = docx_phase.get("docx_bytes")
    if not isinstance(docx_bytes, bytes) or not docx_bytes:
        return None
    # TODO (F15): private cross-module access — ``_build_output_artifacts`` has no public
    # wrapper yet. Exposing one edits ``validation/structural.py`` (out of this module's
    # scope), so this stays a documented private seam. See the module docstring.
    from docxaicorrector.validation.structural import _build_output_artifacts

    return _build_output_artifacts(docx_bytes, runtime_display_markdown)


def _build_translation_quality_report(
    *,
    context: Any,
    final_markdown: str,
    formatting_diagnostics_artifacts: Sequence[str],
    assembly_result: Any | None = None,
    pre_cleanup_formatting_baseline: Mapping[str, object] | None = None,
    runtime_display_markdown: str | None = None,
) -> dict[str, object]:
    normalized_quality_markdown = _normalize_final_markdown_for_quality_gate(final_markdown)
    display_hygiene_markdown = _normalize_final_markdown_for_display_hygiene_reporting(final_markdown)
    # FR-002/003/006: the hygiene reporting metrics describe the DELIVERED artifact —
    # runtime_display_markdown is the exact text fed to convert_markdown_to_docx_bytes,
    # so measuring it matches the harness (structural.py measures latest_markdown).
    # When it is unavailable/empty the report falls back to today's per-metric inputs
    # so behaviour is byte-identical (degrade-safe); production always supplies it.
    bullet_heading_reporting_markdown = runtime_display_markdown or normalized_quality_markdown
    hygiene_reporting_markdown = runtime_display_markdown or display_hygiene_markdown
    mixed_script_reporting_markdown = runtime_display_markdown or final_markdown
    payloads = _load_formatting_diagnostics_payloads(formatting_diagnostics_artifacts)
    latest_payload = payloads[-1] if payloads else {}
    unmapped_source_ids = latest_payload.get("unmapped_source_ids") if isinstance(latest_payload, Mapping) else []
    unmapped_target_indexes = latest_payload.get("unmapped_target_indexes") if isinstance(latest_payload, Mapping) else []
    accepted_merged_sources = latest_payload.get("accepted_merged_sources") if isinstance(latest_payload, Mapping) else []
    # spec 043 P2: the DELIVERY gate must count caption→heading conflicts across ALL
    # current formatting-diagnostics payloads (not just the last artifact), exactly as
    # ``build_acceptance_verdict`` aggregates ``total_caption_heading_conflicts``. With
    # multiple artifacts present a conflict recorded in a NON-last artifact would otherwise
    # escape the single-``latest_payload`` count, letting the delivery gate under-count and
    # diverge from the acceptance verdict. Keyed on the conflict signal only (no per-book
    # literal); mirrors ``acceptance.py``'s ``len(payload.get(...) or [])`` per payload.
    caption_heading_conflict_count = sum(
        len(cast(Sequence[object], payload.get("caption_heading_conflicts") or []))
        for payload in payloads
        if isinstance(payload, Mapping)
    )
    policy = _resolve_translation_quality_gate_policy(context=context)
    quality_status = "pass"
    gate_reasons: list[str] = []
    formatting_review_items: list[dict[str, object]] = []
    bullet_heading_samples = collect_bullet_heading_samples(bullet_heading_reporting_markdown)
    raw_bullet_heading_samples = collect_bullet_heading_samples(final_markdown)
    bullet_heading_count = len(bullet_heading_samples)
    raw_page_placeholder_heading_concat_samples = collect_page_placeholder_heading_concat_samples(final_markdown)
    page_placeholder_heading_concat_samples = collect_page_placeholder_heading_concat_samples(hygiene_reporting_markdown)
    assembly_entries = tuple(getattr(assembly_result, "entries", ()) or ())
    assembly_uses_fallback = any(bool(getattr(entry, "used_fallback", False)) for entry in assembly_entries)
    source_backed_entry_authority = _has_source_backed_entry_authority(assembly_entries)
    entry_false_fragment_heading_samples = collect_false_fragment_heading_samples_from_entries(assembly_entries) if assembly_entries else []
    raw_false_fragment_heading_samples = collect_false_fragment_heading_samples(final_markdown)
    raw_residual_bullet_glyph_samples = collect_residual_bullet_glyph_samples(final_markdown)
    residual_bullet_glyph_samples = collect_residual_bullet_glyph_samples(hygiene_reporting_markdown)
    raw_list_fragment_regression_samples = collect_list_fragment_regression_samples(final_markdown)
    raw_mixed_script_samples = collect_mixed_script_samples(final_markdown)
    mixed_script_samples = collect_mixed_script_samples(mixed_script_reporting_markdown)
    # Spec 008: ADVISORY detection of paragraphs split mid-sentence by the PDF-import
    # ``toc_entry`` mis-tag. Keyed on the source_registry provenance (shared raw block) —
    # it changes NO delivered bytes and never modifies ``final_markdown``.
    # FR-007: scoped to the main-content span using the SAME region provenance
    # ``classify_heading_demotions`` uses (front_matter / references / bounded-TOC
    # boundaries) so front-matter and back-of-book noise is excluded by REGION, not by a
    # per-book literal. The preparation_diagnostic_snapshot is not carried into the finalize
    # scope (the formatting payload does not embed it — exactly as ``classify_heading_demotions``
    # is invoked here without it below), so the snapshot defaults to None: the front-matter
    # and references boundaries do not require it, and the bounded-TOC region always sits
    # inside the front matter, so the front-matter boundary already subsumes it. The offline
    # acceptance re-measure over a saved report passes the real snapshot.
    source_registry_entries = (
        latest_payload.get("source_registry") if isinstance(latest_payload, Mapping) else None
    )
    paragraph_break_samples = (
        collect_paragraph_break_samples(source_registry_entries)
        if isinstance(source_registry_entries, Sequence) and not isinstance(source_registry_entries, str)
        else []
    )
    recovered_heading_entries = collect_recovered_heading_entries(assembly_entries) if assembly_entries and not assembly_uses_fallback else []
    untranslated_structural_samples = _collect_untranslated_structural_samples(
        final_markdown=final_markdown,
        assembly_entries=assembly_entries,
    )
    untranslated_body_samples = _collect_untranslated_body_samples(
        final_markdown=final_markdown,
        assembly_entries=assembly_entries,
    )
    untranslated_body_char_count = sum(int(getattr(sample, "char_count", 0) or 0) for sample in untranslated_body_samples)
    untranslated_body_ratio = (
        untranslated_body_char_count / max(len(_strip_structural_markdown_prefix(final_markdown)), 1)
        if untranslated_body_char_count > 0
        else 0.0
    )
    translation_domain = str(getattr(context, "translation_domain", "") or context.app_config.get("translation_domain", "general") or "general")
    authority_fields = _derive_translation_quality_authority_fields(
        context=context,
        final_markdown=final_markdown,
        formatting_payload=latest_payload if isinstance(latest_payload, Mapping) else None,
        assembly_result=assembly_result,
    )
    role_aware_summary = resolve_role_aware_formatting_unmapped_source_summary(payloads)
    role_aware_target_summary = resolve_role_aware_formatting_unmapped_target_summary(payloads)
    authoritative_unmapped_source_basis = str(
        authority_fields.get("unmapped_source_count_basis") or "legacy_paragraph"
    ).strip().lower() or "legacy_paragraph"
    false_fragment_heading_samples, false_fragment_heading_gate_source = _resolve_false_fragment_heading_gate_samples(
        raw_samples=raw_false_fragment_heading_samples,
        entry_samples=entry_false_fragment_heading_samples,
        source_backed_entry_authority=source_backed_entry_authority,
    )
    list_fragment_regression_samples, list_fragment_regression_gate_source = _resolve_list_fragment_regression_gate_samples(
        raw_samples=raw_list_fragment_regression_samples,
        final_markdown=final_markdown,
        assembly_entries=assembly_entries,
        source_backed_entry_authority=source_backed_entry_authority,
        topology_projection_supported=bool(authority_fields.get("topology_projection_supported", False)),
    )
    suspicious_heading_repetition_samples = [
        sample for sample in false_fragment_heading_samples if getattr(sample, "reason", "") == "suspicious_heading_repetition_present"
    ]
    scripture_reference_heading_samples = [
        sample for sample in false_fragment_heading_samples if getattr(sample, "reason", "") == "scripture_reference_heading_present"
    ]
    toc_body_concat_detected = bool(authority_fields.get("toc_body_concat_detected", False))
    source_paragraph_count = latest_payload.get("source_count") if isinstance(latest_payload, Mapping) else None
    output_paragraph_count = latest_payload.get("target_count") if isinstance(latest_payload, Mapping) else None
    emphasis_coverage_payload = (
        latest_payload.get("emphasis_coverage") if isinstance(latest_payload, Mapping) else None
    )
    if not isinstance(emphasis_coverage_payload, Mapping):
        emphasis_coverage_payload = {"measured": False, "reason": "emphasis_coverage_unavailable"}
    worst_unmapped_source_count = _effective_authoritative_unmapped_count(
        authority_fields,
        basis_key="unmapped_source_count_basis",
        raw_count_key="raw_unmapped_source_paragraph_count",
        structure_count_key="structure_unit_unmapped_source_count",
    )
    if role_aware_summary is not None:
        authority_fields = dict(authority_fields)
        authority_fields["unmapped_source_count_basis"] = "role_aware_formatting_coverage"
        worst_unmapped_source_count = int(role_aware_summary["effective_unmapped_source_count"])
    effective_unmapped_target_count = _effective_authoritative_unmapped_count(
        authority_fields,
        basis_key="unmapped_target_count_basis",
        raw_count_key="raw_unmapped_target_paragraph_count",
        structure_count_key="structure_unit_unmapped_target_count",
    )
    if role_aware_target_summary is not None:
        authority_fields = dict(authority_fields)
        authority_fields["unmapped_target_count_basis"] = "role_aware_formatting_coverage"
        authority_fields["raw_unmapped_target_paragraph_count"] = int(
            role_aware_target_summary["raw_unmapped_target_count"]
        )
        effective_unmapped_target_count = int(role_aware_target_summary["effective_unmapped_target_count"])
    heading_demotion_count = 0
    heading_demotion_samples: list[Mapping[str, object]] = []
    prepared_paragraph_count = getattr(context, "paragraph_count", None) or getattr(context, "total_paragraphs", None)
    if isinstance(prepared_paragraph_count, int) and prepared_paragraph_count > 0:
        if source_paragraph_count is None:
            source_paragraph_count = prepared_paragraph_count
        if output_paragraph_count is None:
            output_paragraph_count = prepared_paragraph_count
    if context.processing_operation == "translate":
        basis = str(authority_fields.get("unmapped_source_count_basis") or "legacy_paragraph").strip().lower() or "legacy_paragraph"
        effective_source_total = source_paragraph_count
        effective_coverage_counts = (
            _effective_formatting_coverage_counts(latest_payload)
            if isinstance(latest_payload, Mapping)
            else {}
        )
        try:
            role_loss_count = int(effective_coverage_counts.get("content_survived_but_format_role_lost") or 0)
        except (TypeError, ValueError):
            role_loss_count = 0
        # Body-integrity axis 1‑D: mapped source-heading → target body/list demotions
        # (content survived, heading role lost). Complements the UNMAPPED role_loss above;
        # main-content scoped inside classify_heading_demotions so TOC / front-matter /
        # references / index / attribution demotions are never counted.
        heading_demotion_result = (
            classify_heading_demotions(latest_payload)
            if isinstance(latest_payload, Mapping)
            else {"demotion_count": 0, "samples": []}
        )
        # classify_heading_demotions always returns "demotion_count" as an int and
        # "samples" as a list of mapping rows.
        heading_demotion_count = cast(int, heading_demotion_result.get("demotion_count") or 0)
        heading_demotion_samples = list(
            cast("list[Mapping[str, object]]", heading_demotion_result.get("samples") or [])
        )
        if basis == "topology_unit":
            structure_unit_total_count = authority_fields.get("structure_unit_total_count")
            if isinstance(structure_unit_total_count, int) and structure_unit_total_count > 0:
                effective_source_total = structure_unit_total_count
        if policy == "strict" and worst_unmapped_source_count > 0:
            if basis == "role_aware_formatting_coverage" and role_loss_count > 0:
                role_loss_samples = (
                    _effective_formatting_coverage_samples_by_class(
                        latest_payload,
                        coverage_class="content_survived_but_format_role_lost",
                    )
                    if isinstance(latest_payload, Mapping)
                    else []
                )
                quality_status, _ = _emit_hygiene_gate(
                    quality_status=quality_status,
                    gate_reasons=gate_reasons,
                    formatting_review_items=formatting_review_items,
                    policy=policy,
                    spec=_HYGIENE_GATE_SPECS["role_loss"],
                    count=role_loss_count,
                    source_total=effective_source_total,
                    samples=role_loss_samples,
                    sample_serializer=_serialize_role_loss_sample,
                )
            elif _is_reviewable_role_aware_unmapped_source_residue(
                count=worst_unmapped_source_count,
                source_total=effective_source_total,
                basis=basis,
                coverage_counts=effective_coverage_counts,
            ):
                quality_status = _apply_quality_review_reason(
                    quality_status=quality_status,
                    gate_reasons=gate_reasons,
                    reason="unmapped_source_paragraphs_review_required",
                )
                formatting_review_items.append(
                    _build_formatting_review_item(
                        reason="unmapped_source_paragraphs_review_required",
                        label="Абзацы без явного соответствия оригиналу",
                        count=worst_unmapped_source_count,
                    )
                )
            else:
                quality_status = "fail"
                gate_reasons.append("unmapped_source_paragraphs_present")
        elif policy == "advisory" and worst_unmapped_source_count > 0:
            if isinstance(effective_source_total, int) and effective_source_total > 0 and (worst_unmapped_source_count / effective_source_total) > 0.01:
                quality_status = "warn"
                gate_reasons.append("unmapped_source_paragraphs_above_advisory_threshold")
            # DATA is policy-independent: emit the role_loss/unmapped discrepancy
            # review-items even under advisory so the UI is not blind (the warn
            # status above stays policy-scaled).
            advisory_role_loss_samples = (
                _effective_formatting_coverage_samples_by_class(
                    latest_payload,
                    coverage_class="content_survived_but_format_role_lost",
                )
                if isinstance(latest_payload, Mapping)
                else []
            )
            _emit_unmapped_source_discrepancy_review_items(
                formatting_review_items=formatting_review_items,
                basis=basis,
                role_loss_count=role_loss_count,
                role_loss_samples=advisory_role_loss_samples,
                unmapped_source_count=worst_unmapped_source_count,
            )
        # spec 011: itemize the genuinely-unmapped TARGET paragraphs (the target-side
        # counterpart of the source items above). Policy-independent DATA — emitted under
        # BOTH strict and advisory, unconditionally, because target coverage is review-DATA
        # (spec 010), not a gate; this appends review-items only and changes no verdict.
        if role_aware_target_summary is not None:
            raw_retained_samples = role_aware_target_summary.get("retained_target_samples")
            retained_target_samples: Sequence[object] = (
                raw_retained_samples
                if isinstance(raw_retained_samples, Sequence)
                and not isinstance(raw_retained_samples, (str, bytes, bytearray))
                else []
            )
            raw_retained_count = role_aware_target_summary.get("retained_target_count")
            retained_target_count = raw_retained_count if isinstance(raw_retained_count, int) else 0
        else:
            retained_target_samples = []
            retained_target_count = 0
        _emit_unmapped_target_discrepancy_review_items(
            formatting_review_items=formatting_review_items,
            has_role_aware_summary=role_aware_target_summary is not None,
            retained_samples=retained_target_samples,
            retained_count=retained_target_count,
            effective_unmapped_target_count=effective_unmapped_target_count,
        )
        if isinstance(latest_payload, Mapping):
            controlled_fallback_review_count, controlled_fallback_review_samples = _controlled_fallback_review_samples(
                latest_payload
            )
            quality_status = _emit_controlled_fallback_review_items(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                formatting_review_items=formatting_review_items,
                count=controlled_fallback_review_count,
                samples=controlled_fallback_review_samples,
            )
        # 1‑D heading-demotion is a fix-severity role_loss axis emitted independently of
        # the unmapped-count gate above, so a mapped demoted heading surfaces even when
        # every source paragraph is otherwise mapped. DATA is policy-independent (advisory
        # applies the review reason, strict routes through the role_loss threshold).
        if heading_demotion_count > 0:
            quality_status, _ = _emit_hygiene_gate(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                formatting_review_items=formatting_review_items,
                policy=policy,
                spec=_HYGIENE_GATE_SPECS["heading_demotion"],
                count=heading_demotion_count,
                source_total=effective_source_total,
                samples=heading_demotion_samples,
                # samples handed to the serializer are always mapping rows.
                sample_serializer=cast(
                    "Callable[[object], Mapping[str, object]]", _serialize_heading_demotion_sample
                ),
            )
        if bullet_heading_count > 0:
            quality_status, _ = _emit_hygiene_gate(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                formatting_review_items=formatting_review_items,
                policy=policy,
                spec=_HYGIENE_GATE_SPECS["bullet_heading"],
                count=bullet_heading_count,
                source_total=effective_source_total,
                samples=bullet_heading_samples,
            )
        if toc_body_concat_detected:
            if bool(authority_fields.get("toc_body_concat_structure_detected", False)):
                quality_status = _apply_quality_gate_reason(
                    quality_status=quality_status,
                    gate_reasons=gate_reasons,
                    policy=policy,
                    reason="toc_body_concatenation_detected",
                )
            else:
                quality_status = _apply_quality_review_reason(
                    quality_status=quality_status,
                    gate_reasons=gate_reasons,
                    reason="toc_body_concatenation_review_required",
                )
                formatting_review_items.append(
                    _build_formatting_review_item(
                        reason="toc_body_concatenation_review_required",
                        label="Возможная строка оглавления склеилась с текстом",
                        sample={
                            "line": None,
                            "text": final_markdown,
                            "reason": "toc_body_concatenation_detected",
                        },
                        severity="fix",
                    )
                )
        if false_fragment_heading_samples:
            quality_status, _ = _emit_hygiene_gate(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                formatting_review_items=formatting_review_items,
                policy=policy,
                spec=_HYGIENE_GATE_SPECS["false_fragment"],
                count=len(false_fragment_heading_samples),
                source_total=effective_source_total,
                samples=false_fragment_heading_samples,
            )
        if residual_bullet_glyph_samples:
            quality_status, _ = _emit_hygiene_gate(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                formatting_review_items=formatting_review_items,
                policy=policy,
                spec=_HYGIENE_GATE_SPECS["residual_bullet"],
                count=len(residual_bullet_glyph_samples),
                source_total=effective_source_total,
                samples=residual_bullet_glyph_samples,
            )
        if list_fragment_regression_samples:
            if _is_reviewable_list_fragment_residue(
                samples=list_fragment_regression_samples,
                gate_source=list_fragment_regression_gate_source,
            ):
                serialized_samples = _serialize_quality_samples(list_fragment_regression_samples)
                quality_status = _apply_quality_review_reason(
                    quality_status=quality_status,
                    gate_reasons=gate_reasons,
                    reason="list_fragment_regressions_review_required",
                )
                for sample in serialized_samples:
                    formatting_review_items.append(
                        _build_formatting_review_item(
                            reason="list_fragment_regressions_review_required",
                            label="Одиночный номер в сносках или библиографии",
                            sample=sample,
                        )
                    )
            else:
                quality_status = _apply_quality_gate_reason(
                    quality_status=quality_status,
                    gate_reasons=gate_reasons,
                    policy=policy,
                    reason="list_fragment_regressions_present",
                )
                # Even on the hard-fail path the discrepancy DATA must reach the UI:
                # emit a review-item per residue sample (previously Money hard-failed
                # list_fragment with review_items=0, leaving the UI blind).
                for sample in _serialize_quality_samples(list_fragment_regression_samples):
                    formatting_review_items.append(
                        _build_formatting_review_item(
                            reason="list_fragment_regressions_present",
                            label="Фрагмент списка потерял структуру",
                            sample=sample,
                            severity="fix",
                        )
                    )
        if mixed_script_samples:
            quality_status, _ = _emit_hygiene_gate(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                formatting_review_items=formatting_review_items,
                policy=policy,
                spec=_HYGIENE_GATE_SPECS["mixed_script"],
                count=len(mixed_script_samples),
                source_total=effective_source_total,
                samples=mixed_script_samples,
            )
        if untranslated_structural_samples:
            quality_status = _apply_quality_review_reason(
                quality_status=quality_status,
                gate_reasons=gate_reasons,
                reason="untranslated_structural_text_review_required",
            )
            serialized_samples = [
                dict(_serialize_untranslated_structural_sample(sample))
                for sample in untranslated_structural_samples[:8]
            ]
            use_aggregate = len(untranslated_structural_samples) > len(serialized_samples)
            for sample_index, sample in enumerate(serialized_samples):
                item = _build_formatting_review_item(
                    reason="untranslated_structural_text_review_required",
                    label="Структурный элемент остался на исходном языке",
                    sample=sample,
                    count=0 if use_aggregate else 1,
                    severity="review",
                )
                if sample_index == 0 and use_aggregate:
                    item["aggregate_count"] = len(untranslated_structural_samples)
                formatting_review_items.append(item)
        if untranslated_body_samples:
            untranslated_body_fail = (
                untranslated_body_char_count >= _UNTRANSLATED_BODY_FAIL_MIN_CHARS
                and untranslated_body_ratio >= _UNTRANSLATED_BODY_FAIL_RATIO
            )
            reason = (
                "untranslated_body_text_above_threshold"
                if untranslated_body_fail
                else "untranslated_body_text_review_required"
            )
            if untranslated_body_fail:
                quality_status = _apply_quality_gate_reason(
                    quality_status=quality_status,
                    gate_reasons=gate_reasons,
                    policy=policy,
                    reason=reason,
                )
            else:
                quality_status = _apply_quality_review_reason(
                    quality_status=quality_status,
                    gate_reasons=gate_reasons,
                    reason=reason,
                )
            serialized_samples = [
                dict(_serialize_untranslated_structural_sample(sample))
                for sample in untranslated_body_samples[:8]
            ]
            use_aggregate = len(untranslated_body_samples) > len(serialized_samples)
            for sample_index, sample in enumerate(serialized_samples):
                item = _build_formatting_review_item(
                    reason=reason,
                    label="Фрагмент основного текста остался на исходном языке",
                    sample=sample,
                    count=0 if use_aggregate else 1,
                    severity="fix" if untranslated_body_fail else "review",
                )
                if sample_index == 0 and use_aggregate:
                    item["aggregate_count"] = len(untranslated_body_samples)
                formatting_review_items.append(item)
        mapping_text_quality_payload = (
            latest_payload.get("mapping_text_quality") if isinstance(latest_payload, Mapping) else None
        )
        _emit_mapping_text_quality_defect_items(
            formatting_review_items=formatting_review_items,
            mapping_text_quality=(
                mapping_text_quality_payload if isinstance(mapping_text_quality_payload, Mapping) else None
            ),
        )

    # spec 041 P1-4 / spec 042 P1-B: a caption→heading structural conflict (a figure/table
    # caption promoted to a heading) corrupts the document outline and is genuinely NON-
    # DELIVERABLE. The acceptance verdict already records it UNCONDITIONALLY via the
    # ``caption_heading_conflict_absent`` check (the auditable record); here we route the
    # SAME signal into the DELIVERY gate so ``quality_status`` becomes "fail" and a
    # ``caption_heading_conflict`` gate_reason is present — which drives the
    # ``late_phases.py`` terminal fail branch that blocks primary-artifact publication.
    # Placed OUTSIDE the translate-only block (like the acceptance check, it is applicable
    # whenever formatting diagnostics exist) and BEFORE the delivery-verdict resolution.
    # The reason token is fatal (``_FATAL_DOCUMENT_GATE_REASONS``), so the verdict below
    # preserves the ``fail`` regardless of policy — mirroring the untranslated-body
    # catastrophic gate. Keyed on the conflict count only (no per-book literal).
    if caption_heading_conflict_count > 0:
        quality_status = _apply_quality_gate_reason(
            quality_status=quality_status,
            gate_reasons=gate_reasons,
            policy=policy,
            reason="caption_heading_conflict",
        )

    # spec 018: resolve the DOCUMENT-level delivery verdict. Review-grade fail-drivers
    # (role_loss / heading_demotion / false_fragment / list_fragment / unmapped-source /
    # toc_body_concat / mixed_script / …) yield a delivered ``warn`` instead of a blocking
    # ``fail``; only a genuinely-fatal reason (untranslated body above the catastrophic
    # threshold, or a caption→heading conflict) keeps ``fail``. Applied AFTER all per-reason
    # emission so every gate_reason and review-item is preserved verbatim — only the verdict
    # severity is reclassified.
    quality_status = _resolve_document_delivery_verdict(
        quality_status=quality_status,
        gate_reasons=gate_reasons,
    )

    report = {
        "version": 2,
        "source_name": context.uploaded_filename,
        "processing_operation": context.processing_operation,
        "quality_gate_policy": policy,
        "translation_domain": translation_domain,
        "source_paragraph_count": source_paragraph_count,
        "target_paragraph_count": output_paragraph_count,
        "output_paragraph_count": output_paragraph_count,
        "mapped_count": latest_payload.get("mapped_count") if isinstance(latest_payload, Mapping) else None,
        "unmapped_source_count": worst_unmapped_source_count,
        "unmapped_target_count": effective_unmapped_target_count,
        "worst_unmapped_source_count": worst_unmapped_source_count,
        "raw_unmapped_source_paragraph_count": authority_fields.get("raw_unmapped_source_paragraph_count", len(unmapped_source_ids) if isinstance(unmapped_source_ids, list) else 0),
        "filtered_unmapped_source_count": role_aware_summary.get("filtered_unmapped_source_count") if role_aware_summary else None,
        "format_neutral_creditable_count": role_aware_summary.get("format_neutral_creditable_count") if role_aware_summary else 0,
        "effective_unmapped_source_count": role_aware_summary.get("effective_unmapped_source_count") if role_aware_summary else None,
        "target_split_accounting_creditable_count": (
            role_aware_target_summary.get("target_split_accounting_creditable_count")
            if role_aware_target_summary
            else 0
        ),
        "effective_unmapped_target_count": (
            role_aware_target_summary.get("effective_unmapped_target_count")
            if role_aware_target_summary
            else None
        ),
        "raw_unmapped_target_paragraph_count": authority_fields.get("raw_unmapped_target_paragraph_count", len(unmapped_target_indexes) if isinstance(unmapped_target_indexes, list) else 0),
        "structure_unit_total_count": authority_fields.get("structure_unit_total_count"),
        "structure_unit_unmapped_source_count": authority_fields.get("structure_unit_unmapped_source_count"),
        "structure_unit_unmapped_target_count": authority_fields.get("structure_unit_unmapped_target_count"),
        "accepted_aggregated_source_unit_count": authority_fields.get("accepted_aggregated_source_unit_count"),
        "accepted_aggregated_target_index_count": authority_fields.get("accepted_aggregated_target_index_count"),
        "unmapped_source_count_basis": authority_fields.get("unmapped_source_count_basis", "legacy_paragraph"),
        "unmapped_target_count_basis": authority_fields.get("unmapped_target_count_basis", "legacy_paragraph"),
        "unit_unmapped_source_gate_source": authority_fields.get(
            "unit_unmapped_source_gate_source",
            authority_fields.get("unmapped_source_count_basis", "legacy_paragraph"),
        ),
        "unit_unmapped_target_gate_source": authority_fields.get(
            "unit_unmapped_target_gate_source",
            authority_fields.get("unmapped_target_count_basis", "legacy_paragraph"),
        ),
        "document_map_toc_detected": authority_fields.get("document_map_toc_detected", False),
        "document_map_toc_region_count": authority_fields.get("document_map_toc_region_count", 0),
        "topology_toc_entry_count": authority_fields.get("topology_toc_entry_count", 0),
        "topology_split_compound_toc_operation_count": authority_fields.get(
            "topology_split_compound_toc_operation_count",
            0,
        ),
        "topology_merge_heading_operation_count": authority_fields.get("topology_merge_heading_operation_count", 0),
        "document_map_compound_toc_split_hint_count": authority_fields.get(
            "document_map_compound_toc_split_hint_count",
            0,
        ),
        "accepted_merged_sources_count": len(accepted_merged_sources) if isinstance(accepted_merged_sources, list) else 0,
        "caption_heading_conflicts_count": caption_heading_conflict_count,
        "bullet_heading_count": bullet_heading_count,
        "bullet_heading_gate_source": "legacy_markdown",
        "bullet_heading_classification": "markdown_gate",
        "raw_bullet_heading_count": len(raw_bullet_heading_samples),
        "bullet_heading_samples": _serialize_quality_samples(bullet_heading_samples),
        "raw_bullet_heading_samples": _serialize_quality_samples(raw_bullet_heading_samples),
        "page_placeholder_heading_concat_count": len(page_placeholder_heading_concat_samples),
        "page_placeholder_heading_concat_samples": _serialize_quality_samples(page_placeholder_heading_concat_samples),
        "page_placeholder_heading_concat_source": "legacy_markdown",
        "page_placeholder_heading_concat_classification": "display_hygiene",
        "raw_page_placeholder_heading_concat_count": len(raw_page_placeholder_heading_concat_samples),
        "raw_page_placeholder_heading_concat_samples": _serialize_quality_samples(raw_page_placeholder_heading_concat_samples),
        "false_fragment_heading_count": len(false_fragment_heading_samples),
        "false_fragment_heading_samples": _serialize_quality_samples(false_fragment_heading_samples),
        "false_fragment_heading_gate_source": false_fragment_heading_gate_source,
        "raw_false_fragment_heading_count": len(raw_false_fragment_heading_samples),
        "raw_false_fragment_heading_samples": _serialize_quality_samples(raw_false_fragment_heading_samples),
        "suspicious_heading_repetition_count": len(suspicious_heading_repetition_samples),
        "suspicious_heading_repetition_samples": _serialize_quality_samples(suspicious_heading_repetition_samples),
        "scripture_reference_heading_count": len(scripture_reference_heading_samples),
        "scripture_reference_heading_samples": _serialize_quality_samples(scripture_reference_heading_samples),
        "residual_bullet_glyph_count": len(residual_bullet_glyph_samples),
        "residual_bullet_glyph_gate_source": "legacy_markdown",
        "residual_bullet_glyph_classification": "display_hygiene",
        "raw_residual_bullet_glyph_count": len(raw_residual_bullet_glyph_samples),
        "residual_bullet_glyph_samples": _serialize_quality_samples(residual_bullet_glyph_samples),
        "raw_residual_bullet_glyph_samples": _serialize_quality_samples(raw_residual_bullet_glyph_samples),
        "heading_demotion_count": heading_demotion_count,
        "heading_demotion_samples": [
            dict(_serialize_heading_demotion_sample(sample)) for sample in heading_demotion_samples
        ],
        "list_fragment_regression_count": len(list_fragment_regression_samples),
        "list_fragment_regression_samples": _serialize_quality_samples(list_fragment_regression_samples),
        "list_fragment_regression_gate_source": list_fragment_regression_gate_source,
        "raw_list_fragment_regression_count": len(raw_list_fragment_regression_samples),
        "raw_list_fragment_regression_samples": _serialize_quality_samples(raw_list_fragment_regression_samples),
        "mixed_script_term_count": len(mixed_script_samples),
        "mixed_script_term_gate_source": "legacy_markdown",
        "mixed_script_term_classification": "non_structural_hygiene",
        "raw_mixed_script_term_count": len(raw_mixed_script_samples),
        "mixed_script_term_samples": _serialize_quality_samples(mixed_script_samples),
        "raw_mixed_script_term_samples": _serialize_quality_samples(raw_mixed_script_samples),
        "paragraph_break_count": len(paragraph_break_samples),
        "paragraph_break_classification": "paragraph_break_advisory",
        "paragraph_break_samples": _serialize_paragraph_break_samples(paragraph_break_samples),
        "untranslated_structural_text_count": len(untranslated_structural_samples),
        "untranslated_structural_text_samples": [
            dict(_serialize_untranslated_structural_sample(sample))
            for sample in untranslated_structural_samples[:8]
        ],
        "untranslated_structural_text_classification": "structural_translation_review",
        "untranslated_body_text_count": len(untranslated_body_samples),
        "untranslated_body_text_chars": untranslated_body_char_count,
        "untranslated_body_text_ratio": round(untranslated_body_ratio, 4),
        "untranslated_body_text_samples": [
            dict(_serialize_untranslated_structural_sample(sample))
            for sample in untranslated_body_samples[:8]
        ],
        "untranslated_body_text_classification": "body_translation_completeness",
        # Round-4 F6: the former config-driven glossary/awkward-heading detector was
        # PRODUCTION-DEAD (every caller passed no glossary/markers, so the axis could
        # never fire). The detector and its ``awkward_judgment_heading_present`` /
        # ``unresolved_glossary_term_present`` sample reasons are removed. These four
        # count/source/classification keys are a broad output contract (the acceptance
        # advisory check, ``structural`` metric copy, and the corpus goldens all read
        # them), so they are kept as INERT constants rather than firing a dead metric.
        "theology_style_deterministic_issue_count": 0,
        "theology_style_deterministic_issue_source": "legacy_markdown",
        "theology_style_deterministic_issue_classification": "domain_style_advisory",
        "raw_theology_style_deterministic_issue_count": 0,
        "emphasis_coverage": dict(emphasis_coverage_payload),
        "toc_body_concat_detected": toc_body_concat_detected,
        "toc_body_concat_markdown_detected": authority_fields.get("toc_body_concat_markdown_detected", False),
        "toc_body_concat_structure_detected": authority_fields.get("toc_body_concat_structure_detected", False),
        "toc_body_concat_gate_source": authority_fields.get("toc_body_concat_gate_source", "legacy_markdown"),
        "quality_gate_audit_classifications": quality_gate_audit_classifications_payload(),
        "formatting_diagnostics_artifact_count": len(formatting_diagnostics_artifacts),
        "role_aware_formatting_coverage_note": (
            role_aware_summary.get("counting_note") if role_aware_summary else None
        ),
        "pre_cleanup_formatting_baseline": dict(pre_cleanup_formatting_baseline)
        if isinstance(pre_cleanup_formatting_baseline, Mapping)
        else None,
        "final_markdown_chars": len(normalized_quality_markdown),
        "quality_status": quality_status,
        "gate_reasons": gate_reasons,
        "formatting_review_required_count": _formatting_review_required_count(formatting_review_items),
        "formatting_review_items": formatting_review_items,
        "formatting_diagnostics_artifact_paths": list(formatting_diagnostics_artifacts),
        "boundary_recovery": {
            "accepted_merges": getattr(getattr(assembly_result, "diagnostics", None), "accepted_merges", 0),
            "denied_merges": getattr(getattr(assembly_result, "diagnostics", None), "denied_merges", 0),
            "protected_boundary_denials": getattr(getattr(assembly_result, "diagnostics", None), "protected_boundary_denials", 0),
            "demoted_false_headings": getattr(getattr(assembly_result, "diagnostics", None), "demoted_false_headings", 0),
            "registry_covered_paragraphs": getattr(getattr(assembly_result, "diagnostics", None), "registry_covered_paragraphs", 0),
            "fallback_paragraphs": getattr(getattr(assembly_result, "diagnostics", None), "fallback_paragraphs", 0),
            "paragraph_count_drift": getattr(getattr(assembly_result, "diagnostics", None), "paragraph_count_drift", 0),
            "inconsistent_registry_blocks": list(getattr(getattr(assembly_result, "diagnostics", None), "inconsistent_registry_blocks", ()) or ()),
            "merge_decisions": _serialize_assembly_decisions(getattr(getattr(assembly_result, "diagnostics", None), "merge_decisions", ()) or ()),
            "recovered_heading_entries": _serialize_recovered_heading_entries(recovered_heading_entries),
        },
    }
    return report


def _derive_translation_quality_authority_fields(
    *,
    context: Any,
    final_markdown: str,
    formatting_payload: Mapping[str, object] | None,
    assembly_result: Any | None,
) -> dict[str, object]:
    markdown_detected = _has_toc_body_concat_markdown(final_markdown)
    raw_unmapped_source_count = 0
    raw_unmapped_target_count = 0
    if formatting_payload is not None:
        candidate_source_ids = formatting_payload.get("unmapped_source_ids")
        if isinstance(candidate_source_ids, list):
            raw_unmapped_source_count = len(candidate_source_ids)
        candidate_target_indexes = formatting_payload.get("unmapped_target_indexes")
        if isinstance(candidate_target_indexes, list):
            raw_unmapped_target_count = len(candidate_target_indexes)
    fields: dict[str, object] = {
        "toc_body_concat_detected": markdown_detected,
        "toc_body_concat_markdown_detected": markdown_detected,
        "toc_body_concat_structure_detected": False,
        "toc_body_concat_gate_source": "legacy_markdown",
        "topology_projection_supported": False,
        "document_map_toc_detected": False,
        "document_map_toc_region_count": 0,
        "topology_toc_entry_count": 0,
        "topology_split_compound_toc_operation_count": 0,
        "topology_merge_heading_operation_count": 0,
        "document_map_compound_toc_split_hint_count": 0,
        "raw_unmapped_source_paragraph_count": raw_unmapped_source_count,
        "raw_unmapped_target_paragraph_count": raw_unmapped_target_count,
        "structure_unit_unmapped_source_count": raw_unmapped_source_count,
        "structure_unit_unmapped_target_count": raw_unmapped_target_count,
        "unmapped_source_count_basis": "legacy_paragraph",
        "unmapped_target_count_basis": "legacy_paragraph",
        "unit_unmapped_source_gate_source": "legacy_paragraph",
        "unit_unmapped_target_gate_source": "legacy_paragraph",
    }
    # Structure recognition (#2) removed: no document map / topology projection is produced,
    # so the structure-side TOC/topology gate fields keep their neutral defaults above and only
    # the markdown-derived toc_body_concat detection and unit-aware unmapped fields run.
    source_paragraphs = cast(Sequence[object], getattr(context, "source_paragraphs", None) or ())
    if formatting_payload is None:
        return fields
    try:
        from docxaicorrector.validation import structural as structural_validation_runtime
    except Exception:
        return fields
    fields.update(
        {
            key: value
            for key, value in structural_validation_runtime._derive_toc_body_concat_gate_fields(
                document_map=None,
                topology_projection=None,
                markdown_detected=markdown_detected,
            ).items()
            if key
            in {
                "toc_body_concat_detected",
                "toc_body_concat_markdown_detected",
                "toc_body_concat_structure_detected",
                "toc_body_concat_gate_source",
            }
        }
    )
    generated_paragraph_registry = None
    if assembly_result is not None:
        assembly_entries = tuple(getattr(assembly_result, "entries", ()) or ())
        if assembly_entries:
            generated_paragraph_registry = build_generated_paragraph_registry_from_entries(assembly_entries)
    unmapped_fields = structural_validation_runtime._derive_unit_aware_unmapped_fields(
        source_paragraphs=source_paragraphs,
        topology_projection=None,
        formatting_payload=formatting_payload,
        generated_paragraph_registry=generated_paragraph_registry,
    )
    fields.update(
        {
            key: value
            for key, value in unmapped_fields.items()
            if key
            in {
                "raw_unmapped_source_paragraph_count",
                "raw_unmapped_target_paragraph_count",
                "structure_unit_total_count",
                "structure_unit_unmapped_source_count",
                "structure_unit_unmapped_target_count",
                "accepted_aggregated_source_unit_count",
                "accepted_aggregated_target_index_count",
                "unmapped_source_count_basis",
                "unmapped_target_count_basis",
                "unit_unmapped_source_gate_source",
                "unit_unmapped_target_gate_source",
            }
        }
    )
    return fields


def _effective_authoritative_unmapped_count(
    fields: Mapping[str, object],
    *,
    basis_key: str,
    raw_count_key: str,
    structure_count_key: str,
) -> int:
    basis = str(fields.get(basis_key) or "legacy_paragraph").strip().lower() or "legacy_paragraph"
    candidate = (
        fields.get(structure_count_key)
        if basis in {"topology_unit", "accepted_aggregation_legacy"}
        else fields.get(raw_count_key)
    )
    return int(candidate or 0) if isinstance(candidate, (int, float, bool)) else 0


def _build_result_quality_warning(
    *,
    quality_report: Mapping[str, object],
    latest_result_notice: Mapping[str, str] | None,
) -> dict[str, object] | None:
    quality_status = str(quality_report.get("quality_status", "") or "")
    if quality_status not in {"warn", "fail"}:
        return None
    warning = {
        "kind": "translation_quality_gate",
        "quality_status": quality_status,
        "gate_reasons": list(cast(Sequence[str], quality_report.get("gate_reasons") or [])),
        "message": str((latest_result_notice or {}).get("message", "") or ""),
    }
    formatting_review_items = list(cast(Sequence[object], quality_report.get("formatting_review_items") or []))
    if formatting_review_items:
        warning["formatting_review_items"] = formatting_review_items
        warning["formatting_review_required_count"] = int(
            quality_report.get("formatting_review_required_count") or len(formatting_review_items)
        )
    return warning


def _russian_paragraph_word(count: int) -> str:
    count_abs = abs(count)
    if 11 <= count_abs % 100 <= 14:
        return "абзацев"
    last_digit = count_abs % 10
    if last_digit == 1:
        return "абзац"
    if 2 <= last_digit <= 4:
        return "абзаца"
    return "абзацев"


def _build_quality_warn_notice_message(quality_report: Mapping[str, object]) -> str:
    """Human-readable YELLOW warn notice for a delivered-but-flagged translation (spec 018).

    Frames the run as "completed, needs review" — the document is usable and every
    discrepancy is itemized in ``formatting_review.txt``. Deliberately carries NO
    internal tokens (``translation_quality_gate_failed`` / raw gate_reason keys) and
    none of the fatal-path wording ("критическая ошибка" / "заблокирован"): the count
    of review paragraphs is the human-facing detail, not the reason tokens.
    """
    review_count = int(quality_report.get("formatting_review_required_count") or 0)
    prefix = "Перевод завершён. Документ готов к использованию, но требует ручной проверки оформления"
    suffix = "Подробности — в отчёте проверки (formatting_review.txt)."
    if review_count > 0:
        detail = f"{review_count} {_russian_paragraph_word(review_count)} с замечаниями"
        return f"{prefix}: {detail}. {suffix}"
    return f"{prefix}. {suffix}"


def _build_quality_gate_activity_message(gate_reasons: Sequence[str]) -> str:
    if not gate_reasons:
        return "Итоговый перевод отклонён document-level quality gate."
    joined_reasons = ", ".join(str(reason) for reason in gate_reasons if str(reason))
    if not joined_reasons:
        return "Итоговый перевод отклонён document-level quality gate."
    return f"Итоговый перевод отклонён quality gate: {joined_reasons}."

