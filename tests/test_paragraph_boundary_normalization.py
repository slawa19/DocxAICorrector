from io import BytesIO
import base64
import json
from pathlib import Path

import pytest

import docxaicorrector.core.config as config
import docxaicorrector.document.extraction as document_module
import docxaicorrector.document.boundary_review as boundary_review_module
import docxaicorrector.document.relations as relation_module
from docx import Document as make_document
from docxaicorrector.core.models import (
    ParagraphBoundaryDecision,
    ParagraphBoundaryNormalizationReport,
    ParagraphRelationDecision,
    ParagraphUnit,
    RawParagraph,
    RelationNormalizationReport,
)

from docxaicorrector.document.extraction import (
    build_document_text,
    extract_document_content_with_normalization_reports,
    extract_document_content_with_boundary_report,
)
from docxaicorrector.document.relations import build_paragraph_relations
from docxaicorrector.document.semantic_blocks import build_marker_wrapped_block_text


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK3cAAAAASUVORK5CYII="
)


def _save_document(document) -> BytesIO:
    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer


def test_false_body_boundary_is_merged_into_one_logical_paragraph():
    document = make_document()
    document.add_paragraph("архетипами: повторяющимися моделями")
    document.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert len(paragraphs) == 1
    assert paragraphs[0].text == "архетипами: повторяющимися моделями поведения во времени, наблюдаемыми в разных системах."
    assert paragraphs[0].origin_raw_indexes == [0, 1]
    assert paragraphs[0].origin_raw_texts == [
        "архетипами: повторяющимися моделями",
        "поведения во времени, наблюдаемыми в разных системах.",
    ]
    assert paragraphs[0].boundary_source == "normalized_merge"
    assert report.merged_group_count == 1
    assert report.merged_raw_paragraph_count == 2
    assert build_document_text(paragraphs) == paragraphs[0].text
    assert build_marker_wrapped_block_text(paragraphs) == f"[[DOCX_PARA_{paragraphs[0].paragraph_id}]]\n{paragraphs[0].text}"


def test_terminal_punctuation_preserves_real_paragraph_boundary():
    document = make_document()
    document.add_paragraph("Первый абзац закончен.")
    document.add_paragraph("Второй абзац начинается с новой мысли.")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.text for paragraph in paragraphs] == [
        "Первый абзац закончен.",
        "Второй абзац начинается с новой мысли.",
    ]
    assert report.merged_group_count == 0
    assert report.decisions[0].decision == "keep"
    assert report.decisions[0].confidence == "blocked"


def test_heading_body_boundary_is_never_merged():
    document = make_document()
    document.add_paragraph("Глава 1", style="Heading 1")
    document.add_paragraph("основной текст после заголовка")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["heading", "body"]
    assert report.merged_group_count == 0
    assert report.decisions[0].reasons == ("heading_boundary", "non_body_role", "style_transition")


def test_list_boundary_is_never_merged():
    document = make_document()
    document.add_paragraph("Вступление без финальной точки")
    document.add_paragraph("Первый пункт", style="List Number")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["body", "list"]
    assert report.merged_group_count == 0
    assert "list_metadata" in report.decisions[0].reasons


def test_merged_text_spacing_is_normalized_conservatively():
    document = make_document()
    document.add_paragraph("Это важное")
    document.add_paragraph("продолжение текста")

    paragraphs, _, _ = extract_document_content_with_boundary_report(_save_document(document))

    assert paragraphs[0].text == "Это важное продолжение текста"


def test_dash_led_continuation_after_superscript_note_is_merged():
    document = make_document()
    first = document.add_paragraph()
    first.add_run("Marrow held tolls worth $187 billion")
    note = first.add_run("4")
    note.font.superscript = True
    document.add_paragraph(
        "— roughly the same size as the Keswick harbour that year, which made the toll arrangement especially visible in public debate."
    )

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert len(paragraphs) == 1
    assert paragraphs[0].text == (
        "Marrow held tolls worth $187 billion<sup>4</sup> — roughly the same size as the Keswick harbour "
        "that year, which made the toll arrangement especially visible in public debate."
    )
    assert paragraphs[0].origin_raw_indexes == [0, 1]
    assert paragraphs[0].boundary_source == "normalized_merge"
    assert paragraphs[0].boundary_confidence == "high"
    assert report.decisions[0].decision == "merge"
    assert report.decisions[0].confidence == "high"
    assert "right_starts_continuation" in report.decisions[0].reasons


def test_high_confidence_merge_chain_collapses_three_adjacent_body_paragraphs():
    document = make_document()
    document.add_paragraph("Это особенно важно")
    document.add_paragraph("для устойчивой")
    document.add_paragraph("работы всей системы.")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert len(paragraphs) == 1
    assert paragraphs[0].text == "Это особенно важно для устойчивой работы всей системы."
    assert paragraphs[0].origin_raw_indexes == [0, 1, 2]
    assert paragraphs[0].boundary_source == "normalized_merge"
    assert paragraphs[0].boundary_confidence == "high"
    assert paragraphs[0].boundary_rationale == (
        "same_body_style, compatible_alignment, left_not_terminal, "
        "right_starts_continuation, left_incomplete, combined_sentence_plausible"
    )
    assert report.merged_group_count == 1
    assert report.merged_raw_paragraph_count == 3
    assert [(decision.left_raw_index, decision.right_raw_index, decision.decision, decision.confidence) for decision in report.decisions] == [
        (0, 1, "merge", "high"),
        (1, 2, "merge", "high"),
    ]


def test_high_only_promotes_medium_chain_lead_when_followed_by_mergeable_continuation(monkeypatch):
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": False,
        },
    )
    document = make_document()
    document.add_paragraph("Почему она")
    document.add_paragraph("Чаще всего просто считается")
    document.add_paragraph("менее надёжной версией северной гавани?")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert len(paragraphs) == 1
    assert paragraphs[0].text == "Почему она Чаще всего просто считается менее надёжной версией северной гавани?"
    assert paragraphs[0].origin_raw_indexes == [0, 1, 2]
    assert paragraphs[0].boundary_source == "normalized_merge"
    assert paragraphs[0].boundary_confidence == "medium"
    assert [(decision.left_raw_index, decision.right_raw_index, decision.decision, decision.confidence) for decision in report.decisions] == [
        (0, 1, "merge", "medium"),
        (1, 2, "merge", "high"),
    ]
    assert report.decisions[0].reasons[-1] == "chain_continuation_supported"


