# Structure-Recognition → Reader-First Migration Plan

Date: 2026-05-29
Status: Proposed migration plan (requires approval before implementation)

Связанные источники истины:

- `docs/specs/SIMPLE_READER_FIRST_MVP_SPEC_2026-05-21.md`
- `docs/specs/SIMPLE_READER_FIRST_MVP_REPAIR_PR_BACKLOG_2026-05-23.md`
- `docs/specs/STRUCTURE_RECOGNITION_PR_BACKLOG_2026-05-21.md` (тупиковая фаза)
- `docs/ARCHIVE_INDEX.md` (контракт архивации)

## 1. Цель и решение

Текущий structure-first пайплайн распознавания структуры (Stage 1 DocumentMap →
Stage 1.5 topology projection → Stage 2 anchored classification → structural
diagnostics → quality gates) признан тупиковым: он превратился в многоуровневый
набор эвристик, который дорого тюнить и который не гарантирует читабельный
reader-facing результат.

Решение:

1. Полностью исключить structure-first распознавание из продакшн-пайплайна.
2. Сделать основным путём **Simple Reader-First** (extraction → перевод большими
   chunks → AI reader cleanup post-pass), который сейчас в разработке как MVP.
3. Архивировать тупиковую фазу распознавания структуры вместе с документацией
   (без молчаливого удаления истории), а мёртвый код удалить из активного дерева.

Этот план НЕ предлагает чинить Stage 1/Stage 2; он переводит их в архив и
закрывает как активную поверхность разработки.

## 2. Оценка готовности MVP (ключевой ответ)

### Что уже готово

- **Slice 0–4 реализованы**: детерминированный block splitter + bounded
  operations, AI post-pass, comparison-only validation profile, AI reader
  verifier (`reader_cleanup_mvp/service.py`).
- **Runtime-интеграция уже есть**: `pipeline/late_phases.py`
  (`_run_reader_cleanup_postprocess` → `run_reader_cleanup`,
  `write_reader_cleanup_diagnostics`), гейтится `reader_cleanup_enabled` в
  `app_config`. То есть reader cleanup исполняется в основном пайплайне, а не
  только в валидации (после PR-G граница валидатора восстановлена).
- **Repair backlog**: PR-A…PR-G завершены.

### Чего ещё нет

- Активна **PR-H (Reader Cleanup Visual Blockers)**, под-слайс **PR-H1**
  (page furniture inline, heading/body fusion, fragmented paragraphs, стабильный
  `reader_cleanup_failed_chunk_count = 0`). Не закрыта.
- **PR-I (Formatting Preservation)** — bold/italic/emphasis, heading/subheading
  styles, list styles в финальном DOCX. Не начата.
- **PR-J (Image Handoff/Reinsertion)** — восстановление PDF-origin картинок. Не
  начата.
- **Slice 5 (UI Toggle)** — пользовательский переключатель reader cleanup. Не
  сделан.
- MVP exit criterion ещё не достигнут: нужен повторяемый `cleaned_better` без
  failed chunks / false deletions / readability regressions на основном proof-
  документе **плюс хотя бы один дополнительный реальный документ**.

### Ответ: после какой фазы MVP готов к интеграции

MVP готов стать основным пайплайном (а не comparison-only инструментом) **после
завершения фазы PR-H и фазы PR-I репейр-беклога, при достигнутом MVP exit
criterion**; **PR-J обязательна дополнительно, если PDF-origin картинки являются
release-блокером** для целевого вывода.

Обоснование границы:

- **PR-H** закрывает reader-visible блокеры и доводит до устойчивого
  `failed_chunk_count = 0` и `cleaned_better` — это превращает «readable draft»
  в надёжный текстовый результат.
- **PR-I** обязателен для замены structure-first как основного пайплайна: без
  сохранения bold/italic/заголовков/списков итоговый DOCX не дотянет до
  book-grade, на который сейчас претендует structure-first.
- **PR-J** — по флагу релиза: если картинки критичны, без неё замена неполна.
- **Slice 5 + флаги по умолчанию** — это и есть собственно акт интеграции в
  основной проект/UI.

Короткая формула готовности:

```text
PR-H (stable) + PR-I (landed) + MVP exit criterion (proof doc + 1 доп. документ)
  [+ PR-J, если картинки — release-блокер]
  => MVP готов заменить structure-first в продакшн-пайплайне и UI (Slice 5).
```

Verifier (Slice 4) и runtime-хук (late_phases) уже на месте, поэтому остаточные
gating-фазы — именно PR-H → PR-I (→ PR-J) → Decision Gate promotion.

## 3. План замены пайплайна (Workstream A: Integration)

Принцип: сначала сделать reader-first дефолтным и доказанным, и только потом
вырезать structure-first. Никогда не удалять старый путь раньше, чем новый
доказан на proof + дополнительном документе.

### A0. Завершить gating-фазы MVP

