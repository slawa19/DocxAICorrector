# DOCX Formatting Regression Fix Plan

## Status

Implemented on 2026-03-15.

### Implementation Progress

- [x] Added regression tests for caption -> heading, heading -> body, multi-variant DOCX reinsertion, and final pipeline assembly order.
- [x] Fixed semantic caption-vs-heading precedence so caption style no longer loses to heuristic heading detection.
- [x] Hardened heading fallback detection for mixed formatting and removed justify-only heading promotion.
- [x] Replaced compare/manual-review vertical label stacks with side-by-side multi-image reinsertion in a shared layout container.
- [x] Stored compare/manual-review variant names in hidden image metadata (`docPr/@descr`) instead of visible body labels.
- [x] Updated regression tests that previously locked visible bold labels.
- [x] Updated delivery-contract documentation in `docs/WORKFLOW_AND_IMAGE_MODES.md`.
- [x] Unified multi-variant reinsertion across placeholder-only, inline-run, and split-run paths so all multi-variant DOCX insertions use the same stable table container.
- [x] Added regression coverage for inherited outline-level heading detection and Russian alias heading styles.
- [x] Added an extraction -> markdown -> normalization regression test for caption preservation.

## Problem Summary

Observed regressions in the final edited DOCX:

1. image and table captions are sometimes promoted to headings;
2. real headings are sometimes downgraded to plain body text;
3. compare and keep-all image variants are inserted with bold visible labels and vertical breaks, which degrades layout.

## Diagnosis

### 1. Captions becoming headings

Primary fault is in semantic extraction, before DOCX generation.

- `document.py` computes `heading_level` before any caption-style short-circuit, and `classify_paragraph_role()` prefers `heading_level` over caption style;
- `document.py` only reclassifies adjacent captions from `body` to `caption`, so paragraphs that already became `heading` are never corrected downstream;
- `models.py` then renders that semantic role as markdown heading syntax;
- `document_pipeline.py` later normalizes the generated DOCX using those roles, so the final DOCX faithfully amplifies the earlier semantic mistake.

Impact:

- this is not only a DOCX styling bug;
- this is an upstream semantic-role bug that already corrupts the markdown representation.

### 2. Headings becoming body text

Primary fault is also in semantic extraction, before DOCX generation.

- `document.py` detects headings from style names, outline levels, and a fallback heuristic;
- support for `Title`, `Subtitle`, localized heading styles matching `heading|заголовок`, and inherited `outlineLvl` already exists, so the main weakness is not complete absence of metadata support;
- the fallback heuristic is too strict for longer or partially bold real-world headings, yet also too permissive for some justified paragraphs because `jc="both"` currently counts as heading-compatible alignment;
- if heading detection fails, the paragraph is treated as ordinary body text, so markdown loses heading markers and the final DOCX can only normalize it as body text.

Impact:

- again, this is not a Pandoc-only or final DOCX-only bug;
- the semantic layer is already losing heading structure.

### 3. Compare and keep-all variants getting ugly bold captions

Primary fault is in final DOCX image reinsertion.

- `document.py` resolves compare/manual-review insertions as `(label, image_bytes)` tuples;
- there are two reinsertion paths, and both render each label as bold text followed by line breaks and then an image;
- this forces a vertical stacked layout with visible labels in the document body;
- the current behavior is also locked in by tests, so it will not regress back to the desired layout unless tests are changed together with code.

Impact:

- this is a final DOCX reconstruction bug;
- the data contract for variant names can stay, but the visual rendering contract should change.

## Root Cause Map

### Semantic stage

- `document.py`: paragraph role classification, heading detection, caption reclassification;
- `models.py`: conversion of `heading` role into markdown heading syntax.

### Final DOCX stage

- `document_pipeline.py`: convert markdown -> preserve paragraph properties -> normalize semantic output -> reinsert images;
- `document.py`: compare/manual-review image reinsertion layout and label rendering.

## Proposed Fix Scope

### A. Fix semantic role precedence for captions vs headings

