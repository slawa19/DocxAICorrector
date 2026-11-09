import logging
import re
import json
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeAlias

from docxaicorrector.core.model_accounting import (
    record_back_matter_delivery,
    record_controlled_block_fallback,
    record_untranslated_prose_block_delivery,
)
from docxaicorrector.core.models import (
    BACK_MATTER_SECTION_NOTES,
    BACK_MATTER_SECTION_REFERENCES,
    LANGUAGE_CHANGING_OPERATIONS,
    PARAGRAPH_REGION_BACK_MATTER,
    PARAGRAPH_REGION_PROSE,
    PARAGRAPH_STATUS_POLICY_KEPT_SOURCE,
)
from docxaicorrector.generation._generation import (
    PARAGRAPH_STATUS_ACCEPTED,
    PARAGRAPH_STATUS_OMITTED,
    PARAGRAPH_STATUS_SOURCE_RESTORED,
    MarkerPreservedBlockText,
    ParagraphDisposition,
    marker_paragraph_dispositions,
)
from docxaicorrector.pipeline.contracts import LatePhaseStopped
from docxaicorrector.pipeline.footnote_markers import preserve_footnote_markers_for_block
from docxaicorrector.pipeline.job_results import persist_terminal_job_result
from docxaicorrector.pipeline.literary_polish import (
    emit_literary_polish_completed,
    first_pass_request_profile,
    literary_polish_applies,
    polish_block,
)
from docxaicorrector.pipeline.output_validation import (
    delivered_text_equals_source,
    is_citation_form_paragraph,
    notes_run_commentary_numbers,
    notes_run_reads_as_citations,
    validate_translated_toc_block,
)
from docxaicorrector.pipeline.support import resolve_system_prompt as _resolve_system_prompt_default
from docxaicorrector.runtime.artifact_retention import prune_artifact_dir


PipelineResult: TypeAlias = Literal["succeeded", "failed", "stopped"]
# Spec 069 FR-004 (2): the system prompt variant of the second pass.
LITERARY_POLISH_PROMPT_VARIANT = "literary_polish"
TOC_VALIDATION_RETRY_BUDGET = 2
TOC_RETRY_HARDENING_ATTEMPT = 2
CONTROLLED_BLOCK_FAILURE_POLICY: dict[str, dict[str, str]] = {
    "empty": {"decision": "fallback_continue", "fallback_kind": "empty_processed_block"},
    "empty_processed_block": {"decision": "fallback_continue", "fallback_kind": "empty_processed_block"},
    "source_text_fallback": {"decision": "fallback_continue", "fallback_kind": "source_text_fallback"},
    "english_residual_output": {"decision": "fallback_continue", "fallback_kind": "english_residual_output"},
    "heading_only_output": {"decision": "fallback_continue", "fallback_kind": "heading_only_output"},
    "bullet_heading_output": {"decision": "fallback_continue", "fallback_kind": "bullet_heading_output"},
    "toc_body_concat": {"decision": "fallback_continue", "fallback_kind": "toc_body_concat"},
    "missing_provider_client": {"decision": "fail"},
    "missing_provider_configuration": {"decision": "fail"},
    "missing_source_segment": {"decision": "fail"},
    "missing_translated_segment": {"decision": "fail"},
    "final_translated_book_incomplete": {"decision": "fail"},
    "marker_registry_failure": {"decision": "fail"},
    "marker_anchor_failure": {"decision": "fail"},
    "invalid_processing_job": {"decision": "fail"},
    "corrupted_block": {"decision": "fail"},
    "source_extraction_failure": {"decision": "fail"},
}
# Spec 059 FR-A8, revised 2026-08-09: the reason a delivered block is announced LOUDLY.
# Named rather than inlined because it travels — into the decision dict, into the log event,
# into the run-level counter and into the acceptance verdict — and three spellings of one
# reason is how a vocabulary drifts.
#
# It used to be a ``fail`` reason. It is not one any more, and the word "warning" in the name
# is the whole change: FR-A8 asked that delivering untranslated prose be an INEXPRESSIBLE
# outcome, and when it was written the only way to make the loss visible was to stop the run,
# because the screen said "Документ обработан." whatever happened. Part B removed that
# premise — the verdict now reaches the screen and every affected paragraph gets an anchor to
# search for — so "never silently" no longer needs a gate. What decided it is the price of a
# DETECTOR defect: a hard stop on a deterministic misfire makes the book unreachable, because
# the next run stops in the same place and no action of the user's gets past it. The measured
# case is on record: run 20260809T_059_doc_rethinking died at 45% on block 140 of 305, whose
# whole text is ``2b`` — a step label on the Terra currency diagram, next to
# ``[[DOCX_IMAGE_img_031]]`` — which the model correctly returned unchanged. That run lost
# $0.21 and a whole book while its own accounting recorded ``omitted=0`` and
# ``source_restored=0``: no text was lost anywhere in it.
UNTRANSLATED_PROSE_WARNING_REASON = "untranslated_prose"
# The key the failure-decision table uses to carry that warning to the delivery site. A
# separate key from ``fail_reason`` on purpose: the two are not the same kind of fact any
# more, and reusing the old name would let a reader (or a call site) believe the run stops.
UNTRANSLATED_PROSE_WARNING_KEY = "warning_reason"
from docxaicorrector.core.constants import RUN_DIR as _RUN_DIR
CONTROLLED_BLOCK_FALLBACK_DIR = _RUN_DIR / "block_fallbacks"
# Retention budget for controlled-block fallback diagnostics (F26). Each rejected
# block writes a uuid-suffixed artifact that never overwrites, so this flat family
# grew without bound. Values match the diagnostic tier used elsewhere under
# ``.run/`` (7-day age, small count); pruning runs right after each write.
BLOCK_FALLBACK_ARTIFACTS_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
BLOCK_FALLBACK_ARTIFACTS_MAX_COUNT = 200


def _safe_artifact_stem(value: str) -> str:
    stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return stem.strip("_")[:80] or "document"


def _write_controlled_block_fallback_artifact(
    *,
    context: Any,
    initialization: Any,
    index: int,
    rejection_kind: str,
    target_text: str,
    processed_chunk: str,
) -> str | None:
    payload = {
        "schema_version": 1,
        "filename": str(getattr(context, "uploaded_filename", "") or ""),
        "block_index": index,
        "block_count": initialization.job_count,
        "fallback_kind": "controlled_processed_block_rejection",
        "output_classification": rejection_kind,
        "target_text_preview": target_text[:1000],
        "processed_chunk_preview": processed_chunk[:1000],
        "note": "Block output was retained so full-document assembly can continue; inspect this artifact before treating the block as clean.",
    }
    try:
        CONTROLLED_BLOCK_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
        artifact_path = (
            CONTROLLED_BLOCK_FALLBACK_DIR
            / f"{_safe_artifact_stem(str(getattr(context, 'uploaded_filename', '') or 'document'))}_block_{index}_{uuid.uuid4().hex[:8]}.json"
        )
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        prune_artifact_dir(
            target_dir=CONTROLLED_BLOCK_FALLBACK_DIR,
            max_age_seconds=BLOCK_FALLBACK_ARTIFACTS_MAX_AGE_SECONDS,
            max_count=BLOCK_FALLBACK_ARTIFACTS_MAX_COUNT,
            glob="*.json",
            emit_log=False,
        )
        return str(artifact_path)
    except OSError:
        return None


def _fallback_markdown_for_processed_block_rejection(*, payload: Any, processed_chunk: str, rejection_kind: str) -> str:
    if rejection_kind in {"empty", "empty_processed_block"}:
        return str(getattr(payload, "target_text", "") or "").strip()
    return processed_chunk


def fallback_delivered_source_text(*, payload: Any, processed_chunk: str) -> bool:
    """True when what the controlled fallback delivered IS the block's own source text.

    No new entity and no list of rejection kinds to keep in sync — the answer is already in
    the two values this call site holds. ``_fallback_markdown_for_processed_block_rejection``
    has exactly two outcomes: ``payload.target_text`` (the ``empty*`` kinds) or the rejected
    model output, and for ``source_text_fallback`` that output IS the source by the
    classifier's own definition (``output_validation.is_source_text_fallback_output``
    requires the two to be equal). Comparing the delivered text against the source recognises
    both without naming either, and stays correct if the policy table grows another kind.

    Spec 059 A-I: this is the payload-shaped face of ``delivered_text_equals_source``, which
    is the single implementation of the comparison (FR-A2 forbids a second predicate) and
    which compares the two texts to the character once surrounding whitespace is trimmed. Until
    that spec this function had exactly ONE consumer — the narration exclusion below — so the
    classifier and the failure-decision table could not see the rule at all, and a block
    delivered wholly in the source language was classified ``valid``. It now has three
    readers: the narration branch, the untranslated-prose invariant, and (through
    ``is_source_text_fallback_output``) the classifier itself.
    """
    return delivered_text_equals_source(
        target_text=str(getattr(payload, "target_text", "") or ""),
        processed_chunk=processed_chunk,
    )


def _language_subtag(value: Any) -> str:
    """The LANGUAGE of a BCP-47 tag: ``en-US`` and ``EN_gb`` are both ``en``.

    A region subtag names a variety of the same language, so ``en`` -> ``en-US`` is a
    reformatting job and not a translation. This reads the tag's structure, not a list of
    locales, so it needs no maintenance as languages are added.
    """
    normalized = str(value or "").strip().casefold()
    for separator in ("-", "_"):
        normalized = normalized.split(separator, 1)[0]
    return normalized


def job_changes_language(
    *,
    processing_operation: Any,
    source_language: Any,
    target_language: Any,
) -> bool:
    """Does this job ask for a different language out than it takes in? (spec 059 FR-A5.)

    Read off the JOB, never guessed from the text — and the job is the OPERATION together
    with the two codes, not the codes alone. Reading only the codes was a P0 defect: the
    shipped defaults are ``processing_operation_default = "edit"`` with ``en`` -> ``ru``
    (``resources/config.toml:25-27``), and the UI renders a source-language selector only
    inside ``LANGUAGE_CHANGING_OPERATIONS`` (``ui/_ui.py:588``), so on a literary edit that
    ``en`` is an artefact the user cannot even correct. Codes alone therefore answered "yes,
    this translates" on the DEFAULT path — where 1 144 of 1 761 recorded deliveries are
    byte-identical to their source and every one of them is right
    (``measurement-translation-signal.md`` §5). The run would have died on the first
    unchanged paragraph of prose.

    ``processing_operation`` is required and has no default, for the same reason: a default
    here is a guess that fails silently in exactly one of the two directions.

    An unnamed language on either side is a MISSING SIGNAL and Constitution VII's "no source
    signal, no repair" applies — the rule does not fire.

    ``auto`` on the source side is not a language and says nothing on its own; what says
    something is the operation around it. Inside ``translate``/``audiobook`` the user asserted
    "put this into <target>", so a delivery identical to the source means the model did
    nothing, and ``auto`` counts as a change. Decided by data rather than by taste: the
    recorded ``money_translate_docx`` run — the only one of the five on the DOCUMENT path, and
    therefore the only one that DELIVERS untranslated text instead of dropping it — ran with
    ``source_language: "auto"``
    (``artifacts/audiobook_final_run/money_translate_docx/run_summary.txt:20``). Reading
    ``auto`` as "unknown, rule off" would have switched the invariant off precisely where the
    loss is delivered. The residual is named rather than hidden: a ``translate`` run over a
    document that is already in the target language can still produce a false failure, and
    that is a misconfiguration the UI already warns about.
    """
    if str(processing_operation or "").strip().casefold() not in LANGUAGE_CHANGING_OPERATIONS:
        return False
    source = _language_subtag(source_language)
    target = _language_subtag(target_language)
    if not source or not target:
        return False
    return source != target


# Structural roles a paragraph can carry that are NOT prose however the region reads. Both
# are set by the document layer (``document/roles.py``, ``document/relations.py``) and both
# are already load-bearing elsewhere (spec 058 reads them; ``layout_cleanup.PROTECTED_ROLES``
# protects them), so this adds no detector and no vocabulary — it reads a label the pipeline
# already computes. An image placeholder and the caption under it sit INSIDE the prose region
# by construction: the region is the span of the book's body, and figures live in the body.
#
# This is a structural narrowing, and it is deliberately NOT a length floor (FR-A3 forbids
# one, and the measurement refutes it: between 14.7% and 38.1% of prose is shorter than 60
# letters) and NOT a word list (Constitution VII).
NON_PROSE_STRUCTURAL_ROLES = frozenset({"image", "caption"})