- Довести PR-H до стабильного `failed_chunk_count = 0`, отсутствия false
  deletions/readability regressions, и `cleaned_better` повторяемо.
- Реализовать PR-I (formatting preservation).
- Реализовать PR-J, если картинки — release-блокер.
- Подтвердить MVP exit criterion на proof-документе
  (`lietaer-pdf-chapter-region-core`) и минимум одном дополнительном реальном
  документе.

Выход: подтверждённые reader-first артефакты, пригодные как основной результат.

### A1. Сделать reader-first дефолтным режимом

- В `config.toml`: `structure_recognition.mode = "off"` как дефолт; включить
  `reader_cleanup_default = true` (через resolve в `validation/profiles.py` и
  app config).
- Проверить, что `_resolve_structure_recognition_mode` и preparation корректно
  доходят до финального Markdown в режиме `off` без segment-required /
  DocumentMap-required / chapter-reassembly ошибок (Slice 0 discovery как
  регрессия).

### A2. Slice 5 — UI-интеграция

- Добавить в `ui/_ui.py` sidebar-чекбокс `Reader cleanup post-pass`
  (рядом с `translation_second_pass`/`audiobook_postprocess`), пробросить в
  app_config (`reader_cleanup_enabled` и связанные поля из MVP-spec § Minimal
  New Config).
- Удалить из UI панель ревью структуры (`ui/structure_review_panel.py`) или
  заменить её на reader-cleanup отчёт (raw vs cleaned + report summary).
- Surface артефактов: убедиться, что `ui_result_artifacts_saved` несёт cleaned
  как primary, raw + `reader_cleanup_report_path` как diagnostic (см. MVP-spec
  § Minimal Integration Point).

### A3. Решение по runtime anchor repair

- Зафиксировать домашнюю точку для anchor repair: либо включить в основном
  пайплайне (`reader_cleanup_anchor_repair_enabled` через late_phases с полным
  DOCX rebuild path), либо оставить diagnostic-only. Не оставлять
  validation-only repair (контракт PR-G).

### A4. Decision Gate

- По § Decision Gate MVP-spec выбрать: promote как основной режим / только
  audiobook-continuous / drop. Для замены structure-first целевой исход —
  **promote**.

## 4. План очистки и архивации тупиковой фазы (Workstream B: Decommission)

Выполняется ТОЛЬКО после A1–A2 (reader-first дефолт доказан и в UI), чтобы не
сломать рабочий продукт. Порядок — сверху вниз по риску.

### B1. Заморозка и архивация документации

Перенести в `docs/archive/specs/` со статусной пометкой `dead-end / superseded`
и записью в `docs/ARCHIVE_INDEX.md` (что реализовано/закрыто и дата):

- `docs/specs/STRUCTURE_RECOGNITION_PR_BACKLOG_2026-05-21.md`
- `docs/AI_FIRST_STRUCTURE_RECOVERY_SPEC_2026-05-08.md`
- `docs/CHAPTER_WORKFLOW_CONTRACT_ALIGNMENT_SPEC_2026-05-07.md`
- Связанные topology/input-fidelity/output-hygiene спеки, перечисленные как
  источники в backlog (`TOPOLOGY_FIRST_*`, `STRUCTURE_RECOGNITION_INPUT_FIDELITY_*`,
  `OUTPUT_DISPLAY_HYGIENE_*` — найти точные пути в `docs/specs/` и `docs/`).
- Зафиксировать в `ARCHIVE_INDEX.md` отдельный раздел
  `Dead-End: Structure-First Recognition` со ссылкой на этот migration plan как
  на причину decommission.

Контракт архивации: соблюсти условия из `ARCHIVE_INDEX.md` (реализация/закрытие
зафиксированы, канонические доки обновлены, есть запись в индексе).

### B2. Удаление мёртвого кода

После того как `mode = off` стал жёстким дефолтом и нет рантайм-вызовов Stage
1/2, удалить (с git-историей как архивом) изолированные модули:

- Пакет `src/docxaicorrector/structure/` целиком:
  `recognition.py`, `document_map.py`, `topology.py`, `reconciliation.py`,
  `layout_signals.py`, `page_furniture_detection.py`, `validation.py`,
  `_responses_timeout.py`.
- Structure-only части `src/docxaicorrector/document/`:
  `structure_authority.py`, `structure_repair.py`, `roles.py`,
  `boundary_review.py`, `relations.py` и structure-specific ветки в
  `boundaries.py` / `segments.py` / `semantic_blocks.py` — аккуратно, проверив,
  что extraction/перевод их больше не используют.
- `src/docxaicorrector/ui/structure_review_panel.py` (после A2).
- Stage 1/1.5/2 оркестрация в `processing/preparation.py`
  (`_run_structure_recognition`, `_build_structure_recognition_summary`,
  window settings, debug-artifact ветки) — оставить только off-path,
  необходимый reader-first.
