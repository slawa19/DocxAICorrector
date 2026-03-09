from pathlib import Path


followup_spec_path = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "Спецификация follow-up - quality hardening для image pipeline.md"
)


def test_followup_image_spec_structure():
    assert followup_spec_path.is_file()

    spec_text = followup_spec_path.read_text(encoding="utf-8")

    assert "# Спецификация v3: Quality Hardening для Image Pipeline (Архитектура 2026)" in spec_text
    assert "## 0. Назначение документа" in spec_text
    assert "## 1. Scope этапа модернизации" in spec_text
    assert "## 2. Архитектурные изменения (2026 Standards)" in spec_text
    assert "## 3. Практические промпты (Best Practices для gpt-image-1)" in spec_text
    assert "## 4. План миграции кода" in spec_text

    assert "Перевод генерации с `dall-e-3` на `gpt-image-1`." in spec_text
    assert "Внедрение **Smart Routing (Умный Bypass)**" in spec_text
    assert "переход на чистый `images.generate`" in spec_text
    assert "пайплайн `semantic_redraw_structured` теперь использует `gpt-image-1`" in spec_text
    assert "`dense_document_or_table` -> активирует Bypass" in spec_text

    assert "Return JSON with keys" in spec_text or '"text_node_count": <int>' in spec_text
    assert '"recommended_route": "gpt-image-1" | "bypass"' in spec_text
    assert '"extracted_text": "<ВЕСЬ текст с картинки для передачи в генератор>"' in spec_text
    assert "client.images.generate(" in spec_text
    assert 'model="gpt-image-1"' in spec_text

    assert "Тестирование кириллицы" in spec_text
    assert "Факты vs Манипуляции" in spec_text
    assert "Mermaid.js" in spec_text
    assert "## 5. Минимальный Spike, внедренный в кодовую базу" in spec_text
    assert "## 6. Рекомендации по тестированию Spike" in spec_text
    assert "## 7. Будущий рефакторинг, если Spike сработает" in spec_text
