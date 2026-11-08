"""Spec 063 P2: what the run glossary's extractor finds in a book, and (``--live``) what one call fixes.

Companion to ``specs/063-translation-fidelity/research.md`` (R3, R5) and ``tasks.md`` (T016,
T018, T019). It runs the PRODUCT code — ``select_glossary_source_units`` and
``extract_glossary_candidates`` from ``src/docxaicorrector/text/glossary_pass.py`` — on exactly
the input a ``translate`` run would give it, so a number printed here is the product's number,
not a prototype's.

INPUT (one of)
--------------
``--document-profile <id>`` [``--run-profile <id>``]
    Re-runs the run's own preparation (``prepare_run_context_for_background`` with the run
    profile's resolved config) with a model client that RAISES, then takes ``prepared.jobs`` and
    ``prepared.paragraphs``. No model may be called during preparation; if one is requested the
    script stops instead of spending.
``--paragraphs <dump.json>``
    A dump with ``{"paragraphs": [{paragraph_id, text, role, heading_level, region, in_llm_job}, ...]}`` —
    the shape ``--dump-paragraphs`` writes — so later measurements need no PDF import.

OUTPUT
------
The candidate list (``--out``); with ``--reviewer-terminology <terminology.json>`` (the shape
the 2026-11-07 reviewers wrote: a list of ``{"term": ...}``, ``{"terms": [...]}`` or a mapping
keyed by term) the share of the reviewer's key terms that appear among the candidates, with the
misses named. ``--extra-term`` adds terms named elsewhere (repeatable).

``--live`` (SPENDS MONEY: up to three calls — required, optional, collisions)
    Runs the product call sequence (``pipeline/glossary_phase._call_model``) with the run's
    default text model (or ``--model``), with the product's acceptance rules, and prints
    the entries, ``prompt_tokens``, ``completion_tokens``, the provider's ``cost``, the rendered
    prompt section's characters and the measured characters-per-input-token ratio. Writes the
    result in the ``.run/run_glossaries`` artifact shape to ``--glossary-out``. Never runs a book.

USAGE (WSL)
-----------
    . .venv/bin/activate && export PYTHONPATH="$PWD/src:$PWD"
    python scripts/measure-glossary-candidates.py --document-profile money-sustainability-pdf-full-heldout \\
        --reviewer-terminology /mnt/d/Temp/docxai-runs/2026-11-07-translate/money_sustainability/review/terminology.json \\
        --out /tmp/money.candidates.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from docxaicorrector.text.glossary_pass import (  # noqa: E402
    DEFAULT_GLOSSARY_CANDIDATE_LIMIT,
    DEFAULT_GLOSSARY_MAX_TERMS,
    extract_glossary_candidates,
    normalize_glossary_key,
    select_glossary_source_units,
    split_name_families,
)

DEFAULT_RUN_PROFILE = "ui-parity-translate-benchmark-advisory-image-safe-no-cleanup"
_PARENTHETICAL_RE = re.compile(r"\([^)]*\)")


def _prepare(document_profile_id: str, run_profile_id: str) -> tuple[list[dict[str, Any]], list[Any]]:
    os.chdir(PROJECT_ROOT)
    from docxaicorrector.core.config import load_app_config
    from docxaicorrector.processing.application_flow import prepare_run_context_for_background
    from docxaicorrector.processing.preparation import prepare_document_for_processing
    from docxaicorrector.processing.processing_runtime import freeze_uploaded_file
    from docxaicorrector.validation.profiles import (
        apply_runtime_resolution_to_app_config,
        load_validation_registry,
        resolve_runtime_resolution,
    )
    from docxaicorrector.validation.structural import UploadedFileStub

    registry = load_validation_registry()
    document_profile = registry.get_document_profile(document_profile_id)
    run_profile = registry.resolve_run_profile(document_profile, run_profile_id)
    app_config = load_app_config()
    resolution = resolve_runtime_resolution(app_config, run_profile)
    app_config_dict = apply_runtime_resolution_to_app_config(app_config, resolution)
    source_path = document_profile.resolved_source_path(PROJECT_ROOT)
    requested: list[str] = []

    def _no_client(*args: object, **kwargs: object) -> object:
        requested.append(repr((args, kwargs))[:200])
        raise RuntimeError("measure-glossary-candidates: preparation asked for a model client; refusing to spend")

    payload = freeze_uploaded_file(UploadedFileStub(source_path.name, source_path.read_bytes()))
    prepared = prepare_run_context_for_background(
        uploaded_payload=payload,
        chunk_size=int(resolution.effective.chunk_size),
        image_mode=resolution.effective.image_mode,
        keep_all_image_variants=resolution.effective.keep_all_image_variants,
        processing_operation=resolution.effective.processing_operation,
        app_config=app_config_dict,
        prepare_document_for_processing_fn=lambda **kwargs: prepare_document_for_processing(
            get_client_fn=_no_client,
            client_factory=_no_client,
            client_cache_identity=None,
            **kwargs,
        ),
    )
    if requested:
        raise SystemExit(f"preparation requested a model client: {requested}")
    return [dict(job) for job in prepared.jobs], list(prepared.paragraphs)


def _load_dump(path: Path) -> tuple[list[dict[str, Any]], list[Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    paragraphs = [SimpleNamespace(**record) for record in data["paragraphs"]]
    if isinstance(data.get("jobs"), list):
        # The reviewers' dump shape (the 2026-11-07 runs): the run's own jobs, with their
        # regions, at the top level and no region on the paragraph records. Read per record,
        # every paragraph -- notes and bibliography too -- would count as prose (spec 065).
        return [dict(job) for job in data["jobs"]], paragraphs
    jobs = [
        {
            "job_kind": "llm" if record.get("in_llm_job", True) else "passthrough",
            "paragraph_ids": [record["paragraph_id"]],
            "paragraph_regions": [record.get("region") or "prose"],
        }
        for record in data["paragraphs"]
    ]
    return jobs, paragraphs


def _dump(jobs: list[dict[str, Any]], paragraphs: list[Any], path: Path) -> None:
    region_by_id: dict[str, str] = {}
    llm_ids: set[str] = set()
    for job in jobs:
        ids = [str(item) for item in job.get("paragraph_ids") or []]
        for paragraph_id, region in zip(ids, job.get("paragraph_regions") or []):
            region_by_id[paragraph_id] = str(region)
        if job.get("job_kind") == "llm":
            llm_ids.update(ids)
    # Every field ``select_glossary_source_units`` reads off a paragraph. ``heading_level``
    # was missing (Codex acceptance finding 5): a dump replayed without it has no level-1/2
    # headings, so heading candidates, h1-requiredness and the chapter split all changed.
    # Emphasis and quotes need no field of their own -- the importer bakes them into ``text``.
    records = [
        {
            "paragraph_id": paragraph.paragraph_id,
            "text": paragraph.text,
            "role": paragraph.role,
            "heading_level": getattr(paragraph, "heading_level", None),
            "region": region_by_id.get(paragraph.paragraph_id),
            "in_llm_job": paragraph.paragraph_id in llm_ids,
        }
        for paragraph in paragraphs
    ]
    path.write_text(json.dumps({"paragraphs": records}, ensure_ascii=False), encoding="utf-8")


def _candidate_identity(candidates) -> list[tuple[object, ...]]:
    return [(candidate.source_term, candidate.family, candidate.required) for candidate in candidates]


def _assert_dump_parity(jobs: list[dict[str, Any]], paragraphs: list[Any], path: Path, *, limit: int) -> int:
    """The dump must reproduce the production decision: same candidates, same required set.

    Returns the number of required candidates (for the printout); raises ``SystemExit`` on a
    difference, because a measurement taken off a lossy dump is not the product's number.
    """

    produced = extract_glossary_candidates(select_glossary_source_units(jobs, paragraphs), limit=limit)
    reloaded_jobs, reloaded_paragraphs = _load_dump(path)
    replayed = extract_glossary_candidates(select_glossary_source_units(reloaded_jobs, reloaded_paragraphs), limit=limit)
    if _candidate_identity(produced) != _candidate_identity(replayed):
        produced_ids, replayed_ids = set(_candidate_identity(produced)), set(_candidate_identity(replayed))
        raise SystemExit(
            f"dump parity failed for {path}: only in production {sorted(produced_ids - replayed_ids, key=str)[:10]}, "
            f"only in the dump {sorted(replayed_ids - produced_ids, key=str)[:10]}"
        )
    return sum(1 for candidate in produced if candidate.required)


def _reviewer_terms(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [str(item["term"]) for item in data if isinstance(item, dict) and "term" in item]
    if isinstance(data, dict) and isinstance(data.get("terms"), list):
        return [str(item["term"]) for item in data["terms"] if isinstance(item, dict) and "term" in item]
    if isinstance(data, dict):
        return [str(key) for key in data]
    return []


def _variants(term: str) -> list[str]:
    """A reviewer's label as source spellings: ``A / B`` alternatives, ``(…)`` remarks dropped."""

    label = term.replace("(y|ies)", "y").replace("(s)", "")
    label = _PARENTHETICAL_RE.sub("", label)
    return [variant.strip() for variant in re.split(r"\s*/\s*", label) if variant.strip()]