def prose_paragraph_indexes(payload: Any) -> tuple[int, ...]:
    """Which paragraphs of this block are PROSE — by region AND by structural role.

    The addressable form of the question ``payload_contains_prose`` answers with a bool, and
    the two must not disagree: the alarm channel needs to name the paragraphs, not just the
    block, or the warning has no address and the reader hunts through a book for it.

    ``None``/empty regions mean the producer resolved none at all. ``build_editing_jobs`` is
    the only producer and always labels, so absence means a caller outside document
    preparation; there the safe direction is to protect the text, and every paragraph counts.

    WHAT THIS DOES NOT CLOSE, said out loud rather than patched (Constitution VII, "no source
    signal, no repair"). A paragraph carries a structural role only where the document layer
    had a signal to give it one. These classes have none, and they stay inside prose:

    * a bare proper name standing alone as a BODY paragraph (``Harbourline Trading Co.``). A
      HEADING that is a bare name is closed since spec 067 FR-004: the document layer marks it
      by role and form (``semantic_blocks._resolve_name_heading_positions``,
      ``name_heading_paragraph_indexes``) and it is not prose -- returned unchanged it is the
      name, not a loss. "Introduction" or "Chapter Five" never carry the mark;
    * a web address or a bare domain (an address-like token: word characters with a dot
      between them, standing alone, often with a trailing full stop);
    * an index or bibliography row that fell OUTSIDE the back-matter region the importer
      resolved;
    * — measured, and the reason the run must not die on this — a DIAGRAM step label such as
      ``2b`` or ``4 3``, which the importer emits with role ``body`` because a PDF text layer
      gives it nothing else. That is exactly what killed run 20260809T_059_doc_rethinking, and
      narrowing by role does NOT catch it. The residual is accepted; the answer to it is that
      the outcome is now a warning, not a dead run.
    """
    regions = getattr(payload, "paragraph_regions", None)
    if not isinstance(regions, list) or not regions:
        paragraph_ids = getattr(payload, "paragraph_ids", None)
        return tuple(range(len(paragraph_ids))) if isinstance(paragraph_ids, list) else ()
    roles = getattr(payload, "structural_roles", None)
    role_list = roles if isinstance(roles, list) else []
    name_headings = set(name_heading_paragraph_indexes(payload))
    return tuple(
        index
        for index, region in enumerate(regions)
        if region == PARAGRAPH_REGION_PROSE
        and str(role_list[index] if index < len(role_list) else "").strip().casefold()
        not in NON_PROSE_STRUCTURAL_ROLES
        and index not in name_headings
    )


def payload_contains_prose(payload: Any) -> bool:
    """Does this block carry at least one paragraph of PROSE? (spec 059 A-II / A-6.)

    The question the invariant asks, and the reason A-II had to be built before A-4. A block
    is substituted as a WHOLE, so the moment one of its paragraphs is prose, substituting the
    block delivers untranslated prose — while a block that is entirely apparatus (front
    matter, the table of contents, the back-matter reference region, an image and its
    caption) may legitimately keep the controlled fallback, which is the anti-vacuum half of
    the rule.

    REGION and structural ROLE, and nothing else: not the length, not the shape of the text.
    The measurement re-counted at block granularity found ONE firing block in 1 394 across
    five recorded runs, and it is the ``# %`` / ``( i)`` title page — a REGION, not a form
    (``scripts/measure-block-pair-rule.py``). The role half was added on 2026-08-09 for the
    figure apparatus, which sits inside the prose region by construction; see
    ``prose_paragraph_indexes`` for what it still does not close.

    A missing list means the producer resolved no regions at all, and there the safe
    direction is to protect the text.
    """
    regions = getattr(payload, "paragraph_regions", None)
    if not isinstance(regions, list) or not regions:
        return True
    return bool(prose_paragraph_indexes(payload))


# --- Spec 063 FR-011 / FR-012: the apparatus policy of owner decision D1 -----------------
#
# D1 (2026-11-07): entries of a bibliography and references stay in the SOURCE language, the
# commentary of notes is translated, one policy per book -- keyed on the REGION, never on the
# shape of an entry (Constitution VII). The region and its section are resolved by the document
# layer (``semantic_blocks._resolve_back_matter_sections``); this module only reads them.
#
# The structural roles a reference-list ENTRY arrives with. Measured on the four corpus books
# (2026-11-07 runs, ``pairs.jsonl``): every paragraph of their back matter is ``body``,
# ``list`` or ``heading``. A heading inside a reference list -- the section title itself, a
# sub-list title such as "Articles" -- is not an entry and is translated, so a block carrying
# one goes to the model under the prompt rule rather than being kept whole. Anything else
# (``image``, ``caption``, ...) is not an entry either, and the same conservative direction
# applies: an unknown role sends the block to the model.
REFERENCE_ENTRY_STRUCTURAL_ROLES = frozenset({"body", "list"})
# The sections D1 speaks about. The index is not one of them: it is translated as before, and
# its repair is a non-goal of spec 063 (P-6).
_BACK_MATTER_POLICY_SECTION_NAMES = {
    BACK_MATTER_SECTION_NOTES: "примечания",
    BACK_MATTER_SECTION_REFERENCES: "список литературы",
}
_APPARATUS_PROMPT_HEADER = "СПРАВОЧНЫЙ АППАРАТ БЛОКА:"
_APPARATUS_PROMPT_RULE = (
    "- Записи библиографии и ссылки на источники оставляйте как есть, на языке оригинала: "
    "авторов, названия, издательства, годы, страницы и адреса не переводите и не "
    "транслитерируйте. Переводите только авторский комментарий."
)
# Spec 069 FR-005 (a), (b): the rule above is addressed to a paragraph, and a run of notes the
# import left in the body mixes references and commentary in one paragraph. One line per such
# paragraph names the NOTES whose entry is not a reference by the per-entry test of spec 067
# (``output_validation.notes_run_commentary_numbers``), in the singular or the plural.
_APPARATUS_PROMPT_COMMENTARY_NOTE = (
    "- В абзаце {paragraph} авторский текст есть в примечании {numbers}: "
    "его переведите, ссылки и имена авторов в нём оставьте."
)
_APPARATUS_PROMPT_COMMENTARY_NOTES = (
    "- В абзаце {paragraph} авторский текст есть в примечаниях {numbers}: "
    "его переведите, ссылки и имена авторов в них оставьте."
)


def _is_translate_job(context: Any) -> bool:
    """D1 is a TRANSLATION policy. On ``edit`` the source is already in the target language,
    and ``audiobook`` never narrates the back matter at all (spec 054)."""
    return str(getattr(context, "processing_operation", "") or "").strip().casefold() == "translate"


def back_matter_paragraph_indexes(payload: Any) -> tuple[int, ...]:
    """Which paragraphs of this block lie in the back-matter REGION. Empty when the producer
    resolved no regions: absence is never read as apparatus (the ``prose_paragraph_indexes``
    rule, from the other side)."""
    regions = getattr(payload, "paragraph_regions", None)
    if not isinstance(regions, list):
        return ()
    return tuple(index for index, region in enumerate(regions) if region == PARAGRAPH_REGION_BACK_MATTER)


def notes_in_body_paragraph_indexes(payload: Any) -> tuple[int, ...]:
    """Spec 067 FR-001: which paragraphs of this block are a run of notes the import left in
    the PROSE region, by the document layer's per-paragraph mark
    (``BlockExecutionPayload.notes_in_body_paragraph_ids``).

    Read together with the region: a marked paragraph outside the prose region is not one (the
    back-matter region has its own section policy). Empty when the producer resolved no mark,
    no regions or no ids -- absence is never read as apparatus.
    """
    marked = getattr(payload, "notes_in_body_paragraph_ids", None)
    regions = getattr(payload, "paragraph_regions", None)
    paragraph_ids = getattr(payload, "paragraph_ids", None)
    if not isinstance(marked, list) or not marked:
        return ()
    if not isinstance(regions, list) or not isinstance(paragraph_ids, list) or len(regions) != len(paragraph_ids):
        return ()
    marked_ids = {str(paragraph_id) for paragraph_id in marked}
    return tuple(
        index
        for index, paragraph_id in enumerate(paragraph_ids)
        if str(paragraph_id) in marked_ids and regions[index] == PARAGRAPH_REGION_PROSE
    )


# Spec 067 FR-004: the REASON a paragraph carries ``policy_kept_source`` when it is a heading that
# is a bare name the model returned unchanged. A reason, not a new status: every consumer of the
# status (the gate's exemptions, the source-text delivery channel, the narration filters) reads a
# name kept in the source language exactly as it reads a kept reference.
POLICY_KEPT_REASON_NAME_KEPT = "name_kept"


def name_heading_paragraph_indexes(payload: Any) -> tuple[int, ...]:
    """Spec 067 FR-004: which paragraphs of this block are a HEADING that is a bare name, by the
    document layer's mark (``BlockExecutionPayload.name_heading_paragraph_ids``) AND the role the
    payload carries -- a marked paragraph whose role is not ``heading``, or which lies outside the
    prose region, is not one. Empty when anything is missing: absence is never read as a name.
    """
    marked = getattr(payload, "name_heading_paragraph_ids", None)
    regions = getattr(payload, "paragraph_regions", None)
    roles = getattr(payload, "structural_roles", None)
    paragraph_ids = getattr(payload, "paragraph_ids", None)
    if not isinstance(marked, list) or not marked:
        return ()
    if not isinstance(paragraph_ids, list) or not isinstance(regions, list) or not isinstance(roles, list):
        return ()
    if not len(paragraph_ids) == len(regions) == len(roles):
        return ()
    marked_ids = {str(paragraph_id) for paragraph_id in marked}
    return tuple(
        index
        for index, paragraph_id in enumerate(paragraph_ids)
        if str(paragraph_id) in marked_ids
        and regions[index] == PARAGRAPH_REGION_PROSE
        and str(roles[index] or "").strip().casefold() == "heading"
    )


def reference_list_block_keeps_source(*, context: Any, payload: Any) -> bool:
    """Is this a block the pipeline delivers in the source language WITHOUT a model call?
    (spec 063 FR-011.)

    All of, and nothing else:

    * the job is ``translate``;
    * the block lies in a back-matter section that is a REFERENCE LIST (by its anchor title);
    * EVERY paragraph is in the back-matter region -- one paragraph of any other region, prose
      above all, sends the block to the model, which is the anti-vacuum half of the rule;
    * EVERY paragraph carries an entry role (``REFERENCE_ENTRY_STRUCTURAL_ROLES``) -- a
      heading is translated, so a block carrying one is a mixed block;
    * the block is an ordinary model block with addressable paragraphs, not a TOC routed
      through its own validator.

    Every input that is missing or out of step answers "no": the safe direction is the model.
    """
    if not _is_translate_job(context):
        return False
    if getattr(payload, "job_kind", None) != "llm" or bool(getattr(payload, "toc_dominant", False)):
        return False
    if getattr(payload, "back_matter_section", None) != BACK_MATTER_SECTION_REFERENCES:
        return False
    regions = getattr(payload, "paragraph_regions", None)
    roles = getattr(payload, "structural_roles", None)
    paragraph_ids = getattr(payload, "paragraph_ids", None)
    if not isinstance(regions, list) or not regions:
        return False
    if not isinstance(roles, list) or len(roles) != len(regions):
        return False
    if not isinstance(paragraph_ids, list) or len(paragraph_ids) != len(regions):
        return False
    if any(region != PARAGRAPH_REGION_BACK_MATTER for region in regions):
        return False
    return all(str(role or "").strip().casefold() in REFERENCE_ENTRY_STRUCTURAL_ROLES for role in roles)


def _source_paragraph_texts(payload: Any) -> list[str] | None:
    """The block's own SOURCE text per paragraph, parallel to ``paragraph_ids``, or ``None``.

    Read off ``target_text_with_markers`` -- the producer's ``[[DOCX_PARA_<id>]]`` + newline +
    text wrapping (``semantic_blocks.build_marker_wrapped_block_text``) -- by locating each
    expected marker in order. Exact, never repaired: a marker missing, out of order, or text in
    front of the first one means the source cannot be addressed paragraph by paragraph, and
    the caller then falls back to the model or counts nothing.
    """
    paragraph_ids = getattr(payload, "paragraph_ids", None)
    if not isinstance(paragraph_ids, list) or not paragraph_ids:
        return None
    marked = str(getattr(payload, "target_text_with_markers", "") or "")
    spans: list[tuple[int, int]] = []
    cursor = 0
    for paragraph_id in paragraph_ids:
        marker = f"[[DOCX_PARA_{paragraph_id}]]\n"
        position = marked.find(marker, cursor)
        if position < 0:
            return None
        spans.append((position, position + len(marker)))
        cursor = position + len(marker)
    if marked[: spans[0][0]].strip():
        return None
    texts = [
        marked[end : (spans[order + 1][0] if order + 1 < len(spans) else len(marked))].strip()
        for order, (_, end) in enumerate(spans)
    ]
    if any(not text for text in texts):
        return None
    return texts


def policy_kept_source_chunk(*, context: Any, payload: Any, marker_mode_enabled: bool) -> str | None:
    """The block exactly as its source, when FR-011 keeps it without a model call; else ``None``.

    In marker mode the text carries a per-paragraph record whose every status is
    ``policy_kept_source`` (``core.models.PARAGRAPH_STATUS_POLICY_KEPT_SOURCE``), so the
    registry, the source-text delivery channel and both narration projections can tell this
    paragraph from a translation and from a loss. Without markers there is no registry to
    carry it and the block's own source text ships as one string, as a passthrough block does.
    """
    if not reference_list_block_keeps_source(context=context, payload=payload):
        return None
    if not marker_mode_enabled:
        return str(getattr(payload, "target_text", "") or "")
    texts = _source_paragraph_texts(payload)
    if texts is None:
        return None
    dispositions = tuple(
        ParagraphDisposition(
            paragraph_id=str(paragraph_id),
            text=text,
            status=PARAGRAPH_STATUS_POLICY_KEPT_SOURCE,
        )
        for paragraph_id, text in zip(payload.paragraph_ids, texts)
    )
    return MarkerPreservedBlockText("\n\n".join(texts), dispositions)


