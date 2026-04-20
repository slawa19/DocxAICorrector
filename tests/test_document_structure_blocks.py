import config

from document import (
    build_editing_jobs,
    build_marker_wrapped_block_text,
    build_paragraph_relations,
    build_semantic_blocks,
)
from models import ParagraphUnit


def test_build_semantic_blocks_keeps_heading_with_following_body():
    paragraphs = [
        ParagraphUnit(text="Глава 1", role="heading"),
        ParagraphUnit(text="Короткий абзац после заголовка.", role="body"),
        ParagraphUnit(text="Следующий абзац, который уже должен перейти в отдельный блок.", role="body"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=70)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Глава 1",
        "Короткий абзац после заголовка.",
    ]
    assert blocks[1].text == "Следующий абзац, который уже должен перейти в отдельный блок."


def test_build_semantic_blocks_keeps_consecutive_headings_with_following_body():
    paragraphs = [
        ParagraphUnit(text="Глава 1", role="heading", heading_level=1),
        ParagraphUnit(text="Раздел 1.1", role="heading", heading_level=2),
        ParagraphUnit(text="Первый содержательный абзац после цепочки заголовков.", role="body"),
        ParagraphUnit(text="Следующий абзац уже должен перейти в отдельный блок из-за лимита.", role="body"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=90)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Глава 1",
        "Раздел 1.1",
        "Первый содержательный абзац после цепочки заголовков.",
    ]
    assert blocks[1].text == "Следующий абзац уже должен перейти в отдельный блок из-за лимита."


def test_build_editing_jobs_uses_neighbor_blocks_for_context():
    paragraphs = [
        ParagraphUnit(text="Первый блок.", role="body"),
        ParagraphUnit(text="Второй блок.", role="body"),
        ParagraphUnit(text="Третий блок.", role="body"),
    ]
    blocks = build_semantic_blocks(paragraphs, max_chars=20)

    jobs = build_editing_jobs(blocks, max_chars=3000)

    assert len(jobs) == 3
    assert jobs[1]["target_text"] == "Второй блок."
    assert jobs[1]["context_before"] == "Первый блок."
    assert jobs[1]["context_after"] == "Третий блок."
    assert all(str(job["target_text"]).strip() for job in jobs)


def test_build_editing_jobs_marks_image_only_blocks_as_passthrough():
    paragraphs = [
        ParagraphUnit(text="Вступление", role="body"),
        ParagraphUnit(text="[[DOCX_IMAGE_img_001]]", role="image"),
        ParagraphUnit(text="Основной текст", role="body"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=20)
    jobs = build_editing_jobs(blocks, max_chars=3000)

    assert [job["target_text"] for job in jobs] == ["Вступление", "[[DOCX_IMAGE_img_001]]", "Основной текст"]
    assert [job["job_kind"] for job in jobs] == ["llm", "passthrough", "llm"]
    assert jobs[0]["paragraph_ids"] == ["p0000"]
    assert str(jobs[1]["target_text_with_markers"]).startswith("[[DOCX_PARA_p0001]]")


def test_build_semantic_blocks_keeps_heading_with_following_epigraph_cluster_even_over_soft_limit():
    paragraphs = [
        ParagraphUnit(text="Глава 1", role="heading", paragraph_id="p0000", heading_level=1),
        ParagraphUnit(
            text="Богатство заключается не в количестве имущества, а в свободе желаний.",
            role="body",
            structural_role="epigraph",
            paragraph_id="p0001",
        ),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution", paragraph_id="p0002"),
        ParagraphUnit(text="Следующий обычный абзац.", role="body", paragraph_id="p0003"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=65, relations=[])

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Глава 1",
        "Богатство заключается не в количестве имущества, а в свободе желаний.",
        "— Эпиктет",
    ]


def test_build_semantic_blocks_uses_structural_roles_for_toc_grouping_without_relations():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0000"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        ParagraphUnit(text="Первый обычный абзац после содержания.", role="body", paragraph_id="p0003"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=60, relations=[])

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Содержание",
        "Глава 1........ 12",
        "Глава 2........ 18",
    ]


def test_build_editing_jobs_marks_toc_only_blocks_as_passthrough():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0000"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        ParagraphUnit(text="Первый обычный абзац.", role="body", paragraph_id="p0003"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=80, relations=[])
    jobs = build_editing_jobs(blocks, max_chars=3000)

    assert [job["job_kind"] for job in jobs] == ["passthrough", "llm"]
    assert jobs[0]["paragraph_ids"] == ["p0000", "p0001", "p0002"]


def test_build_paragraph_relations_detects_caption_epigraph_and_toc_groups():
    paragraphs = [
        ParagraphUnit(text="[[DOCX_IMAGE_img_001]]", role="image", structural_role="image", paragraph_id="p0000", asset_id="img_001"),
        ParagraphUnit(
            text="Рис. 1. Подпись",
            role="caption",
            structural_role="caption",
            paragraph_id="p0001",
            attached_to_asset_id="img_001",
        ),
        ParagraphUnit(
            text="Богатство заключается не в том, чтобы иметь много имущества.",
            role="body",
            structural_role="epigraph",
            paragraph_id="p0002",
            paragraph_alignment="center",
        ),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution", paragraph_id="p0003"),
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0004"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0005"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0006"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert [relation.relation_kind for relation in relations] == [
        "image_caption",
        "epigraph_attribution",
        "toc_region",
    ]
    assert report.total_relations == 3
    assert report.relation_counts == {
        "image_caption": 1,
        "epigraph_attribution": 1,
        "toc_region": 1,
    }


