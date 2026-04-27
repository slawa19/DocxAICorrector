# PDF Translation Quality Recovery Specification

Дата: 2026-04-27

## Цель

Радикально повысить качество обработки длинных PDF-derived документов после провального UI-прогона `Are_We_In_The_End_Times.pdf`, где одновременно деградировали:

- структура документа: TOC, заголовки, подзаголовки, списки;
- paragraph boundaries после LibreOffice PDF import;
- Markdown-разметка (`## ●`, склейка TOC с body, потеря section breaks);
- качество перевода и терминологическая точность богословского текста;
- paragraph/formatting mapping после LLM (`source_count=377`, `target_count=364`, `unmapped_source_count=30`).

Эта спецификация не заменяет `PDF_SOURCE_IMPORT_SPEC_2026-04-26.md` и `LAYOUT_ARTIFACT_CLEANUP_SPEC_2026-04-26.md`. Она фиксирует следующий слой: quality recovery для PDF-derived long-form translation, когда простая нормализация PDF в DOCX уже работает, но качество результата неприемлемо.

## Evidence

Последний user-visible результат:

```text
.run/ui_results/20260427_125300_Are_We_In_The_End_Times.result.md
.run/ui_results/20260427_125300_Are_We_In_The_End_Times.result.docx
```

Ключевые логи:

```text
app.log.1:1783 processing_started filename=Are_We_In_The_End_Times.docx model=gpt-5.4-mini block_count=42 translation_second_pass_enabled=false
app.log.1:1784 block_plan_summary total_target_chars=39289 first_block_target_chars=[3891, 946, 935, 54, 56]
app.log.1:1785 markdown_empty_response_recovery_started target_chars=105
app.log.1:1786 paragraph_count_mismatch_preserve source_count=377 target_count=364 mapped_count=347 unmapped_source_count=30 unmapped_target_count=17
app.log.1:1788 ui_result_artifacts_saved markdown_path=...20260427_125300_Are_We_In_The_End_Times.result.md
```

Ранее для этого же источника auto structure gate уже фиксировал structural risk:

```text
app.log.1:1506 prepared_source_key=Are_We_In_The_End_Times.docx...sr=auto:sv=1:op=translate
app.log.1:1512 structure_processing_outcome escalation_reasons=[low_explicit_heading_density, high_suspicious_short_body_ratio, toc_like_sequence_detected]
app.log.1:1512 ai_classified_count=0 ai_heading_count=0 status="AI не внёс изменений"
```

Показательные фрагменты результата:

```text
Line 33: Заключение...29 «Вас будут ненавидеть...». — Марка 13:13 Введение Мой дед...
Line 95: ## ●
Line 97: Сторонники середины трибуляции считают...
Line 99: ●
Line 101: трибуляции.
Line 219: Великая скорбь Вот самое худшее... 1/3.) Семь судов печатей...
Line 531: Judgment #1 в Откровении 16:3...
Line 657: Практические шаги для отдельных людей 1.
```

Вывод: это не одиночная ошибка перевода. LLM получил уже поврежденный structural substrate и местами дополнительно усугубил его, не сохранив paragraph mapping.

## Предыдущие Спецификации И Недостающие Контракты

Эта доработка должна явно учитывать, какие решения предыдущих спецификаций были осознанными MVP-ограничениями, но стали причиной отсутствующего quality contract для реального PDF-перевода.

### S-1. `PDF_SOURCE_IMPORT_SPEC_2026-04-26.md`

Что спецификация сделала правильно:

- добавила PDF как input format без создания второго document model;
- зафиксировала канонический путь `PDF -> normalized DOCX -> existing DOCX pipeline`;
- потребовала `writer_pdf_import`, стабильный source token по original PDF bytes, понятную ошибку отсутствующего LibreOffice, timeout cleanup и downstream DOCX-only boundary;
- честно указала, что качество структуры зависит от PDF и backend-конвертера.

Критический gap:

- спецификация сознательно запретила PDF-specific логику в `document_extraction.py`, `formatting_transfer.py`, `document_pipeline.py` и `preparation.py` для MVP;
- acceptance criteria проверяли факт конвертации и downstream DOCX contract, но не проверяли semantic usability полученного DOCX;
- manual validation была optional и ограничивалась тем, что результат сохраняется в `.run/ui_results/`, без критериев TOC/headings/lists/paragraph mapping;
- риск `LibreOffice PDF conversion может быть нестабильной` был описан, но не был превращен в fail/warn gate или follow-up trigger;
- `best-effort PDF import` в UI не защищал pipeline от запуска дорогого перевода на структурно непригодном DOCX.

Итоговая ошибка проектирования:

```text
"PDF converted to DOCX" was treated as sufficient readiness for the existing pipeline.
```

Для длинной книги это неверно. После PDF conversion нужен отдельный `converted DOCX semantic readiness` contract.

### S-2. `LAYOUT_ARTIFACT_CLEANUP_SPEC_2026-04-26.md`

Что спецификация сделала правильно:

- добавила generic cleanup после extraction;
- выделила repeated headers/footers, page numbers, running titles;
- потребовала traceable cleanup report, fail-open behavior, language-neutral predicates, protected roles и debug artifacts;
- прямо зафиксировала, что TOC сохраняется в translation/document-preserving mode.

Критический gap:

- cleanup решает удаление мусора, но не решает восстановление структуры;
- standalone bullets/list markers не были частью cleanup contract, потому что это content structure, а не layout artifact;
- TOC должен был `оставаться marked as toc_header/toc_entry`, но spec не требовал bounded TOC reconstruction и end-of-TOC detection;
- regression check для `Are_We_In_The_End_Times` был qualitative: `source_chars > 30000`, `paragraph_count > 100`, `jobs > 10`; это пропускает документ, где content есть, но structure broken;
- `cleanup_applied=true removed_count=0` может выглядеть успешным, хотя structural repair вообще не запускался.

Итоговая ошибка проектирования:

```text
"No layout artifacts removed" was not distinguished from "PDF-derived structure is healthy".
```

Для реального PDF нужен отдельный `structure_repair_report`, а не расширение cleanup до агрессивного удаления/переклассификации.

### S-3. `TOC_TRANSLATION_AND_MINIMAL_FORMATTING_SPEC_2026-04-21.md`

Что спецификация сделала правильно:

- ввела dedicated `toc_translate` prompt path;
- добавила deterministic TOC validation and retry;
- зафиксировала mixed TOC dominance threshold;
- ограничила source geometry replay для headings;
- усилила минимальный formatting contract.

Критический gap:

- спецификация исходила из того, что TOC already detected and grouped; для PDF-derived `Are_We_In_The_End_Times` это предположение не выполняется надежно;
- TOC validation работает после routing, но не может помочь, если TOC/body boundary уже сломан и block не является bounded TOC;
- acceptance focused on untranslated TOC lines and heading alignment, not on TOC concatenation with epigraph/body start;
- mixed TOC policy допускает TOC-dominant routing, но не требует splitting unsafe mixed blocks before translation;
- spec не запрещала first block composition вида `title + abstract + TOC + epigraph + Introduction body`.

Итоговая ошибка проектирования:

```text
TOC translation hardening assumed the upstream TOC region was structurally valid.
```

Для PDF-derived документов сначала нужен `TOC region reconstruction`, и только потом `TOC translation`.

### S-4. `TRANSLATION_QUALITY_AND_SECOND_PASS_SPEC_2026-04-20.md`

Что спецификация сделала правильно:

- усилила anti-calque/literary first-pass contract;
- добавила optional second literary pass;
- зафиксировала, что second pass не должен менять markers/placeholders/paragraph boundaries;
- сохранила block-based pipeline и structure-preservation guarantees.

Критический gap:

- спецификация была рассчитана на prose quality, а не на domain terminology quality;
- не было `translation_domain`, glossary, terminology memory или theological term policy;
- second pass не решает структурные дефекты и может только отполировать уже неверно нарезанные/склеенные блоки;
- не было requirement, что high-risk structural validation must pass before second pass or high-quality profile is meaningful;
- `gpt-5.4-mini + literary` без domain glossary не обязан стабильно переводить эсхатологическую терминологию.

Итоговая ошибка проектирования:

```text
Generic literary translation quality was treated as enough for specialized theological material.
```

Для богословского PDF нужен domain-aware translation layer, но только после structural repair.

