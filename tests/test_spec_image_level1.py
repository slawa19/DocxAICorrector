from pathlib import Path


spec_path = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "archive"
    / "specs"
    / "Спецификация разработки_ Level 1 post-check для image semantic-redraw-mode.md"
)


def test_level1_spec_structure():
    assert spec_path.is_file()

    spec_text = spec_path.read_text(encoding="utf-8")

    assert "## 14.2. Отдельный checklist по текущему статусу реализации" in spec_text
    assert "### Уже реализовано" in spec_text
    assert "### Остается / требует отдельного следующего шага" in spec_text
    assert "- [x] Data contracts для image pipeline вынесены в `models.py`." in spec_text
    assert "- [ ] Улучшить качество `image_analysis` эвристик" in spec_text
    assert "- [ ] Улучшить качество `image_generation` эвристик" in spec_text

    assert "## 14.3. Критерии приемки для обновления этой спецификации" in spec_text
    assert "1. в документе есть **отдельный** checklist по текущему статусу реализации;" in spec_text
    assert "6. наличие этих секций и ключевых формулировок может быть проверено автоматическим тестом." in spec_text

    assert "## 14.4. Объективная проверка / test plan" in spec_text
    assert "улучшение качества `image_analysis` /" in spec_text
    assert "`image_generation` относится к следующей итерации" in spec_text
    assert "это отдельная итерация улучшения качества, а не незакрытый обязательный scope текущего merge." in spec_text