def _recall(candidates, terms: list[str]) -> tuple[list[str], list[str]]:
    keys = {normalize_glossary_key(candidate.source_term) for candidate in candidates}
    caught, missed = [], []
    for term in terms:
        if any(normalize_glossary_key(variant) in keys for variant in _variants(term)):
            caught.append(term)
        else:
            missed.append(term)
    return caught, missed


def _live_call(
    candidates,
    units,
    *,
    model: str | None,
    max_terms: int,
    prompt_max_chars: int | None,
    source_language: str,
    glossary_out: Path | None,
) -> None:
    """The PRODUCT call sequence (``pipeline/glossary_phase._call_model``): one call, then one
    re-ask for the rule-included terms the answer left out, then rule-included first."""

    from docxaicorrector.core import model_accounting
    from docxaicorrector.core.config import get_client_for_model_selector, load_app_config, resolve_model_selector
    from docxaicorrector.pipeline import glossary_phase

    app_config = load_app_config()
    selector = model or str(app_config["default_model"])
    model_id = resolve_model_selector(selector, "responses_text", source_name="measure-glossary-candidates").model_id
    client = get_client_for_model_selector(selector, "responses_text")
    record: dict[str, object] = {}
    runtime = object()
    with model_accounting.run_model_accounting_scope(run_id="measure-glossary-live", source_token="measure"):
        status, terms = glossary_phase._call_model(
            context=SimpleNamespace(source_language=source_language, target_language="ru", runtime=runtime),
            dependencies=SimpleNamespace(should_stop_processing=lambda _runtime: False),
            emitters=SimpleNamespace(emit_status=lambda *_args, **_kwargs: None),
            initialization=SimpleNamespace(text_client=client, job_count=0),
            model=model_id,
            sent_candidates=tuple(candidates),
            max_terms=max_terms,
            sample_text="\n\n".join(unit.text for unit in units)[:2000],
            record=record,
            request_text_completion_fn=None,
        )
        stage = model_accounting.snapshot_run_model_accounting()["stages"].get("glossary_extraction", {})
    if prompt_max_chars is None:
        prompt_max_chars = glossary_phase.RUN_GLOSSARY_PROMPT_MAX_CHARS
    section = glossary_phase.render_run_glossary_section(terms, tuple(candidates), max_chars=prompt_max_chars)
    prompt_tokens = int(stage.get("prompt_tokens") or 0)
    request_chars = int(record.get("request_chars") or 0)
    rendered = sum(1 for line in section.splitlines() if line.startswith("- ") and line != "- ...")
    print(
        f"live: model={selector} status={status} calls={record.get('model_call_count')} entries={len(terms)} "
        f"required={record.get('required_count')} reasked={record.get('reasked_required_count')} "
        f"unrendered={record.get('unrendered_terms')} rejected={record.get('rejected_counts')}"
    )
    print(
        f"live: collisions_found={record.get('collisions_found')} resolved={record.get('collisions_resolved')} "
        f"remaining={record.get('collisions')} calls={record.get('calls')}"
    )
    print(
        f"live: prompt_tokens={prompt_tokens} completion_tokens={stage.get('completion_tokens')} "
        f"cost_usd={stage.get('cost_usd_reported_by_provider')} first_request_chars={request_chars}"
    )
    print(f"live: prompt_section_chars={len(section)} rendered_terms={rendered} of {len(terms)}")
    for term in terms:
        print(f"  {term.kind:4} {term.source_term} -> {term.target_term}" + (f"  [{term.note}]" if term.note else ""))
    if glossary_out is not None:
        glossary_out.write_text(
            json.dumps(
                {
                    "schema": "run_glossary/v1",
                    "status": status,
                    "model": selector,
                    "candidate_count": len(candidates),
                    "terms": [
                        {"source_term": t.source_term, "target_term": t.target_term, "kind": t.kind, "note": t.note}
                        for t in terms
                    ],
                    "rejected_counts": record.get("rejected_counts"),
                    "required_count": record.get("required_count"),
                    "reasked_required_count": record.get("reasked_required_count"),
                    "unrendered_terms": record.get("unrendered_terms"),
                    "model_call_count": record.get("model_call_count"),
                    "calls": record.get("calls"),
                    "collisions_found": record.get("collisions_found"),
                    "collisions_resolved": record.get("collisions_resolved"),
                    "collisions": record.get("collisions"),
                    "collision_groups_found": record.get("collision_groups_found"),
                    "name_entries": [
                        {"source_term": t.source_term, "target_term": t.target_term} for t in terms if t.kind == "name"
                    ],
                    "rendered_term_count": rendered,
                    "prompt_section_chars": len(section),
                    "request_chars": request_chars,
                    "usage": {
                        "prompt_tokens": stage.get("prompt_tokens"),
                        "completion_tokens": stage.get("completion_tokens"),
                        "cost_usd": stage.get("cost_usd_reported_by_provider"),
                    },
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"live: glossary written to {glossary_out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--document-profile")
    source.add_argument("--paragraphs", type=Path)
    parser.add_argument("--run-profile", default=DEFAULT_RUN_PROFILE)
    parser.add_argument("--dump-paragraphs", type=Path, help="write the prepared paragraphs with regions here")
    parser.add_argument("--limit", type=int, default=DEFAULT_GLOSSARY_CANDIDATE_LIMIT)
    parser.add_argument("--reviewer-terminology", type=Path)
    parser.add_argument("--extra-term", action="append", default=[])
    parser.add_argument("--out", type=Path)
    parser.add_argument("--live", action="store_true", help="SPENDS MONEY: one glossary call")
    parser.add_argument("--model")
    parser.add_argument("--max-terms", type=int, default=DEFAULT_GLOSSARY_MAX_TERMS)
    parser.add_argument("--prompt-max-chars", type=int, help="default: the product's glossary_prompt_max_chars")
    parser.add_argument("--glossary-out", type=Path)
    parser.add_argument("--source-language", default="auto", help="as the run profile sets it; 'auto' is resolved like the product does")
    args = parser.parse_args(argv)

    if args.document_profile:
        jobs, paragraphs = _prepare(args.document_profile, args.run_profile)
    else:
        jobs, paragraphs = _load_dump(args.paragraphs)
    if args.dump_paragraphs:
        _dump(jobs, paragraphs, args.dump_paragraphs)
        required_count = _assert_dump_parity(jobs, paragraphs, args.dump_paragraphs, limit=args.limit)
        print(f"dump parity: candidates and required set reproduced from {args.dump_paragraphs} (required={required_count})")
    units = select_glossary_source_units(jobs, paragraphs)
    candidates = extract_glossary_candidates(units, limit=args.limit)
    families: dict[str, int] = {}
    for candidate in candidates:
        families[candidate.family] = families.get(candidate.family, 0) + 1
    request_chars = sum(len(candidate.source_term) + len(candidate.context) for candidate in candidates)
    print(f"units={len(units)} candidates={len(candidates)} families={families} term+context_chars={request_chars}")
    # Spec 064 FR-009: the required set by route, one-word lowercase entries among them, and the
    # short forms of names that are not asked for (they inherit the full form's rendering).
    required = [candidate for candidate in candidates if candidate.required]
    routes: dict[str, int] = {}
    for candidate in required:
        route = (
            "defined" if "defined" in candidate.signals
            else "family_head" if "family_head" in candidate.signals
            else "heading" if candidate.family == "heading"
            else "marked"
        )
        routes[route] = routes.get(route, 0) + 1
    # Spec 065 FR-002: one lowercase word with no hyphen ("value-based" is a compound).
    single_lowercase = [
        c.source_term for c in required if len(c.key) == 1 and "-" not in c.source_term and c.source_term == c.source_term.lower()
    ]
    _, name_members = split_name_families(candidates)
    print(f"required={len(required)} by_route={routes} single_lowercase={len(single_lowercase)} {single_lowercase}")
    print(
        f"name_family_members={len(name_members)} "
        + str([f"{member.member.source_term} <- {member.head.source_term}" for member in name_members])
    )

    terms: list[str] = []
    if args.reviewer_terminology:
        terms.extend(_reviewer_terms(args.reviewer_terminology))
    terms.extend(args.extra_term)
    if terms:
        caught, missed = _recall(candidates, terms)
        print(f"reviewer terms in candidates: {len(caught)}/{len(terms)}")
        print(f"  missed: {missed}")
    if args.out:
        args.out.write_text(
            json.dumps([candidate.to_payload() for candidate in candidates], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    if args.live:
        _live_call(
            candidates,
            units,
            source_language=args.source_language,
            model=args.model,
            max_terms=args.max_terms,
            prompt_max_chars=args.prompt_max_chars,
            glossary_out=args.glossary_out,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