def test_toc_like_entries_are_not_merged_by_boundary_normalization():
    document = make_document()
    document.add_paragraph("Contents")
    document.add_paragraph("Meet the Lantern Boundary")
    document.add_paragraph("Why Tide Theory Matters")
    document.add_paragraph("The Structure of the Ledger")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.text for paragraph in paragraphs] == [
        "Contents",
        "Meet the Lantern Boundary",
        "Why Tide Theory Matters",
        "The Structure of the Ledger",
    ]
    assert [paragraph.structural_role for paragraph in paragraphs] == [
        "toc_header",
        "toc_entry",
        "toc_entry",
        "toc_entry",
    ]
    assert report.merged_group_count == 0
    assert report.decisions[1].decision == "keep"
    assert report.decisions[1].confidence == "blocked"
    assert "adjacent_toc_like_entries" in report.decisions[1].reasons


def test_debug_artifact_report_writes_expected_path_and_payload(monkeypatch, tmp_path):
    reports_dir = tmp_path / "paragraph-boundary-reports"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_REPORTS_DIR", reports_dir)
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": True,
        },
    )
    monkeypatch.setattr(document_module, "resolve_uploaded_filename", lambda uploaded_file: "debug sample.docx")

    debug_doc = make_document()
    debug_doc.add_paragraph("архетипами: повторяющимися моделями")
    debug_doc.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")
    uploaded = _save_document(debug_doc)

    paragraphs, _, report = extract_document_content_with_boundary_report(uploaded)

    assert len(paragraphs) == 1
    artifact_files = sorted(reports_dir.glob("*.json"))
    assert len(artifact_files) == 1
    assert artifact_files[0].name.startswith("debug_sample.docx_")

    payload = json.loads(artifact_files[0].read_text(encoding="utf-8"))
    assert payload == {
        "version": 1,
        "source_file": "debug sample.docx",
        "source_hash": payload["source_hash"],
        "mode": "high_only",
        "total_raw_paragraphs": 2,
        "total_logical_paragraphs": 1,
        "merged_group_count": 1,
        "merged_raw_paragraph_count": 2,
        "high_confidence_merge_count": 1,
        "medium_accepted_merge_count": 0,
        "medium_rejected_candidate_count": 0,
        "decisions": [
            {
                "left_raw_index": 0,
                "right_raw_index": 1,
                "decision": "merge",
                "confidence": "high",
                "reasons": [
                    "same_body_style",
                    "compatible_alignment",
                    "left_not_terminal",
                    "right_starts_continuation",
                    "left_incomplete",
                    "combined_sentence_plausible",
                ],
            }
        ],
    }
    assert len(payload["source_hash"]) == 8


def test_debug_artifact_report_uses_default_filename_for_plain_bytesio(monkeypatch, tmp_path):
    reports_dir = tmp_path / "paragraph-boundary-reports"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_REPORTS_DIR", reports_dir)
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": True,
        },
    )

    debug_doc = make_document()
    debug_doc.add_paragraph("архетипами: повторяющимися моделями")
    debug_doc.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")

    extract_document_content_with_boundary_report(_save_document(debug_doc))

    artifact_files = sorted(reports_dir.glob("*.json"))
    assert len(artifact_files) == 1
    assert artifact_files[0].name.startswith("document.docx_")


def test_relation_debug_artifact_writes_expected_payload(monkeypatch, tmp_path):
    relation_reports_dir = tmp_path / "relation-normalization-reports"
    monkeypatch.setattr(document_module, "RELATION_NORMALIZATION_REPORTS_DIR", relation_reports_dir)
    report = RelationNormalizationReport(
        total_relations=1,
        relation_counts={"toc_region": 1},
        rejected_candidate_count=0,
        decisions=[
            ParagraphRelationDecision(
                relation_kind="toc_region",
                decision="accept",
                member_paragraph_ids=("p0000", "p0001", "p0002"),
                reasons=("toc_header_with_entries",),
            )
        ],
    )

    artifact_path = document_module._write_relation_normalization_report_artifact(
        source_name="debug sample.docx",
        source_bytes=b"debug-source-bytes",
        profile="phase2_default",
        enabled_relation_kinds=("image_caption", "table_caption", "epigraph_attribution", "toc_region"),
        report=report,
    )

    assert artifact_path is not None
    artifact_files = sorted(relation_reports_dir.glob("*.json"))
    assert len(artifact_files) == 1

    payload = json.loads(artifact_files[0].read_text(encoding="utf-8"))
    assert payload == {
        "version": relation_module.RELATION_NORMALIZATION_REPORT_VERSION,
        "source_file": "debug sample.docx",
        "source_hash": payload["source_hash"],
        "profile": "phase2_default",
        "enabled_relation_kinds": ["image_caption", "table_caption", "epigraph_attribution", "toc_region"],
        "total_relations": 1,
        "relation_counts": {"toc_region": 1},
        "rejected_candidate_count": 0,
        "decisions": [
            {
                "relation_kind": "toc_region",
                "decision": "accept",
                "member_paragraph_ids": ["p0000", "p0001", "p0002"],
                "anchor_asset_id": None,
                "reasons": ["toc_header_with_entries"],
                "structure_phase": "post_ai_final",
                "structure_source": "post_ai_final_binding",
            }
        ],
    }
    assert len(payload["source_hash"]) == 8


def test_relation_normalization_artifact_persists_decision_provenance_variants(monkeypatch, tmp_path):
    relation_reports_dir = tmp_path / "relation-normalization-reports"
    monkeypatch.setattr(document_module, "RELATION_NORMALIZATION_REPORTS_DIR", relation_reports_dir)
    report = RelationNormalizationReport(
        total_relations=1,
        relation_counts={"toc_region": 1},
        rejected_candidate_count=2,
        decisions=[
            ParagraphRelationDecision(
                relation_kind="toc_region",
                decision="accept",
                member_paragraph_ids=("p0000", "p0001"),
                reasons=("toc_header_with_entries",),
                structure_phase="pre_ai_diagnostic",
                structure_source="pre_ai_diagnostic_hint",
            ),
            ParagraphRelationDecision(
                relation_kind="toc_region",
                decision="reject",
                member_paragraph_ids=("p0002",),
                reasons=("isolated_toc_entry",),
                structure_phase="post_ai_final",
                structure_source="post_ai_final_binding",
            ),
            ParagraphRelationDecision(
                relation_kind="toc_region",
                decision="reject",
                member_paragraph_ids=("p0003",),
                reasons=("toc_header_without_entries",),
                structure_phase="post_ai_readiness",
                structure_source="post_ai_final_binding",
            ),
        ],
    )

    artifact_path = document_module._write_relation_normalization_report_artifact(
        source_name="debug sample.docx",
        source_bytes=b"debug-source-bytes",
        profile="phase2_default",
        enabled_relation_kinds=("toc_region",),
        report=report,
    )

    assert artifact_path is not None
    payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))

    assert payload["version"] == relation_module.RELATION_NORMALIZATION_REPORT_VERSION
    assert [decision["decision"] for decision in payload["decisions"]] == ["accept", "reject", "reject"]
    assert [decision["structure_source"] for decision in payload["decisions"]] == [
        "pre_ai_diagnostic_hint",
        "post_ai_final_binding",
        "post_ai_final_binding",
    ]
    assert [decision["structure_phase"] for decision in payload["decisions"]] == [
        "pre_ai_diagnostic",
        "post_ai_final",
        "post_ai_readiness",
    ]


