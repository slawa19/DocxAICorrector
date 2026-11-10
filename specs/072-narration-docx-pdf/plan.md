# Implementation Plan: текст для озвучки в DOCX и PDF

**Branch**: `072/integration` (интеграционная, от `main` @ `f6de2fd`; рабочие ветки пакетов — `072/wp-<буква>-<slug>`) |
**Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: `specs/072-narration-docx-pdf/spec.md` (после ревью Codex `docs/reviews/CODEX_REVIEW_072_SPEC_2026-11-10.md` и
двух замеров владельца в Studio 2026-11-10); решения — [research.md](research.md); сущности — [data-model.md](data-model.md);
контракты — [contracts/](contracts/); проверка — [quickstart.md](quickstart.md); задачи — [tasks.md](tasks.md).

**База**: `main` @ `f6de2fd`. Все ссылки `file:line` ниже сверены на нём; код между `2e5e8d5` (спека) и `f6de2fd` не
менялся. Если интеграционная ветка уйдёт вперёд — сверять заново (Конституция VIII).

## Summary

Режим аудиокниги, кроме `.tts.txt`, выдаёт `.tts.docx` (для ElevenLabs Studio) и `.tts.pdf`. Сборка `.tts.txt`
начинает отдавать упорядоченные группы абзацев (ID, роль, уровень, текст) — `.tts.txt` остаётся их побайтной
проекцией (R2); уровень заголовка один раз вычисляется при финализации абзаца и хранится в записи (R1). Чистый план
документа (R3) превращает группы в абзацы `Heading 1`/`Normal` по FR-003 в редакции владельца (главой Studio
становится КАЖДЫЙ заголовок Word — стиль заголовка получает только ранг 1; серии подряд идущих заголовков сливаются) и
считает лимиты Studio. python-docx пишет текст дословно (R4) шрифтом Times New Roman (в LibreOffice — Liberation Serif с
кириллицей, R5); LibreOffice без интерфейса делает PDF с закладками и встроенными шрифтами в отдельном временном
каталоге и с НОВЫМ профилем на каждую конвертацию, тайм-аут 60 с (R6, R7; замер: полная книга 7–8,4 с, общий профиль
ломает каждую вторую параллельную конвертацию). Поиск `soffice` и помощник процесса уезжают в `runtime/external_process.py`
(R8). Байты идут одним ключом состояния через bundle на экран из двух строк кнопок (R10), в группу результата тем же
`_atomic_write_group` с суффиксами хранения (R12), в раннер и событие (R13). Девять пакетов, шесть — параллельно с
первого дня.

## Technical Context

**Language/Version**: Python 3.13.5 (WSL Debian, `.venv/bin/python`); Streamlit 1.64.0.

**Primary Dependencies**: python-docx 1.2.0 (уже в `requirements.txt`), pdfminer.six 20260107 (уже в `.venv`, только
тесты), LibreOffice 25.2.3.2 (`system-requirements.apt:4`); **новая системная строка** — `fonts-liberation` (сейчас
приходит только как «Recommends» `libreoffice`, R5). Новых Python-зависимостей нет.

**Storage**: `.run/ui_results/<stem>.result.{tts.docx,tts.pdf}` рядом с `.result.{md,docx,tts.txt}`; отчёт раннера —
`tests/artifacts/real_document_pipeline/runs/<run_id>/<output_basename>.tts.{docx,pdf}`. Временный каталог экспорта
PDF (с профилем LibreOffice) живёт только на время конвертации.

**Testing**: pytest через `bash scripts/test.sh` под WSL; системные тесты PDF — маркер `system_deps` (CI его исключает,
`.github/workflows/ci.yml:92`; в CI конвертер подменяется, R14); Streamlit — `AppTest`/рендер-тесты и проверка в
браузере (FR-009); платный замер — `scripts/run-real-document-validation.sh` (FR-011, по согласию владельца).

**Target Platform**: WSL Debian (`/mnt/d/Work/Projects/DocxAICorrector`), UI Streamlit локально.