Change the extraction rules so caption evidence wins over weak heading evidence, without demoting truly explicit headings.

Planned changes:

1. Short-circuit explicit caption styles before `_extract_heading_level()` or otherwise ensure caption styles cannot acquire a heuristic `heading_level`.
2. Keep explicit heading styles and explicit outline levels authoritative, but prevent caption evidence from losing to the fallback heading heuristic.
3. Expand adjacency reclassification so it can revisit heuristic `heading` candidates after image or table blocks instead of only downgrading `body` paragraphs.

Expected result:

- captions stay captions in markdown and in final DOCX;
- heading normalization no longer misstyles caption paragraphs.

### B. Harden heading detection to avoid downgrading true headings to body

Relax only the heading signals that are clearly too brittle, without making the heuristic noisy.

Planned changes:

1. Keep style names, `Title` and `Subtitle`, and outline levels as the highest-confidence sources.
2. Improve fallback detection for headings with mixed formatting instead of requiring every visible run to be bold.
3. Do not re-implement inherited outline lookup that already exists; instead add regression coverage for inherited outline levels and extend localized heading aliases only if real documents expose gaps beyond the current `heading|заголовок` handling.
4. Keep conservative guardrails against false positives, especially for full sentences and long prose paragraphs, and stop treating justified alignment alone as heading evidence.

Expected result:

- real headings recover their semantic level earlier in the pipeline;
- markdown receives correct `#` markers;
- final DOCX gets correct `Heading N` normalization.

### C. Redesign compare and keep-all variant reinsertion layout

Replace visible bold labels in the body with comparison-friendly layout metadata.

Planned changes:

1. Stop rendering compare/manual-review labels as visible bold text in the paragraph stream.
2. Insert multiple variants in a side-by-side structure in final DOCX.
3. Store variant names as image alternative text or equivalent hidden metadata, so the name is available on hover instead of being printed in the body.
4. Preserve existing single-image insertion behavior for the normal non-compare case.
5. Keep the existing data trigger contract explicit in tests: compare-all uses `validation_status == "compared"` plus `comparison_variants`, while manual-review uses `metadata.preserve_all_variants_in_docx`.

Preferred implementation direction:

1. build a dedicated multi-image reinsertion helper for compare and keep-all flows;
2. render variants in a single-row table or equivalent stable layout container;
3. attach per-image alt text from compare labels or candidate mode names.

Expected result:

- compare variants appear рядом and are easy to inspect visually;
- the body text is no longer polluted by bold labels;
- manual-review output is cleaner and closer to the intended review workflow.

## Tests To Add Or Update

### Semantic extraction regressions

1. caption after image with bold formatting and caption style must still be classified as `caption`, even when it also matches the fallback heading heuristic;
2. caption after table with heading-like formatting must still be classified as `caption`, including cases initially promoted to heuristic `heading`;
3. justified body paragraphs must not become `heading` solely because `jc="both"` is present;
4. heuristic headings with mixed formatting in `Normal` or `Body Text` must remain recoverable when the remaining signals are strong enough;
5. inherited outline levels and Russian heading styles should remain covered by regression tests, because current code already supports them and that support should not drift.

### Markdown and normalization regressions

1. extracted headings must render to markdown heading syntax without double-prefixing already marked headings;
2. extracted captions must not render as headings;
3. normalized DOCX must apply `Heading N` only to real headings and `Caption` only to real captions;
4. pipeline-level tests should verify the real final-assembly order with non-empty `source_paragraphs` and processed images, not only the markdown-only branch.

### Compare and keep-all reinsertion regressions

1. compare-all reinsertion must insert all available variants without visible label text in paragraph body;
2. manual-review reinsertion must still preserve the safe image plus candidate variants selected by `resolve_image_insertions()`, but without visible label text in paragraph body;
3. compare/manual-review variants must be inserted in a shared layout container instead of a vertical break-separated stack;
4. alt text or equivalent hidden descriptive metadata must contain the variant name;
5. tests should pin the actual trigger conditions for multi-variant insertion, not only the visual output.

## Implementation Order

