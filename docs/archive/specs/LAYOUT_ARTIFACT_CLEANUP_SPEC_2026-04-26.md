# PDF/DOCX Layout Artifact Cleanup Specification

Дата: 2026-04-26

## Цель

Добавить консервативный слой очистки layout artifacts после извлечения DOCX paragraphs и до построения `source_text`, semantic blocks и editing jobs.

Основной практический мотив: PDF, импортированный через LibreOffice Writer PDF import, часто превращается в DOCX с большим числом text boxes. Вместе с основным текстом в поток попадают repeated headers, footers, page numbers, декоративные плашки, running titles и другие элементы верстки. Перед переводом приложение должно передавать в AI преимущественно содержательный текст, без очевидных служебных элементов страницы.

## Ключевое Архитектурное Решение

Cleanup является generic DOCX post-extraction stage, а не отдельным PDF pipeline.

Правильный поток:

```text
uploaded PDF/DOC/DOCX
  -> processing_runtime.normalize_uploaded_document()
  -> normalized DOCX bytes
  -> document_extraction.extract_document_content_with_normalization_reports()
  -> raw/logical ParagraphUnit list
  -> layout_artifact_cleanup.clean_paragraph_layout_artifacts()
  -> cleaned ParagraphUnit list + cleanup report
  -> structure recognition / semantic blocks / jobs
```

Запрещенный поток:

```text
uploaded PDF
  -> direct PDF layout parser
  -> separate PDF paragraph model
  -> PDF-only translation preparation path
```

Обоснование: текущий ingestion boundary уже приводит PDF к каноническому DOCX. Cleanup должен улучшать качество DOCX extraction для всех источников, а не создавать второй document model.

## Область Изменений

### Основные файлы

- `document_extraction.py`
- новый модуль `document_layout_cleanup.py` или локальные функции в `document_extraction.py` с последующим выносом при росте сложности
- `models.py` для cleanup report dataclass, если отчет нужен вне extraction layer
- `application_flow.py` / `preparation.py` для прокидывания метрик отчета в UI summary
- `tests/test_document_extraction.py`
- отдельный `tests/test_document_layout_cleanup.py`, если логика будет вынесена в модуль

### Файлы, которые не должны получать PDF-specific ветвления

- `document_pipeline.py`
- `formatting_transfer.py`
- `document_pipeline_*`
- AI prompt construction, кроме использования уже очищенного `source_text`

## Термины

- **Layout artifact**: текстовый элемент, порожденный версткой страницы, а не содержанием документа: номер страницы, repeated header/footer, running title, watermark text, decorative cover label, repeated URL/footer contact.
- **Content paragraph**: paragraph, который должен переводиться или сохраняться как часть документа.
- **Conservative cleanup**: удаляются только high-confidence artifacts. Сомнительные элементы остаются в тексте.
- **Repeated artifact**: short normalized text, встречающийся много раз в документе и соответствующий safe artifact predicate.

## Функциональные Требования

### FR-1. Cleanup должен выполняться после extraction, boundary normalization и protection-stage для title/headings

Cleanup должен запускаться после того, как:

- DOCX bytes валидированы;
- raw DOCX blocks извлечены;
- text boxes превращены в raw/logical paragraphs;
- paragraph boundary normalization завершена;
- inline break normalization завершена;
- выполнены deterministic paragraph-level protection transforms, которые могут повысить роль paragraph до protected state:
  - `promote_short_standalone_headings(paragraphs)`;
  - `normalize_front_matter_display_title(paragraphs)`.

Рекомендуемая точка в `document_extraction.extract_document_content_with_normalization_reports()`:

```python
paragraphs = _build_logical_paragraph_units(normalized_blocks)
paragraphs = _normalize_inline_break_paragraphs(paragraphs)
promote_short_standalone_headings(paragraphs)
normalize_front_matter_display_title(paragraphs)
paragraphs, cleanup_report = clean_paragraph_layout_artifacts(paragraphs)
```

Если cleanup меняет список paragraphs, subsequent structure recognition должен видеть уже cleaned paragraphs.

Причина такого порядка: cleanup не должен удалить paragraph, который на pre-cleanup этапе ещё выглядит как `body`, но после deterministic role/title normalization становится защищённым heading/display-title paragraph.

### FR-2. Cleanup должен быть generic DOCX, не PDF-specific