# --- Spec 064 FR-006: a reference the MODEL kept is apparatus, not a fallback -------------
#
# Prompt rule 12 (``operation_translate.txt``) tells the model to leave references in notes and
# reference lists as they are, and it does. Until this rule the pair rule of spec 059 then read
# the unchanged answer as ``source_text_fallback`` and the run filed it as a controlled fallback
# -- a counter, an artifact in ``block_fallbacks/`` and a warning on the screen for the outcome
# the prompt asked for: 209 blocks and 312 paragraphs of The Value of Everything's notes on the
# 2026-11-07 rerun. What changes is the DISPOSITION by region, never the predicate: "unchanged"
# is still ``delivered_text_equals_source`` and nothing else (spec 064 Anti-regression 4).
_APPARATUS_POLICY_SECTIONS = frozenset({BACK_MATTER_SECTION_NOTES, BACK_MATTER_SECTION_REFERENCES})


@dataclass(frozen=True)
class ModelKeptApparatus:
    """What FR-006 decided for one model-answered block.

    ``processed_chunk`` is the block to deliver -- the model's own text, with the per-paragraph
    record relabelled in marker mode; ``paragraph_count`` is how many paragraphs now carry
    ``policy_kept_source``; ``whole_block`` says that every paragraph of the block is such a
    reference, which is the only case in which a ``source_text_fallback`` stops being one.
    ``notes_in_body_paragraph_count`` is how many of them are notes left in the body (spec 067
    FR-001), so the log line can tell the two apparatus sources apart;
    ``name_kept_paragraph_count`` is how many are headings kept as names (spec 067 FR-004,
    reason ``POLICY_KEPT_REASON_NAME_KEPT``), which are announced by their own log line.
    """

    processed_chunk: str
    paragraph_count: int
    whole_block: bool
    notes_in_body_paragraph_count: int = 0
    name_kept_paragraph_count: int = 0


# How a paragraph ENDS when it ends a sentence: a full stop, a question or exclamation mark or
# an ellipsis, optionally followed by closing quotes or brackets. A paragraph that ends any other
# way continues in the next one -- the torn line of a PDF text layer.
_SENTENCE_END_PATTERN = re.compile(r'[.!?…]["”’»)\]*]*\s*$')


def _torn_paragraph_runs(source_texts: Sequence[str]) -> list[list[int]]:
    """Positions grouped into runs joined by a torn end (no sentence end) in the SOURCE."""
    runs: list[list[int]] = []
    for position, text in enumerate(source_texts):
        if runs and _SENTENCE_END_PATTERN.search(source_texts[position - 1]) is None:
            runs[-1].append(position)
        else:
            runs.append([position])
    return runs


def model_kept_apparatus(*, context: Any, payload: Any, processed_chunk: str) -> ModelKeptApparatus | None:
    """Which paragraphs of this answer are references the model kept under rule 12, or ``None``.

    A paragraph qualifies when, all of:

    * the job is ``translate`` and the block lies in a ``notes`` or ``references`` section --
      the two D1 speaks about; the index is translated, so an unchanged index entry stays what
      it was;
    * the paragraph lies in the back-matter REGION -- a prose paragraph in the same block is
      never apparatus, which keeps the spec 059 invariant out of reach of this rule;
    * the generator ACCEPTED it (an ``omitted`` or ``source_restored`` paragraph is a loss and
      keeps its own status) and its text equals its own source (``delivered_text_equals_source``);
    * the source reads as a reference by its form (``output_validation.is_citation_form_paragraph``)
      -- an unchanged sentence of commentary stays a fallback, which is the anti-vacuum half;
    * a ``heading`` is held to the same positive signal as any other paragraph. D1 translates
      the titles of the apparatus, and a real section title ("Notes", "Chapter 7") carries no
      year, locator, initials, address or title span, so its echo stays a fallback; a torn
      reference the importer typed as a heading (VoE: ten blocks such as
      ``### *Tides: What Should Turn?* (Kelbrook: Bureau of``) carries one and is
      relabelled (orchestrator decision 2026-11-07 after the Codex acceptance review).

    Spec 067 FR-001 extends the same disposition to a run of notes the import left in the
    PROSE region (``notes_in_body_paragraph_indexes``), in any block: such a paragraph is
    eligible like a back-matter one, and its citation test is taken per ENTRY
    (``output_validation.notes_run_reads_as_citations``) -- a notes run holds several entries,
    and one entry of commentary left in the source language keeps the paragraph out. Only in
    marker mode: without a per-paragraph record a prose block is never relabelled.

    Spec 067 FR-004 adds the one non-apparatus case with the same disposition: a HEADING the
    document layer marked as a bare name (``name_heading_paragraph_indexes``) that the model
    returned unchanged -- the name is the right answer, so it is ``policy_kept_source`` with the
    reason ``name_kept``, not a ``source_text_fallback``. Its form was already decided on the
    document layer (role, shape, the document's case count); here only "accepted and unchanged"
    is asked. The torn-run rule below applies to it as to a reference: a heading never ends a
    sentence, so it is relabelled only where nothing follows it in its block -- in practice a
    block of that one heading, the case of A-4.

    Decided per PARAGRAPH where the answer carries its per-paragraph record. Without markers
    there is no record to carry a status, so the decision is per BLOCK: the whole answer equals
    the whole source, every paragraph is in the back-matter region and reads as a reference,
    and the document layer already keeps the block out of the narration (without a record
    nothing else would). Every input that is missing or out of step answers ``None``: the safe
    direction is the old one.
    """
    if not _is_translate_job(context):
        return None
    if getattr(payload, "job_kind", None) != "llm" or bool(getattr(payload, "toc_dominant", False)):
        return None
    in_apparatus_section = getattr(payload, "back_matter_section", None) in _APPARATUS_POLICY_SECTIONS
    notes_in_body = set(notes_in_body_paragraph_indexes(payload))
    name_headings = set(name_heading_paragraph_indexes(payload))
    if not in_apparatus_section and not notes_in_body and not name_headings:
        return None
    regions = getattr(payload, "paragraph_regions", None)
    paragraph_ids = getattr(payload, "paragraph_ids", None)
    if not isinstance(regions, list) or not regions:
        return None
    if not isinstance(paragraph_ids, list) or len(paragraph_ids) != len(regions):
        return None
    eligible = [
        (in_apparatus_section and region == PARAGRAPH_REGION_BACK_MATTER) or position in notes_in_body
        for position, region in enumerate(regions)
    ]
    dispositions = marker_paragraph_dispositions(processed_chunk)
    if dispositions is None:
        if not in_apparatus_section:
            return None
        target_text = str(getattr(payload, "target_text", "") or "")
        if bool(getattr(payload, "narration_include", True)):
            return None
        if not all(eligible):
            return None
        if not delivered_text_equals_source(target_text=target_text, processed_chunk=processed_chunk):
            return None
        source_paragraphs = [chunk.strip() for chunk in target_text.split("\n\n") if chunk.strip()]
        if not source_paragraphs or not all(is_citation_form_paragraph(text) for text in source_paragraphs):
            return None
        return ModelKeptApparatus(
            processed_chunk=processed_chunk, paragraph_count=len(paragraph_ids), whole_block=True
        )
    if [str(disposition.paragraph_id) for disposition in dispositions] != [str(pid) for pid in paragraph_ids]:
        return None
    source_texts = _source_paragraph_texts(payload)
    if source_texts is None:
        return None
    kept_positions = {
        position
        for position, disposition in enumerate(dispositions)
        if eligible[position]
        and disposition.status == PARAGRAPH_STATUS_ACCEPTED
        and delivered_text_equals_source(target_text=source_texts[position], processed_chunk=disposition.text)
        and (
            notes_run_reads_as_citations(source_texts[position])
            if position in notes_in_body
            else is_citation_form_paragraph(source_texts[position])
        )
    } | {
        position
        for position in name_headings
        if dispositions[position].status == PARAGRAPH_STATUS_ACCEPTED
        and delivered_text_equals_source(
            target_text=source_texts[position], processed_chunk=dispositions[position].text
        )
    }
    # A reference torn across two paragraphs is ONE entry: assembly welds the halves back
    # together, but never two halves of different narration admissibility
    # (``output_validation._entry_is_narration_admissible``). Relabelling one half alone would
    # therefore split an entry the reader saw whole (Codex acceptance review 2026-11-07,
    # finding 3), so a torn run is relabelled together or not at all.
    kept_positions = {
        position
        for run in _torn_paragraph_runs(source_texts)
        if all(member in kept_positions for member in run)
        for position in run
    }
    if not kept_positions:
        return None
    relabelled = tuple(
        ParagraphDisposition(
            paragraph_id=disposition.paragraph_id,
            text=disposition.text,
            status=PARAGRAPH_STATUS_POLICY_KEPT_SOURCE,
        )
        if position in kept_positions
        else disposition
        for position, disposition in enumerate(dispositions)
    )
    return ModelKeptApparatus(
        processed_chunk=MarkerPreservedBlockText(
            "\n\n".join(disposition.text for disposition in relabelled), relabelled
        ),
        paragraph_count=len(kept_positions),
        whole_block=len(kept_positions) == len(dispositions),
        notes_in_body_paragraph_count=len(kept_positions & notes_in_body),
        name_kept_paragraph_count=len(kept_positions & name_headings),
    )


def _build_block_apparatus_prompt(*, context: Any, payload: Any, marker_mode_enabled: bool) -> str:
    """The per-block half of FR-011: which paragraphs of THIS block are apparatus, and the rule.

    The system prompt is cached per run (``_get_cached_system_prompt``) and cannot know the
    block; the region is per paragraph. So the rule in ``operation_translate.txt`` names this
    section, and this section names the paragraphs. Only notes and reference lists carry it --
    the two D1 speaks about.

    Spec 067 FR-001: a block of the body that holds a run of notes the import left there
    (``notes_in_body_paragraph_indexes``) carries the section too, as notes, naming exactly
    those paragraphs -- the region of the book is not relabelled, the paragraph is named.

    Spec 069 FR-005: for each of those in-body paragraphs, in marker mode, one more line names
    the notes of the run whose entry is not a reference (``notes_run_commentary_numbers`` on the
    paragraph's own source) -- the rule is applied note by note, not to the paragraph whole. A
    run of references only gets no line. Without markers, or when the source cannot be
    addressed paragraph by paragraph (``_source_paragraph_texts``), nothing is added. A notes
    section of the back matter keeps its section as before: the defect was measured on the
    in-body runs only.
    """
    if not _is_translate_job(context):
        return ""
    section_name = _BACK_MATTER_POLICY_SECTION_NAMES.get(str(getattr(payload, "back_matter_section", "") or ""))
    indexes = back_matter_paragraph_indexes(payload) if section_name is not None else ()
    unmarked_scope = "абзацы этого раздела в блоке"
    notes_in_body = not indexes
    if not indexes:
        indexes = notes_in_body_paragraph_indexes(payload)
        section_name = _BACK_MATTER_POLICY_SECTION_NAMES[BACK_MATTER_SECTION_NOTES]
        unmarked_scope = "абзацы с нумерованными примечаниями в блоке"
    if not indexes:
        return ""
    regions = getattr(payload, "paragraph_regions", None) or []
    paragraph_ids = getattr(payload, "paragraph_ids", None)
    if len(indexes) == len(regions):
        scope = "все абзацы блока"
    elif marker_mode_enabled and isinstance(paragraph_ids, list) and len(paragraph_ids) == len(regions):
        scope = ", ".join(f"[[DOCX_PARA_{paragraph_ids[index]}]]" for index in indexes)
    else:
        scope = unmarked_scope
    commentary_lines: list[str] = []
    addressable = marker_mode_enabled and isinstance(paragraph_ids, list) and len(paragraph_ids) == len(regions)
    source_texts = _source_paragraph_texts(payload) if notes_in_body and addressable else None
    if source_texts is not None and isinstance(paragraph_ids, list):
        for index in indexes:
            numbers = notes_run_commentary_numbers(source_texts[index])
            if numbers:
                template = (
                    _APPARATUS_PROMPT_COMMENTARY_NOTE if len(numbers) == 1 else _APPARATUS_PROMPT_COMMENTARY_NOTES
                )
                commentary_lines.append(
                    template.format(
                        paragraph=f"[[DOCX_PARA_{paragraph_ids[index]}]]",
                        numbers=", ".join(str(number) for number in numbers),
                    )
                )
    return "\n".join(
        (
            _APPARATUS_PROMPT_HEADER,
            f"- Раздел: {section_name}",
            f"- Абзацы: {scope}",
            _APPARATUS_PROMPT_RULE,
            *commentary_lines,
        )
    )


def _delivered_paragraph_texts(processed_chunk: str, paragraph_count: int) -> list[str] | None:
    dispositions = marker_paragraph_dispositions(processed_chunk)
    if dispositions is not None:
        texts = [disposition.text for disposition in dispositions]
    else:
        texts = [chunk.strip() for chunk in str(processed_chunk).split("\n\n") if chunk.strip()]
    return texts if len(texts) == paragraph_count else None