1. [x] Add regression tests that reproduce caption -> heading, heading -> body, and visible bold label failures.
2. [x] Fix semantic caption-vs-heading precedence.
3. [x] Harden heading detection and add extraction tests.
4. [x] Replace compare/manual-review reinsertion layout.
5. [x] Update regression tests that currently lock the incorrect bold-label behavior.
6. [x] Update user-facing docs if the compare/manual-review output contract is clarified.

## Risks

1. Over-correcting heading heuristics can create false-positive headings in short bold body lines.
2. Multi-image layout in DOCX can be fragile if implemented with freeform runs instead of a stable container.
3. Alt text support may require lower-level OOXML handling beyond plain `python-docx` helpers.
4. Paragraph-count mapping between source and generated DOCX must remain stable after semantic fixes.

## Acceptance Criteria

1. captions in source documents remain captions in markdown and in final DOCX;
2. headings in source documents remain headings in markdown and in final DOCX;
3. compare and keep-all variants are placed side by side without visible bold labels in body text;
4. variant names are preserved in hidden descriptive metadata such as alt text;
5. focused regression tests cover all three bug classes.

## Files Expected To Change In The Implementation Phase

1. `document.py`
2. `models.py`
3. `tests/test_document.py`
4. `tests/test_document_pipeline.py`
5. `docs/WORKFLOW_AND_IMAGE_MODES.md`

---

## Аудит и дополнения к плану (верификация агентом)

Проведена повторная верификация по текущему исходному коду. Общий вектор плана остаётся актуальным, но несколько формулировок требовали уточнения: inherited/localized heading support уже частично реализован, а `_is_caption_style()` шире, чем выглядело в исходной версии аудита. Ниже — подтверждённые механизмы, исправленные неточности и дополнительные рекомендации.

### Уточнения по диагнозу

#### 1. Caption -> Heading: точный механизм ошибки

Цепочка вызовов:

1. `_build_paragraph_unit()` сначала вызывает `_extract_heading_level()` — до любой проверки на caption.
2. `_extract_heading_level()` проходит 4 ступени: `Title/Subtitle` -> `HEADING_STYLE_PATTERN` -> `outlineLvl` -> `_is_probable_heading()`.
3. Результат `heading_level` передаётся в `classify_paragraph_role()`, где `heading_level is not None` проверяется раньше, чем `_is_caption_style()`.
4. `_reclassify_adjacent_captions()` работает только для `paragraph.role == "body"`. Абзац, уже ставший `heading`, никогда не будет откорректирован до `caption`.

Это значит, что даже явная caption-стилизация вроде `Caption` или `Подпись` проигрывает любому heading-сигналу, включая слабую эвристику `_is_probable_heading()`. Для исправления недостаточно полагаться только на перестановку проверок в `classify_paragraph_role()` — нужно либо short-circuit для caption style до `_extract_heading_level()`, либо отдельное правило, которое не позволит heuristic heading перекрыть caption evidence.

**Рекомендация**: проверять `_is_caption_style(normalized_style)` до вызова `_extract_heading_level()` внутри `_build_paragraph_unit()` либо передавать в heading extraction явный запрет на heuristic heading для caption-style абзацев. При этом explicit heading style и explicit outline level лучше оставить сильнее adjacency-эвристики.

#### 2. Heading -> Body: конкретные слабые места эвристики

`_is_probable_heading()` отклоняет абзац по любому из четырёх барьеров:

| Барьер | Где проявляется | Проблема |
|--------|-----------------|----------|
| `len(stripped_text) > 90` | current code | Заголовки на русском языке часто длиннее 90 символов. Порог слишком жёсткий. |
| `len(stripped_text.split()) > 12` | current code | Аналогично, 12 слов — мало для русскоязычных заголовков. |
| `stripped_text.endswith((".", "!", "?", ";"))` | current code | Абсолютный фильтр. Заголовки вида `Введение.` или `Часть 1.` будут потеряны. |
| `_paragraph_has_strong_heading_format()` | current code | Требует все visible runs bold или center/both alignment. Заголовок с частично жирным форматированием легко теряется. |