def test_build_semantic_blocks_keeps_epigraph_attribution_pair_together():
    paragraphs = [
        ParagraphUnit(text="Богатство заключается в свободе желаний.", role="body", structural_role="epigraph", paragraph_id="p0000"),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution", paragraph_id="p0001"),
        ParagraphUnit(text="Следующий обычный абзац должен перейти в отдельный блок.", role="body", paragraph_id="p0002"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=70)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Богатство заключается в свободе желаний.",
        "— Эпиктет",
    ]


def test_build_semantic_blocks_keeps_toc_region_together():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0000"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        ParagraphUnit(text="Первый обычный абзац после содержания.", role="body", paragraph_id="p0003"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=60)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Содержание",
        "Глава 1........ 12",
        "Глава 2........ 18",
    ]


def test_build_semantic_blocks_keeps_epigraph_pair_via_structural_role_even_when_relation_config_excludes_it(monkeypatch):
    monkeypatch.setattr(
        config,
        "load_app_config",
        lambda: {
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("image_caption", "table_caption"),
            "relation_normalization_save_debug_artifacts": True,
        },
    )
    paragraphs = [
        ParagraphUnit(
            text="Богатство заключается не в накоплении вещей, а в свободе от лишнего.",
            role="body",
            structural_role="epigraph",
            paragraph_id="p0000",
        ),
        ParagraphUnit(text="— Эпиктет", role="body", structural_role="attribution", paragraph_id="p0001"),
        ParagraphUnit(text="Следующий обычный абзац должен остаться отдельным блоком.", role="body", paragraph_id="p0002"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=55)

    assert len(blocks) == 2
    assert [paragraph.text for paragraph in blocks[0].paragraphs] == [
        "Богатство заключается не в накоплении вещей, а в свободе от лишнего.",
        "— Эпиктет",
    ]
    assert [paragraph.text for paragraph in blocks[1].paragraphs] == ["Следующий обычный абзац должен остаться отдельным блоком."]


def test_build_paragraph_relations_records_epigraph_and_isolated_toc_rejections():
    paragraphs = [
        ParagraphUnit(text="Богатство заключается в свободе желаний.", role="body", structural_role="epigraph", paragraph_id="p0000"),
        ParagraphUnit(text="Комментарий редактора", role="body", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0002"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert relations == []
    assert report.rejected_candidate_count == 2
    assert [(decision.relation_kind, decision.reasons) for decision in report.decisions] == [
        ("epigraph_attribution", ("epigraph_without_attribution",)),
        ("toc_region", ("isolated_toc_entry",)),
    ]


def test_build_paragraph_relations_detects_table_caption_and_headerless_toc_run():
    paragraphs = [
        ParagraphUnit(text="<table><tr><td>1</td></tr></table>", role="table", structural_role="table", paragraph_id="p0000", asset_id="table_001"),
        ParagraphUnit(text="Табл. 1. Подпись", role="caption", structural_role="caption", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0002"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0003"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert [relation.relation_kind for relation in relations] == ["table_caption", "toc_region"]
    assert report.relation_counts == {"table_caption": 1, "toc_region": 1}


def test_build_paragraph_relations_records_rejected_caption_candidate():
    paragraphs = [
        ParagraphUnit(text="Рис. 3. Одинокая подпись", role="caption", structural_role="caption", paragraph_id="p0000"),
        ParagraphUnit(text="Обычный абзац", role="body", paragraph_id="p0001"),
    ]

    relations, report = build_paragraph_relations(paragraphs)

    assert relations == []
    assert report.total_relations == 0
    assert report.rejected_candidate_count == 1
    assert report.decisions[0].decision == "reject"
    assert report.decisions[0].relation_kind == "caption_attachment"
    assert report.decisions[0].reasons == ("caption_without_preceding_asset",)


def test_build_editing_jobs_preserves_marker_count_after_relation_grouping():
    paragraphs = [
        ParagraphUnit(text="Содержание", role="body", structural_role="toc_header", paragraph_id="p0000"),
        ParagraphUnit(text="Глава 1........ 12", role="body", structural_role="toc_entry", paragraph_id="p0001"),
        ParagraphUnit(text="Глава 2........ 18", role="body", structural_role="toc_entry", paragraph_id="p0002"),
    ]

    blocks = build_semantic_blocks(paragraphs, max_chars=200)
    jobs = build_editing_jobs(blocks, max_chars=200)

    assert len(blocks) == 1
    assert jobs[0]["paragraph_ids"] == ["p0000", "p0001", "p0002"]
    assert str(jobs[0]["target_text_with_markers"]).count("[[DOCX_PARA_") == 3


def test_build_marker_wrapped_block_text_preserves_paragraph_ids_and_boundaries():
    paragraphs = [
        ParagraphUnit(text="Глава", role="heading", paragraph_id="p0001", heading_level=1),
        ParagraphUnit(text="Основной текст", role="body", paragraph_id="p0002"),
    ]

    result = build_marker_wrapped_block_text(paragraphs)

    assert result == "[[DOCX_PARA_p0001]]\n# Глава\n\n[[DOCX_PARA_p0002]]\nОсновной текст"