Нельзя проверять `source_format == "pdf"` внутри core extraction/cleanup path.

Допустимо:

- использовать свойства paragraph текста, style, structural role, origin metadata;
- использовать признаки DOCX XML/textbox origin, если они generic;
- добавить source metadata в `RawParagraph`/`ParagraphUnit`, например `layout_origin="textbox" | "paragraph"`, но не `pdf_origin=True`.

Для MVP textbox/direct-paragraph provenance считается обязательной частью origin metadata, если cleanup использует textbox-derived heuristics для repeated layout artifacts. Этот признак должен описывать generic DOCX extraction origin, а не тип исходного загруженного файла.

### FR-3. Удалять standalone page numbers

Cleanup должен удалять high-confidence page number paragraphs, например:

```text
1
12
- 12 -
— 12 —
Page 12
page 12
Стр. 12
стр. 12
С. 12
12 / 40
12 of 40
```

Ограничения:

- удалять только short standalone paragraphs;
- не удалять числовые list items с явным list metadata;
- не удалять headings/TOC entries вида `Chapter 12`, `Revelation 13`, `2026 Outlook`;
- не удалять номера внутри table content.

### FR-4. Удалять repeated running headers/footers

Cleanup должен удалять repeated short text, если выполняются все условия:

- normalized text встречается не менее `min_repeat_count`, по умолчанию `3`;
- text короткий: например `<= 80` символов или `<= 12` слов;
- text не классифицирован как heading explicit;
- text не является caption/table/list;
- text соответствует одному из safe artifact predicates:
  - содержит URL/email/contact-like footer;
  - совпадает с document title и повторяется много раз;
  - является author/title running header pattern;
  - содержит только короткую служебную строку без terminal sentence punctuation;
  - расположен рядом с page number artifacts, если доступен origin/order context.

Примеры кандидатов:

```text
Are We In the End Times?
Jared Brock
www.jaredbrock.com
Draft
Confidential
```

### FR-5. Не удалять содержательные повторения

Cleanup не должен удалять:

- заголовки разделов, если они встречаются только в TOC и body;
- first front-matter display title, который был повышен существующей deterministic logic до document title heading;
- short standalone heading, который был повышен существующей deterministic logic до `role="heading"`;
- цитаты, которые повторяются как художественный прием;
- короткие абзацы с terminal punctuation, если это normal prose;
- list items;
- captions;
- table paragraphs;
- epigraph/attribution/dedication structural roles;
- TOC entries по умолчанию.

Пример: `Introduction` встречается в TOC и как heading body. Это не repeated header/footer, если встречается 2 раза.

### FR-6. TOC не удаляется по умолчанию

Оглавление должно оставаться частью документа в translation/document-preserving mode.

Допускается отдельная future option:

```toml
[layout_artifact_cleanup]
drop_toc = false
```

В рамках MVP cleanup TOC только маркируется существующей логикой (`toc_header`, `toc_entry`) и не удаляется.

### FR-7. Cleanup должен возвращать отчет

Нужно добавить отчет с минимальными метриками:

```python
@dataclass
class LayoutArtifactCleanupReport:
    original_paragraph_count: int
    cleaned_paragraph_count: int
    removed_paragraph_count: int
    removed_page_number_count: int
    removed_repeated_artifact_count: int
    removed_empty_or_whitespace_count: int
    decisions: list[LayoutArtifactCleanupDecision]

@dataclass(frozen=True)
class LayoutArtifactCleanupDecision:
    original_source_index: int
    original_paragraph_id: str
    origin_raw_indexes: tuple[int, ...]
    text_preview: str
    action: str  # keep/remove
    reason: str
    confidence: str  # high/medium/low
    normalized_text: str
    repeat_count: int = 1
```

`LayoutArtifactCleanupDecision` должен ссылаться на pre-cleanup identity, а не на reassigned post-cleanup `source_index`. Это нужно для traceability удалённых paragraphs.

Cleanup API должен явно возвращать новый список и отчет:

```python
cleaned_paragraphs, cleanup_report = clean_paragraph_layout_artifacts(paragraphs)
```

Extraction API должен прокидывать cleanup report как отдельную часть результата, а не скрывать его только во внутренних локальных переменных. Предпочтительный контракт для `extract_document_content_with_normalization_reports()`:

```python
paragraphs, image_assets, boundary_report, relations, relation_report, cleanup_report
```

Если проект позже перейдёт с tuple на dedicated result object, cleanup report должен остаться first-class полем этого результата. Молчаливое скрытие cleanup report только в preparation layer запрещено.

Отчет должен быть доступен в `PreparedDocumentData` / `PreparedRunContext` аналогично normalization/relation reports.

### FR-8. UI summary должен показывать cleanup metrics

В preparation summary добавить метрики, если были удаления:

```text
Очистка: удалено 18 служебных элементов (12 номеров страниц, 6 повторяющихся колонтитулов).
```

Для нулевой очистки не нужно шуметь в UI.

В machine-readable metrics добавить:

- `layout_cleanup_removed_count`
- `layout_cleanup_page_number_count`
- `layout_cleanup_repeated_artifact_count`

Предпочтительно добавить отдельный flatten helper рядом с существующими helpers normalization/relation metrics, чтобы эти поля не собирались вручную в нескольких call sites.

### FR-9. Debug artifact для cleanup decisions

Если включены debug artifacts для cleanup, cleanup должен писать JSON artifact в `.run/layout_cleanup_reports/`.

Формат аналогичен текущим reports:

```json
{
  "version": 1,
  "source_file": "Are_We_In_The_End_Times.docx",
  "source_hash": "...",
  "original_paragraph_count": 1045,
  "cleaned_paragraph_count": 377,
  "removed_paragraph_count": 20,
  "decisions": [...]
}
```

Artifact нужен для ручной проверки false positives/false negatives.

Как и другие runtime debug artifacts в репозитории, этот artifact type должен иметь:

- retention constants в `runtime_artifact_retention.py`;
- writer, который после записи вызывает `prune_artifact_dir(...)`;
- регистрацию в `scripts/_run_cleanup_now.py`.

### FR-10. Cleanup должен быть отключаемым конфигом

Добавить отдельную config section в существующем стиле репозитория:

```toml
[layout_artifact_cleanup]
enabled = true
min_repeat_count = 3
max_repeated_text_chars = 80
save_debug_artifacts = true
```

Новые поля должны быть встроены в существующую config architecture:

- `config.toml` section;
- `AppConfig` typed fields;
- dedicated resolver в стиле `config_structure_sections.py`;
- optional env overrides, если проект применяет их для соседних extraction/structure flags.

Если disabled, cleanup возвращает исходный list и report с нулевыми removals.

### FR-11. Cleanup должен сохранять source identity и formatting restoration compatibility

Удаление paragraphs меняет набор source paragraphs, но не должно менять uploaded source token.

`ParagraphUnit` после cleanup должен сохранять:

- reassigned `source_index`, последовательный после `_assign_paragraph_identity()`;
- reassigned `paragraph_id`, соответствующий новому `source_index`;
- `origin_raw_indexes` и `origin_raw_texts` для диагностики;
- formatting metadata для оставшихся paragraphs.

Важно различать два identity слоя:

- pre-cleanup identity для report/debug traceability: `original_source_index`, `original_paragraph_id`, `origin_raw_indexes`;
- post-cleanup identity для downstream processing: reassigned `source_index` и `paragraph_id` surviving paragraphs.

Если cleanup удаляет paragraph, formatting restoration не должен пытаться восстановить его в output. Это ожидаемо.

### FR-12. Fail-open error handling

Cleanup является quality-improvement stage и не должен делать extraction unusable из-за локальной ошибки cleanup logic.

Обязательный runtime contract для MVP:

- если cleanup encounters unexpected paragraph shape, malformed metadata или internal exception, extraction path не должен падать только из-за cleanup;
- в случае cleanup failure downstream stages получают исходный список paragraphs без удаления artifacts;
- cleanup report возвращается даже при деградации и явно отражает skipped/fallback state.

Минимальный fail-open contract:

```python
@dataclass
class LayoutArtifactCleanupReport:
    ...
    cleanup_applied: bool = False
    skipped_reason: str | None = None
    error_code: str | None = None
```

Ожидаемое поведение:

- normal path: `cleanup_applied = True`, `skipped_reason = None`, `error_code = None`;
- cleanup disabled by config: `cleanup_applied = False`, `skipped_reason = "disabled"`, `error_code = None`;
- cleanup internal failure: `cleanup_applied = False`, `skipped_reason = "cleanup_failed"`, `error_code` содержит deterministic machine-readable code.

