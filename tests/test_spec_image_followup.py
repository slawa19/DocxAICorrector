from pathlib import Path


followup_spec_path = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "Спецификация follow-up - quality hardening для image pipeline.md"
)


def test_followup_image_spec_structure():
    assert followup_spec_path.is_file()

    spec_text = followup_spec_path.read_text(encoding="utf-8")

    assert "# Спецификация follow-up: quality hardening для image pipeline" in spec_text
    assert "## 1. Scope follow-up этапа" in spec_text
    assert "## 2. Цели этапа" in spec_text
    assert "## 3. Не входит в scope" in spec_text
    assert "## 6. Критерии приемки follow-up спецификации" in spec_text
    assert "## 7. Объективная проверка / test plan" in spec_text

    assert "улучшение качества `image_analysis` эвристик" in spec_text
    assert "улучшение качества `image_generation` эвристик" in spec_text
    assert "усиление извлечения `text/label signals`" in spec_text
    assert "quality tuning для `prompt_key`, `render_strategy`, thresholds" in spec_text
    assert "возможное расширение UI / run-log" in spec_text
    assert "дальнейший hardening по `false positive / false negative`" in spec_text

    assert "следующий этап после Level 1" in spec_text
    assert "существует **отдельный документ**, посвященный именно оставшимся image follow-up доработкам;" in spec_text
    assert "в документе есть отдельный test plan, который можно проверить автоматическим тестом." in spec_text
    assert "pytest-тест читает markdown-файл follow-up спецификации;" in spec_text