def _record_back_matter_delivery(
    *,
    context: Any,
    dependencies: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    kept_by_policy: bool,
    model_kept_paragraph_count: int = 0,
    model_kept_replaced_fallback: bool = False,
) -> None:
    """Spec 063 FR-012: book how this block's back-matter paragraphs reached the reader.

    Data, not a gate. A paragraph counts as delivered in the source language when its
    delivered text equals its own source (``delivered_text_equals_source`` -- the one
    comparison, FR-A2 of spec 059), and as translated otherwise. A paragraph with nothing to
    translate (a year, a URL) counts as source: the share is an upper bound on the policy's
    reach, said here rather than discovered. A block whose paragraphs cannot be aligned to
    their source is not counted at all, rather than counted by a guess.
    """
    if not _is_translate_job(context):
        return
    section = getattr(payload, "back_matter_section", None)
    indexes = back_matter_paragraph_indexes(payload)
    if not section or not indexes:
        return
    paragraph_ids = getattr(payload, "paragraph_ids", None)
    if not isinstance(paragraph_ids, list) or not paragraph_ids:
        return
    source_texts = _source_paragraph_texts(payload)
    delivered_texts = _delivered_paragraph_texts(processed_chunk, len(paragraph_ids))
    if source_texts is None or delivered_texts is None:
        return
    kept = [
        position
        for position in indexes
        if delivered_text_equals_source(
            target_text=source_texts[position], processed_chunk=delivered_texts[position]
        )
    ]
    translated = [position for position in indexes if position not in kept]
    roles = getattr(payload, "structural_roles", None)
    role_list = roles if isinstance(roles, list) else []
    entry_positions = {
        position
        for position in indexes
        if position < len(role_list)
        and str(role_list[position] or "").strip().casefold() in REFERENCE_ENTRY_STRUCTURAL_ROLES
    }
    kept_entries = [position for position in kept if position in entry_positions]
    translated_entries = [position for position in translated if position in entry_positions]
    mixed = section == BACK_MATTER_SECTION_REFERENCES and bool(kept_entries) and bool(translated_entries)
    record_back_matter_delivery(
        section=str(section),
        source_paragraph_count=len(kept),
        translated_paragraph_count=len(translated),
        kept_by_policy=kept_by_policy,
        kept_chars=len(processed_chunk) if kept_by_policy else 0,
        mixed=mixed,
        model_kept_paragraph_count=model_kept_paragraph_count,
        model_kept_replaced_fallback=model_kept_replaced_fallback,
    )
    if mixed:
        dependencies.log_event(
            logging.WARNING,
            "back_matter_policy_mixed_block",
            "Записи списка литературы в одном блоке доставлены частью на языке оригинала, частью переведёнными; нужна проверка.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            back_matter_section=str(section),
            needs_review=True,
            review_data=True,
            advisory=True,
            source_paragraph_ids=[str(paragraph_ids[position]) for position in kept_entries][:20],
            translated_paragraph_ids=[str(paragraph_ids[position]) for position in translated_entries][:20],
        )


def _has_intact_controlled_fallback_substrate(
    *,
    payload: Any,
    fallback_markdown: str,
    build_processed_paragraph_registry_entries_fn: Any,
) -> bool:
    paragraph_ids = getattr(payload, "paragraph_ids", None)
    if getattr(payload, "job_kind", None) != "llm":
        return False
    if not isinstance(paragraph_ids, list) or not paragraph_ids:
        return False
    if not str(getattr(payload, "target_text", "") or "").strip():
        return False
    if not str(getattr(payload, "target_text_with_markers", "") or "").strip():
        return False
    if not fallback_markdown.strip():
        return False
    try:
        build_processed_paragraph_registry_entries_fn(
            block_index=0,
            paragraph_ids=paragraph_ids,
            processed_chunk=fallback_markdown,
        )
    except Exception:
        return False
    return True


def untranslated_prose_would_be_delivered(
    *,
    payload: Any,
    fallback_markdown: str,
    languages_differ: bool,
) -> bool:
    """The spec 059 FR-A8 rule, in the three facts it stands on.

    * the job CHANGES LANGUAGE (FR-A5) — otherwise a delivery identical to its source is the
      right outcome and says nothing about completeness;
    * the text about to ship IS the block's own source (A-I, the measured pair rule);
    * the block carries at least one paragraph of PROSE (A-II, by region and role).

    All three, or there is nothing to announce. That is why the order A-I -> A-II -> A-4 is
    fixed in the spec: written before either of the first two, this function would be a rule
    that never fires, and a declared rule that cannot fire is worse than none.

    What it deliberately does NOT look at: the rejection kind. The seven quality kinds differ
    in why the block was rejected, not in what gets delivered, and only the second decides
    whether prose is lost.

    Revised 2026-08-09: the block is DELIVERED either way now. What this answers is whether
    the delivery has to be announced — counted, logged, given an anchor and turned into a red
    acceptance check — not whether it happens. See ``UNTRANSLATED_PROSE_WARNING_REASON``.
    """
    if not languages_differ:
        return False
    if not fallback_delivered_source_text(payload=payload, processed_chunk=fallback_markdown):
        return False
    return payload_contains_prose(payload)


def classify_processed_block_failure_decision(
    *,
    rejection_kind: str,
    payload: Any,
    processed_chunk: str,
    build_processed_paragraph_registry_entries_fn: Any,
    languages_differ: bool = True,
) -> dict[str, str]:
    policy = CONTROLLED_BLOCK_FAILURE_POLICY.get(rejection_kind, {"decision": "fail"})
    decision = str(policy.get("decision") or "fail")
    fallback_kind = str(policy.get("fallback_kind") or rejection_kind)
    if decision != "fallback_continue":
        return {"decision": decision, "fallback_kind": fallback_kind}
    fallback_markdown = _fallback_markdown_for_processed_block_rejection(
        payload=payload,
        processed_chunk=processed_chunk,
        rejection_kind=fallback_kind,
    )
    # The substrate test now runs FIRST, and that is a consequence of the invariant losing its
    # ``fail``: a broken marker substrate is the only reason left that can stop the run here,
    # so there is no longer a competition between two reasons for one report to get wrong.
    if not _has_intact_controlled_fallback_substrate(
        payload=payload,
        fallback_markdown=fallback_markdown,
        build_processed_paragraph_registry_entries_fn=build_processed_paragraph_registry_entries_fn,
    ):
        return {"decision": "fail", "fallback_kind": fallback_kind}
    decided: dict[str, str] = {
        "decision": "fallback_continue",
        "fallback_kind": fallback_kind,
        "fallback_markdown": fallback_markdown,
    }
    # Spec 059 FR-A8, revised 2026-08-09. This used to return ``fail`` here and it no longer
    # does; the block ships and the answer travels as a WARNING instead. The rule is still
    # evaluated in exactly one place — this table — so the log event, the run counter, the
    # alarm channel and the acceptance check all read the same decision rather than each
    # re-deriving it and drifting.
    if untranslated_prose_would_be_delivered(
        payload=payload,
        fallback_markdown=fallback_markdown,
        languages_differ=languages_differ,
    ):
        decided[UNTRANSLATED_PROSE_WARNING_KEY] = UNTRANSLATED_PROSE_WARNING_REASON
    return decided


def _resolve_segment_status_payload(*, initialization: Any, index: int, status: str) -> tuple[dict[str, str], dict[str, float], str, str]:
    segment_ids_by_job = tuple(getattr(initialization, "segment_ids_by_job", ()) or ())
    segment_titles_by_id = dict(getattr(initialization, "segment_titles_by_id", {}) or {})
    segment_job_totals = dict(getattr(initialization, "segment_job_totals", {}) or {})
    if not segment_ids_by_job:
        return {}, {}, "", ""

    active_segment_index = max(0, min(index - 1, len(segment_ids_by_job) - 1))
    active_segment_id = segment_ids_by_job[active_segment_index]
    if active_segment_id is None:
        return {}, {}, "", ""

    active_segment_title = str(segment_titles_by_id.get(active_segment_id, active_segment_id) or active_segment_id)
    completed_jobs_by_segment: dict[str, int] = {}
    for segment_index in range(max(0, min(index, len(segment_ids_by_job)))):
        segment_id = segment_ids_by_job[segment_index]
        if segment_id is None:
            continue
        completed_jobs_by_segment[segment_id] = completed_jobs_by_segment.get(segment_id, 0) + 1

    status_by_id: dict[str, str] = {}
    progress_by_id: dict[str, float] = {}
    for segment_id, total_jobs in segment_job_totals.items():
        completed_jobs = completed_jobs_by_segment.get(segment_id, 0)
        if segment_id == active_segment_id:
            status_by_id[segment_id] = status
        elif completed_jobs >= total_jobs > 0:
            status_by_id[segment_id] = "completed"
        elif completed_jobs > 0:
            status_by_id[segment_id] = "processing"
        else:
            status_by_id[segment_id] = "pending"
        progress_by_id[segment_id] = 0.0 if total_jobs <= 0 else min(completed_jobs / total_jobs, 1.0)
    return status_by_id, progress_by_id, str(active_segment_id), active_segment_title


def _is_toc_dominant_payload(*, payload: Any) -> bool:
    return bool(getattr(payload, "toc_dominant", False))


def _should_route_toc_through_llm(*, context: Any, payload: Any) -> bool:
    return context.processing_operation == "translate" and _is_toc_dominant_payload(payload=payload)


def _resolve_block_prompt_variant(*, context: Any, payload: Any) -> str:
    if _should_route_toc_through_llm(context=context, payload=payload):
        return "toc_translate"
    return "default"


def _build_system_prompt_arguments(*, context: Any, prompt_variant: str) -> dict[str, Any]:
    # Spec 064 FR-001: the document context goes to the loader as ``document_context_prompt``
    # and is rendered in its own section; ``source_text`` stays the term scanner's input. Until
    # 064 both were folded into ``source_text``, which the template never renders.
    from docxaicorrector.pipeline.support import build_system_prompt_arguments

    return build_system_prompt_arguments(context=context, prompt_variant=prompt_variant)


def _build_block_segment_focus_prompt(*, context: Any, initialization: Any, index: int) -> str:
    if getattr(context, "processing_operation", "") != "translate":
        return ""

    segment_ids_by_job = tuple(getattr(initialization, "segment_ids_by_job", ()) or ())
    if not segment_ids_by_job or index <= 0:
        return ""

    active_segment_index = min(index - 1, len(segment_ids_by_job) - 1)
    active_segment_id = segment_ids_by_job[active_segment_index]
    if active_segment_id is None:
        return ""

    ordered_segments = [
        segment
        for segment in list(getattr(context, "document_segments", ()) or ())
        if str(getattr(segment, "segment_id", "") or "").strip()
    ]
    if not ordered_segments:
        return ""

    ordered_segment_ids = [str(getattr(segment, "segment_id", "") or "").strip() for segment in ordered_segments]
    try:
        segment_position = ordered_segment_ids.index(str(active_segment_id))
    except ValueError:
        return ""

    active_segment = ordered_segments[segment_position]
    segment_titles_by_id = dict(getattr(initialization, "segment_titles_by_id", {}) or {})
    active_title = str(
        getattr(active_segment, "title", "") or segment_titles_by_id.get(str(active_segment_id), active_segment_id)
    ).strip()
    if not active_title:
        return ""

    active_level = max(1, int(getattr(active_segment, "level", 1) or 1))
    active_ordinal = max(1, int(getattr(active_segment, "ordinal", segment_position + 1) or (segment_position + 1)))
    active_role = str(getattr(active_segment, "structural_role", "body_range") or "body_range").strip() or "body_range"

    lines = [f"- Текущий сегмент: #{active_ordinal} | L{active_level} | {active_role} | {active_title}"]

    if segment_position > 0:
        previous_title = str(getattr(ordered_segments[segment_position - 1], "title", "") or "").strip()
        if previous_title:
            lines.append(f"- Предыдущий сегмент: {previous_title}")
    if segment_position + 1 < len(ordered_segments):
        next_title = str(getattr(ordered_segments[segment_position + 1], "title", "") or "").strip()
        if next_title:
            lines.append(f"- Следующий сегмент: {next_title}")

    return "ТЕКУЩИЙ БЛОК ДОКУМЕНТА:\n" + "\n".join(lines)


def _resolve_job_segment_id(*, initialization: Any, index: int) -> str | None:
    segment_ids_by_job = tuple(getattr(initialization, "segment_ids_by_job", ()) or ())
    if not segment_ids_by_job or index <= 0 or index > len(segment_ids_by_job):
        return None
    segment_id = segment_ids_by_job[index - 1]
    return str(segment_id).strip() if isinstance(segment_id, str) and str(segment_id).strip() else None


def _mark_segment_progress_after_completed_block(*, state: Any, initialization: Any, index: int, processed_chunk: str) -> None:
    segment_id = _resolve_job_segment_id(initialization=initialization, index=index)
    if not segment_id:
        return

    state.segment_outputs.setdefault(segment_id, []).append(str(processed_chunk or ""))

    segment_ids_by_job = tuple(getattr(initialization, "segment_ids_by_job", ()) or ())
    next_segment_id = None
    if index < len(segment_ids_by_job):
        raw_next_segment_id = segment_ids_by_job[index]
        if isinstance(raw_next_segment_id, str) and str(raw_next_segment_id).strip():
            next_segment_id = str(raw_next_segment_id).strip()
    if next_segment_id != segment_id:
        state.completed_segment_ids.add(segment_id)