def test_debug_artifact_report_is_not_written_when_saving_disabled(monkeypatch, tmp_path):
    reports_dir = tmp_path / "paragraph-boundary-reports"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_REPORTS_DIR", reports_dir)
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": False,
        },
    )
    monkeypatch.setattr(document_module, "resolve_uploaded_filename", lambda uploaded_file: "debug sample.docx")

    debug_doc = make_document()
    debug_doc.add_paragraph("архетипами: повторяющимися моделями")
    debug_doc.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(debug_doc))

    assert len(paragraphs) == 1
    assert report.merged_group_count == 1
    assert not reports_dir.exists()


def test_debug_artifact_directory_creation_failure_is_non_fatal(monkeypatch, tmp_path):
    reports_dir = tmp_path / "paragraph-boundary-reports"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_REPORTS_DIR", reports_dir)
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": True,
        },
    )

    def fail_mkdir(self, *args, **kwargs):
        raise OSError("mkdir blocked")

    monkeypatch.setattr(document_module.Path, "mkdir", fail_mkdir)

    debug_doc = make_document()
    debug_doc.add_paragraph("архетипами: повторяющимися моделями")
    debug_doc.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(debug_doc))

    assert len(paragraphs) == 1
    assert paragraphs[0].text == "архетипами: повторяющимися моделями поведения во времени, наблюдаемыми в разных системах."
    assert report.merged_group_count == 1
    assert not reports_dir.exists()


def test_debug_artifact_file_write_failure_is_non_fatal(monkeypatch, tmp_path):
    reports_dir = tmp_path / "paragraph-boundary-reports"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_REPORTS_DIR", reports_dir)
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": True,
        },
    )
    monkeypatch.setattr(document_module, "resolve_uploaded_filename", lambda uploaded_file: "debug sample.docx")

    original_write_text = document_module.Path.write_text

    def fail_report_write(self, *args, **kwargs):
        if self.suffix == ".json":
            raise OSError("write blocked")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(document_module.Path, "write_text", fail_report_write)

    debug_doc = make_document()
    debug_doc.add_paragraph("архетипами: повторяющимися моделями")
    debug_doc.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(debug_doc))

    assert len(paragraphs) == 1
    assert report.merged_group_count == 1
    assert reports_dir.exists()
    assert list(reports_dir.glob("*.json")) == []


def test_disabled_normalization_preserves_legacy_boundaries(monkeypatch):
    document = make_document()
    document.add_paragraph("архетипами: повторяющимися моделями")
    document.add_paragraph("поведения во времени, наблюдаемыми в разных системах.")
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": False,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": False,
        },
    )

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.text for paragraph in paragraphs] == [
        "архетипами: повторяющимися моделями",
        "поведения во времени, наблюдаемыми в разных системах.",
    ]
    assert report.merged_group_count == 0
    assert report.merged_raw_paragraph_count == 0


def test_medium_candidate_is_rejected_in_high_only_mode(monkeypatch):
    document = make_document()
    document.add_paragraph("Это важное наблюдение:")
    document.add_paragraph("Следующий шаг требует дополнительной проверки.")
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": False,
        },
    )

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.text for paragraph in paragraphs] == [
        "Это важное наблюдение:",
        "Следующий шаг требует дополнительной проверки.",
    ]
    assert report.merged_group_count == 0
    assert report.decisions[0].decision == "keep"
    assert report.decisions[0].confidence == "medium"
    assert "medium_mode_disabled" in report.decisions[0].reasons


def test_medium_diagnostics_are_distinguished_in_boundary_report_artifact(monkeypatch, tmp_path):
    reports_dir = tmp_path / "paragraph-boundary-reports"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_REPORTS_DIR", reports_dir)
    monkeypatch.setattr(document_module, "resolve_uploaded_filename", lambda uploaded_file: "medium sample.docx")
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_normalization_save_debug_artifacts": True,
        },
    )

    document = make_document()
    document.add_paragraph("Это важное наблюдение:")
    document.add_paragraph("Следующий шаг требует дополнительной проверки.")

    extract_document_content_with_boundary_report(_save_document(document))

    artifact_files = sorted(reports_dir.glob("*.json"))
    payload = json.loads(artifact_files[0].read_text(encoding="utf-8"))
    assert payload["high_confidence_merge_count"] == 0
    assert payload["medium_accepted_merge_count"] == 0
    assert payload["medium_rejected_candidate_count"] == 1


def test_medium_candidate_is_merged_in_high_and_medium_mode(monkeypatch):
    document = make_document()
    document.add_paragraph("Это важное наблюдение:")
    document.add_paragraph("Следующий шаг требует дополнительной проверки.")
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_and_medium",
            "paragraph_boundary_normalization_save_debug_artifacts": False,
        },
    )

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert len(paragraphs) == 1
    assert paragraphs[0].text == "Это важное наблюдение: Следующий шаг требует дополнительной проверки."
    assert paragraphs[0].boundary_confidence == "medium"
    assert report.merged_group_count == 1
    assert report.decisions[0].decision == "merge"
    assert report.decisions[0].confidence == "medium"
    assert "medium_mode_disabled" not in report.decisions[0].reasons


def test_blocked_boundary_stays_blocked_in_high_and_medium_mode(monkeypatch):
    document = make_document()
    document.add_paragraph("Первый абзац закончен.")
    document.add_paragraph("Второй абзац начинается с новой мысли.")
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_and_medium",
            "paragraph_boundary_normalization_save_debug_artifacts": False,
        },
    )

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert len(paragraphs) == 2
    assert report.merged_group_count == 0
    assert report.decisions[0].decision == "keep"
    assert report.decisions[0].confidence == "blocked"


def test_resolve_paragraph_boundary_ai_review_settings_uses_boundary_review_model(monkeypatch):
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "paragraph_boundary_ai_review_enabled": True,
            "paragraph_boundary_ai_review_mode": "review_only",
            "paragraph_boundary_ai_review_candidate_limit": 200,
            "paragraph_boundary_ai_review_timeout_seconds": 30,
            "paragraph_boundary_ai_review_max_tokens_per_candidate": 120,
            "models": {
                "text": {
                    "default": "openrouter:google/gemini-3.1-flash-lite-preview",
                    "options": ["openrouter:google/gemini-3.1-flash-lite-preview"],
                },
                "boundary_review": "gpt-5-mini",
            },
        },
    )

    settings = boundary_review_module.resolve_paragraph_boundary_ai_review_settings(
        allowed_modes=("off", "review_only", "apply"),
    )

    assert settings[-1] == "gpt-5-mini"


