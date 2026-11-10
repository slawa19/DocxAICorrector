# Quickstart: проверка спеки 072

Все команды — канонический путь AGENTS.md: из не-WSL shell через `wsl.exe -d Debian --cd "<дерево>" -- …`; один
selector на команду, selector ДО опций pytest. Финальное «зелёное» — только полный прогон в ГЛАВНОМ дереве при пустом
`git status --porcelain`. В боковом worktree пакета заменить путь в `--cd` на `D:\Temp\claude\wt-072-<slug>` (`.venv` —
симлинк на главное дерево). Голый `python`, `.venv-win`, `py -m pytest` запрещены; debug-путь помечается `debug-only`.
Тесты, читающие историю git (`test_spec_status_consistency` и др.), в боковом worktree пропускаются — это ожидаемо.

## 0. Готовность окружения

```bash
wsl.exe -l -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "uname; pwd; test -f scripts/test.sh; test -f .venv/bin/activate; echo READY"
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "soffice --version; fc-list ':lang=ru:family=Liberation Serif' | head -2"
```

Ожидаемо: `READY`; `LibreOffice 25.2.3.2 …`; хотя бы одна строка Liberation Serif. Без `soffice` системные тесты
пропускаются (или падают при `DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES=1`), остальное работает.

## 1. Волна 1 — пакеты без зависимостей

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_narration_groups.py -q     # WP-A, SC-004 (золотой .tts.txt)
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_audiobook_pass.py -q                # WP-A, без изменений
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_narration_markdown.py -q            # WP-A, без изменений
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_narration_document.py -q   # WP-B, SC-002, FR-006
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_narration_docx.py -q       # WP-C, FR-004
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_narration_pdf.py -q        # WP-D, подменённый конвертер
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_narration_pdf_system.py -q -m system_deps   # WP-D, SC-003, SC-006
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_result_group.py -q         # WP-E
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_result_screen.py -q        # WP-G
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_script_contract_static.py -q        # WP-D (apt), оркестратор (инвентарь)
```

Ожидаемо: зелёные; золотой тест WP-A зелёный ДО и ПОСЛЕ правки (`.tts.txt` побайтно прежний). Системный тест печатает
время конвертации; ориентир — до ~10 с на тест (замер `research.md` R7: 6,5 с на 120 абзацев с новым профилем).

## 2. Волна 2 — состояние и bundle (WP-F)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_state_bundle.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_processing_runtime.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_state.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_processing_service.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_real_document_validation_corpus.py -q -m system_deps
```

Последняя команда — импорт PDF/DOC через общий поиск `soffice` по-прежнему работает.

## 3. Волна 3 — поздний этап (WP-H)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_late_phase_exports.py -vv
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_exports_system.py -q -m system_deps
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_late_phases_finalize_gate_persistence.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_document_pipeline.py -q
```

Ожидаемо: SC-001 (абзацы `.tts.docx` = абзацы `.tts.txt` с перечисленными слияниями, побайтно, U+0301 на месте), SC-005
(без `soffice` и при тайм-ауте — успех, TXT и DOCX выданы, причина в событии и в состоянии), перевод/редактура без
экспорта.

## 4. Волна 4 — раннер, гард событий, документы (WP-I)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_agent_contract_consistency.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_documentation_links.py -q
```

## 5. Приёмка (оркестратор, главное дерево)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/ -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_narration_pdf_system.py -q -m system_deps
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_exports_system.py -q -m system_deps
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_status_consistency.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_where_we_are_freshness.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_typecheck.py -q
git status --porcelain
git diff --check
```

`test_typecheck.py` (pyright) идёт 40–120 с — timeout ≥ 180 000 мс. Перед «всё зелёное» вывод `git status --porcelain`
пуст.

**Проверка экрана в браузере (FR-009, Streamlit Layout Contract).** Запустить приложение задачей VS Code `Start Project`
(`scripts/start-project.ps1`; состояние — `Project Status`, остановка — `Stop Project`), во встроенном браузере: загрузить короткий переведённый DOCX
(например `tests/sources/translated/rm_ch3_translated_ru.docx`) в режиме «Подготовка аудиокниги» — это платный вызов
модели (≈ центы); если оплачивать нельзя, оркестратор проверяет экран на подставленном bundle (рендер-тест WP-G) и
пишет об этом прямо. Проверить: строка «Текст для озвучки» — DOCX (основная), PDF, TXT; строка «Для проверки» — DOCX
для проверки и Markdown; кнопки растянуты по ширине колонок; имена скачанных файлов `<stem>.tts.docx` / `.tts.pdf` /
`.tts.txt`; скачанный `.tts.docx` открывается в Word, `.tts.pdf` — с закладками глав. Экран без PDF (две кнопки и
строка причины) и старый bundle проверяются рендер-тестами WP-G, не в браузере. Режимы «Перевод» и «Редактура» —
экран как до спеки.

## 6. FR-011 — замер на полной книге (оркестратор, ПЛАТНО ≈ 0,35 $, только с согласия владельца)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "DOCXAI_REAL_DOCUMENT_PROFILE=audiobook-money-full-standard-translated DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-standalone-audiobook bash scripts/run-real-document-validation.sh"
```

Читать в `tests/artifacts/real_document_pipeline/runs/<run_id>/` (и `audiobook_money_full_standard_translated_report.json`):

| Что | Где | Ожидание |
|---|---|---|
| файлы | `output_artifacts.tts_docx_path`, `tts_pdf_path`, `tts_docx_openable` | оба есть, DOCX открывается |
| главы | `narration_artifact.heading1_count`, `tts_docx_heading1_count` | равны; прогноз 23 (R11) |
| нет других стилей заголовков | `tts_docx_other_heading_style_count` | 0 (SC-002) |
| слияния | `narration_artifact.heading_merges` | каждое — с ID; прогноз 8 (R11) |
| лимиты Studio | `studio_limits_exceeded`, `studio_max_chapter_paragraph_count`, `studio_max_paragraph_chars` | `[]`; прогноз 183 и ~4 000 |
| PDF | `narration_pdf_status`, `narration_pdf_seconds` | `built`, единицы секунд |
| равенство SC-001 на реальных данных | абзацы `.tts.docx` против абзацев `.tts.txt` с перечисленными слияниями (скрипт оркестратора над файлами прогона) | равны |

При падении профиля — сначала свежий run report: `failed_checks` дословно с `actual` / `threshold` и отношением, только
потом гипотезы (AGENTS.md, Real-document failure analysis contract). Затем владелец загружает `.tts.docx` в ElevenLabs
Studio («Create an Audiobook») и сообщает число глав и нет ли потерянного текста до первой главы. Итоги — в Changelog
спеки как есть (неудача критерия фиксируется, не ретушируется).