Допустимые MVP error codes:

- `unexpected_paragraph_shape`;
- `invalid_cleanup_metadata`;
- `cleanup_runtime_error`.

Fail-open fallback не должен подменяться silent failure без report/log signal.

### FR-13. Language-neutral behavior и ограниченная language-specific поддержка

MVP cleanup должен быть в первую очередь language-neutral, а не language-classification-driven.

Приоритетные predicates для cleanup:

- repeated identical short normalized text;
- numeric page-number shapes;
- URL/email/contact-like footer text;
- repeated boilerplate tokens из маленького explicit allowlist.

Language-specific aliases допустимы только как conservative расширение к language-neutral predicates.

Для MVP explicitly covered language-specific tokens/patterns:

- English page-number aliases: `page`, `p.`;
- Russian page-number aliases: `стр.`, `с.`;
- English and Russian boilerplate tokens, перечисленные в spec.

Для документов на других языках cleanup всё равно должен корректно работать на language-neutral predicates. Отсутствие language-specific alias не является ошибкой cleanup и не должно приводить к агрессивному удалению paragraphs по догадке.

## Нефункциональные Требования

### NFR-1. Консервативность важнее агрессивности

False positive (удалили контент) хуже false negative (оставили мусор). MVP должен удалять только high-confidence artifacts.

### NFR-2. Deterministic behavior

Cleanup должен быть deterministic: одинаковый input paragraphs -> одинаковый cleaned paragraphs/report.

Не использовать AI для cleanup MVP.

### NFR-3. Локальность изменений

Изменения должны быть локализованы в extraction/preparation boundary. Нельзя добавлять cleanup branches в processing pipeline.

### NFR-4. Производительность

Cleanup должен быть O(n) или O(n log n) по числу paragraphs. Для документов с 10k paragraphs overhead должен быть мал по сравнению с LibreOffice conversion и AI processing.

### NFR-5. Traceability

Каждое удаление должно иметь reason/confidence в report. Без trace невозможно безопасно итеративно настраивать эвристику.

Reason strings и repeated-artifact predicates должны быть перечислимыми и deterministic, а не свободным текстом реализации. Для MVP нужно использовать фиксированный набор reason codes/labels, например: `page_number_pattern`, `repeated_url_footer`, `repeated_boilerplate_token`, `repeated_title_header`, `disabled`, `protected_role_keep`.

### NFR-6. Backward compatibility

Для обычных DOCX без repeated layout artifacts behavior должен оставаться прежним.

Если cleanup удаляет что-то в existing real-document tests, это должно быть явно подтверждено обновленными snapshots/acceptance.

### NFR-7. Fail-open resilience

Cleanup failure хуже, чем пропущенный layout artifact, только если он ломает extraction pipeline. Поэтому MVP должен быть fail-open: при любой cleanup-specific ошибке документ продолжает обработку без artifact removal, но с traceable report/log signal.

### NFR-8. Language neutrality over aggressive language heuristics

MVP не должен зависеть от полного определения языка документа. Если paragraph не подпадает под high-confidence language-neutral predicate или под explicit supported alias list, paragraph должен быть сохранён.

### NFR-9. Observability

Помимо debug artifact, cleanup должен оставлять lightweight operational signals для сравнения документов и расследования regressions.

Минимальный observability contract для MVP:

- preparation/extraction path emit'ит structured log event для cleanup outcome;
- event включает counters removals и fallback/error fields;
- отсутствие removals также может логироваться, но без обязательного UI noise.

Рекомендуемые event fields:

- `layout_cleanup_enabled`;
- `layout_cleanup_applied`;
- `layout_cleanup_removed_count`;
- `layout_cleanup_page_number_count`;
- `layout_cleanup_repeated_artifact_count`;
- `layout_cleanup_skipped_reason`;
- `layout_cleanup_error_code`.

### NFR-10. Performance guardrails for large documents

Помимо target complexity O(n) / O(n log n), MVP должен избегать implementation choices, которые practically деградируют на больших документах.

Обязательные guardrails:

- не выполнять pairwise paragraph-to-paragraph comparisons по всему документу;
- repeated artifact detection должен строиться через normalized frequency map, а не через nested scan;
- page number detection должен быть local predicate per paragraph;
- report building не должен повторно сканировать весь документ более необходимого числа проходов.