### S-5. Общая системная ошибка между specs

Предыдущие спецификации оптимизировали отдельные слои:

- upload normalization;
- layout cleanup;
- TOC translation after detection;
- generic literary translation.

Но между ними отсутствовал сквозной acceptance contract:

```text
converted PDF is semantically ready for expensive document-preserving translation
```

Этот контракт должен включать:

- converted DOCX has enough semantic paragraphs, not just text chars;
- TOC is bounded;
- major headings recovered;
- list fragments repaired;
- first block is not a front-matter mega-block;
- structure AI escalation is actionable;
- source/target paragraph mapping drift is a quality failure;
- domain terminology plan exists when selected or auto-detected.

Без этого каждый слой формально “работает”, а общий результат всё равно неприемлем.

## Диагноз

### D-1. PDF import формально работает, но quality contract отсутствует

Текущий путь:

```text
PDF -> LibreOffice writer_pdf_import -> DOCX -> existing DOCX extraction -> semantic blocks -> translation
```

Этот путь достаточен для ingestion MVP, но не гарантирует semantic document structure. Для `Are_We_In_The_End_Times.pdf` downstream получил DOCX, где TOC, bullets, body lines и headings уже были смешаны как визуальные фрагменты страницы.

### D-2. Structure recognition auto gate сработал, но AI structure pass оказался no-op

Gate обнаружил ровно те признаки, которые должны были спасать PDF-derived документ:

- low explicit heading density;
- high suspicious short body ratio;
- toc-like sequence detected.

Но AI pass вернул `ai_classified_count=0`, `ai_heading_count=0`. Это критический дефект observability и качества: pipeline видит структурную опасность, но продолжает перевод как будто документ подготовлен нормально.

### D-3. TOC detection слишком узкий и не формирует жесткую границу конца TOC

В результате `Заключение...29`, эпиграф `Марк 13:13` и `Введение` попали в одну строку. TOC должен был быть распознан как bounded region:

```text
Содержание
...
Заключение ... 29
<TOC_END>
epigraph
Введение
```

Фактически TOC and body boundary не был восстановлен до перевода.

### D-4. Bullets и numbered lists разрушены на уровне extraction/boundary normalization

Симптомы:

```text
## ●
●
Посттрибуляционисты ... конце ● трибуляции.
Практические шаги для отдельных людей 1.
```

Вероятная причина: PDF-derived bullet glyphs и list numbers приходят отдельными paragraphs или inline fragments, а текущая классификация либо повышает их до heading, либо не склеивает с item body.

### D-5. Heading/subheading policy переоптимизирована под DOCX fixtures

Фразы вроде `Что такое Книга Откровения?`, `Как нам относиться к восхищению христиан?`, `Великая скорбь`, `Кто такой Антихрист?`, `Начертание зверя`, `Практические шаги...` должны становиться headings. В результате часть остается body, часть склеивается с последующим текстом, а случайные bullet glyphs становятся `##` headings.

Текущие heuristics хорошо покрывают `Chapter`, `Heading N`, centered/bold DOCX patterns, но не полноценную PDF-derived реконструкцию outline.

### D-6. Translation prompt не имеет domain/terminology layer

Фраза пользователя:

```text
"Сторонники предскорбного восхищения считают, что христиане будут восхищены до начала Скорби."
```

Проблема не только в слове `восхищение`, а в отсутствии glossary/terminology policy для богословских терминов. Для эсхатологии нужны устойчивые варианты и consistency across blocks:

- rapture: восхищение Церкви / восхищение верующих, но не механическое повторение `восхищены` в каждом предложении;
- pre-tribulation / mid-tribulation / post-tribulation: претрибулационизм / мидтрибулационизм / посттрибулационизм или описательные русские эквиваленты по glossary policy;
- Great Tribulation: Великая скорбь;
- mark of the beast: начертание зверя;
- Antichrist: Антихрист;
- Revelation: Откровение / книга Откровения;
- dispensation / dispensationalists: диспенсация / диспенсационалисты;
- abomination of desolation: мерзость запустения.

Без document-level terminology memory блоки переводятся локально и нестабильно.

### D-7. Marker/paragraph preservation недостаточно строг для acceptance