def _build_previous_completed_segment_summary_prompt(*, context: Any, state: Any, initialization: Any, index: int) -> str:
    if getattr(context, "processing_operation", "") != "translate":
        return ""

    current_segment_id = _resolve_job_segment_id(initialization=initialization, index=index)
    if not current_segment_id:
        return ""

    ordered_segments = [
        segment
        for segment in list(getattr(context, "document_segments", ()) or ())
        if str(getattr(segment, "segment_id", "") or "").strip()
    ]
    if not ordered_segments:
        return ""

    ordered_segment_ids = [str(getattr(segment, "segment_id", "") or "").strip() for segment in ordered_segments]
    try:
        current_segment_position = ordered_segment_ids.index(current_segment_id)
    except ValueError:
        return ""

    previous_completed_segment = None
    for previous_position in range(current_segment_position - 1, -1, -1):
        candidate_segment = ordered_segments[previous_position]
        candidate_segment_id = str(getattr(candidate_segment, "segment_id", "") or "").strip()
        if not candidate_segment_id:
            continue
        if candidate_segment_id not in set(getattr(state, "completed_segment_ids", set()) or set()):
            continue
        candidate_outputs = list(getattr(state, "segment_outputs", {}).get(candidate_segment_id, []) or [])
        if not candidate_outputs:
            continue
        previous_completed_segment = (candidate_segment, candidate_outputs)
        break

    if previous_completed_segment is None:
        return ""

    segment, outputs = previous_completed_segment
    segment_title = str(getattr(segment, "title", "") or "").strip() or str(getattr(segment, "segment_id", "") or "").strip()
    summary_text = " ".join(part.strip() for part in outputs if str(part or "").strip())
    summary_text = " ".join(summary_text.split())
    if not summary_text:
        return ""
    summary_excerpt = summary_text[:280].rstrip()
    if len(summary_text) > 280:
        summary_excerpt += "..."
    return (
        "СВОДКА ПРЕДЫДУЩЕГО ЗАВЕРШЁННОГО СЕГМЕНТА:\n"
        f"- Сегмент: {segment_title}\n"
        f"- Краткое содержание текущего перевода: {summary_excerpt}"
    )


def _combine_system_prompt_with_block_focus(*, system_prompt: str, block_focus_prompt: str) -> str:
    base_prompt = str(system_prompt or "").strip()
    focus_prompt = str(block_focus_prompt or "").strip()
    if not focus_prompt:
        return base_prompt
    if not base_prompt:
        return focus_prompt
    return f"{base_prompt}\n\n{focus_prompt}"


def _get_cached_system_prompt(*, context: Any, dependencies: Any, state: Any, resolve_system_prompt_fn: Any, prompt_variant: str) -> str:
    if prompt_variant == LITERARY_POLISH_PROMPT_VARIANT:
        # Spec 069 FR-004 (2): the second pass's prompt has a cache entry of its own and the
        # same loader arguments as the first pass -- operation ``translate``, so the document
        # context and the run glossary are in it (``support.build_system_prompt_arguments``).
        cached = getattr(state, "polish_system_prompt", None)
        if cached is None:
            cached = resolve_system_prompt_fn(
                dependencies.load_system_prompt,
                **_build_system_prompt_arguments(context=context, prompt_variant=LITERARY_POLISH_PROMPT_VARIANT),
            )
            state.polish_system_prompt = cached
        return cached

    if prompt_variant == "toc_translate":
        if state.toc_system_prompt is None:
            state.toc_system_prompt = resolve_system_prompt_fn(
                dependencies.load_system_prompt,
                **_build_system_prompt_arguments(context=context, prompt_variant="toc_translate"),
            )
        return state.toc_system_prompt

    if state.system_prompt is None:
        state.system_prompt = resolve_system_prompt_fn(
            dependencies.load_system_prompt,
            **_build_system_prompt_arguments(context=context, prompt_variant="default"),
        )
    return state.system_prompt


def _build_toc_retry_system_prompt(*, system_prompt: str, source_language: str, target_language: str) -> str:
    return (
        f"{system_prompt}\n\n"
        "TOC retry hardening.\n"
        f"Translate each input paragraph from {source_language} to {target_language} as a table-of-contents entry, not as prose.\n"
        "Keep one output paragraph for each input paragraph.\n"
        "Preserve ordering, numbering, Roman numerals, and page-reference-like suffixes.\n"
        "Do not leave the TOC header or substantive entries unchanged unless they are proper names or acronyms."
    )


def _generate_block_chunk(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    marker_mode_enabled: bool,
    system_prompt: str,
) -> str:
    client = initialization.text_client or initialization.client
    model_id = context.model_id or initialization.text_model_id or context.model
    block_system_prompt = _combine_system_prompt_with_block_focus(
        system_prompt=system_prompt,
        block_focus_prompt="\n\n".join(
            part
            for part in (
                _build_block_segment_focus_prompt(
                    context=context,
                    initialization=initialization,
                    index=index,
                ),
                _build_previous_completed_segment_summary_prompt(
                    context=context,
                    state=state,
                    initialization=initialization,
                    index=index,
                ),
                # Spec 063 FR-011: the block's back-matter paragraphs and the D1 rule.
                _build_block_apparatus_prompt(
                    context=context,
                    payload=payload,
                    marker_mode_enabled=marker_mode_enabled,
                ),
            )
            if part
        ),
    )
    # Spec 069 FR-003: a ``standard`` / ``quality`` translate run gives every first-pass block
    # call its pass's profile (reasoning level, model multiplier). ``single``, ``edit`` and
    # ``audiobook`` pass no keyword at all, so their request is the one of before (SC-006).
    request_profile = first_pass_request_profile(context)
    profile_kwargs: dict[str, Any] = {} if request_profile is None else {"request_profile": request_profile}
    return dependencies.generate_markdown_block(
        client=client,
        model=model_id,
        system_prompt=block_system_prompt,
        target_text=payload.target_text_with_markers if marker_mode_enabled else payload.target_text,
        context_before=payload.context_before,
        context_after=payload.context_after,
        max_retries=context.max_retries,
        expected_paragraph_ids=payload.paragraph_ids if marker_mode_enabled else None,
        marker_mode=marker_mode_enabled,
        # Names the block in the rejected-attempt capture (spec 056 D'). The generator has
        # no other way to say WHICH block an artifact under ``.run/marker_attempts/``
        # belongs to, and without that the record cannot be matched to the run log.
        block_index=index,
        # Spec 061 FR-022: the same Stop the block loop checks between blocks, asked before
        # every model call inside this block's retries and ladder as well.
        should_stop=lambda: bool(dependencies.should_stop_processing(context.runtime)),
        # Spec 065 FR-005: a translation of a short paragraph has a bounded length, so an
        # answer many times longer took in a neighbour's text. Only the translate job says
        # so; an audiobook answer is told to spell abbreviations out.
        detect_short_source_absorption=_is_translate_job(context),
        **profile_kwargs,
    )


def _validate_toc_chunk_with_retries(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    marker_mode_enabled: bool,
    resolve_system_prompt_fn: Any,
) -> str:
    prompt_variant = _resolve_block_prompt_variant(context=context, payload=payload)
    retry_budget = TOC_VALIDATION_RETRY_BUDGET
    rejection_reasons: list[str] = []

    for attempt in range(retry_budget + 1):
        base_prompt = _get_cached_system_prompt(
            context=context,
            dependencies=dependencies,
            state=state,
            resolve_system_prompt_fn=resolve_system_prompt_fn,
            prompt_variant=prompt_variant,
        )
        system_prompt = (
            _build_toc_retry_system_prompt(
                system_prompt=base_prompt,
                source_language=context.source_language,
                target_language=context.target_language,
            )
            if attempt == TOC_RETRY_HARDENING_ATTEMPT
            else base_prompt
        )
        dependencies.log_event(
            logging.INFO,
            "toc_prompt_routing_selected",
            "Для блока выбран TOC-ориентированный prompt path.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            prompt_variant=prompt_variant,
            retry_attempt=attempt,
            toc_paragraph_count=getattr(payload, "toc_paragraph_count", 0),
            paragraph_count=getattr(payload, "paragraph_count", 0),
            structural_roles=list(getattr(payload, "structural_roles", []) or []),
        )
        processed_chunk = _generate_block_chunk(
            context=context,
            dependencies=dependencies,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            marker_mode_enabled=marker_mode_enabled,
            system_prompt=system_prompt,
        )
        validation_result = validate_translated_toc_block(
            source_text=payload.target_text,
            processed_chunk=processed_chunk,
            structural_roles=getattr(payload, "structural_roles", None),
            source_language=context.source_language,
            target_language=context.target_language,
        )
        if validation_result.is_valid:
            return processed_chunk

        dependencies.log_event(
            logging.WARNING,
            "toc_validation_rejected",
            "TOC-блок отклонён deterministic validation и будет перегенерирован или завершится ошибкой.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            prompt_variant=prompt_variant,
            retry_attempt=attempt,
            rejection_reason=validation_result.reason,
            toc_paragraph_count=getattr(payload, "toc_paragraph_count", 0),
            paragraph_count=getattr(payload, "paragraph_count", 0),
            structural_roles=list(getattr(payload, "structural_roles", []) or []),
            input_preview=payload.target_text[:300],
            output_preview=processed_chunk[:300],
        )
        rejection_reasons.append(str(validation_result.reason or "unknown"))
        if attempt >= retry_budget:
            raise RuntimeError(
                "toc_language_validation_failed:"
                f"{validation_result.reason};attempt={attempt};history={'|'.join(rejection_reasons)}"
            )
        prompt_variant = "toc_translate"

    raise RuntimeError("toc_language_validation_failed:retry_budget_exhausted;attempt=2;history=retry_budget_exhausted")


def build_processed_paragraph_registry_entries(
    *,
    block_index: int,
    paragraph_ids: list[str] | tuple[str, ...],
    processed_chunk: str,
) -> list[dict[str, object]]:
    """Map this block's paragraph ids onto the text that will ship for each of them.

    Spec 056 E: when the generator hands back a block that REMEMBERS what happened to each
    paragraph, use that instead of re-splitting the joined string. Re-splitting on ``\\n\\n``
    can only recover the text — never the reason it is there — so a paragraph the model
    returned nothing for was indistinguishable from one it translated, and the only way to
    express the difference was to throw the whole block away.

    The fallback path is unchanged and stays reachable: a plain string (passthrough blocks,
    controlled fallbacks, every test double that returns text) is split exactly as before,
    and the paragraph-count mismatch is still fatal.
    """

    dispositions = marker_paragraph_dispositions(processed_chunk)
    if dispositions is not None:
        found_ids = [disposition.paragraph_id for disposition in dispositions]
        if found_ids != list(paragraph_ids):
            raise RuntimeError(
                f"paragraph_marker_registry_mismatch:block={block_index}:expected={len(paragraph_ids)}:actual={len(found_ids)}"
            )
        # The record describes THIS text or it describes nothing. A string operation that
        # kept the subclass but changed the characters would otherwise leave every
        # paragraph's status attached to text it no longer belongs to, and the paragraph
        # count would still match — the same shape of silence that put source-language text
        # into the narration under a green classification.
        if "\n\n".join(disposition.text for disposition in dispositions) != str(processed_chunk):
            raise RuntimeError(
                f"paragraph_marker_registry_record_desynchronised:block={block_index}:paragraphs={len(found_ids)}"
            )
        return [
            {
                "block_index": block_index,
                "paragraph_id": disposition.paragraph_id,
                "text": disposition.text,
                # Carried on the paragraph so the narration projection and the run report
                # can both see it; ``accepted`` is written out too, so the field's absence
                # means "this entry predates the disposition", not "everything was fine".
                "paragraph_status": disposition.status,
            }
            for disposition in dispositions
        ]

    paragraph_chunks = [chunk.strip() for chunk in processed_chunk.split("\n\n") if chunk.strip()]
    if len(paragraph_chunks) != len(paragraph_ids):
        raise RuntimeError(
            f"paragraph_marker_registry_mismatch:block={block_index}:expected={len(paragraph_ids)}:actual={len(paragraph_chunks)}"
        )
    return [
        {
            "block_index": block_index,
            "paragraph_id": paragraph_id,
            "text": paragraph_chunk,
        }
        for paragraph_id, paragraph_chunk in zip(paragraph_ids, paragraph_chunks)
    ]


def excluded_narration_paragraph_records(processed_chunk: str) -> list[dict[str, str]]:
    """One ``{paragraph_id, text}`` record per paragraph of a block kept OUT of the narration.

    The address half of the audio warning, built at the point of the decision for the same
    reason ``_delivered_prose_paragraph_records`` is: only here is it known that this block
    was headed for the narration at all. Re-deriving the set at finalization would sweep in
    the blocks the DOCUMENT layer excluded (59 of 338 on the recorded 20260809T_059_audio_money
    run) and report them as an audio loss.

    A block with no per-paragraph record still yields ONE record carrying the whole block —
    it is the block that was excluded, and the sanitiser downstream decides whether that text
    gives a searchable fragment. An empty ``paragraph_id`` is a paragraph nothing else can
    name, never a paragraph that can be silently matched against another message's ids.
    """
    dispositions = marker_paragraph_dispositions(processed_chunk)
    if dispositions is None:
        return [{"paragraph_id": "", "text": str(processed_chunk)}]
    return [
        {"paragraph_id": str(disposition.paragraph_id), "text": disposition.text}
        for disposition in dispositions
    ]