Практическая цель для large synthetic input:

- документ порядка 10k paragraphs не должен вызывать pathological slowdown;
- cleanup overhead должен оставаться малым относительно DOCX parse, LibreOffice conversion и AI processing;
- performance validation может быть оформлена как targeted synthetic test/benchmark helper, а не как flaky strict microbenchmark SLA.

## Предлагаемый Алгоритм MVP

### Шаг 1. Нормализация текста для matching

```python
def normalize_layout_artifact_text(text: str) -> str:
    text = strip_markdown_wrappers(text)
    text = normalize_unicode_quotes_dashes(text)
    text = collapse_whitespace(text)
    text = strip_outer_punctuation(text)
    return text.casefold()
```

Важно: matching normalization не должен менять actual paragraph text, только fingerprint.

### Шаг 2. Page number detector

High-confidence detector:

```python
PAGE_NUMBER_PATTERNS = [
    r"^\d{1,4}$",
    r"^[\-–—]\s*\d{1,4}\s*[\-–—]$",
    r"^(?:page|p\.)\s+\d{1,4}$",
    r"^(?:стр\.|с\.)\s*\d{1,4}$",
    r"^\d{1,4}\s*/\s*\d{1,4}$",
    r"^\d{1,4}\s+of\s+\d{1,4}$",
]
```

Guardrails:

- max chars <= 20;
- role must be body;
- no list metadata;
- not inside TOC structural role.

### Шаг 3. Candidate frequency map

Build frequency only for candidate-safe paragraphs:

```python
candidate = (
    role == "body"
    and structural_role == "body"
    and len(normalized_text) <= max_repeated_text_chars
    and word_count <= 12
    and not terminal_sentence_like(text)
)
```

Then remove repeated artifacts only if repeat_count >= min_repeat_count and one of safe predicates is true.

Для MVP constants должны быть explicit и testable:

- `min_repeat_count = 3`;
- `max_repeated_text_chars = 80`;
- `max_repeated_word_count = 12`;
- `title_first_paragraph_scan_limit = 12`.

### Шаг 4. Safe repeated artifact predicates

High-confidence examples:

- contains URL/email:
  - `http://`, `https://`, `www.`, `@domain`
- contains document title repeated >= 3 and the same normalized text appears in first `title_first_paragraph_scan_limit` paragraphs;
- all occurrences are short and identical;
- contains known boilerplate tokens:
  - `confidential`, `draft`, `copyright`, `all rights reserved`
- optional Russian equivalents:
  - `конфиденциально`, `черновик`, `все права защищены`

`terminal_sentence_like(text)` для MVP должен быть deterministic helper: true, если trimmed paragraph оканчивается на один из terminal punctuation markers `.`, `!`, `?`, `…`, кроме случаев page-number pattern match. Это нужно, чтобы prose-like short repetitions не попадали в artifact bucket.

`author/title running header pattern` в MVP не должен быть абстрактной эвристикой. Разрешённый deterministic вариант: короткий normalized text, который либо совпадает с repeated document title fingerprint, либо состоит из 2-6 слов без terminal punctuation и встречается не менее `min_repeat_count`, причём не является heading/list/caption/table/TOC paragraph.

### Шаг 5. Keep protected roles

Never remove paragraphs with:

```python
protected_roles = {"heading", "caption", "list", "table", "image"}
protected_structural_roles = {"toc_header", "toc_entry", "epigraph", "attribution", "dedication"}
```

Exception: page number pattern with body role only.

### Шаг 6. Reassign paragraph identity after cleanup

After filtering, call existing identity assignment equivalent:

```python
for index, paragraph in enumerate(cleaned):
    _assign_paragraph_identity(paragraph, index)
```

Origin metadata remains from original extraction.

Cleanup stage не должен менять uploaded file token, source hash и другие identity markers uploaded source; меняется только paragraph-level downstream identity surviving paragraphs.

## Тестовые Требования

### Unit tests: page numbers

- removes `1`, `- 12 -`, `Page 4`, `стр. 5`, `12 / 40`.
- keeps `Chapter 12`.
- keeps list item `1. Real item`.
- keeps TOC entry `Introduction........4`.

### Unit tests: repeated headers/footers

