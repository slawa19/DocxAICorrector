"""Characterization safety net for ``validation/structural.py`` (spec 034, Step 0).

Snapshots the behaviour of the pure leaf clusters that spec 034 relocates out of the
~3110-line ``validation/structural.py`` orchestration module into focused
``validation/structural_*.py`` modules. The goldens live under
``tests/fixtures/structural_validation_characterization/`` and MUST stay byte-identical
across every behaviour-preserving decomposition step of spec 034.

Coverage:

* **Cluster E (unit alignment, untested in isolation):** ``_derive_unit_aware_unmapped_fields``
  over legacy + topology-unit payloads, plus the compact trace captured from
  ``_emit_target_alignment_trace_artifact`` (``write_formatting_diagnostics_artifact`` is
  stubbed to capture the diagnostics payload instead of writing an artifact to disk).
* **Cluster D (TOC/body-concat signals):** ``_derive_toc_body_concat_gate_fields`` and
  ``has_toc_body_concat_structure`` over legacy-markdown and topology-projection fixtures.
* **Orchestrator prep snapshot:** ``build_preparation_diagnostic_snapshot`` over a fixed
  paragraph set with ``build_semantic_blocks`` stubbed (the lighter of the two spec-034
  orchestrator-golden variants -- reproducing the full ``run_structural_passthrough_validation``
  stub harness offline is unnecessarily heavy for a pure-refactor safety net).

All inputs are built fully offline and deterministically; the module constructs no SDK
client and touches no network.

To regenerate the goldens after an intentional, reviewed behaviour change, run::

    UPDATE_STRUCTURAL_GOLDEN=1 <run this test>
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import docxaicorrector.validation.structural as structural

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "structural_validation_characterization"
_UPDATE = os.environ.get("UPDATE_STRUCTURAL_GOLDEN") == "1"


def _canonical(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def _assert_golden(name: str, obj: object) -> None:
    path = _FIXTURE_DIR / f"{name}.json"
    serialized = _canonical(obj)
    if _UPDATE:
        _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding="utf-8")
        return
    assert path.exists(), f"missing golden fixture: {path} (run UPDATE_STRUCTURAL_GOLDEN=1)"
    expected = path.read_text(encoding="utf-8")
    assert serialized == expected, f"golden diff for {name}"


# --------------------------------------------------------------------------- #
# Fixture builders
# --------------------------------------------------------------------------- #


def _source_paragraphs() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(paragraph_id="p0001", logical_index=0, source_index=0),
        SimpleNamespace(paragraph_id="p0002", logical_index=1, source_index=1),
        SimpleNamespace(paragraph_id="p0003", logical_index=2, source_index=2),
    ]


def _unit(unit_id: str, logical_indexes: tuple[int, ...]) -> SimpleNamespace:
    return SimpleNamespace(
        unit_id=unit_id,
        logical_indexes=logical_indexes,
        role="body",
        unit_type="body",
        authority="document_map_v2",
        confidence="high",
    )


def _unit_alignment_projection() -> SimpleNamespace:
    return SimpleNamespace(
        projected_units=[
            _unit("u1", (0,)),
            _unit("u2", (1,)),
            _unit("u3", (2,)),
        ],
        operations=[SimpleNamespace(op="split_compound_toc_entries", authority="document_map_v2", confidence="high")],
    )


def _unit_alignment_payload() -> dict[str, object]:
    return {
        "unmapped_source_ids": ["p0002"],
        "unmapped_target_indexes": [5],
        "accepted_aggregated_sources": [{"paragraph_id": "p0001", "target_index": 3}],
        "source_registry": [
            {"paragraph_id": "p0001", "mapped_target_index": 3, "relation_ids": []},
            {"paragraph_id": "p0002", "mapped_target_index": -1, "relation_ids": []},
            {"paragraph_id": "p0003", "mapped_target_index": -1, "relation_ids": []},
        ],
        "target_registry": [
            {"target_index": 3, "mapped": True, "text_preview": "Introduction heading"},
            {"target_index": 5, "mapped": False, "text_preview": "Body paragraph three"},
        ],
    }


def _generated_registry() -> list[dict[str, object]]:
    return [
        {"paragraph_id": "p0001", "text": "Introduction heading"},
        {"paragraph_id": "p0003", "text": "Body paragraph three"},
    ]


# --------------------------------------------------------------------------- #
# Cluster E: _derive_unit_aware_unmapped_fields
# --------------------------------------------------------------------------- #


def test_derive_unit_aware_unmapped_fields_legacy_golden():
    fields = structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=_source_paragraphs(),
        topology_projection=None,
        formatting_payload=_unit_alignment_payload(),
        generated_paragraph_registry=None,
    )
    _assert_golden("cluster_e_unmapped_fields_legacy", fields)


def test_derive_unit_aware_unmapped_fields_none_payload_golden():
    fields = structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=_source_paragraphs(),
        topology_projection=_unit_alignment_projection(),
        formatting_payload=None,
        generated_paragraph_registry=None,
    )
    _assert_golden("cluster_e_unmapped_fields_none_payload", fields)


def test_derive_unit_aware_unmapped_fields_topology_golden():
    fields = structural._derive_unit_aware_unmapped_fields(
        source_paragraphs=_source_paragraphs(),
        topology_projection=_unit_alignment_projection(),
        formatting_payload=_unit_alignment_payload(),
        generated_paragraph_registry=_generated_registry(),
    )
    _assert_golden("cluster_e_unmapped_fields_topology", fields)


# --------------------------------------------------------------------------- #
# Cluster E: _emit_target_alignment_trace_artifact (captured diagnostics payload)
# --------------------------------------------------------------------------- #


def test_emit_target_alignment_trace_artifact_golden(monkeypatch):
    captured: dict[str, object] = {}

    def _capture(*, stage, filename_prefix, diagnostics, scope):
        captured["stage"] = stage
        captured["filename_prefix"] = filename_prefix
        captured["diagnostics"] = diagnostics
        captured["scope"] = scope
        return "/tmp/owned-offline-trace.json"

    monkeypatch.setattr(structural, "write_formatting_diagnostics_artifact", _capture)

    artifact_path = structural._emit_target_alignment_trace_artifact(
        source_paragraphs=_source_paragraphs(),
        topology_projection=_unit_alignment_projection(),
        formatting_payload=_unit_alignment_payload(),
        generated_paragraph_registry=_generated_registry(),
    )

    assert captured, "write_formatting_diagnostics_artifact was not called"
    assert artifact_path == "/tmp/owned-offline-trace.json"
    assert captured.pop("scope") == "offline"
    _assert_golden("cluster_e_target_alignment_trace", captured)


# --------------------------------------------------------------------------- #
# Cluster D: _derive_toc_body_concat_gate_fields + has_toc_body_concat_structure
# --------------------------------------------------------------------------- #


def _toc_body_concat_projection() -> SimpleNamespace:
    return SimpleNamespace(
        projected_units=[
            SimpleNamespace(
                unit_id="t1", role="toc_entry", unit_type="toc_entry", logical_indexes=(4,),
                authority="document_map_v2", confidence="high",
            ),
            SimpleNamespace(
                unit_id="h1", role="heading", unit_type="chapter_heading", logical_indexes=(4,),
                authority="document_map_v2", confidence="high",
            ),
            SimpleNamespace(
                unit_id="t2", role="toc_entry", unit_type="toc_entry", logical_indexes=(2,),
                authority="document_map_v2", confidence="high",
            ),
        ],
        operations=[
            SimpleNamespace(op="split_compound_toc_entries", authority="document_map_v2", confidence="high"),
            SimpleNamespace(op="merge_heading_continuation", authority="document_map_v2", confidence="high"),
        ],
    )


def _bounded_document_map() -> SimpleNamespace:
    return SimpleNamespace(
        toc_region=SimpleNamespace(confidence="high", start_logical_index=0, end_logical_index=6),
        split_hints=[
            SimpleNamespace(
                split_kind="compound_toc_entries", confidence="high", logical_index=2,
                expected_parts=["Part A", "Part B"],
            )
        ],
    )


def test_derive_toc_body_concat_gate_fields_topology_golden():
    fields = structural._derive_toc_body_concat_gate_fields(
        document_map=_bounded_document_map(),
        topology_projection=_toc_body_concat_projection(),
        markdown_detected=False,
    )
    _assert_golden("cluster_d_gate_fields_topology", fields)


def test_derive_toc_body_concat_gate_fields_legacy_markdown_golden():
    # No document map -> projection unsupported -> legacy-markdown gate source.
    fields = structural._derive_toc_body_concat_gate_fields(
        document_map=None,
        topology_projection=_toc_body_concat_projection(),
        markdown_detected=True,
    )
    _assert_golden("cluster_d_gate_fields_legacy_markdown", fields)


def test_has_toc_body_concat_structure_golden():
    results = {
        "concat_present": structural.has_toc_body_concat_structure(_toc_body_concat_projection()),
        "none_projection": structural.has_toc_body_concat_structure(None),
        "empty_units": structural.has_toc_body_concat_structure(SimpleNamespace(projected_units=[])),
    }
    _assert_golden("cluster_d_has_toc_body_concat_structure", results)


# --------------------------------------------------------------------------- #
# Orchestrator: build_preparation_diagnostic_snapshot (build_semantic_blocks stubbed)
# --------------------------------------------------------------------------- #


def _snapshot_paragraphs() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(text="Contents", role="body", structural_role="toc_header"),
        SimpleNamespace(text="Chapter 1 ........ 12", role="body", structural_role="toc_entry"),
        SimpleNamespace(text="Introduction", role="heading", structural_role="body", heading_level=1),
        SimpleNamespace(text="Body paragraph.", role="body", structural_role="body"),
    ]


def _snapshot_event_log() -> list[dict[str, object]]:
    return [
        {
            "event_id": "structure_processing_outcome",
            "context": {
                "readiness_status": "ready",
                "readiness_reasons": ["structure_recognized"],
                "document_map_present": True,
                "outline_coverage_ratio": 0.75,
                "quality_gate_status": "passed",
                "quality_gate_reasons": [],
                "structure_ai_attempted": True,
                "ai_classified_count": 4,
                "ai_heading_count": 1,
                "document_map_status": "built",
                "document_topology_projection_status": "built",
            },
        }
    ]


def test_build_preparation_diagnostic_snapshot_golden(monkeypatch):
    monkeypatch.setattr(
        structural,
        "build_semantic_blocks",
        lambda paragraphs, max_chars, relations=None: [SimpleNamespace(paragraphs=list(paragraphs))],
    )

    structure_repair_report = SimpleNamespace(
        bounded_toc_regions=1,
        repaired_bullet_items=2,
        repaired_numbered_items=3,
        toc_body_boundary_repairs=1,
        remaining_isolated_marker_count=0,
    )

    snapshot = structural.build_preparation_diagnostic_snapshot(
        paragraphs=_snapshot_paragraphs(),
        relations=None,
        structure_repair_report=structure_repair_report,
        chunk_size=6000,
        event_log=_snapshot_event_log(),
    )
    _assert_golden("orchestrator_prep_snapshot", snapshot)