def test_caption_boundary_is_never_merged():
    document = make_document()
    document.add_paragraph("Вступление без завершающей точки")
    document.add_paragraph("Рисунок 1. Подпись", style="Caption")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["body", "caption"]
    assert report.merged_group_count == 0
    assert "caption_like_boundary" in report.decisions[0].reasons


def test_build_paragraph_relations_accepts_adjacent_caption_candidate_without_prior_reclassification():
    paragraphs = [
        ParagraphUnit(text="[[DOCX_IMAGE_img-1]]", role="image", asset_id="img-1", paragraph_id="p0000"),
        ParagraphUnit(text="Рисунок 1. Подпись", role="body", paragraph_id="p0001"),
    ]

    relations, report = build_paragraph_relations(
        paragraphs,
        enabled_relation_kinds=("image_caption",),
    )

    assert len(relations) == 1
    assert relations[0].relation_kind == "image_caption"
    assert relations[0].member_paragraph_ids == ("p0000", "p0001")
    assert relations[0].anchor_asset_id == "img-1"
    assert report.total_relations == 1


def test_adjacent_caption_candidate_is_attached_after_relation_side_effects_and_reclassification(tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(PNG_BYTES)
    document = make_document()
    document.add_paragraph().add_run().add_picture(str(image_path))
    document.add_paragraph("Рисунок 1. Подпись")

    paragraphs, _, _, relations, relation_report, _, _ = extract_document_content_with_normalization_reports(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["image", "caption"]
    assert paragraphs[1].attached_to_asset_id == paragraphs[0].asset_id
    assert len(relations) == 1
    assert relations[0].relation_kind == "image_caption"
    assert relation_report.total_relations == 1


def test_image_boundary_is_never_merged(tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(PNG_BYTES)
    document = make_document()
    document.add_paragraph("Вступление без завершающей точки")
    document.add_paragraph().add_run().add_picture(str(image_path))
    document.add_paragraph("продолжение после изображения")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["body", "image", "body"]
    assert report.merged_group_count == 0
    assert report.decisions[0].decision == "keep"
    assert report.decisions[0].confidence == "blocked"
    assert "non_body_role" in report.decisions[0].reasons
    assert report.decisions[1].decision == "keep"
    assert report.decisions[1].confidence == "blocked"
    assert "non_body_role" in report.decisions[1].reasons


def test_table_boundary_is_never_merged():
    document = make_document()
    document.add_paragraph("Вступление без завершающей точки")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "ячейка"
    document.add_paragraph("продолжение после таблицы")

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.role for paragraph in paragraphs] == ["body", "table", "body"]
    assert report.merged_group_count == 0


def _add_paragraph(document, text: str, *, cell: bool):
    from docxaicorrector.document.shared_xml import set_paragraph_pdf_table_cell_signal

    paragraph = document.add_paragraph(text)
    if cell:
        set_paragraph_pdf_table_cell_signal(paragraph)
    return paragraph


def _bridge_document():
    # The PDF bridge marks its intermediate DOCX (`_convert_pdf_text_layer_to_docx`); only in such
    # a document is the per-paragraph cell signal honoured.
    from docxaicorrector.document.shared_xml import mark_document_as_pdf_bridge_output

    document = make_document()
    mark_document_as_pdf_bridge_output(document)
    return document


def _add_native_cnf_style(paragraph, value: str) -> None:
    # What Word writes for conditional table formatting -- a standard property, not provenance.
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    cnf_style = OxmlElement("w:cnfStyle")
    cnf_style.set(qn("w:val"), value)
    paragraph._element.get_or_add_pPr().append(cnf_style)


@pytest.mark.parametrize("value", ["100000000000", "000000000000"])
def test_native_docx_cnf_style_is_not_a_pdf_table_cell(value):
    # Codex acceptance review of spec 067 (P1): a native DOCX carrying `w:cnfStyle` -- of any
    # value, the bridge's own included -- is not the bridge's document, so no paragraph of it
    # becomes a cell and a torn sentence is joined as before.
    document = make_document()
    for text in ("The vessel carried", "the supplies to the next port."):
        _add_native_cnf_style(document.add_paragraph(text), value)

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.text for paragraph in paragraphs] == ["The vessel carried the supplies to the next port."]
    assert paragraphs[0].is_pdf_table_cell is False
    assert not any("table_cell_boundary" in decision.reasons for decision in report.decisions)


def test_bridge_marked_document_honours_only_the_bridge_value():
    # In the bridge's own document a `w:cnfStyle` with another value is still no cell signal.
    document = _bridge_document()
    _add_native_cnf_style(document.add_paragraph("The vessel carried"), "100000000000")
    document.add_paragraph("the supplies to the next port.")

    paragraphs, _, _ = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.text for paragraph in paragraphs] == ["The vessel carried the supplies to the next port."]
    assert paragraphs[0].is_pdf_table_cell is False


def test_pdf_table_cell_is_never_merged_with_either_neighbour():
    # Spec 067 FR-002: a cell the PDF bridge marked (``w:cnfStyle``) is a paragraph of its own.
    # Each pair below reads as a torn sentence by text -- no full stop on the left, a
    # lower-case start on the right -- which is how 379 of Rethinking Money's 616 cells were
    # joined again before the flag crossed the bridge.
    document = _bridge_document()
    _add_paragraph(document, "NORTH WING", cell=True)
    _add_paragraph(document, "south wing", cell=True)  # cell + cell
    _add_paragraph(document, "and the harbour.", cell=False)  # cell -> plain
    _add_paragraph(document, "Lanternfield p.142 and", cell=False)
    _add_paragraph(document, "harbour tokens p.144", cell=True)  # plain -> cell

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.text for paragraph in paragraphs] == [
        "NORTH WING",
        "south wing",
        "and the harbour.",
        "Lanternfield p.142 and",
        "harbour tokens p.144",
    ]
    assert [paragraph.is_pdf_table_cell for paragraph in paragraphs] == [True, True, False, False, True]
    assert report.merged_group_count == 0
    blocked = [decision for decision in report.decisions if "table_cell_boundary" in decision.reasons]
    assert [(decision.left_raw_index, decision.right_raw_index) for decision in blocked] == [(0, 1), (1, 2), (3, 4)]
    assert all(decision.confidence == "blocked" for decision in blocked)