**Project Type**: одно Python-приложение (`src/docxaicorrector/`), тесты в `tests/`.

**Performance Goals**: сборка `.tts.docx` полной книги — 0,12–0,15 с (замер R4); PDF — 7–8,4 с с новым профилем (R7),
не дольше 60 с (тайм-аут); всё в фоновом рабочем потоке после сборки текста.

**Constraints**: `.tts.txt` побайтно прежний (SC-004); перевод и редактура — ни байта нового (Anti-regression 2);
сбой DOCX/PDF не блокирует выдачу (Anti-regression 3); никаких слов заголовков в правилах и цитат книг в тестах (VII);
только штатные примитивы Streamlit (AGENTS.md, Streamlit Layout Contract).

**Scale/Scope**: книги до ~1 200 абзацев / 0,5 млн знаков; ≈ 14 файлов продукта (5 новых), ≈ 9 новых тестовых файлов,
5 документов.

Неизвестных `NEEDS CLARIFICATION` нет: все развилки решены в research (R1–R15); что определяется только платным
прогоном и Studio — раздел «Что не определено».

## Constitution Check

### До дизайна

- **I/II — PASS.** Все проверки — `scripts/test.sh` через `wsl.exe -d Debian`; замеры плана — `.venv/bin/python -I` под
  WSL (скрипты вне git, `D:\Temp\docxai-research\072\`), FR-011 — канонический раннер.
- **III — PASS, полный цикл** (спека так решила): новые модули (план документа, рендерер, экспорт PDF, общий помощник
  процесса), новый контракт артефактов и состояния между конвейером, runtime, UI и раннером; порядок слияния важен.
- **IV — PASS.** Реальные документы — только как объём текста и как вход прогноза без модели (R11); утверждений о
  живом дефекте нет. FR-011 — веха, не цикл отладки.
- **V — PASS.** Пути файлов, события, поля, хранение — `contracts/`; документ логирования обновляет WP-I.
- **VI — PASS.** Пакеты владеют непересекающимися файлами (таблица ниже); импорт PDF/DOC не меняется, кроме
  общего поиска `soffice`, который требует FR-005.
- **VII — PASS с обязательствами.** FR-003 — по роли и уровню (ранг, серия), не по словам; заголовок без уровня — не
  восстанавливается (FR-003 (г)). Тесты — синтетические тексты той же формы. Правило вычитания из числа заголовков
  (`Normal` вместо `Heading N`) несёт анти-вакуумную проверку: абзац тела никогда не становится `Heading 1`, текст
  понижённого заголовка присутствует побайтно.
- **VIII — PASS.** Ссылки сверены 2026-11-10 на `f6de2fd`; прогнозы спеки заменены замерами (Assumptions, R5–R7, R11).

### После дизайна

PASS. Отклонения от спеки (ниже) — уточнения формы реализации, без ослабления проверок. Нарушений, требующих
Complexity Tracking, нет.

## Project Structure

### Документация (эта спека)

```text
specs/072-narration-docx-pdf/
├── spec.md
├── plan.md                  # этот файл
├── research.md              # решения R1–R15 и замеры
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── events.md            # события, поля ui_audiobook_artifact_saved, notices, отчёт раннера
│   ├── result-group.md      # файлы группы, имена скачивания, команда экспорта PDF, содержимое .tts.docx
│   └── state-bundle.md      # ключ состояния, bundle, экран аудиокниги, локали
├── checklists/requirements.md
└── tasks.md
```

### Исходный код (затронуто / создано)

```text
src/docxaicorrector/
├── pipeline/
│   ├── audiobook_pass.py          # WP-A: heading_level в записи, narration_heading_level, heading_levels_by_id
│   ├── block_execution.py         # WP-A: только finalize_audiobook_block_for_delivery (:1572-1619)
│   ├── narration_postprocess.py   # WP-A: NarrationGroup, assembly.groups, state.narration_groups
│   ├── contracts.py               # WP-A: ProcessingState.narration_groups; ResultArtifactWriter (+2 аргумента)
│   ├── narration_document.py      # НОВЫЙ WP-B: план документа (FR-003, FR-006)
│   ├── narration_exports.py       # НОВЫЙ WP-H: оркестратор план → DOCX → PDF, события
│   └── late_phases.py             # WP-H: вызов, граница Stop, emit_state, писатель группы, поля события, notice
├── generation/
│   ├── narration_docx.py          # НОВЫЙ WP-C: рендерер python-docx (FR-004)
│   └── narration_pdf.py           # НОВЫЙ WP-D: экспорт LibreOffice (FR-005)
├── runtime/
│   ├── external_process.py        # НОВЫЙ WP-D: find_soffice_binary, run_completed_process, terminate_process_tree
│   ├── artifacts.py               # WP-E: write_ui_result_artifacts (+2 файла)
│   ├── artifact_retention.py      # WP-E: суффиксы группы
│   └── state.py                   # WP-F: init/reset ключа
├── processing/
│   ├── processing_runtime.py      # WP-F: разрешённый ключ, bundle, правило пары, общий поиск soffice
│   └── processing_service.py      # WP-F: аварийный обработчик
└── ui/
    ├── _ui.py, _app.py            # WP-G: экран аудиокниги (FR-009)
    └── locales/ru.json, en.json   # WP-G
system-requirements.apt, scripts/setup-wsl.sh                   # WP-D: fonts-liberation и проверка
tests/artifacts/real_document_pipeline/run_lietaer_validation.py # WP-I
scripts/_list_log_events.py                                     # WP-I
docs/LOGGING_AND_ARTIFACT_RETENTION.md, AGENTS.md («UI result artifacts»),
README.md, docs/WORKFLOW_AND_IMAGE_MODES.md                     # WP-I (FR-010)
docs/testing/TEST_TIER_INVENTORY.md                             # оркестратор при слиянии (R15)
```

**Structure Decision**: решение (план документа) — в `pipeline/`, чистое и без python-docx; запись файлов — в
`generation/` (там уже строятся выходные документы); внешний процесс — в `runtime/`, ниже всех потребителей, чтобы
импорт `processing → runtime` и экспорт `pipeline → generation → runtime` шли сверху вниз (R8). Протоколы
`NarrationGroupLike` / `NarrationDocumentParagraphLike` делают WP-B и WP-C независимыми от WP-A.

---

## Дизайн по требованиям

### FR-001, FR-002 — группы и уровень (WP-A)

R1, R2; `data-model.md` §1–2. `narration_heading_level` — одно правило; запись и `FinalizedAudiobookBlock` несут уровень;
`rebuild_block_with_narration_texts` ставит префикс по нему (DOCX для проверки — побайтно как раньше, характеристический
тест). `NarrationAssembly.groups` строится из тех же `group_texts`, что и `text`; золотой SHA-256 `.tts.txt` фиксируется ДО
правки. `ProcessingState.narration_groups` заполняет `_build_narration_text`.

### FR-003, FR-006 — план документа (WP-B)

R3; `data-model.md` §3 с таблицей примеров. Ранг 1 → `Heading 1`, всё глубже → `Normal`; серии (б); заголовок без
уровня — `Normal` (г); счётчики и лимиты — после слияний, строго больше.

### FR-004 — DOCX (WP-C)

R4, R5; `contracts/result-group.md` §4. Один run на абзац (`\n` → `<w:br/>`), явный Times New Roman, без колонтитулов
(к `section.header` не обращаться), свойства без «python-docx». Исключение рендерера — наружу (его ловит WP-H и пишет
ERROR).

### FR-005 — PDF и общий `soffice` (WP-D, переключение импорта — WP-F)

R6–R8; `contracts/result-group.md` §3. Новый профиль на конвертацию, фильтр с `ExportBookmarks`, 60 с, проверка
`%PDF-`, причины закрытым словарём; `fonts-liberation` в `system-requirements.apt` и проверка в `setup-wsl.sh`.
`processing_runtime` переходит на `find_soffice_binary()` и импортирует помощник процесса (WP-F, после WP-D).

### FR-007 — группа, событие, раннер (WP-E, WP-H, WP-I)

R12 (группа и суффиксы — WP-E), R9 (`emit_state`, аргументы писателя, поля события, три новых события — WP-H), R13
(раннер — WP-I). `contracts/events.md`.

### FR-008, FR-009 — состояние, bundle, экран (WP-F, WP-G)

R10; `contracts/state-bundle.md`. Один ключ `latest_narration_exports`, правило пары в bundle, экран из двух строк.

### FR-010 — документы (WP-I); FR-011 — замер (оркестратор, платно)

`quickstart.md` §6.

---

## Отклонения от спеки (уточнения формы, проверки не ослаблены)

- **О-1. Слияние применяется ко всем сериям, и серия подразделов становится ОДНИМ обычным абзацем** (FR-003 (б) «без
  изменений» + (а) в редакции владельца). Спека говорит о слиянии в терминах заголовков; после замера владельца
  глубокие заголовки — не заголовки DOCX. План читает (б) как правило над группами-заголовками независимо от
  будущего стиля (R3). На полной Money: 7 из 8 слияний — такие серии (R11).
- **О-2. Отсутствие PDF/DOCX показывается строкой у кнопок, а не общим notice** (FR-005 «строка на экране»): причина
  едет в bundle (FR-008) и рисуется там, где пользователь ищет кнопку (R10). Превышение лимитов Studio — notice.
- **О-3. Stop перед экспортом завершает прогон как остановленный** (FR-005 «Stop проверяется перед запуском
  конвертации»): так ведут себя все границы позднего этапа (R9). Причины `stopped` у PDF нет.
- **О-4. Импорт PDF/DOC остаётся без отдельного профиля LibreOffice** — FR-005 требует профиль для экспорта и общий
  поиск бинаря; риск одновременных импортов (замер R7) записан как находка вне объёма.
- **О-5. Свойства `.tts.docx`**: `title` = основа исходника, `author`/`comments` пустые — спека молчит; иначе Word и
  Studio увидят автора «python-docx».

## Дефекты спеки, найденные при планировании (исправлены в этой же ветке — Changelog спеки)

1. Assumptions «`Heading 1` распознаётся как глава», «Heading 1–3» — сняты замером владельца (каждый заголовок —
   глава); FR-003 (а), SC-002 переписаны.
2. SC-003 «нормализация пробелов» неисполнима в форме «схлопнуть пробелы»: pdfminer вставляет пробелы внутри строк
   (+10 665 знаков на полной книге, R6) — уточнено: удаление всех пробельных символов.
3. Текстовый слой PDF для U+0301 не гарантирован (R6) — в Non-goals; набор SC-003 без комбинирующих знаков.
4. Assumptions о шрифтах и времени — заменены замерами (R5, R7); найдена недетерминированность пакета шрифтов
   («Recommends»).

---

## Порядок реализации: пакеты работ

Каждый пакет — отдельная ветка в отдельном боковом worktree вне репозитория (`D:\Temp\claude\wt-072-<slug>`, `.venv` —
симлинк на главное дерево; AGENTS.md «Боковые worktree»). Тесты истории — только в главном дереве. Каждый пакет:
характеристика того, что должно остаться прежним → падающие тесты нового поведения (с анти-вакуумом) → код →
каноническая проверка. Агенты — по правилу владельца: Haiku механика, Sonnet ограниченная инженерия, Opus — правила
конвейера уровня спеки. Строки `docs/testing/TEST_TIER_INVENTORY.md` добавляет оркестратор при слиянии (R15).

| Пакет | Объём | Агент / усилие | Владеет файлами | Доказывающие тесты (анти-вакуум) | Зависит от |
|---|---|---|---|---|---|
| **WP-A** Записи и группы (FR-001, FR-002) | малый, точный | Sonnet / high | `pipeline/audiobook_pass.py`, `pipeline/block_execution.py` (только `finalize_audiobook_block_for_delivery`), `pipeline/narration_postprocess.py`, `pipeline/contracts.py` (поле `ProcessingState.narration_groups`, 2 аргумента `ResultArtifactWriter`), `tests/test_spec_072_narration_groups.py` (нов.) | золотой SHA-256 `.tts.txt` (зелёный ДО и ПОСЛЕ); текст блока DOCX для проверки по матрице роль × префикс — как раньше; `heading_level` в записи (падает: поля нет); `assembly.text == "\n\n".join(groups.text)`; группа-заголовок — одна запись; ID групп = ID записей с кратностью | — (волна 1) |
| **WP-B** План документа (FR-003, FR-006) | средний | **Opus** / high | `pipeline/narration_document.py` (нов.), `tests/test_spec_072_narration_document.py` (нов.) | таблица примеров `data-model.md` §3 целиком; нет `Heading 2+`; тело никогда не H1 (анти-вакуум: тело, начинающееся с `#`, с ролью `body` → `Normal`); понижённый заголовок — текст побайтно; лимиты 500/501, 400/401, 5000/5001; глава до первого H1; книга без заголовков | — (волна 1) |
| **WP-C** Рендерер DOCX (FR-004) | малый | Sonnet / medium | `generation/narration_docx.py` (нов.), `tests/test_spec_072_narration_docx.py` (нов.) | `paragraph.text` побайтно = вход (U+0301, заглавная гласная, `*_#<>`, тире, `\n` → `<w:br/>`); стили только `Heading 1`/`Normal`; шрифт Times New Roman во всех слотах; в zip нет `header*`/`footer*`; нет пустых абзацев; свойства без «python-docx»; символ `\x0b` → исключение наружу | — (волна 1) |
| **WP-D** Экспорт PDF, общий помощник процесса, шрифты (FR-005) | средний | Sonnet / high | `runtime/external_process.py` (нов.), `generation/narration_pdf.py` (нов.), `system-requirements.apt`, `scripts/setup-wsl.sh`, `tests/test_spec_072_narration_pdf.py` (нов.), `tests/test_spec_072_narration_pdf_system.py` (нов., `system_deps`) | CI-часть: команда (профиль `file://…/lo_profile`, фильтр, `--norestore`), уникальный профиль у двух вызовов, удаление временного каталога, все 7 причин, нет исключений наружу; системная: SC-003 (текст без пробельных = ожидаемый, порядок, хвост, закладки = H1, шрифты встроены, отрицательные контроли), SC-006 (два в потоках) | — (волна 1) |
| **WP-E** Группа результата и хранение (FR-007 файлы) | малый | Sonnet / medium | `runtime/artifacts.py`, `runtime/artifact_retention.py`, `tests/test_spec_072_result_group.py` (нов.) | `.tts.docx`/`.tts.pdf` в группе и в `artifact_paths` только при непустых байтах; без них группа и пути побайтно прежние; сбой записи члена откатывает всю группу; хранение удаляет оба новых файла вместе с группой (падает: сегодня они «passthrough» и не удаляются никогда) | — (волна 1) |
| **WP-G** Экран аудиокниги (FR-009) | средний | Sonnet / medium | `ui/_ui.py`, `ui/_app.py`, `ui/locales/ru.json`, `ui/locales/en.json`, `tests/test_spec_072_result_screen.py` (нов.), `tests/test_ui.py` (только случаи аудиокниги, если их ожидания меняются) | две строки, порядок DOCX/PDF/TXT, основная — DOCX, имена `<stem>.tts.*`, MIME; нет PDF → две кнопки и строка причины; старый bundle → одна кнопка TXT, без ошибки; перевод/редактура — те же кнопки и метки, что до спеки (снимок ДО правки); ключи в обоих каталогах | — (волна 1; контракт bundle фиксирован) |
| **WP-F** Состояние, bundle, общий поиск `soffice` в импорте (FR-008, FR-005) | средний | Sonnet / medium | `processing/processing_runtime.py`, `processing/processing_service.py`, `runtime/state.py`, `tests/test_spec_072_state_bundle.py` (нов.), `tests/test_processing_runtime.py` (только цель подмены `_terminate_process_tree`) | ключ проходит фильтр (падает: WARNING `state_event_unknown_keys` и потеря); bundle несёт `narration_exports` только при тексте озвучки; сброс в `reset_run_state`/`init_session_state`/аварии; старый bundle; одна функция поиска (три копии удалены — `grep` в тесте); `_run_completed_process is run_completed_process`; тесты импорта DOC/PDF зелёные | WP-D слит |
| **WP-H** Поздний этап: интеграция (FR-003 (в), FR-005 вызов, FR-006 notice, FR-007 событие и запись) | средний | **Opus** / high | `pipeline/narration_exports.py` (нов.), `pipeline/late_phases.py`, `tests/test_spec_072_late_phase_exports.py` (нов.), `tests/test_spec_072_exports_system.py` (нов., `system_deps`), `tests/test_late_phases_finalize_gate_persistence.py` (только если ожидания `emit_state`/писателя меняются) | через `_build_narration_text` + поздний этап с подменёнными писателем и экспортом: SC-001 на синтетическом наборе (U+0301, `\n`, `#` в теле, `needs_review`, `source_fallback`) — абзацы `.tts.docx` = абзацы `.tts.txt` с перечисленными слияниями; SC-005 (нет `soffice` / тайм-аут → успех, TXT+DOCX, причина в событии и state); сбой рендерера → ERROR, книга без DOCX/PDF; Stop перед экспортом → прогон остановлен, экспорта нет; перевод/редактура — экспорт не вызывается, ключ не пишется; поля события по контракту; системный e2e: записи → `.tts.docx` → `.tts.pdf` продуктовой цепочкой | A, B, C, D, E, F слиты |
| **WP-I** Раннер, гард событий, документы (FR-007 раннер, FR-010) | средний | Sonnet / medium | `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`, `tests/test_real_document_pipeline_validation.py`, `scripts/_list_log_events.py`, `docs/LOGGING_AND_ARTIFACT_RETENTION.md`, `AGENTS.md` (только раздел «UI result artifacts»), `README.md` (абзац narration artifact, `:512`), `docs/WORKFLOW_AND_IMAGE_MODES.md` (`:145`) | `_SPEC_072_LOG_EVENTS`: каждое событие эмитится и зарегистрировано; отчёт на синтетическом логе несёт поля `contracts/events.md`, «нет события» = `not_reported`; раннер пишет `.tts.docx`/`.tts.pdf` в каталог прогона и `latest`; AGENTS.md без `mode`/`tag_count`/`excluded_blocks`; `test_agent_contract_consistency`, `test_documentation_links` зелёные | H слит |

### Порядок слияния

```text
волна 1:  WP-A ─┐  WP-B ─┐  WP-C ─┐  WP-D ─┐  WP-E ─┐  WP-G ─┐    (общих файлов нет)
          слияние в 072/integration в любом порядке; после каждого — полный прогон в главном дереве
волна 2:  WP-F  ← D
волна 3:  WP-H  ← A, B, C, D, E, F
волна 4:  WP-I  ← H
приёмка:  полный `scripts/test.sh tests/ -q` в ГЛАВНОМ дереве + системные тесты (`-m system_deps` по файлам 072),
          `git status --porcelain` пуст → проверка экрана в браузере (FR-009) → расширенное ревью Codex по всем
          затронутым поверхностям (SC-008) → слияние в main → FR-011 (платно, по согласию владельца)
```

Критический путь: **WP-D → WP-F → WP-H → WP-I**. Общих файлов у пакетов нет: `pipeline/contracts.py` целиком у WP-A
(оба изменения — объявления), `processing/processing_runtime.py` целиком у WP-F, `pipeline/late_phases.py` — у WP-H;
`TEST_TIER_INVENTORY.md`, `docs/WHERE_WE_ARE.md`, статус спеки — у оркестратора. После КАЖДОГО переноса пакета на свежую
`072/integration` — повторный полный прогон в главном дереве (AGENTS.md, 2026-08-08). Тема коммита пакета называет
`spec 072`.

## Риски

| Риск | Чем закрыт |
|---|---|
| `.tts.txt` изменится при выделении групп | золотой SHA-256 до правки; `text` и `groups` из одних `group_texts` |
| DOCX для проверки поменяется при переносе уровня | характеристический тест на матрице роль × префикс до правки |
| Studio всё же режет главы иначе (напр. по стилю `Title`, по жирному) | только `Heading 1` и `Normal`, без жирного; FR-011 — загрузка владельцем |
| Глава в Studio названа номером («Глава первая»), название — абзацем | правило (б) владельца; наблюдение R11 вынесено в FR-011 |
| LibreOffice зависнет | 60 с + завершение группы процессов; причина `timeout`; выдача не блокируется |
| Параллельные экспорты помешают друг другу | новый профиль на конвертацию (замер R7: общий профиль — 5 из 10 без PDF); SC-006 |
| Пакет шрифтов не установится на новом WSL | `fonts-liberation` в `system-requirements.apt` + проверка `setup-wsl.sh` |
| Новые файлы никогда не удалятся | суффиксы хранения + тест (R12) |
| Байты не дойдут до экрана / покажутся старые | один разрешённый ключ, правило пары, сброс в начале запуска; SC-007 тесты |
| U+0301 в PDF | Non-goals; DOCX — побайтно (SC-001) |
| Символ, недопустимый в XML, в ответе модели | ERROR `audiobook_narration_docx_failed`, книга без DOCX/PDF, TXT доставлен |

## Сохраняемые контракты AGENTS.md

- **WSL runtime:** тесты и диагностические импорты — `wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh <selector>
  -q`, один selector на команду; Windows `python` и `.venv-win` не используются; в боковых worktree — литеральные пути,
  без `$VAR` и циклов на границе Git Bash → `wsl.exe`.
- **Каноническая проверка:** «зелёное» — полный `scripts/test.sh tests/ -q` в главном дереве при пустом
  `git status --porcelain`; системные тесты 072 — отдельными командами с `-m system_deps`; debug-путь помечается
  `debug-only`.
- **Real-document evidence:** FR-011 — только `scripts/run-real-document-validation.sh`; при падении профиля — сначала
  свежий run report и `failed_checks` с `actual`/`threshold`; полный прогон — веха, не цикл.
- **Логирование и артефакты:** события и поля — `contracts/events.md`; полные тексты не в лог; новые файлы группы —
  с суффиксами хранения; `.run/` и `.env` вне git.
- **Line endings:** все новые файлы — LF; после правок `git diff --check`.

## Что не определено (сказано прямо)

- **Сколько глав покажет Studio на продуктовом `.tts.docx`** — прогноз 23 (R11); замер — загрузка владельцем (FR-011).
- **Что Studio делает с одиночным `<w:br/>` внутри абзаца** (пауза? склейка?) — на корпусе таких абзацев 0 (Codex 2);
  проверяет только прослушивание.
- **Почему пара параллельных конвертаций быстрее одиночной** (2,1 с против 7 с, R7) — не объяснено; на тайм-аут не влияет.
- **Одновременные импорты PDF/DOC с общим профилем LibreOffice** — замер показывает отказ одной из двух конвертаций
  при общем профиле (R7); импорт вне объёма 072 — кандидат в отдельную спеку (оркестратору).
- **Как Studio читает текстовый слой PDF с U+0301** — не проверялось (Non-goals; владелец работает с DOCX).

## Complexity Tracking

Нарушений Конституции, требующих обоснования, нет.