- removes repeated `www.example.com` appearing 5 times.
- removes repeated document title appearing as short body artifact on many pages, but keeps first title if protected as heading or first display title.
- removes repeated `Confidential`.
- keeps repeated quote with punctuation if not safe artifact.
- keeps `Introduction` when repeated only twice.

### Integration tests: extraction cleanup

Synthetic DOCX:

- body content paragraphs;
- textbox paragraphs simulating per-page repeated header/footer;
- page numbers;
- real content.

Expected:

- content remains;
- page numbers removed;
- repeated footer removed;
- cleanup report counters are correct.

### Unit/integration tests: fail-open behavior

- если cleanup helper raises internal exception, extraction возвращает исходные paragraphs и cleanup report с `cleanup_applied = False`;
- report содержит deterministic `skipped_reason` / `error_code`;
- downstream `build_document_text()` и job construction продолжают работать.

### Unit tests: language-neutral behavior

- repeated URL/footer artifact удаляется независимо от языка surrounding content;
- numeric standalone page number удаляется независимо от языка surrounding content;
- short repeated paragraph на unsupported language без safe predicate остаётся preserved.

### Performance test/helper: large synthetic document

- synthetic input на порядке 10k paragraphs не должен требовать quadratic scan pattern;
- test/helper должен подтверждать, что cleanup проходит через frequency-map style logic и завершает run без pathological slowdown.

### Regression test: Are_We_In_The_End_Times PDF-derived flow

Preferred as debug/integration helper, not necessarily unit path requiring real LibreOffice.

Options:

1. Store a small synthetic DOCX fixture that mimics LibreOffice text boxes and repeated artifacts.
2. For real PDF validation, use WSL-only/manual validation command and assert metrics qualitatively:
   - source_chars is large enough;
   - page-number artifacts are not present in first-level `source_text` as standalone blocks;
   - repeated footer/title count is reduced.

Не добавлять unit test, который требует реального LibreOffice, в обычный test path.

## Acceptance Criteria

### AC-1. Main content is preserved

После cleanup `Are_We_In_The_End_Times.pdf` должен давать большой `source_text`, а не image placeholder only.

Минимальная проверка:

```text
source_chars > 30000
paragraph_count > 100
jobs > 10
```

### AC-2. Page numbers are removed

Standalone page number paragraphs не попадают в `build_document_text()` и `build_editing_jobs()`.

### AC-3. Repeated headers/footers are removed

High-confidence repeated footer/header artifacts удаляются и отражаются в cleanup report.

### AC-4. TOC remains by default

TOC entries сохраняются в translation mode и остаются marked as `toc_header`/`toc_entry`.

### AC-5. No PDF-specific core branch

Cleanup не проверяет source format PDF и не создает PDF-specific pipeline.

### AC-6. Report and UI metrics available

Preparation summary содержит cleanup metrics, если были удаления.

Под этим подразумевается:

- cleanup report доступен в extraction result, `PreparedDocumentData` и `PreparedRunContext`;
- machine-readable summary содержит cleanup metric fields;
- UI summary добавляет cleanup status note только при `removed_paragraph_count > 0`.

### AC-6a. Fail-open fallback is observable

Если cleanup disabled или cleanup runtime error приводит к fallback, это видно в cleanup report и structured logs; extraction при этом остаётся usable и продолжает подготовку документа без cleanup removals.

### AC-6b. Language-neutral behavior preserved

Для документа на unsupported language cleanup всё ещё удаляет only high-confidence language-neutral artifacts и не начинает агрессивно удалять short repeated content по guessed language rules.

### AC-7. Existing extraction tests pass

```bash
bash scripts/test.sh tests/test_document_extraction.py -vv
bash scripts/test.sh tests/test_processing_runtime.py -vv
bash scripts/test.sh tests/test_application_flow.py -vv
bash scripts/test.sh tests/test_preparation.py -vv
bash scripts/test.sh tests/test_app_preparation.py -vv
```

### AC-8. False positive guardrails covered

Тесты подтверждают, что cleanup не удаляет headings, captions, lists, TOC entries и содержательные повторения.

## План Реализации

### Этап 1. Contracts

- [ ] Добавить `LayoutArtifactCleanupReport` и `LayoutArtifactCleanupDecision`.
- [ ] Решить location: `models.py` или новый `document_layout_cleanup.py`.
- [ ] Добавить `layout_artifact_cleanup` section, typed config fields и resolver.
- [ ] Зафиксировать extraction API contract для `cleanup_report`.