- `chapter_workflow/service.py` — если используется только structure-first,
  удалить; иначе вырезать structure-зависимые ветки.

Важно: удаление вести итеративно «лист за листом» (сначала самые внешние
вызовы), каждый шаг — прогон тестов, чтобы не получить каскад импорт-ошибок.

### B3. Очистка конфигурации

- Удалить `structure_recognition` секции и поля из `core/config*.py`
  (`config_structure_sections.py`, `config_loader_layers.py`,
  `config_model_registry.py` role `structure_recognition`), оставив
  миграционный no-op/deprecation для старых `config.toml`/env, чтобы не падать
  на существующих конфигах.
- Удалить `structure_recognition.*` из `config.toml` и
  `DOCX_AI_STRUCTURE_RECOGNITION_*` из `.env.example`.
- Удалить structure-поля из `validation/profiles.py` и из run-profile-ов в
  `corpus_registry.toml`, кроме reader-cleanup профилей.

### B4. Промпты

Архивировать/удалить неиспользуемые промпты:

- `prompts/structure_recognition_system.txt`
- `prompts/document_map_system.txt`
- `prompts/scene_graph_extraction.txt`
- `prompts/reconciliation_targeted_system.txt`

(Сначала grep по коду — убедиться, что ни один из них не грузится reader-first
путём.)

### B5. Валидация и бенчмарки

- Удалить/архивировать structure-specific валидацию: `validation/structural.py`
  (или сократить до reader-first нужного), `validation/common.py` structure-
  ветки.
- Архивировать `benchmark_projects/structure_recognition_benchmark/`.
- Удалить/перенести тесты: `test_structure_*`, `test_document_structure_*`,
  `test_real_document_structure_recognition_integration.py`,
  `test_structure_recognition_benchmark_runner.py`,
  `test_structure_layout_signals.py`, `test_structure_*` и др.; обновить
  `test_real_document_validation_corpus.py`, `test_typecheck.py`,
  `test_script_contract_static.py`.

### B6. Обновление канонических доков

- `README.md`, `docs/WORKFLOW_AND_IMAGE_MODES.md`,
  `docs/REAL_DOCUMENT_VALIDATION_WORKFLOW.md`,
  `docs/AI_AGENT_DEVELOPMENT_RULES.md`, `AGENTS.md` — убрать structure-first как
  активный путь, описать reader-first как основной; снять structural-diagnostic
  routing из AGENTS, где он только про тупиковую фазу.

## 5. Последовательность и зависимости

```text
A0 (PR-H stable, PR-I, [PR-J], MVP exit)        # доказать reader-first
  -> A1 (mode=off default, reader_cleanup default)
  -> A2 (UI Slice 5, убрать structure review panel)
  -> A3 (anchor repair home)  -> A4 (Decision Gate: promote)
        -> B1 (архив доков)
        -> B2 (удаление кода, итеративно + тесты)
        -> B3 (конфиг)  -> B4 (промпты)  -> B5 (валидация/бенчмарки/тесты)
        -> B6 (канонические доки)
```

Жёсткое правило: ни один шаг Workstream B не начинается раньше, чем A1+A2
доказаны user-visible verification (не только agent-side).

## 6. Риски и митигации

- **Скрытые зависимости extraction/translation от structure-модулей.** Митигация:
  перед B2 — grep всех импортов удаляемых модулей; удалять листьями.
- **Off-path не доходит до финального Markdown.** Митигация: A1 повторяет Slice 0
  discovery как регрессионный тест.
- **Потеря book-grade форматирования.** Митигация: PR-I — обязательный gate.
- **Старые config.toml/.env ломаются после B3.** Митигация: deprecation no-op
  для удалённых ключей вместо жёсткой ошибки.
- **CI/typecheck падает из-за висячих импортов.** Митигация: каждый под-шаг B2/B5
  завершать каноническим прогоном тестов (`scripts/test.sh`) и `git status
  --porcelain` перед верификацией.

## 7. Верификация

- Каждая фаза A: focused тесты `tests/test_reader_cleanup_mvp.py` и
  `tests/test_real_document_pipeline_validation.py -k 'reader_verifier or
  comparison_only'`, затем comparison-only прогон proof-документа.
- Финал A: user-visible UI прогон с reader cleanup, проверка
  `ui_result_artifacts_saved` (cleaned primary + raw/report).
- Каждая фаза B: полный `bash scripts/test.sh tests/ -q` (в WSL runtime) +
  `git diff --check`.
- Decommission считается завершённым, когда: structure-first код удалён, тесты
  зелёные, канонические доки обновлены, архивные записи внесены в
  `ARCHIVE_INDEX.md`.

## 8. Out of Scope

- Любой ре-тюнинг Stage 1/Stage 2/topology (фаза закрыта, не чинится).
- Document-specific regex/phrase lists в reader cleanup (запрещено MVP-spec).
- Изменение acceptance-порогов ради «зелёного» comparison-only прогона.