def narration_projection_for_processed_block(
    processed_chunk: str,
    *,
    processing_operation: Any,
) -> tuple[str, list[dict[str, str]]]:
    """What of this block is READ ALOUD, and what was left out doing it.

    Spec 056 E: a paragraph the model returned nothing for keeps its own SOURCE text in the
    document — losing it there would break the paragraph-per-marker mapping the formatting
    restorer depends on, and a human editing a DOCX can see and fix an untranslated line.
    Nothing sits between the audio and the listener, so the narration drops it instead.
    That is spec 054's rule applied one level down: source-language text does not reach the
    narration artifact, and the DOCX/narration asymmetry is deliberate.

    Returns the narratable text together with a RECORD of every withheld paragraph rather
    than a pair of counters. The counters are still published — spec 054's own metric is a
    share of source-language characters in the artifact, and a rule that subtracts from the
    artifact and reports only "1 paragraph" cannot be compared against the metric it serves;
    on block 174 of the 2026-08-04 run that one line stood for 1 378 characters — but they
    are now derived from the records at the call site, so the quantity on the screen and the
    addresses under it can never describe two different sets of paragraphs. The recorded
    20260809T_059_audio_money run is why: it published "8 paragraphs, 4 455 characters" and
    no address at all.

    A block with no per-paragraph record is returned untouched with nothing withheld, so
    passthrough blocks and controlled fallbacks whose substrate is a plain string behave
    exactly as before.

    WHICH paragraphs are withheld is decided by the OPERATION, not by the status alone
    (spec 061 FR-006/007). Both ``omitted`` and ``source_restored`` mean the same thing about
    the text — it is the paragraph's own SOURCE — and in an operation that changes the
    language (``core.models.LANGUAGE_CHANGING_OPERATIONS``) that is source-language text,
    which a listener must not hear under either label. Until 2026-11-06 only ``omitted`` was
    withheld and ``source_restored`` was spoken; on ``20260809T_059_audio_money`` that read
    two English paragraphs (587 characters, target-alphabet share 0.000) into a Russian
    audiobook. On ``edit`` the source IS in the target language, so a restored paragraph is
    a real paragraph of the book and is spoken, as before; ``omitted`` stays withheld on
    every operation, as before. ``accepted`` is always spoken.

    ``processing_operation`` has no default for the reason ``job_changes_language`` gives:
    a default is a guess that fails silently in one of the two directions. The record
    carries the status so the notice built from it can tell the two causes apart.
    """

    dispositions = marker_paragraph_dispositions(processed_chunk)
    if dispositions is None:
        return processed_chunk, []
    withheld_statuses = (
        {PARAGRAPH_STATUS_OMITTED, PARAGRAPH_STATUS_SOURCE_RESTORED}
        if str(processing_operation or "").strip().casefold() in LANGUAGE_CHANGING_OPERATIONS
        else {PARAGRAPH_STATUS_OMITTED}
    )
    spoken: list[str] = []
    withheld: list[dict[str, str]] = []
    for disposition in dispositions:
        # Spec 063 FR-011: a reference-list entry kept in the source language by policy is
        # apparatus by region -- never read aloud, and not an audio LOSS either (spec 054
        # never narrates the back matter), so it is neither spoken nor booked as withheld.
        if disposition.status == PARAGRAPH_STATUS_POLICY_KEPT_SOURCE:
            continue
        if disposition.status in withheld_statuses:
            withheld.append(
                {
                    "paragraph_id": str(disposition.paragraph_id),
                    "text": disposition.text,
                    "status": str(disposition.status),
                }
            )
            continue
        if disposition.text.strip():
            spoken.append(disposition.text)
    return "\n\n".join(spoken), withheld


def narration_text_for_processed_block(processed_chunk: str, *, processing_operation: Any) -> str:
    """The narratable text alone. See ``narration_projection_for_processed_block``."""

    return narration_projection_for_processed_block(
        processed_chunk, processing_operation=processing_operation
    )[0]


def _record_narration_omitted_paragraphs(state: Any, withheld: Sequence[Mapping[str, str]]) -> None:
    """Book the per-paragraph audio loss ONCE, for both call sites.

    The count, the characters and the addresses come from the same list, so the warning
    cannot say "8 paragraphs" while pointing at a different set. Written as one function
    because the two branches that withhold paragraphs (the ordinary path and the controlled
    fallback beside it) drifted apart once already: the fallback path had no per-paragraph
    filter at all, and the block it delivered was read aloud in English.
    """
    if not withheld:
        return
    state.narration_excluded_omitted_paragraph_count += len(withheld)
    state.narration_excluded_omitted_chars += sum(len(record["text"]) for record in withheld)
    recorded = getattr(state, "narration_excluded_omitted_paragraphs", None)
    if isinstance(recorded, list):
        recorded.extend(dict(record) for record in withheld)


def emit_block_started(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    initialization: Any,
    index: int,
    payload: Any,
) -> None:
    segment_status_by_id, segment_progress_by_id, active_segment_id, active_segment_title = _resolve_segment_status_payload(
        initialization=initialization,
        index=index,
        status="processing",
    )
    emitters.emit_status(
        context.runtime,
        stage="Подготовка блока",
        detail=(
            f"Готовлю блок {index} из {initialization.job_count} к отправке в модель."
            if payload.job_kind == "llm"
            else f"Готовлю passthrough-блок {index} из {initialization.job_count} без вызова модели."
        ),
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        segment_status_by_id=segment_status_by_id,
        segment_progress_by_id=segment_progress_by_id,
        active_segment_id=active_segment_id,
        active_segment_title=active_segment_title,
        progress=(index - 1) / initialization.job_count,
        is_running=True,
    )
    dependencies.log_event(
        logging.DEBUG,
        "block_started",
        "Начата обработка блока",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        model=context.model,
        model_selector=context.model_selector or context.model,
        canonical_model_selector=context.canonical_model_selector or context.model,
        model_provider=context.model_provider,
        model_id=context.model_id or context.model,
        job_kind=payload.job_kind,
    )


def execute_processing_block(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    is_marker_mode_enabled_fn: Any,
    resolve_system_prompt_fn: Any,
) -> tuple[str, bool]:
    if payload.job_kind == "passthrough" and not _should_route_toc_through_llm(context=context, payload=payload):
        emitters.emit_status(
            context.runtime,
            stage="Passthrough блока",
            detail=f"Блок {index} не требует LLM-обработки и будет перенесён в Markdown как есть.",
            current_block=index,
            block_count=initialization.job_count,
            target_chars=payload.target_chars,
            context_chars=payload.context_chars,
            progress=(index - 1) / initialization.job_count,
            is_running=True,
        )
        context.on_progress(preview_title="Текущий Markdown")
        return payload.target_text, False

    marker_mode_enabled = is_marker_mode_enabled_fn(context, payload)
    emitters.emit_status(
        context.runtime,
        stage="Ожидание ответа модели",
        detail=f"Блок {index} отправлен в модель. Приложение работает, ожидаю ответ.",
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        progress=(index - 1) / initialization.job_count,
        is_running=True,
    )
    context.on_progress(preview_title="Текущий Markdown")
    if _should_route_toc_through_llm(context=context, payload=payload):
        processed_chunk = _validate_toc_chunk_with_retries(
            context=context,
            dependencies=dependencies,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            marker_mode_enabled=marker_mode_enabled,
            resolve_system_prompt_fn=resolve_system_prompt_fn,
        )
    else:
        system_prompt = _get_cached_system_prompt(
            context=context,
            dependencies=dependencies,
            state=state,
            resolve_system_prompt_fn=resolve_system_prompt_fn,
            prompt_variant="default",
        )
        processed_chunk = _generate_block_chunk(
            context=context,
            dependencies=dependencies,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            marker_mode_enabled=marker_mode_enabled,
            system_prompt=system_prompt,
        )
    return processed_chunk, marker_mode_enabled


def append_marker_registry_entries(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    build_processed_paragraph_registry_entries_fn: Any,
) -> None:
    paragraph_ids = payload.paragraph_ids or []
    state.generated_paragraph_registry.extend(
        build_processed_paragraph_registry_entries_fn(
            block_index=index,
            paragraph_ids=paragraph_ids,
            processed_chunk=processed_chunk,
        )
    )
    dependencies.log_event(
        logging.DEBUG,
        "block_marker_registry_built",
        "Для блока собран marker-aware paragraph registry.",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        paragraph_count=len(paragraph_ids),
    )


def append_controlled_fallback_registry_entries(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    rejection_kind: str,
    append_marker_registry_entries_fn: Any,
    narration_excluded: bool = False,
) -> None:
    if payload.job_kind != "llm" or not payload.paragraph_ids:
        return

    before_count = len(state.generated_paragraph_registry)
    append_marker_registry_entries_fn(
        context=context,
        dependencies=dependencies,
        state=state,
        initialization=initialization,
        index=index,
        payload=payload,
        processed_chunk=processed_chunk,
    )
    for entry in state.generated_paragraph_registry[before_count:]:
        entry["controlled_fallback"] = True
        entry["controlled_fallback_kind"] = rejection_kind
        # Carried on the paragraph, not only in ``state.narration_chunks``, because the
        # reader-cleanup projection (``narration_postprocess._project_final_cleanup_narration_chunks``)
        # rebuilds the narration from the FINAL registry rather than from those chunks. Without
        # this flag the optional ElevenLabs post-pass on a cleaned translate run would narrate
        # the untranslated source the standalone operation drops — the two entry points must
        # behave the same (spec 054 anti-regression 3).
        entry["controlled_fallback_narration_excluded"] = narration_excluded


def emit_block_completed(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    current_markdown_fn: Any,
) -> None:
    _mark_segment_progress_after_completed_block(
        state=state,
        initialization=initialization,
        index=index,
        processed_chunk=processed_chunk,
    )
    segment_status_by_id, segment_progress_by_id, active_segment_id, active_segment_title = _resolve_segment_status_payload(
        initialization=initialization,
        index=index,
        status="completed",
    )
    emitters.emit_state(
        context.runtime,
        processed_block_markdowns=state.processed_chunks.copy(),
        latest_markdown=current_markdown_fn(state.processed_chunks),
        processed_paragraph_registry=state.generated_paragraph_registry.copy(),
    )
    emitters.emit_log(
        context.runtime,
        status="OK",
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        details=f"готово за {time.perf_counter() - state.started_at:.1f} сек. с начала запуска",
    )
    persist_terminal_job_result(
        context=context,
        dependencies=dependencies,
        index=index,
        status="completed",
    )
    emitters.emit_status(
        context.runtime,
        stage="Блок обработан",
        detail=f"Получен ответ для блока {index}. Обновляю промежуточный Markdown.",
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        segment_status_by_id=segment_status_by_id,
        segment_progress_by_id=segment_progress_by_id,
        active_segment_id=active_segment_id,
        active_segment_title=active_segment_title,
        progress=index / initialization.job_count,
        is_running=True,
    )
    output_chars = len(processed_chunk)
    output_ratio = round(output_chars / max(payload.target_chars, 1), 2)
    dependencies.log_event(
        logging.DEBUG,
        "block_completed",
        "Блок обработан успешно",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        output_chars=output_chars,
        output_ratio=output_ratio,
        input_preview=payload.target_text[:300],
        output_preview=processed_chunk[:300],
        job_kind=payload.job_kind,
    )
    context.on_progress(preview_title="Текущий Markdown")


def _delivered_prose_paragraph_records(
    *, payload: Any, processed_chunk: str
) -> list[dict[str, str]]:
    """One record per PROSE paragraph of a block delivered in the source language.

    The address half of the warning. ``quality_gate.build_source_text_delivery_facts`` sees
    paragraphs through the delivered block's per-paragraph record
    (``generation.marker_paragraph_dispositions``), and on THIS class of delivery that record
    says ``accepted`` for every paragraph — the model did answer, its answer was simply its
    own input — so the alarm channel saw nothing at all. That is the same silence part B was
    built to end, one level down: the recorded run 20260809T_059_doc_value delivered 48 blocks
    and 8 828 characters of source text while the channel reported one paragraph, and
    20260809T_059_doc_money delivered 9 characters and the channel said nothing whatsoever.

    The record is built HERE rather than re-derived at finalization because only here are the
    block's payload (which paragraph is prose) and its delivered text in the same scope.

    ``text`` is the paragraph's own delivered text when the block carries a per-paragraph
    record, and EMPTY when it does not (a non-marker block, or a fallback that shipped
    ``payload.target_text`` as one string). Empty is not a gap in the count: the paragraph is
    still counted, it is simply reported without a searchable fragment, because an address
    that was guessed is worse than none (anti-regression #14).
    """
    indexes = prose_paragraph_indexes(payload)
    if not indexes:
        return []
    paragraph_ids = getattr(payload, "paragraph_ids", None)
    id_list = paragraph_ids if isinstance(paragraph_ids, list) else []
    dispositions = marker_paragraph_dispositions(processed_chunk)
    text_by_paragraph_id = (
        {}
        if dispositions is None
        else {str(disposition.paragraph_id): disposition.text for disposition in dispositions}
    )
    records: list[dict[str, str]] = []
    for position, index in enumerate(indexes):
        paragraph_id = str(id_list[index]) if index < len(id_list) else f"#{position}"
        records.append(
            {
                "paragraph_id": paragraph_id,
                "text": str(text_by_paragraph_id.get(paragraph_id, "")),
            }
        )
    return records