Итоговый mapping drift:

```text
source_count=377 target_count=364 mapped_count=347 unmapped_source_count=30 unmapped_target_count=17
```

Это должно быть quality gate failure для document-preserving translation, а не warning после сборки DOCX.

### D-8. Corpus validation не покрывает этот класс документов

`tests/sources/Are_We_In_The_End_Times.pdf` есть в репозитории, но отсутствует в `corpus_registry.toml`.

Текущий corpus покрывает:

- `Лиетар глава1.docx`;
- `Собственность и богатство в религиях.doc`;
- `The Value of Everything...docx`.

Это подтверждает риск переоптимизации: real-document validation держит несколько известных DOCX/DOC сценариев, но не проверяет long-form PDF-derived theological translation.

## Ключевое Архитектурное Решение

Нужен новый `quality recovery` слой между DOCX extraction и LLM translation:

```text
normalized DOCX paragraphs
  -> deterministic PDF-derived structure repair
  -> AI structure recognition with full-text windows when gate escalates
  -> structural quality gate
  -> semantic blocks with list/TOC/headings protected
  -> domain-aware translation prompts/glossary
  -> output structural validation before DOCX assembly
```

Запрещено считать успешным результат, если preparation уже обнаружила structural risk, AI structure pass не внес изменений, а output mapping/structure затем деградировали.

## Functional Requirements

### FR-1. Ввести PDF-derived structural risk profile

Pipeline должен уметь помечать normalized documents как high-risk не через `source_format == pdf` в core extraction, а через измеримые признаки:

- low explicit heading density;
- high short body paragraph ratio;
- high single-glyph paragraph ratio (`●`, `•`, isolated numbers);
- TOC-like sequence near front matter;
- large first block before first recognized heading;
- many paragraphs with visual-line length distribution;
- heading candidates present in TOC but absent as body headings.

Результат: `PreparedDocumentData` / summary получает `structure_quality_risk_level = low|medium|high` and reasons.

### FR-2. Structure auto escalation must be actionable

Если `structure_validation` recommends escalation, AI structure recognition must not silently no-op.

Required behavior:

- if AI call fails or returns zero usable classifications for a high-risk document, emit `structure_recognition_noop_on_high_risk` warning;
- if high-risk + no-op + document goes to translate, block preparation or mark result as `quality_gate_failed` unless user explicitly chooses unsafe best-effort mode;
- UI must display a hard warning before translation starts.

Acceptance:

```text
Are_We_In_The_End_Times prepared in auto mode must not proceed as "ready" when escalation reasons include TOC-like sequence and AI classified count is 0.
```

### FR-3. AI structure recognition must receive enough text to classify PDF-derived fragments

Current descriptor preview is too small for ambiguous theology/scripture/list fragments. For high-risk documents, descriptors must include:

- full paragraph text up to a larger cap, e.g. 400-800 chars;
- previous and next paragraph previews;
- local index within front matter/body;
- raw text length, line/bullet/list signals;
- TOC region candidate flags;
- source formatting: bold, centered, all-caps, font size;
- existing deterministic role and reason.

Prompt must explicitly handle:

- isolated bullet glyphs;
- bullet glyph followed by body line;
- numbered list marker as separate paragraph;
- TOC/body boundary;
- scripture references that are citations, not headings;
- theological section headings without `Chapter` prefix.

### FR-4. Add deterministic list repair before semantic block construction

Implement conservative repair for PDF-derived list fragments:

```text
●
Text of item

1.
Text of item
```

Target normalized form:

```text
- Text of item

1. Text of item
```

Rules:

- isolated bullet glyph paragraphs must never become headings;
- merge bullet marker with next body paragraph when next paragraph is not heading/TOC/caption/table/image;
- merge isolated numeric marker `1.` / `2.` with next body paragraph under same guardrails;
- preserve paragraph traceability via origin indexes;
- report decisions in boundary/layout reports or a new `structure_repair_report`.

### FR-5. Add bounded TOC reconstruction

TOC logic must identify a bounded front-matter region, not just individual entries.

Requirements:

- recognize headers: `contents`, `table of contents`, `содержание`, common case variants;
- treat consecutive leader/page-number lines as TOC entries;
- support Unicode dotted leaders and mixed ASCII/Unicode leaders;
- support entries without page numbers when surrounded by strong TOC evidence;
- determine TOC end before epigraph/body heading;
- forbid merging final TOC entry with epigraph/introduction;
- keep TOC entries in translation mode but route them through TOC prompt.

Acceptance against observed artifact:

```text
"Заключение...29" must remain a TOC entry.
"Вас будут ненавидеть..." must be epigraph/body, not same paragraph as TOC entry.
"Введение" must be heading or front-matter/body start, not appended to TOC line.
```

### FR-6. Add heading recovery from TOC/body alignment

For high-risk documents with a recognized TOC, use TOC entries as candidate outline hints.

Requirements:

- extract normalized TOC titles;
- scan body for matching or near-matching standalone lines;
- promote matched body lines to headings with inferred hierarchy;
- do not promote TOC entries themselves to body headings;
- avoid promoting scripture citations and bullet/list items.

Example required headings from this document:

```text
Введение
Что такое Книга Откровения?
Цикл родовых схваток
Восхищение
Великая скорбь
Кто такой Антихрист?
Начертание зверя
Антихрист уже здесь?
Секулярная хронология уничтожения человечества ИИ
Христианская хронология Великой скорби
Практические шаги для отдельных людей
Практические шаги для государств
Заключение
```

### FR-7. Add structural block quality gates before LLM translation

Before `run_document_processing`, fail or require explicit unsafe override if:

- first semantic block exceeds threshold and contains TOC + epigraph + body start;
- any block contains isolated heading-only bullet glyphs;
- high-risk document has fewer than expected headings based on TOC entries;
- TOC region is detected but not routed as TOC-dominant or bounded;
- paragraphs with list markers remain split from item text above threshold.

For this document, the first block of 3891 chars containing title, abstract, TOC, epigraph and `Введение` is a quality gate failure.

### FR-8. Add output structural validation after LLM translation

After block generation and before final DOCX assembly:

- marker count/order must match per block and globally;
- source/target paragraph count drift above tolerance must fail document-preserving mode;
- reject headings that consist only of bullet glyphs (`## ●`, `# •`);
- reject mixed-language leftovers in target for non-proper text (`Judgment #1` in Russian result);
- reject TOC/body concatenation patterns;
- reject list marker separation patterns.

Default tolerance for translation mode with paragraph markers enabled:

```text
unmapped_source_count == 0 for strict mode
unmapped_source_count <= 1% for advisory mode, but UI must mark quality warning
bullet_heading_count == 0
english_residual_count <= allowed proper nouns / citations threshold
```

Observed `unmapped_source_count=30` must not be treated as acceptable warning.

### FR-9. Add domain-aware translation layer

Introduce optional `translation_domain` with initial values:

```toml
[translation]
domain_default = "general"
available_domains = ["general", "theology"]
```

For `theology`, add glossary and style instructions:

- preserve biblical references in Russian convention: `Матфея 24:36`, `Откровение 13:16-17`;
- maintain consistent eschatology terms;
- avoid awkward repetitive passive constructions;
- distinguish `rapture` concept from generic emotional `восхищение`;
- prefer readable Russian theological prose over calques;
- preserve doctrinal nuance and avoid adding certainty not present in source.

Initial glossary file:

```text
prompts/domains/theology_glossary_ru.txt
```

Example preferred rewrite:

```text
Сторонники претрибулационного взгляда считают, что Церковь будет восхищена до начала Великой скорби.
```

or, if using descriptive style:

```text
Сторонники взгляда о восхищении до скорби считают, что Христос заберет Церковь до начала Великой скорби.
```

The exact wording should be controlled by glossary/style policy and consistent across the document.

### FR-10. Add document-level terminology memory

Before translating blocks, build a lightweight terminology plan for high-risk/domain documents:

- scan source text for known glossary source terms;
- record chosen Russian equivalents;
- inject glossary subset into every block prompt;
- optionally save `translation_terms_report` under `.run/translation_terms/`.

Do not rely only on neighboring context for terms that recur across distant blocks.

### FR-11. Model/profile recommendations for long-form translation

Current run used `gpt-5.4-mini`, second pass disabled. For high-risk long-form translation, the app should expose or automatically recommend a safer profile:

```text
translation_quality_profile = draft|balanced|high_quality
```

High-quality profile:

- stronger text model option;
- domain glossary enabled when selected;
- stricter output validation;
- optional second pass, but only after structural validation passes;
- smaller chunks if marker/list preservation is unstable.

Second pass must not be used as a structure fixer. It is only for target-language polish after structure is already valid.

### FR-12. Add Are_We_In_The_End_Times to real-document corpus

Register the PDF source in `corpus_registry.toml` with a PDF-specific profile.

Proposed document entry:

```toml
[[documents]]
id = "end-times-pdf-core"
source_path = "tests/sources/Are_We_In_The_End_Times.pdf"
artifact_prefix = "end_times_pdf_validation"
output_basename = "Are_We_In_The_End_Times_validated"
structural_mode = "strict"
min_paragraphs = 250
has_headings = true
min_headings = 10
has_numbered_lists = true
min_numbered_items = 10
has_images = false
min_images = 0
has_tables = false
min_tables = 0
require_toc_detected = true
require_pdf_conversion = true
require_no_bullet_headings = true
require_no_toc_body_concat = true
require_translation_domain = "theology"
default_run_profile = "ui-parity-translate-theology-pdf-high-quality"
tags = ["pdf", "translation", "theology", "toc", "headings", "lists", "manual-regression"]
provenance = "Regression source for PDF-derived long-form theological translation quality after 2026-04-27 failure."
```

Do not put real LibreOffice PDF conversion into generic unit tests. Use canonical WSL real-document validation path.

### FR-13. Add source/translated quality diagnostics artifact

For every high-risk translation run, save a compact quality report:

```text
.run/quality_reports/<source>_<hash>.json
```

Fields:

- source paragraph count;
- semantic block count;
- heading count before/after AI;
- TOC region count and bounded status;
- list repair decisions;
- isolated bullet paragraphs count;
- first block composition summary;
- marker/paragraph mapping stats;
- mixed-language residual samples;
- final quality status: pass/warn/fail.

This report must be referenced from logs and UI summary.

### FR-14. Add converted-DOCX semantic readiness gate

After `normalize_uploaded_document()` and extraction, but before `build_semantic_blocks()` is treated as production-ready, run a semantic readiness check for converted or structurally suspicious documents.

Inputs:

- extraction metrics;
- boundary normalization report;
- layout cleanup report;
- structure validation report;
- TOC relation/reconstruction report;
- source metadata: `source_format`, `conversion_backend`, normalized filename.

Readiness statuses:

```text
ready
ready_with_warnings
blocked_needs_structure_repair
blocked_unsafe_best_effort_only
```

Minimum blocking reasons:

- converted PDF has TOC-like sequence but no bounded TOC region;
- first semantic block contains TOC + epigraph/body start;
- isolated bullet/list marker paragraphs remain above threshold;
- explicit/AI heading count is far below TOC-derived expected count;
- structure AI was recommended, attempted, and no-op on a high-risk document;
- paragraph boundary report shows many rejected medium merges in a PDF-like visual-line distribution;
- source text is large but semantic block count/heading count indicates flat-document collapse.

UI behavior:

- `blocked_needs_structure_repair` must prevent normal translation start;
- user may only continue via an explicit unsafe best-effort override, and output artifacts must be marked with quality warning;
- default UI path should recommend running/using high-quality PDF recovery mode.

### FR-15. Add structure repair stage distinct from cleanup

Introduce a first-class stage after layout cleanup and before structure recognition/semantic blocks:

```text
ParagraphUnit list
  -> clean_paragraph_layout_artifacts()
  -> repair_pdf_derived_structure()
  -> validate_structure_quality()
  -> optional AI structure recognition
```

The stage must not be named or implemented as cleanup because it does not remove artifacts by default. It repairs content structure.

Responsibilities:

- merge isolated bullet markers with item body;
- merge isolated numeric list markers with item body;
- split or mark compact front-matter TOC clusters when deterministic evidence is strong;
- add bounded TOC region markers;
- protect epigraph and first body heading from TOC tail merge;
- produce heading candidates from TOC/body alignment;
- preserve origin traceability.

Output report:

```python
@dataclass
class StructureRepairReport:
    applied: bool
    repaired_bullet_items: int
    repaired_numbered_items: int
    bounded_toc_regions: int
    toc_body_boundary_repairs: int
    heading_candidates_from_toc: int
    remaining_isolated_marker_count: int
    decisions: list[StructureRepairDecision]
```

### FR-16. Add unsafe block composition splitter

Semantic block construction must not allow a front-matter mega-block that mixes unrelated structural regions.

Split before LLM if a block contains:

- document title/abstract + TOC;
- TOC + epigraph;
- TOC + first body heading/body paragraph;
- multiple major headings with unrelated long body spans;
- list marker fragments separated from item body.

For `Are_We_In_The_End_Times`, the observed first LLM block of 3891 chars should be split into at least:

```text
title/abstract/front matter
bounded TOC
epigraph
Introduction section start
```

This splitter is a safety mechanism. It does not replace proper structure repair, but it prevents one bad block from contaminating translation, TOC handling and marker preservation simultaneously.

### FR-17. Add postmortem-driven validation fixtures

Create fixtures that encode the exact previous-spec blind spots:

- synthetic converted-DOCX paragraphs where TOC tail is followed by epigraph and introduction;
- isolated bullet glyphs promoted incorrectly to heading candidates;
- numbered marker `1.` split from body text;
- theology heading lines with no `Chapter` prefix;
- TOC entries that match later body headings;
- high-risk structure AI no-op.

These fixtures must fail under the old behavior and pass under the repaired pipeline.

Do not rely solely on live `Are_We_In_The_End_Times.pdf` for unit coverage. Use the real PDF for canonical integration/regression validation, and synthetic fixtures for deterministic unit tests.

## Non-Functional Requirements

### NFR-1. Do not add a second PDF document model yet

Continue using DOCX as canonical internal model. The new layer repairs generic paragraph/list/TOC/heading structure after extraction. Direct PDF parsing via PyMuPDF/pdfplumber remains future work unless LibreOffice-derived quality cannot reach acceptance criteria.

### NFR-2. Conservative repair over content loss

Never delete or rewrite content during structural repair unless it is already covered by layout cleanup high-confidence artifact rules. Repair should merge/split/classify, not discard.

### NFR-3. Traceability

Every structural repair decision must preserve `origin_raw_indexes` and be visible in a report. This is mandatory because false positives in theological material can silently corrupt meaning.

### NFR-4. No silent quality downgrade

High-risk + failed recovery cannot be logged as successful preparation. It must be visible in UI and machine-readable logs.

### NFR-5. WSL canonical validation

Real PDF conversion and validation must use the repository's canonical WSL path, not Windows-only pytest fallback.

## Proposed Implementation Plan

### Phase 1. Investigation Harness

- Add a diagnostic command/helper that prepares `tests/sources/Are_We_In_The_End_Times.pdf` through canonical WSL runtime and saves source Markdown before LLM.
- Emit source metrics: paragraphs, headings, TOC entries, list fragments, first block composition.
- Compare converted DOCX/extracted Markdown against final translated Markdown.
- Compare the output against the explicit blind spots from `PDF_SOURCE_IMPORT_SPEC`, `LAYOUT_ARTIFACT_CLEANUP_SPEC`, `TOC_TRANSLATION_AND_MINIMAL_FORMATTING_SPEC`, and `TRANSLATION_QUALITY_AND_SECOND_PASS_SPEC`.
- Produce a `converted_docx_semantic_readiness` report for the current broken document before implementing fixes.

### Phase 2. Deterministic Structure Repair

- Add `StructureRepairReport` and report persistence/retention.
- Implement isolated bullet/number marker repair.
- Implement bounded TOC reconstruction.
- Implement TOC/body boundary protection.
- Ensure `## ●` cannot be produced from source structure.
- Add unsafe block composition splitter for front-matter mega-blocks.

### Phase 3. Better AI Structure Recovery

- Expand descriptor payload for high-risk documents.
- Update structure recognition prompt for PDF-derived fragments and theology/scripture ambiguity.
- Treat no-op AI on high-risk document as failure/warning, not success.
- Ensure structure AI runs after deterministic repair, not before bullet/TOC fragments are normalized enough to classify.