Также: `_paragraph_has_strong_heading_format()` считает `alignment_value == "both"` justify эквивалентом center. Это ложный позитив: justified alignment — стандартное выравнивание body text в большинстве русскоязычных документов.

Уточнение к исходному плану: пункт про необходимость добавить поддержку inherited и localized heading metadata в прежней формулировке был слишком широким. В текущем коде уже есть:

- поддержка `Title` и `Subtitle`;
- матчинг стилей по `heading|заголовок`;
- поиск `outlineLvl` не только в абзаце, но и по цепочке `style.base_style` через `_find_paragraph_property_element()`.

То есть основной пробел сейчас не в полном отсутствии такой поддержки, а в недостаточно надёжной fallback-эвристике и в нехватке тестов, страхующих уже существующую поддержку.

**Рекомендация**:

- убрать `"both"` из списка heading-совместимых alignments — justify не является heading-сигналом;
- увеличить пороги или убрать жёсткие числовые ограничения, оставив пунктуацию и formatting как более надёжные фильтры;
- для `bold`-проверки учитывать mixed formatting и не завязываться на требование, чтобы все visible runs были жирными.

#### 3. Жирные подписи к вариантам: полная карта затронутых точек

В коде две параллельные ветки вставки, каждая из которых рендерит label жирным:

| Функция | Когда используется |
|---------|--------------------|
| `_append_image_insertions_to_paragraph()` | fallback-path, когда placeholder заменяется на уровне paragraph после split по regex |
| `_build_insertion_run_elements()` | primary path, когда placeholder лежит внутри run или split across runs |

Обе функции дублируют одну и ту же логику label -> bold run -> break -> picture -> break. При рефакторинге нужно менять обе ветки, иначе один путь останется сломанным.

Дополнительное подтверждение: multi-variant branch активируется не напрямую по UI mode, а через состояние ассета в `resolve_image_insertions()`:

- compare-all: `validation_status == "compared"` и заполненный `comparison_variants`;
- manual-review keep-all: `asset.metadata.preserve_all_variants_in_docx == True`, затем берутся `safe_bytes` и максимум две записи из `attempt_variants`.

Это важно зафиксировать и в тестах, и в обновлённом плане реализации.

Дополнительно, `_build_label_run_element()` копирует `rPr` из template run и поверх ставит `bold = True`. Это может привести к наследованию нежелательных свойств вроде italic или underline из окружающего контекста.

#### 4. Alt text: `python-docx` не поддерживает alt text через high-level API

`Run.add_picture()` в `python-docx` не принимает параметр для alt text или description. Alt text в OOXML хранится в атрибуте `descr` элемента `<wp:docPr>` внутри `<wp:inline>`. Значит, если план оставляет требование про скрытую descriptive metadata, реализация почти наверняка потребует низкоуровневого XML-шага после вставки картинки.

Это делает пункт плана про alt text актуальным, но его лучше воспринимать как low-level OOXML task, а не как простой вызов стандартного API.

#### 5. Side-by-side layout: выбор контейнера

План предлагает `single-row table` или equivalent stable layout container. По текущему стеку наиболее реалистичный вариант действительно выглядит так:

| Вариант | Плюсы | Минусы |
|---------|-------|--------|
| Таблица 1 x N | Стабильный макет, поддержка `python-docx`, работает в Word-ридерах предсказуемо | Нужно скрывать border-ы, ширина ячеек может требовать настройки |
| Inline images подряд | Минимум кода | Word переносит по ширине страницы и не гарантирует side-by-side |
| Tab-separated images | Визуально рядом в простых случаях | Хрупко и зависит от tab stops, страницы и шаблона |

**Рекомендация**: таблица 1 x N с невидимыми границами — самый надёжный вариант для compare/manual-review output.

### Дополнительные наблюдения

#### 6. `document_pipeline.py`: подтверждённый порядок финальной сборки и реальный тестовый пробел

Пайплайн действительно собирает DOCX в таком порядке:

1. `convert_markdown_to_docx_bytes`;
2. `preserve_source_paragraph_properties` при наличии `source_paragraphs`;
3. `normalize_semantic_output_docx` при наличии `source_paragraphs`;
4. `reinsert_inline_images` при наличии `processed_image_assets`.

Но текущий тест `test_run_document_processing_applies_semantic_output_normalization_before_image_reinsertion` проверяет только `convert -> preserve -> normalize`, потому что запускается с пустым набором изображений и фактически не доказывает вызов `reinsert_inline_images` после нормализации.

**Рекомендация**: добавить один success-path test с непустыми `source_paragraphs` и `processed_image_assets`, который зафиксирует полный порядок `convert -> preserve -> normalize -> reinsert`, и отдельные crash-path тесты на падение каждого из шагов финальной сборки.

#### 7. Тесты, закрепляющие неправильное поведение

Конкретные тесты, которые нужно будет обновить:

| Тест | Что закрепляет |
|------|----------------|
| `test_reinsert_inline_images_labels_manual_review_variants` | Проверяет, что label `safe`, `candidate1`, `candidate2` появляются в тексте paragraph, то есть остаются видимыми |
| `test_resolve_image_insertions_keeps_safe_and_candidates_for_manual_review` | Проверяет, что `resolve_image_insertions()` возвращает label-строки в tuple, и этот контракт можно сохранить |
| `test_reinsert_inline_images_in_compare_all_mode_inserts_all_generated_variants` | Проверяет label-тексты `Вариант 1/2/3` в paragraph body |
| `test_resolve_image_insertions_returns_all_compare_all_variants_before_single_final_choice` | Проверяет label-строки в tuples, и эта часть логики может остаться без изменений |

Из этих тестов:

- тесты на `resolve_image_insertions()` могут остаться без изменений, если сохранить контракт `(label, bytes)` на уровне данных;
- тесты на `reinsert_inline_images()` должны быть переписаны: вместо проверки видимого текста label в paragraph — проверка layout-контейнера и скрытой descriptive metadata.

#### 8. Отсутствуют тесты на caption при наличии heading-эвристики

Текущие тесты `test_extract_document_content_from_docx_marks_caption_after_image` и `test_extract_document_content_from_docx_marks_caption_after_table` тестируют счастливый путь, где caption-абзац не является heading-кандидатом. Нет ни одного теста, где:

- caption-абзац содержит только bold-текст до текущего лимита эвристики и без финальной пунктуации, то есть формально совпадает с `_is_probable_heading()`;
- caption-абзац имеет стиль `Caption`, но при этом текст и форматирование совпадают с heading-эвристикой;
- абзац после image/table сначала получает heuristic heading, а затем должен быть переопределён в `caption`.

Это именно тот gap, который нужно закрыть в первую очередь.

#### 9. `_is_caption_style()` — не такой узкий, как казалось, но всё ещё неполный

`_is_caption_style()` ищет `caption` или `подпись` в имени стиля. Значит, примеры вроде `Caption 1`, `Подпись рисунка`, `Image Caption`, `Table Caption` уже распознаются корректно.

Реальный пробел другой: функция всё ещё не увидит стили без этих токенов, например `Описание рисунка`, `Описание таблицы`, `Legend`, `Figure text` и другие локальные соглашения конкретного шаблона.

Для плана A это важно так: текущий detector не нулевой, но если стиль не попадает под `caption|подпись`, то защита остаётся только за adjacency logic, а она сейчас не умеет переигрывать heuristic heading.

#### 10. Рекомендация по порядку реализации

Предлагаю уточнить порядок:

1. Сначала добавить тесты, которые воспроизводят все три бага: caption -> heading, heading -> body и visible bold labels.
2. Потом исправлять код, ожидая, что новые регрессии начнут проходить.
3. В конце обновить старые тесты, которые закрепляли неправильное поведение.

Это безопаснее, чем менять тесты одновременно с кодом — легче отследить, что именно исправлено. Использование `xfail` возможно, но не должно считаться обязательной частью спецификации.