def _announce_untranslated_prose_delivery(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    rejection_kind: str,
) -> None:
    """Everything the block's delivery owes the reader, in one place (spec 059 FR-A8).

    Three consumers, one decision (``classify_processed_block_failure_decision``): the run
    counter, the log line, and the per-paragraph record the alarm channel turns into anchors.
    The acceptance verdict reads the counter, so the screen goes red without this module
    knowing anything about the screen.

    WARNING, not ERROR. The level used to be ERROR and the justification written beside it
    was "the decision is ``fail``: there will be no run, and that is a visible distinguishable
    state". That justification expired with the decision. The run now completes and delivers,
    which is the same level of severity the block's twin event ``block_controlled_fallback``
    carries — and a log whose level says "the run died" beside a run that succeeded teaches
    the next reader to distrust the levels.
    """
    records = _delivered_prose_paragraph_records(payload=payload, processed_chunk=processed_chunk)
    existing = getattr(state, "untranslated_prose_delivered_paragraphs", None)
    if isinstance(existing, list):
        existing.append(records)
    record_untranslated_prose_block_delivery(kind=rejection_kind, chars=len(processed_chunk))
    paragraph_regions = list(getattr(payload, "paragraph_regions", None) or ())
    dependencies.log_event(
        logging.WARNING,
        "block_untranslated_prose_delivered",
        "Блок доставлен с прозой на языке источника; см. приёмочный вердикт и якоря для поиска.",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        rejection_kind=rejection_kind,
        delivered_chars=len(processed_chunk),
        paragraph_count=len(paragraph_regions),
        prose_paragraph_count=len(records),
        anchored_paragraph_count=sum(1 for record in records if record["text"].strip()),
        source_language=str(getattr(context, "source_language", "") or ""),
        target_language=str(getattr(context, "target_language", "") or ""),
        input_preview=payload.target_text[:300],
    )


def continue_controlled_processed_block_rejection(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    rejection_kind: str,
    append_marker_registry_entries_fn: Any,
    languages_differ: bool = True,
    untranslated_prose_delivered: bool = False,
) -> None:
    # Run-level accounting for the pipeline half of the loss. Until this call the ONLY
    # trace a ``fallback_continue`` left was a per-block diagnostic under ``.run/`` and a
    # log line — nothing a run report could add up — so how often
    # ``english_residual_output``, ``heading_only_output`` or ``toc_body_concat``
    # substituted text was unknowable after the fact, and the run-level discard numbers
    # (fed only by ``generation/_generation.py``) were a LOWER bound nobody labelled as one.
    # This is the single choke point of the branch: ``process_single_block`` calls it only
    # for decision ``fallback_continue``, so a structural ``fail`` can never land here.
    # ``processed_chunk`` is what the block actually delivered (the caller passes
    # ``rejection_decision["fallback_markdown"]``), which is the text whose length is the
    # cost — the same quantity and the same unit as
    # ``state.narration_excluded_source_fallback_chars`` below.
    record_controlled_block_fallback(kind=rejection_kind, chars=len(processed_chunk))
    _record_back_matter_delivery(
        context=context,
        dependencies=dependencies,
        initialization=initialization,
        index=index,
        payload=payload,
        processed_chunk=processed_chunk,
        kept_by_policy=False,
    )
    if untranslated_prose_delivered:
        _announce_untranslated_prose_delivery(
            context=context,
            dependencies=dependencies,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            processed_chunk=processed_chunk,
            rejection_kind=rejection_kind,
        )
    artifact_path = _write_controlled_block_fallback_artifact(
        context=context,
        initialization=initialization,
        index=index,
        rejection_kind=rejection_kind,
        target_text=payload.target_text,
        processed_chunk=processed_chunk,
    )
    state.processed_chunks.append(processed_chunk)
    # The narration artifact carries only speakable text in the TARGET language, so a block
    # whose model output was rejected and replaced by its own SOURCE text does not go into
    # it. The asymmetry against the DOCX is deliberate: the document is editable and a human
    # who meets an untranslated paragraph fixes it, while nothing sits between the audio and
    # the listener — on the 2026-08-04 Money & Sustainability run six such blocks put 20 597
    # characters of English into the middle of a Russian audiobook. Taking the model's
    # rejected output instead was considered and refused: the rejection means the model may
    # have LOST a paragraph, which would trade a visible defect for an unverifiable one.
    # The decision belongs here, not in ``_resolve_narration_include``, because only here is
    # the block's outcome known.
    #
    # Spec 059 FR-A9. The branch below appends NOTHING: the text is discarded, not skipped —
    # 5 581 characters of the 2026-08-06 Money & Sustainability run left the audiobook this
    # way. Two things changed, and neither of them is "narrate the source anyway":
    #
    # * ``languages_differ`` now guards it (FR-A5). "The delivery equals its source" only
    #   means "untranslated" where the job asked for another language. On the recorded ru->ru
    #   literary edit 1 144 of 1 761 deliveries are byte-identical to their source and every
    #   one is correct, so without this guard the branch would have thrown two thirds of that
    #   book out of the narration.
    # * PROSE can no longer reach the branch at all, because the invariant in
    #   ``untranslated_prose_would_be_delivered`` turns exactly this situation into ``fail``
    #   before the block gets here. What still reaches it is a block that is entirely
    #   APPARATUS and was delivered in the source language, and keeping that out of the
    #   audiobook is spec 054's decision, not a hole.
    narration_excluded_by_source_fallback = False
    if not payload.narration_include:
        state.excluded_narration_block_count += 1
    elif languages_differ and fallback_delivered_source_text(
        payload=payload, processed_chunk=processed_chunk
    ):
        narration_excluded_by_source_fallback = True
        state.narration_excluded_source_fallback_block_count += 1
        state.narration_excluded_source_fallback_chars += len(processed_chunk)
        # The block is counted in BLOCKS and addressed in PARAGRAPHS: the reader searches the
        # DOCX for a passage, not for a block index. Same records, same sanitiser, same floor
        # as the per-paragraph twin below and as the document warning.
        excluded_source_fallback_paragraphs = getattr(
            state, "narration_excluded_source_fallback_paragraphs", None
        )
        if isinstance(excluded_source_fallback_paragraphs, list):
            excluded_source_fallback_paragraphs.extend(
                excluded_narration_paragraph_records(processed_chunk)
            )
    else:
        # The per-paragraph filter belongs HERE too, and its absence was a hole: a block
        # holding an ``omitted`` paragraph keeps that paragraph's SOURCE text, which makes
        # the block likelier to be classified ``english_residual_output`` — and the rejection
        # then routed it down this path, which appended the raw chunk and read the English
        # aloud. The defect fed itself: the substitution caused the classification that
        # bypassed the filter that would have removed the substitution.
        narratable_text, withheld_paragraphs = narration_projection_for_processed_block(
            processed_chunk, processing_operation=getattr(context, "processing_operation", None)
        )
        _record_narration_omitted_paragraphs(state, withheld_paragraphs)
        if narratable_text.strip():
            state.narration_chunks.append(narratable_text)
    try:
        append_controlled_fallback_registry_entries(
            context=context,
            dependencies=dependencies,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            processed_chunk=processed_chunk,
            rejection_kind=rejection_kind,
            append_marker_registry_entries_fn=append_marker_registry_entries_fn,
            narration_excluded=narration_excluded_by_source_fallback,
        )
    except Exception as exc:
        dependencies.log_event(
            logging.WARNING,
            "controlled_fallback_registry_build_failed",
            "Не удалось собрать marker registry для controlled fallback блока.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            rejection_kind=rejection_kind,
            error_message=str(exc),
        )
    persist_terminal_job_result(
        context=context,
        dependencies=dependencies,
        index=index,
        status="controlled_fallback",
        error_code=rejection_kind,
        error_message="Controlled fallback retained rejected block output for full-document assembly.",
    )
    segment_status_by_id, segment_progress_by_id, active_segment_id, active_segment_title = _resolve_segment_status_payload(
        initialization=initialization,
        index=index,
        status="completed_with_fallback",
    )
    latest_markdown = "\n\n".join(state.processed_chunks).strip()
    emitters.emit_state(
        context.runtime,
        processed_block_markdowns=state.processed_chunks.copy(),
        latest_markdown=latest_markdown,
        processed_paragraph_registry=state.generated_paragraph_registry.copy(),
        latest_controlled_block_fallback_artifact=artifact_path,
    )
    emitters.emit_status(
        context.runtime,
        stage="Блок сохранён с предупреждением",
        detail=f"Блок {index} сохранён как controlled fallback: {rejection_kind}.",
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        segment_status_by_id=segment_status_by_id,
        segment_progress_by_id=segment_progress_by_id,
        active_segment_id=active_segment_id,
        active_segment_title=active_segment_title,
        progress=index / initialization.job_count,
        is_running=True,
    )
    emitters.emit_log(
        context.runtime,
        status="WARN",
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        details=f"controlled_fallback:{rejection_kind}",
    )
    dependencies.log_event(
        logging.WARNING,
        "block_controlled_fallback",
        "Блок сохранён с controlled fallback после quality rejection.",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        output_classification=rejection_kind,
        artifact_path=artifact_path,
        narration_excluded_by_source_fallback=narration_excluded_by_source_fallback,
        input_preview=payload.target_text[:300],
        output_preview=processed_chunk[:300],
    )
    context.on_progress(preview_title="Текущий Markdown")


def _announce_policy_kept_source_block(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
) -> None:
    """Say on the screen and in the log that a block was kept by policy, not translated.

    INFO, not WARNING: this is the decided outcome of D1, not a defect -- the fallback's
    WARNING twin (``block_controlled_fallback``) is for blocks that were supposed to be
    translated and were not.
    """
    emitters.emit_status(
        context.runtime,
        stage="Список литературы",
        detail=(
            f"Блок {index}: записи списка литературы остаются на языке оригинала "
            "(политика справочного аппарата), без вызова модели."
        ),
        current_block=index,
        block_count=initialization.job_count,
        target_chars=payload.target_chars,
        context_chars=payload.context_chars,
        progress=(index - 1) / initialization.job_count,
        is_running=True,
    )
    dependencies.log_event(
        logging.INFO,
        "block_apparatus_policy_kept_source",
        "Блок списка литературы доставлен на языке оригинала по политике аппарата, без вызова модели.",
        filename=context.uploaded_filename,
        block_index=index,
        block_count=initialization.job_count,
        back_matter_section=str(getattr(payload, "back_matter_section", "") or ""),
        paragraph_count=len(getattr(payload, "paragraph_ids", None) or ()),
        delivered_chars=len(processed_chunk),
    )


def _announce_model_kept_apparatus(
    *,
    context: Any,
    dependencies: Any,
    initialization: Any,
    index: int,
    payload: Any,
    model_kept: ModelKeptApparatus,
    replaced_fallback: bool,
) -> None:
    """Spec 064 FR-006: one INFO line per block whose references the model kept.

    INFO, like its twin ``block_apparatus_policy_kept_source``: this is the outcome rule 12
    asked for, not a defect. ``replaced_fallback`` says the pair rule had read the block as a
    ``source_text_fallback`` -- the number of controlled fallbacks this rule took off the
    screen, counted here rather than inferred later.

    Spec 067 FR-004: a heading kept as a NAME is not apparatus and gets its own INFO line,
    ``block_name_kept_by_model``, carrying the reason ``name_kept``; the apparatus line is
    written only when references were kept, so neither line describes the other's paragraphs.
    """
    apparatus_paragraph_count = model_kept.paragraph_count - model_kept.name_kept_paragraph_count
    if apparatus_paragraph_count > 0:
        dependencies.log_event(
            logging.INFO,
            "block_apparatus_kept_by_model",
            "Ссылки справочного аппарата оставлены моделью на языке оригинала по правилу 12; это не controlled fallback.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            back_matter_section=str(getattr(payload, "back_matter_section", "") or ""),
            paragraph_count=len(getattr(payload, "paragraph_ids", None) or ()),
            kept_paragraph_count=apparatus_paragraph_count,
            notes_in_body_paragraph_count=model_kept.notes_in_body_paragraph_count,
            whole_block=model_kept.whole_block,
            replaced_fallback=replaced_fallback,
        )
    if model_kept.name_kept_paragraph_count > 0:
        dependencies.log_event(
            logging.INFO,
            "block_name_kept_by_model",
            "Заголовок-имя оставлен моделью как есть; это имя, а не непереведённый текст и не controlled fallback.",
            filename=context.uploaded_filename,
            block_index=index,
            block_count=initialization.job_count,
            reason=POLICY_KEPT_REASON_NAME_KEPT,
            paragraph_count=len(getattr(payload, "paragraph_ids", None) or ()),
            kept_paragraph_count=model_kept.name_kept_paragraph_count,
            whole_block=model_kept.whole_block,
            replaced_fallback=replaced_fallback,
        )