### Phase 4. Structural Quality Gates

- Add converted-DOCX semantic readiness gate.
- Add pre-translation quality gates.
- Add post-translation structural validation.
- Turn severe paragraph mapping drift into failure for strict document-preserving mode.

### Phase 5. Domain Translation Quality

- Add `translation_domain` UI/config plumbing.
- Add theology glossary prompt fragment.
- Add terminology memory injection per block.
- Add tests for glossary application and mixed-language leftovers.

### Phase 6. Corpus Coverage

- Register `Are_We_In_The_End_Times.pdf` in `corpus_registry.toml`.
- Add validation checks for TOC, headings, lists, no bullet headings, no TOC/body concatenation.
- Add real-document quality gate command/profile for PDF translation.
- Add deterministic synthetic fixtures for previous-spec blind spots so unit coverage does not require live LibreOffice.

### Phase 7. Documentation and UI Contract

- Update PDF user-facing language from generic `best-effort` to a two-stage explanation: conversion may succeed while semantic readiness can still block translation.
- Document `unsafe best-effort` override separately from normal high-quality PDF translation.
- Link this recovery spec from the PDF import spec as the follow-up quality contract for long-form translation.

## Acceptance Criteria

### AC-1. No TOC/body concatenation

The output must not contain a line equivalent to:

```text
Заключение...29 ... Марка 13:13 Введение Мой дед...
```

### AC-2. No bullet headings

The output must contain zero headings matching:

```text
^#{1,6}\s*[●•*-]\s*$
```

### AC-3. Headings recovered

At least 10 expected major sections from the source TOC are present as Markdown headings or mapped DOCX headings.

### AC-4. Lists repaired

Bullet and numbered list items are represented as complete list items, not isolated glyphs or detached numbers.

### AC-5. Paragraph mapping preserved

For strict translation mode with markers:

```text
unmapped_source_count == 0
bullet_heading_count == 0
```

For advisory mode, drift above 1% must surface as visible quality warning and quality report failure/warn status.

### AC-6. Theology terminology consistent

Key terms are translated consistently across the document according to glossary policy:

- Great Tribulation;
- rapture;
- pre/mid/post-tribulation;
- Antichrist;
- mark of the beast;
- Revelation;
- abomination of desolation.

### AC-7. No unexplained English leftovers

Non-proper English fragments like `Judgment #1` must not remain in Russian output unless explicitly protected as source quotation/code.

### AC-8. Corpus validation covers the regression

`Are_We_In_The_End_Times.pdf` is present in real-document registry and fails on the current broken output conditions before fixes.

### AC-9. Converted-DOCX readiness is explicit

The pipeline emits `converted_docx_semantic_readiness` for converted PDF inputs and does not treat DOCX validation alone as readiness for translation.

For the current broken `Are_We_In_The_End_Times` extraction, the readiness gate must be `blocked_needs_structure_repair` or equivalent until TOC/list/heading repair is implemented.

### AC-10. Previous-spec blind spots are regression-tested

Synthetic tests cover:

- successful PDF conversion but broken semantic structure;
- cleanup removing zero artifacts while structure remains unhealthy;
- TOC translation path not invoked because TOC boundary is missing;
- second pass unavailable or irrelevant when structural validation fails;
- structure AI no-op on high-risk input.

### AC-11. Unsafe best-effort path is not silent

If the user explicitly overrides a blocked high-risk PDF and runs translation anyway, output artifacts and logs must carry a machine-readable quality warning. The UI must not present such result as normal successful high-quality processing.

## Out Of Scope

- OCR for scanned PDFs.
- Full PDF geometry reconstruction.
- Direct PDF parser as primary ingestion path.
- Human-level theological editing guarantees.
- Automatic doctrinal correction beyond preserving source meaning.

## Definition Of Done

This work is done when `Are_We_In_The_End_Times.pdf` can be processed through canonical WSL/UI-parity validation with high-risk structure recovery enabled, the resulting Markdown/DOCX has bounded TOC, recovered headings, repaired lists, no bullet headings, acceptable paragraph mapping, and theology-domain translation terminology is consistent enough that the observed phrase-level failures are prevented by glossary/prompt policy rather than manual luck.