def test_same_pairs_without_the_cell_flag_still_merge():
    # Anti-regression 3 of spec 067: a real continuation of body text -- the same shapes with no
    # cell flag -- is still joined, so the refusal above is the flag's doing, not the text's.
    document = make_document()
    _add_paragraph(document, "NORTH WING", cell=False)
    _add_paragraph(document, "south wing.", cell=False)
    _add_paragraph(document, "The bank lends money and", cell=False)
    _add_paragraph(document, "creates a deposit at the same time.", cell=False)

    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(document))

    assert [paragraph.text for paragraph in paragraphs] == [
        "NORTH WING south wing.",
        "The bank lends money and creates a deposit at the same time.",
    ]
    assert paragraphs[0].is_pdf_table_cell is False
    assert not any("table_cell_boundary" in decision.reasons for decision in report.decisions)


def test_ai_review_candidates_include_medium_boundaries_and_rejected_relations():
    candidates = boundary_review_module.build_ai_review_candidates(
        raw_blocks=[
            RawParagraph(raw_index=0, text="Это важное наблюдение:", style_name="Normal"),
            RawParagraph(raw_index=1, text="Следующий шаг требует проверки.", style_name="Normal"),
        ],
        paragraphs=[
            ParagraphUnit(text="Подпись 1", role="caption", paragraph_id="p0001"),
            ParagraphUnit(text="Подпись 2", role="caption", paragraph_id="p0002"),
        ],
        boundary_report=ParagraphBoundaryNormalizationReport(
            total_raw_paragraphs=2,
            total_logical_paragraphs=2,
            merged_group_count=0,
            merged_raw_paragraph_count=0,
            decisions=[
                ParagraphBoundaryDecision(
                    left_raw_index=0,
                    right_raw_index=1,
                    decision="keep",
                    confidence="medium",
                    reasons=("combined_sentence_plausible", "medium_mode_disabled"),
                )
            ],
        ),
        relation_report=RelationNormalizationReport(
            total_relations=0,
            relation_counts={},
            rejected_candidate_count=1,
            decisions=[
                ParagraphRelationDecision(
                    relation_kind="epigraph_attribution",
                    decision="reject",
                    member_paragraph_ids=("p0001", "p0002"),
                    reasons=("spacing_gap",),
                )
            ],
        ),
        candidate_limit=10,
    )

    assert [candidate["candidate_kind"] for candidate in candidates] == [
        "boundary_medium",
        "relation_rejected",
    ]
    assert candidates[0]["candidate_id"] == "0:1"
    assert candidates[0]["left_text"] == "Это важное наблюдение:"
    assert candidates[1]["candidate_id"] == "epigraph_attribution:p0001|p0002"
    assert candidates[1]["member_texts"] == ["Подпись 1", "Подпись 2"]