def run_literary_polish_for_block(
    *,
    context: Any,
    dependencies: Any,
    state: Any,
    initialization: Any,
    index: int,
    payload: Any,
    processed_chunk: str,
    resolve_system_prompt_fn: Any = _resolve_system_prompt_default,
) -> str:
    """The production ``literary_polish_fn``: the second pass with the run's cached prompt.

    Returns what the block delivers -- the polished record where accepted, otherwise the first
    pass unchanged (``pipeline/literary_polish.py``). Never raises for a model failure; a Stop
    during the pass sets ``state.stopped_during_polish`` and returns the first pass.
    """

    return polish_block(
        context=context,
        dependencies=dependencies,
        state=state,
        initialization=initialization,
        index=index,
        payload=payload,
        processed_chunk=processed_chunk,
        system_prompt_fn=lambda: _get_cached_system_prompt(
            context=context,
            dependencies=dependencies,
            state=state,
            resolve_system_prompt_fn=resolve_system_prompt_fn,
            prompt_variant=LITERARY_POLISH_PROMPT_VARIANT,
        ),
    ).processed_chunk


def process_single_block(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    index: int,
    job: Any,
    parse_processing_job_fn: Any,
    handle_invalid_processing_job_fn: Any,
    emit_block_started_fn: Any,
    is_marker_mode_enabled_fn: Any,
    execute_processing_block_fn: Any,
    handle_block_generation_failure_fn: Any,
    classify_processed_block_fn: Any,
    handle_processed_block_rejection_fn: Any,
    append_marker_registry_entries_fn: Any,
    handle_marker_registry_failure_fn: Any,
    emit_block_completed_fn: Any,
    literary_polish_fn: Any = None,
) -> PipelineResult | None:
    try:
        payload = parse_processing_job_fn(job=job)
    except (KeyError, TypeError, ValueError) as exc:
        return handle_invalid_processing_job_fn(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            index=index,
            exc=exc,
        )

    emit_block_started_fn(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        initialization=initialization,
        index=index,
        payload=payload,
    )
    marker_mode_enabled = is_marker_mode_enabled_fn(context, payload)
    # Spec 063 FR-011: a block of reference-list entries is delivered as its own source with no
    # model call. Decided ONCE, here, so the classifier skip below reads the same answer.
    policy_kept_chunk = policy_kept_source_chunk(
        context=context, payload=payload, marker_mode_enabled=marker_mode_enabled
    )
    if policy_kept_chunk is not None:
        processed_chunk = policy_kept_chunk
        _announce_policy_kept_source_block(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            initialization=initialization,
            index=index,
            payload=payload,
            processed_chunk=processed_chunk,
        )
    else:
        try:
            processed_chunk, marker_mode_enabled = execute_processing_block_fn(
                context=context,
                dependencies=dependencies,
                emitters=emitters,
                state=state,
                initialization=initialization,
                index=index,
                payload=payload,
            )
        except Exception as exc:
            return handle_block_generation_failure_fn(
                context=context,
                dependencies=dependencies,
                emitters=emitters,
                state=state,
                initialization=initialization,
                index=index,
                payload=payload,
                marker_mode_enabled=marker_mode_enabled,
                exc=exc,
            )

    # A genuine passthrough block is emitted as the VERBATIM source markdown (no LLM call), so
    # the LLM-output-quality classifier (heading_only_output / untranslated / ...) must not gate
    # it — doing so produced hard failures and EMPTY DOCX for passthrough-heavy real documents
    # (round-5 finding 1). TOC blocks routed through the LLM are genuinely processed and stay
    # classified as before.
    is_genuine_passthrough = (
        payload.job_kind == "passthrough" and not _should_route_toc_through_llm(context=context, payload=payload)
    ) or policy_kept_chunk is not None
    # Spec 059 FR-A5: the pair rule is only a completeness signal where the job changes the
    # language, and that is read off the run, not off the text.
    languages_differ = job_changes_language(
        processing_operation=getattr(context, "processing_operation", None),
        source_language=getattr(context, "source_language", None),
        target_language=getattr(context, "target_language", None),
    )
    if is_genuine_passthrough:
        processed_block_status = "valid"
    else:
        processed_block_status = classify_processed_block_fn(
            payload.target_text,
            processed_chunk,
            languages_differ=languages_differ,
        )
    # Spec 069 FR-004 (3): the literary polish pass. HERE -- after the first pass was accepted
    # and before the apparatus relabel, footnote restoration, the registry, the narration
    # projection and the back-matter accounting below -- so every one of them reads the text
    # that ships. A passthrough, a block kept by policy, a TOC block and any block whose first
    # pass is not ``valid`` are never sent.
    if (
        processed_block_status == "valid"
        and not is_genuine_passthrough
        and not _is_toc_dominant_payload(payload=payload)
        and literary_polish_applies(context=context, initialization=initialization)
    ):
        processed_chunk = (literary_polish_fn or run_literary_polish_for_block)(
            context=context,
            dependencies=dependencies,
            state=state,
            initialization=initialization,
            index=index,
            payload=payload,
            processed_chunk=processed_chunk,
        )
    # Spec 064 FR-006: references the model kept under prompt rule 12 are apparatus by region.
    # A valid block keeps its translated paragraphs and relabels the kept references; a
    # ``source_text_fallback`` stops being one only when EVERY paragraph is such a reference.
    model_kept = None
    if not is_genuine_passthrough and processed_block_status in {"valid", "source_text_fallback"}:
        model_kept = model_kept_apparatus(context=context, payload=payload, processed_chunk=processed_chunk)
        if model_kept is not None and processed_block_status == "source_text_fallback" and not model_kept.whole_block:
            model_kept = None
    model_kept_replaced_fallback = model_kept is not None and processed_block_status == "source_text_fallback"
    if model_kept is not None:
        processed_chunk = model_kept.processed_chunk
        processed_block_status = "valid"
        _announce_model_kept_apparatus(
            context=context,
            dependencies=dependencies,
            initialization=initialization,
            index=index,
            payload=payload,
            model_kept=model_kept,
            replaced_fallback=model_kept_replaced_fallback,
        )
    if processed_block_status != "valid":
        rejection_decision = classify_processed_block_failure_decision(
            rejection_kind=processed_block_status,
            payload=payload,
            processed_chunk=processed_chunk,
            build_processed_paragraph_registry_entries_fn=build_processed_paragraph_registry_entries,
            languages_differ=languages_differ,
        )
        if rejection_decision["decision"] == "fallback_continue":
            continue_controlled_processed_block_rejection(
                context=context,
                dependencies=dependencies,
                emitters=emitters,
                state=state,
                initialization=initialization,
                index=index,
                payload=payload,
                processed_chunk=rejection_decision["fallback_markdown"],
                rejection_kind=rejection_decision["fallback_kind"],
                append_marker_registry_entries_fn=append_marker_registry_entries_fn,
                languages_differ=languages_differ,
                # Spec 059 FR-A8, revised 2026-08-09: the block ships either way; this says
                # whether its delivery has to be announced. Read off the decision rather than
                # re-derived, so one evaluation of the rule feeds every consumer.
                untranslated_prose_delivered=(
                    rejection_decision.get(UNTRANSLATED_PROSE_WARNING_KEY)
                    == UNTRANSLATED_PROSE_WARNING_REASON
                ),
            )
            return None
        return handle_processed_block_rejection_fn(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            initialization=initialization,
            index=index,
            target_chars=payload.target_chars,
            context_chars=payload.context_chars,
            target_text=payload.target_text,
            processed_chunk=processed_chunk,
            rejection_kind=processed_block_status,
        )

    # Spec 063 FR-005: a footnote reference the model dropped is put back before the block
    # is committed anywhere, so the DOCX, the registry and the preview all carry it.
    processed_chunk = preserve_footnote_markers_for_block(
        processed_chunk=processed_chunk,
        payload=payload,
        processing_operation=getattr(context, "processing_operation", None),
        block_index=index,
        log_event=getattr(dependencies, "log_event", None),
        filename=getattr(context, "uploaded_filename", None),
    )
    state.processed_chunks.append(processed_chunk)
    if payload.narration_include:
        # Spec 056 E: the DOCX keeps every paragraph, the narration keeps only the ones the
        # model actually spoke for. Identical to ``processed_chunk`` for every block that
        # carries no per-paragraph record.
        narratable_text, withheld_paragraphs = narration_projection_for_processed_block(
            processed_chunk, processing_operation=getattr(context, "processing_operation", None)
        )
        _record_narration_omitted_paragraphs(state, withheld_paragraphs)
        if narratable_text.strip():
            state.narration_chunks.append(narratable_text)
    else:
        state.excluded_narration_block_count += 1
    if payload.job_kind == "llm" and marker_mode_enabled and payload.paragraph_ids:
        try:
            append_marker_registry_entries_fn(
                context=context,
                dependencies=dependencies,
                state=state,
                initialization=initialization,
                index=index,
                payload=payload,
                processed_chunk=processed_chunk,
            )
        except Exception as exc:
            return handle_marker_registry_failure_fn(
                context=context,
                dependencies=dependencies,
                emitters=emitters,
                state=state,
                initialization=initialization,
                index=index,
                payload=payload,
                processed_chunk=processed_chunk,
                exc=exc,
            )
    _record_back_matter_delivery(
        context=context,
        dependencies=dependencies,
        initialization=initialization,
        index=index,
        payload=payload,
        processed_chunk=processed_chunk,
        kept_by_policy=policy_kept_chunk is not None,
        model_kept_paragraph_count=model_kept.paragraph_count if model_kept is not None else 0,
        model_kept_replaced_fallback=model_kept_replaced_fallback,
    )
    emit_block_completed_fn(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
        index=index,
        payload=payload,
        processed_chunk=processed_chunk,
    )
    return None


def run_block_processing_phase(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    emit_stopped_result_fn: Any,
    process_single_block_fn: Any,
    current_markdown_fn: Any,
    emit_failed_result_fn: Any,
) -> PipelineResult | None:
    def _emit_stopped(index: int) -> PipelineResult | None:
        stop_message = "Обработка остановлена пользователем."
        return emit_stopped_result_fn(
            emitters=emitters,
            runtime=context.runtime,
            detail=stop_message,
            progress=(index - 1) / initialization.job_count,
            block_index=max(0, index - 1),
            block_count=initialization.job_count,
        )

    try:
        return _run_block_loop(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            emit_stopped=_emit_stopped,
            process_single_block_fn=process_single_block_fn,
            current_markdown_fn=current_markdown_fn,
            emit_failed_result_fn=emit_failed_result_fn,
        )
    finally:
        # Spec 069 FR-004 (6): the second pass's run totals, once, however the phase ended.
        try:
            emit_literary_polish_completed(
                context=context, dependencies=dependencies, state=state, initialization=initialization
            )
        except Exception:  # pragma: no cover - a report must never change the run's outcome
            pass


def _run_block_loop(
    *,
    context: Any,
    dependencies: Any,
    emitters: Any,
    state: Any,
    initialization: Any,
    emit_stopped: Any,
    process_single_block_fn: Any,
    current_markdown_fn: Any,
    emit_failed_result_fn: Any,
) -> PipelineResult | None:
    _emit_stopped = emit_stopped
    for index, job in enumerate(context.jobs, start=1):
        if dependencies.should_stop_processing(context.runtime):
            return _emit_stopped(index)

        try:
            block_outcome = process_single_block_fn(
                context=context,
                dependencies=dependencies,
                emitters=emitters,
                state=state,
                initialization=initialization,
                index=index,
                job=job,
            )
        except LatePhaseStopped:
            # Spec 061 FR-022: Stop pressed while this block was still retrying. The
            # generator refused the next model call; the block is not delivered, and the
            # run stops exactly as if Stop had been seen before the block began.
            return _emit_stopped(index)
        if block_outcome is not None:
            return block_outcome
        if getattr(state, "stopped_during_polish", False):
            # Spec 069 FR-004 (5): Stop came during this block's SECOND pass. Unlike the case
            # above the block IS delivered (its first pass), so the run stops after it -- and
            # this check is the only one left when it was the last block.
            return _emit_stopped(index + 1)

    if len(state.processed_chunks) != initialization.job_count:
        critical_message = dependencies.present_error(
            "processed_block_count_mismatch",
            RuntimeError("Количество обработанных блоков не совпало с планом обработки."),
            "Критическая ошибка финализации",
            filename=context.uploaded_filename,
            processed_count=len(state.processed_chunks),
            planned_count=initialization.job_count,
            incomplete_count=max(initialization.job_count - len(state.processed_chunks), 0),
        )
        emitters.emit_state(
            context.runtime,
            last_error=critical_message,
            latest_docx_bytes=None,
            latest_narration_text=None,
        )
        return emit_failed_result_fn(
            emitters=emitters,
            runtime=context.runtime,
            finalize_stage="Критическая ошибка",
            detail=critical_message,
            progress=len(state.processed_chunks) / max(initialization.job_count, 1),
            block_index=len(state.processed_chunks),
            block_count=initialization.job_count,
            target_chars=len(current_markdown_fn(state.processed_chunks)),
            context_chars=0,
            log_details=critical_message,
        )

    return None
