import json
from pathlib import Path

from models import ParagraphUnit
import structure_validation
from structure_validation import StructureValidationReport, validate_structure_quality


def _paragraph(
    index: int,
    text: str,
    *,
    role: str = "body",
    structural_role: str = "body",
    heading_source: str | None = None,
    paragraph_alignment: str | None = None,
    list_kind: str | None = None,
    attached_to_asset_id: str | None = None,
) -> ParagraphUnit:
    return ParagraphUnit(
        text=text,
        role=role,
        structural_role=structural_role,
        heading_source=heading_source,
        paragraph_alignment=paragraph_alignment,
        list_kind=list_kind,
        attached_to_asset_id=attached_to_asset_id,
        source_index=index,
    )


def _config(**overrides):
    base = {
        "structure_validation_toc_like_sequence_min_length": 4,
        "structure_validation_min_paragraphs_for_auto_gate": 40,
        "structure_validation_min_explicit_heading_density": 0.003,
        "structure_validation_max_suspicious_short_body_ratio_without_escalation": 0.05,
        "structure_validation_max_all_caps_or_centered_body_ratio_without_escalation": 0.03,
        "structure_validation_forbid_heading_only_collapse": True,
    }
    base.update(overrides)
    return base


def test_validate_structure_quality_does_not_escalate_low_risk_document():
    paragraphs = [
        _paragraph(0, "Chapter 1", role="heading", heading_source="explicit"),
        _paragraph(1, "This is a long enough body paragraph with many ordinary words and extra context."),
        _paragraph(2, "Another ordinary body paragraph with stable narrative structure and additional detail here."),
    ]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert report.escalation_recommended is False
    assert report.escalation_reasons == ()
    assert report.readiness_status == "ready"


def test_validate_structure_quality_triggers_on_low_explicit_heading_density():
    paragraphs = [_paragraph(index, f"Body paragraph number {index} with plain text.") for index in range(50)]

    report = validate_structure_quality(
        paragraphs=paragraphs,
        app_config=_config(structure_validation_min_explicit_heading_density=0.1),
    )

    assert report.escalation_recommended is True
    assert "low_explicit_heading_density" in report.escalation_reasons


def test_validate_structure_quality_triggers_on_suspicious_short_body_ratio():
    paragraphs = [_paragraph(index, f"Section {index}") for index in range(10)]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert report.escalation_recommended is True
    assert "high_suspicious_short_body_ratio" in report.escalation_reasons


def test_validate_structure_quality_triggers_on_all_caps_or_centered_body_ratio():
    paragraphs = [
        _paragraph(0, "INTRODUCTION", paragraph_alignment="center"),
        _paragraph(1, "CHAPTER ONE"),
        _paragraph(2, "Regular body paragraph with enough words to be ordinary."),
    ]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert report.escalation_recommended is True
    assert "high_all_caps_or_centered_body_ratio" in report.escalation_reasons


def test_validate_structure_quality_triggers_on_toc_like_region():
    paragraphs = [
        _paragraph(0, "Introduction"),
        _paragraph(1, "Chapter One"),
        _paragraph(2, "Chapter Two"),
        _paragraph(3, "Appendix"),
    ]

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert report.escalation_recommended is True
    assert "toc_like_sequence_detected" in report.escalation_reasons
    assert report.readiness_status == "blocked_needs_structure_repair"


def test_validate_structure_quality_heading_only_collapse_boundary_119_and_3():
    paragraphs = [_paragraph(index, f"Paragraph {index} with enough words to count as body text.") for index in range(119)]
    paragraphs.extend(
        [
            _paragraph(1000, "Heading A", role="heading", heading_source="explicit"),
            _paragraph(1001, "Heading B", role="heading", heading_source="explicit"),
            _paragraph(1002, "Heading C", role="heading", heading_source="explicit"),
        ]
    )

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert "heading_only_collapse_risk" not in report.escalation_reasons


def test_validate_structure_quality_heading_only_collapse_boundary_120_and_2():
    paragraphs = [_paragraph(index, f"Paragraph {index} with enough words to count as body text.") for index in range(120)]
    paragraphs.extend(
        [
            _paragraph(1000, "Heading A", role="heading", heading_source="explicit"),
            _paragraph(1001, "Heading B", role="heading", heading_source="explicit"),
        ]
    )

    report = validate_structure_quality(paragraphs=paragraphs, app_config=_config())

    assert report.escalation_recommended is True
    assert "heading_only_collapse_risk" in report.escalation_reasons


def test_write_structure_validation_debug_artifact_writes_json_payload(tmp_path, monkeypatch):
    diagnostics_dir = tmp_path / ".run" / "structure_validation"
    monkeypatch.setattr(structure_validation, "_STRUCTURE_VALIDATION_DEBUG_DIR", diagnostics_dir)
    report = StructureValidationReport(
        paragraph_count=120,
        nonempty_paragraph_count=118,
        explicit_heading_count=2,
        heuristic_heading_count=5,
        suspicious_short_body_count=9,
        all_caps_body_count=3,
        centered_body_count=1,
        toc_like_sequence_count=1,
        ambiguous_paragraph_count=13,
        explicit_heading_density=0.0169,
        suspicious_short_body_ratio=0.0763,
        all_caps_or_centered_body_ratio=0.0339,
        escalation_recommended=True,
        escalation_reasons=(
            "high_suspicious_short_body_ratio",
            "toc_like_sequence_detected",
        ),
        isolated_marker_paragraph_count=2,
        large_front_matter_block_risk=False,
        toc_region_bounded_count=0,
        expected_heading_candidates_from_toc=4,
        structure_quality_risk_level="high",
        readiness_status="blocked_needs_structure_repair",
        readiness_reasons=("toc_like_sequence_without_bounded_region",),
    )

    artifact_path = structure_validation.write_structure_validation_debug_artifact(
        report=report,
        app_config={
            "structure_recognition_mode": "always",
            "structure_recognition_model": "gpt-5.4",
        },
    )

    artifact_file = Path(artifact_path)
    assert artifact_file.exists()
    assert artifact_file.parent == diagnostics_dir
    assert artifact_file.name.startswith("gate_report_")
    payload = json.loads(artifact_file.read_text(encoding="utf-8"))
    assert payload == {
        "mode": "always",
        "model": "gpt-5.4",
        "paragraph_count": 120,
        "nonempty_paragraph_count": 118,
        "explicit_heading_count": 2,
        "heuristic_heading_count": 5,
        "suspicious_short_body_count": 9,
        "all_caps_body_count": 3,
        "centered_body_count": 1,
        "toc_like_sequence_count": 1,
        "ambiguous_paragraph_count": 13,
        "explicit_heading_density": 0.0169,
        "suspicious_short_body_ratio": 0.0763,
        "all_caps_or_centered_body_ratio": 0.0339,
        "escalation_recommended": True,
        "escalation_reasons": [
            "high_suspicious_short_body_ratio",
            "toc_like_sequence_detected",
        ],
        "isolated_marker_paragraph_count": 2,
        "large_front_matter_block_risk": False,
        "toc_region_bounded_count": 0,
        "expected_heading_candidates_from_toc": 4,
        "structure_quality_risk_level": "high",
        "readiness_status": "blocked_needs_structure_repair",
        "readiness_reasons": ["toc_like_sequence_without_bounded_region"],
        "structure_repair_report": None,
    }