def test_ai_review_timeout_writes_non_authoritative_artifact(monkeypatch, tmp_path):
    review_dir = tmp_path / "paragraph-boundary-ai-review"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_AI_REVIEW_DIR", review_dir)
    monkeypatch.setattr(
        document_module,
        "_request_ai_review_recommendations",
        lambda **kwargs: (_ for _ in ()).throw(TimeoutError("review timeout")),
    )

    artifact_path = document_module._run_paragraph_boundary_ai_review(
        source_name="debug sample.docx",
        source_bytes=b"debug-source-bytes",
        mode="review_only",
        model="gpt-5.4",
        raw_blocks=[
            RawParagraph(raw_index=0, text="Это важное наблюдение:", style_name="Normal"),
            RawParagraph(raw_index=1, text="Следующий шаг требует проверки.", style_name="Normal"),
        ],
        paragraphs=[],
        boundary_report=ParagraphBoundaryNormalizationReport(
            total_raw_paragraphs=2,
            total_logical_paragraphs=2,
            merged_group_count=0,
            merged_raw_paragraph_count=0,
            decisions=[
                ParagraphBoundaryDecision(
                    left_raw_index=0,
                    right_raw_index=1,
                    decision="keep",
                    confidence="medium",
                    reasons=("combined_sentence_plausible", "medium_mode_disabled"),
                )
            ],
        ),
        relation_report=RelationNormalizationReport(
            total_relations=0,
            relation_counts={},
            rejected_candidate_count=0,
            decisions=[],
        ),
        candidate_limit=10,
        timeout_seconds=5,
        max_tokens_per_candidate=120,
    )

    assert artifact_path is not None
    payload = json.loads(next(review_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["mode"] == "review_only"
    assert payload["error_code"] == "timeout"
    assert payload["reviewed_candidate_count"] == 1
    assert payload["accepted_candidate_count"] == 0
    assert payload["decisions"][0]["final_decision"] == "keep"
    assert "ai_review_unavailable:timeout" in payload["decisions"][0]["reasons"]


def test_ai_review_disagreement_is_logged_but_deterministic_decision_is_retained(monkeypatch, tmp_path):
    review_dir = tmp_path / "paragraph-boundary-ai-review"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_AI_REVIEW_DIR", review_dir)
    monkeypatch.setattr(
        document_module,
        "_request_ai_review_recommendations",
        lambda **kwargs: {"0:1": {"recommendation": "merge", "reasons": ["continuation"]}},
    )

    artifact_path = document_module._run_paragraph_boundary_ai_review(
        source_name="debug sample.docx",
        source_bytes=b"debug-source-bytes",
        mode="review_only",
        model="gpt-5.4",
        raw_blocks=[
            RawParagraph(raw_index=0, text="Это важное наблюдение:", style_name="Normal"),
            RawParagraph(raw_index=1, text="Следующий шаг требует проверки.", style_name="Normal"),
        ],
        paragraphs=[],
        boundary_report=ParagraphBoundaryNormalizationReport(
            total_raw_paragraphs=2,
            total_logical_paragraphs=2,
            merged_group_count=0,
            merged_raw_paragraph_count=0,
            decisions=[
                ParagraphBoundaryDecision(
                    left_raw_index=0,
                    right_raw_index=1,
                    decision="keep",
                    confidence="medium",
                    reasons=("combined_sentence_plausible", "medium_mode_disabled"),
                )
            ],
        ),
        relation_report=RelationNormalizationReport(
            total_relations=0,
            relation_counts={},
            rejected_candidate_count=0,
            decisions=[],
        ),
        candidate_limit=10,
        timeout_seconds=5,
        max_tokens_per_candidate=120,
    )

    assert artifact_path is not None
    payload = json.loads(next(review_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["decisions"][0]["ai_recommendation"] == "merge"
    assert payload["decisions"][0]["final_decision"] == "keep"
    assert "deterministic_decision_retained" in payload["decisions"][0]["reasons"]


def test_ai_review_empty_response_falls_back_to_deterministic_artifact(monkeypatch, tmp_path):
    review_dir = tmp_path / "paragraph-boundary-ai-review"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_AI_REVIEW_DIR", review_dir)
    monkeypatch.setattr(
        document_module,
        "_request_ai_review_recommendations",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("AI review returned empty output.")),
    )

    artifact_path = document_module._run_paragraph_boundary_ai_review(
        source_name="debug sample.docx",
        source_bytes=b"debug-source-bytes",
        mode="review_only",
        model="gpt-5.4",
        raw_blocks=[
            RawParagraph(raw_index=0, text="Это важное наблюдение:", style_name="Normal"),
            RawParagraph(raw_index=1, text="Следующий шаг требует проверки.", style_name="Normal"),
        ],
        paragraphs=[],
        boundary_report=ParagraphBoundaryNormalizationReport(
            total_raw_paragraphs=2,
            total_logical_paragraphs=2,
            merged_group_count=0,
            merged_raw_paragraph_count=0,
            decisions=[
                ParagraphBoundaryDecision(
                    left_raw_index=0,
                    right_raw_index=1,
                    decision="keep",
                    confidence="medium",
                    reasons=("combined_sentence_plausible",),
                )
            ],
        ),
        relation_report=RelationNormalizationReport(
            total_relations=0,
            relation_counts={},
            rejected_candidate_count=0,
            decisions=[],
        ),
        candidate_limit=10,
        timeout_seconds=5,
        max_tokens_per_candidate=120,
    )

    assert artifact_path is not None
    payload = json.loads(next(review_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["error_code"] == "empty_response"
    assert payload["decisions"][0]["final_decision"] == "keep"
    assert "ai_review_unavailable:empty_response" in payload["decisions"][0]["reasons"]


def test_ai_review_malformed_response_falls_back_to_deterministic_artifact(monkeypatch, tmp_path):
    review_dir = tmp_path / "paragraph-boundary-ai-review"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_AI_REVIEW_DIR", review_dir)
    monkeypatch.setattr(
        document_module,
        "_request_ai_review_recommendations",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("AI review did not return JSON.")),
    )

    artifact_path = document_module._run_paragraph_boundary_ai_review(
        source_name="debug sample.docx",
        source_bytes=b"debug-source-bytes",
        mode="review_only",
        model="gpt-5.4",
        raw_blocks=[
            RawParagraph(raw_index=0, text="Это важное наблюдение:", style_name="Normal"),
            RawParagraph(raw_index=1, text="Следующий шаг требует проверки.", style_name="Normal"),
        ],
        paragraphs=[],
        boundary_report=ParagraphBoundaryNormalizationReport(
            total_raw_paragraphs=2,
            total_logical_paragraphs=2,
            merged_group_count=0,
            merged_raw_paragraph_count=0,
            decisions=[
                ParagraphBoundaryDecision(
                    left_raw_index=0,
                    right_raw_index=1,
                    decision="keep",
                    confidence="medium",
                    reasons=("combined_sentence_plausible",),
                )
            ],
        ),
        relation_report=RelationNormalizationReport(
            total_relations=0,
            relation_counts={},
            rejected_candidate_count=0,
            decisions=[],
        ),
        candidate_limit=10,
        timeout_seconds=5,
        max_tokens_per_candidate=120,
    )

    assert artifact_path is not None
    payload = json.loads(next(review_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["error_code"] == "no_json_object"
    assert payload["decisions"][0]["final_decision"] == "keep"
    assert "ai_review_unavailable:no_json_object" in payload["decisions"][0]["reasons"]


def test_ai_review_without_matching_recommendation_marks_no_recommendation(monkeypatch, tmp_path):
    review_dir = tmp_path / "paragraph-boundary-ai-review"
    monkeypatch.setattr(document_module, "PARAGRAPH_BOUNDARY_AI_REVIEW_DIR", review_dir)
    monkeypatch.setattr(
        document_module,
        "_request_ai_review_recommendations",
        lambda **kwargs: {"different-candidate": {"recommendation": "merge", "reasons": ["other"]}},
    )

    artifact_path = document_module._run_paragraph_boundary_ai_review(
        source_name="debug sample.docx",
        source_bytes=b"debug-source-bytes",
        mode="review_only",
        model="gpt-5.4",
        raw_blocks=[
            RawParagraph(raw_index=0, text="Это важное наблюдение:", style_name="Normal"),
            RawParagraph(raw_index=1, text="Следующий шаг требует проверки.", style_name="Normal"),
        ],
        paragraphs=[],
        boundary_report=ParagraphBoundaryNormalizationReport(
            total_raw_paragraphs=2,
            total_logical_paragraphs=2,
            merged_group_count=0,
            merged_raw_paragraph_count=0,
            decisions=[
                ParagraphBoundaryDecision(
                    left_raw_index=0,
                    right_raw_index=1,
                    decision="keep",
                    confidence="medium",
                    reasons=("combined_sentence_plausible",),
                )
            ],
        ),
        relation_report=RelationNormalizationReport(
            total_relations=0,
            relation_counts={},
            rejected_candidate_count=0,
            decisions=[],
        ),
        candidate_limit=10,
        timeout_seconds=5,
        max_tokens_per_candidate=120,
    )

    assert artifact_path is not None
    payload = json.loads(next(review_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert "error_code" not in payload
    assert payload["decisions"][0]["ai_recommendation"] is None
    assert payload["decisions"][0]["final_decision"] == "keep"
    assert "ai_review_no_recommendation" in payload["decisions"][0]["reasons"]


def test_request_ai_review_uses_passed_client_factory_not_global(monkeypatch):
    # F9b: boundary AI review must use the provider-aware factory/client threaded in by
    # the caller, never the global openai-only get_client().
    sentinel_client = object()
    factory_calls: list[str] = []

    def factory(model: str) -> object:
        factory_calls.append(model)
        return sentinel_client

    captured: dict[str, object] = {}

    def fake_call(client, payload, *, max_retries, retryable_error_predicate, **kwargs):
        # ``**kwargs`` absorbs usage_stage, added when model accounting started
        # recording at this call site. These tests pin WHICH CLIENT is used, not the
        # signature, so they must not break every time the call gains a keyword.
        captured["client"] = client
        return object()

    def boom_get_client() -> object:
        raise AssertionError("global get_client() must not be used by boundary AI review")

    monkeypatch.setattr(boundary_review_module, "call_responses_create_with_retry", fake_call)
    monkeypatch.setattr(boundary_review_module, "extract_response_text", lambda *a, **k: '{"recommendations": []}')
    monkeypatch.setattr(boundary_review_module, "parse_json_object", lambda *a, **k: {"recommendations": []})
    monkeypatch.setattr(config, "get_client", boom_get_client)

    result = boundary_review_module.request_ai_review_recommendations(
        model="anthropic:claude-x",
        candidates=[{"candidate_id": "0:1"}],
        timeout_seconds=5,
        max_tokens_per_candidate=100,
        client_factory=factory,
    )

    assert captured["client"] is sentinel_client
    assert factory_calls == ["anthropic:claude-x"]
    assert result == {}


def test_request_ai_review_default_resolves_provider_aware_not_global(monkeypatch):
    # F9b: with no factory supplied, the default resolution goes through the provider-aware
    # model-selector factory (get_client_for_model_selector), NOT the global get_client().
    sentinel_client = object()
    selector_calls: list[tuple[str, str]] = []

    def fake_get_client_for_model_selector(selector, required_capability, *, config_like=None):
        selector_calls.append((selector, required_capability))
        return sentinel_client

    captured: dict[str, object] = {}

    def fake_call(client, payload, *, max_retries, retryable_error_predicate, **kwargs):
        # ``**kwargs`` absorbs usage_stage, added when model accounting started
        # recording at this call site. These tests pin WHICH CLIENT is used, not the
        # signature, so they must not break every time the call gains a keyword.
        captured["client"] = client
        return object()

    def boom_get_client() -> object:
        raise AssertionError("global get_client() must not be used by boundary AI review")

    monkeypatch.setattr(config, "get_client_for_model_selector", fake_get_client_for_model_selector)
    monkeypatch.setattr(config, "get_client", boom_get_client)
    monkeypatch.setattr(boundary_review_module, "call_responses_create_with_retry", fake_call)
    monkeypatch.setattr(boundary_review_module, "extract_response_text", lambda *a, **k: '{"recommendations": []}')
    monkeypatch.setattr(boundary_review_module, "parse_json_object", lambda *a, **k: {"recommendations": []})

    boundary_review_module.request_ai_review_recommendations(
        model="gpt-5.4",
        candidates=[{"candidate_id": "0:1"}],
        timeout_seconds=5,
        max_tokens_per_candidate=100,
    )

    assert captured["client"] is sentinel_client
    assert selector_calls == [("gpt-5.4", "responses_text")]


def test_run_paragraph_boundary_ai_review_threads_client_factory(monkeypatch, tmp_path):
    # F9b: run_paragraph_boundary_ai_review forwards the provider-aware factory to the impl.
    monkeypatch.setattr(
        boundary_review_module,
        "build_ai_review_candidates",
        lambda **kwargs: [{"candidate_id": "0:1", "candidate_kind": "boundary_medium", "deterministic_decision": "keep"}],
    )
    recorded: dict[str, object] = {}

    def fake_impl(*, model, candidates, timeout_seconds, max_tokens_per_candidate, client_factory=None):
        recorded["client_factory"] = client_factory
        return {"0:1": {"recommendation": "keep", "reasons": []}}

    sentinel_factory = lambda model: object()

    artifact_path = boundary_review_module.run_paragraph_boundary_ai_review(
        source_name="doc.docx",
        source_bytes=b"x",
        mode="review_only",
        model="anthropic:claude-x",
        raw_blocks=[],
        paragraphs=[],
        boundary_report=ParagraphBoundaryNormalizationReport(
            total_raw_paragraphs=0,
            total_logical_paragraphs=0,
            merged_group_count=0,
            merged_raw_paragraph_count=0,
            decisions=[],
        ),
        relation_report=RelationNormalizationReport(
            total_relations=0,
            relation_counts={},
            rejected_candidate_count=0,
            decisions=[],
        ),
        candidate_limit=10,
        timeout_seconds=5,
        max_tokens_per_candidate=100,
        target_dir=tmp_path,
        max_age_seconds=3600,
        max_count=10,
        request_ai_review_recommendations_impl=fake_impl,
        client_factory=sentinel_factory,
    )

    assert artifact_path is not None
    assert recorded["client_factory"] is sentinel_factory


def test_run_paragraph_boundary_ai_review_omits_factory_kwarg_for_legacy_impl(monkeypatch, tmp_path):
    # Backward-compat: an injected impl that does not accept client_factory must keep working
    # when no factory is threaded (the extraction-layer wrapper relies on this).
    monkeypatch.setattr(
        boundary_review_module,
        "build_ai_review_candidates",
        lambda **kwargs: [{"candidate_id": "0:1", "candidate_kind": "boundary_medium", "deterministic_decision": "keep"}],
    )

    def legacy_impl(*, model, candidates, timeout_seconds, max_tokens_per_candidate):
        return {"0:1": {"recommendation": "keep", "reasons": []}}

    artifact_path = boundary_review_module.run_paragraph_boundary_ai_review(
        source_name="doc.docx",
        source_bytes=b"x",
        mode="review_only",
        model="gpt-5.4",
        raw_blocks=[],
        paragraphs=[],
        boundary_report=ParagraphBoundaryNormalizationReport(
            total_raw_paragraphs=0,
            total_logical_paragraphs=0,
            merged_group_count=0,
            merged_raw_paragraph_count=0,
            decisions=[],
        ),
        relation_report=RelationNormalizationReport(
            total_relations=0,
            relation_counts={},
            rejected_candidate_count=0,
            decisions=[],
        ),
        candidate_limit=10,
        timeout_seconds=5,
        max_tokens_per_candidate=100,
        target_dir=tmp_path,
        max_age_seconds=3600,
        max_count=10,
        request_ai_review_recommendations_impl=legacy_impl,
    )

    assert artifact_path is not None


def test_build_ai_review_request_payload_sends_bare_model_id_for_qualified_selector():
    # The API model field must carry the provider-side model id, not the
    # provider-qualified selector, otherwise a qualified selector 404s at the API.
    config.reset_app_config_cache()

    openai_payload = boundary_review_module.build_ai_review_request_payload(
        model="openai:gpt-5.4-mini",
        candidates=[{"candidate_id": "0:1"}],
        timeout_seconds=5,
        max_tokens_per_candidate=100,
    )
    anthropic_payload = boundary_review_module.build_ai_review_request_payload(
        model="anthropic:claude-sonnet-4-6",
        candidates=[{"candidate_id": "0:1"}],
        timeout_seconds=5,
        max_tokens_per_candidate=100,
    )
    bare_payload = boundary_review_module.build_ai_review_request_payload(
        model="gpt-5.4-mini",
        candidates=[{"candidate_id": "0:1"}],
        timeout_seconds=5,
        max_tokens_per_candidate=100,
    )

    assert openai_payload["model"] == "gpt-5.4-mini"
    assert anthropic_payload["model"] == "claude-sonnet-4-6"
    assert bare_payload["model"] == "gpt-5.4-mini"


# --- Spec 080: a change of font size between two paragraphs is a structural boundary ------------


def _sized_document(*paragraphs: tuple[str, float | None]):
    document = make_document()
    for text, size in paragraphs:
        run = document.add_paragraph().add_run(text)
        if size is not None:
            from docx.shared import Pt

            run.font.size = Pt(size)
    return document


def _non_space_characters(texts) -> list[str]:
    return sorted(character for text in texts for character in text if not character.isspace())


def _raw(raw_index: int, text: str, size: float | None) -> RawParagraph:
    return RawParagraph(raw_index=raw_index, text=text, style_name="Normal", font_size_pt=size)


def _evaluate(left: RawParagraph, right: RawParagraph) -> ParagraphBoundaryDecision:
    return document_module._evaluate_paragraph_boundary(left, right)


def test_epigraph_mark_and_chapter_opening_are_not_glued_across_the_mark():
    # The shape that motivated spec 080: an epigraph with its attribution, its note mark set as a
    # paragraph of its own in a much smaller size, then the chapter's first paragraph (which ends
    # unfinished, so the chain rule would carry the medium mark -> body pair). The mark stays with
    # the text it marks; the chapter opening is a paragraph of its own.
    source = [
        ("“Quiet harbours keep the oldest promises.” – Ilsa Varn", 14.0),
        ("1", 5.5),
        ("We have followed the lantern keepers through three winters and each of them kept", 14.0),
        ("Every keeper writes the tide down by hand.", 14.0),
    ]
    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(_sized_document(*source)))

    assert [paragraph.text for paragraph in paragraphs] == [
        "“Quiet harbours keep the oldest promises.” – Ilsa Varn 1",
        "We have followed the lantern keepers through three winters and each of them kept",
        "Every keeper writes the tide down by hand.",
    ]
    decision = next(item for item in report.decisions if (item.left_raw_index, item.right_raw_index) == (1, 2))
    assert decision.decision == "keep"
    assert decision.confidence == "blocked"
    assert "font_size_transition" in decision.reasons
    assert _non_space_characters(paragraph.text for paragraph in paragraphs) == _non_space_characters(text for text, _ in source)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # a lead-in and a displayed quotation that starts in lower case
        (("As the harbour master wrote in his ledger:", 14.5), ("every keeper must log the tide by hand", 11.0)),
        # a caption set small and the body text that resumes after the figure
        (("A ledger page from the northern harbour. Note the stamp “Kept by Hand.”", 8.0), ("for recording tides, which the keepers used", 10.5)),
        # an epigraph attribution (it ends with its note number) and the chapter's first paragraph
        (("Ilsa Varn, The Harbour Ledger, 19261", 11.0), ("the winter edition of the gazette was devoted to the keepers", 14.5)),
    ],
)
def test_paragraphs_in_clearly_different_sizes_are_not_merged(left, right):
    paragraphs, _, report = extract_document_content_with_boundary_report(_save_document(_sized_document(left, right)))

    assert [paragraph.text for paragraph in paragraphs] == [left[0], right[0]]
    assert report.decisions[0].confidence == "blocked"
    assert report.decisions[0].reasons == ("font_size_transition",)


def test_same_pairs_in_one_size_still_merge():
    # Anti-regression of spec 080: the refusal above is the size's doing, not the text's.
    paragraphs, _, _ = extract_document_content_with_boundary_report(
        _save_document(
            _sized_document(
                ("As the harbour master wrote in his ledger:", 14.5),
                ("every keeper must log the tide by hand", 14.5),
            )
        )
    )

    assert [paragraph.text for paragraph in paragraphs] == [
        "As the harbour master wrote in his ledger: every keeper must log the tide by hand"
    ]


def test_note_mark_joins_the_text_it_marks():
    # The mark is a superscript the importer set as a paragraph of its own: it belongs to the
    # text before it, whatever that text's size.
    paragraphs, _, report = extract_document_content_with_boundary_report(
        _save_document(_sized_document(("– Ilsa Varn, keeper of the northern light", 14.0), ("27", 5.5)))
    )

    assert [paragraph.text for paragraph in paragraphs] == ["– Ilsa Varn, keeper of the northern light 27"]
    assert report.decisions[0].decision == "merge"


def test_sentence_continues_across_its_note_mark():
    # A mark inside a sentence: the text after it continues the sentence, so all three are one.
    # (The dash-led right side is longer than 120 characters: a shorter one is read as an
    # attribution line, `is_likely_attribution_text`, and kept apart before size is looked at.)
    paragraphs, _, _ = extract_document_content_with_boundary_report(
        _save_document(
            _sized_document(
                ("The tolls were never set by the harbour board", 14.0),
                ("33", 5.5),
                ("– but rather by the keepers themselves, who wrote every toll into the ledger by hand and read it aloud at the winter meeting.", 14.0),
            )
        )
    )

    assert [paragraph.text for paragraph in paragraphs] == [
        "The tolls were never set by the harbour board 33 – but rather by the keepers themselves, who wrote every toll into the ledger by hand and read it aloud at the winter meeting."
    ]


def test_a_longer_number_is_not_a_note_mark():
    # Four digits (a year) is not the importer's standalone-marker form (1-3 digits), so its size
    # change is evidence like any other.
    decision = _evaluate(_raw(0, "the ledger was printed in", 14.0), _raw(1, "1926", 5.5))

    assert decision.confidence == "blocked"
    assert "font_size_transition" in decision.reasons


def test_unknown_size_leaves_the_decision_as_before():
    left = _raw(0, "The vessel carried", None)
    right = _raw(1, "the supplies to the next port.", 11.0)

    for pair in ((left, right), (right, left)):
        assert "font_size_transition" not in _evaluate(*pair).reasons
    assert _evaluate(left, right).decision == "merge"


@pytest.mark.parametrize(
    ("first", "second", "differs"),
    [
        (10.0, 10.5, False),  # 0.5 is the absolute floor of the tolerance
        (10.0, 11.0, False),  # 10 % of the smaller
        (10.0, 11.5, True),
        (14.0, 15.0, False),
        (14.0, 15.5, True),
        (14.0, 5.5, True),
    ],
)
def test_size_tolerance_is_the_importers(first, second, differs):
    decision = _evaluate(_raw(0, "The vessel carried", first), _raw(1, "the supplies to the next port.", second))

    assert ("font_size_transition" in decision.reasons) is differs
    assert (decision.decision == "merge") is not differs


def test_size_match_and_mark_form_agree_with_the_pdf_importer():
    # boundaries.py restates the importer's two notions instead of importing the importer; this
    # pins them to the same answers.
    from docxaicorrector.document import boundaries
    from docxaicorrector.pdf_import import logical_import

    sizes = [4.0, 5.5, 5.76, 7.5, 8.0, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5, 12.0, 14.0, 14.4, 15.0, 15.5, 16.5, 20.5, 23.5]
    for first in sizes:
        for second in sizes:
            assert boundaries.font_sizes_match(first, second) == logical_import._font_sizes_match(first, second)
    for text in ("1", "12", "123", "1234", "a1", " 7 ", "1.", "", "¹"):
        assert boundaries.is_standalone_note_mark(text) == bool(
            logical_import._STANDALONE_FOOTNOTE_MARKER_PATTERN.match(text.strip())
        )