### Этап 2. Cleanup engine

- [ ] Реализовать text normalization для matching.
- [ ] Реализовать standalone page number detector.
- [ ] Реализовать repeated artifact frequency detector.
- [ ] Реализовать protected role guardrails.
- [ ] Реализовать report decisions.
- [ ] Реализовать fail-open fallback и deterministic error codes.
- [ ] Отделить language-neutral predicates от explicit language-specific aliases.

### Этап 3. Integration into extraction

- [ ] Встроить cleanup после `_normalize_inline_break_paragraphs()`, `promote_short_standalone_headings()` и `normalize_front_matter_display_title()`.
- [ ] Переназначить paragraph identity после cleanup.
- [ ] Прокинуть cleanup report из `extract_document_content_with_normalization_reports()`.
- [ ] Обновить callers и dataclasses.

### Этап 4. UI/preparation metrics

- [ ] Добавить cleanup report в `PreparedDocumentData`.
- [ ] Добавить cleanup report в `PreparedRunContext`.
- [ ] Добавить flatten metrics helper.
- [ ] Добавить status note при removed_count > 0.
- [ ] Обновить preparation/app summary builders и связанные tests/stubs.
- [ ] Добавить structured log event / observability fields для cleanup outcome.

### Этап 5. Tests

- [ ] Unit tests for page number detector.
- [ ] Unit tests for repeated artifact detector.
- [ ] Integration extraction tests with synthetic text boxes.
- [ ] Regression tests for protected roles.
- [ ] Fail-open tests для cleanup exceptions и disabled mode.
- [ ] Language-neutral behavior tests.
- [ ] Large synthetic document performance helper/test.
- [ ] Обновить tuple/result stubs в `tests/test_preparation.py`, `tests/test_application_flow.py`, `tests/test_real_document_validation_corpus.py` и связанных integration tests.
- [ ] Targeted canonical tests.

### Этап 6. Manual/real validation

- [ ] Через WSL runtime нормализовать `Are_We_In_The_End_Times.pdf`.
- [ ] Проверить paragraph/source/job metrics до/после cleanup.
- [ ] Проверить sample start/end текста.
- [ ] Проверить cleanup report decisions на false positives.

## Риски И Ограничения

### R-1. False positives

Риск: удаление короткого содержательного paragraph. Митигация: conservative predicates, protected roles, debug report.

### R-2. Нехватка геометрии

Без page geometry некоторые headers/footers неотличимы от короткого content. Митигация MVP: удалять только repeated high-confidence artifacts.

### R-3. LibreOffice output нестабилен

Разные версии LibreOffice могут менять textbox ordering и duplication. Митигация: тестировать на generic textboxes, не на exact LibreOffice XML snapshot.

### R-4. TOC policy зависит от режима

Для перевода документа TOC нужен, для audiobook/clean prose может быть нежелателен. MVP: TOC сохраняется, future config для prose-only cleanup.

### R-5. Cleanup runtime failures

Риск: новый cleanup layer падает на unexpected paragraph metadata и ломает extraction path. Митигация: fail-open contract, deterministic error codes, structured log event, cleanup report со skipped/error state.

### R-6. Language overfitting

Риск: слишком language-specific heuristics начнут удалять короткие абзацы в unsupported languages. Митигация: language-neutral predicates first, small explicit alias list, conservative keep-on-uncertainty behavior.

### R-7. Performance regression on large documents

Риск: repeated artifact detector будет реализован через nested comparisons и начнёт деградировать на тысячах paragraphs. Митигация: frequency-map design, targeted synthetic large-document test/helper.

## Out Of Scope для MVP

- Direct PDF parsing через PyMuPDF/pdfplumber.
- OCR.
- AI-based cleanup classification.
- Полная page geometry reconstruction.
- Автоматическое удаление TOC.
- Aggressive boilerplate removal без report.

## Definition Of Done

Доработка завершена, когда после DOCX/PDF extraction выполняется deterministic conservative cleanup, standalone page numbers и high-confidence repeated headers/footers удаляются до построения `source_text` и jobs, UI показывает cleanup metrics при удалениях, debug report позволяет проверить каждое решение, а targeted tests подтверждают сохранение основного контента и защиту от false positives.
