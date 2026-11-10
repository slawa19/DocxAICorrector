# Quickstart: проверка спеки 073

Все команды — канонический путь AGENTS.md: из не-WSL shell через `wsl.exe -d Debian --cd "<дерево>" -- …`; один
selector на команду, selector ДО опций pytest. Финальное «зелёное» — только полный прогон в ГЛАВНОМ дереве при пустом
`git status --porcelain`. В боковом worktree пакета заменить путь в `--cd` на `D:\Temp\claude\wt-073-<slug>` (`.venv` —
симлинк на главное дерево). Голый `python`, `.venv-win`, `py -m pytest` запрещены; debug-путь помечается `debug-only`.
Тесты, читающие историю git (`test_spec_status_consistency` и др.), в боковом worktree пропускаются — это ожидаемо. Из
Git Bash к `wsl.exe` с путём `/mnt/...` в аргументах — `MSYS_NO_PATHCONV=1`, иначе Git Bash переписывает путь.

## 0. Готовность окружения

```bash
wsl.exe -l -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "uname; pwd; test -f scripts/test.sh; test -f .venv/bin/activate; echo READY"
```

Ожидаемо: `READY`. Новых системных зависимостей нет.

## 1. Волна 1 — пакеты без зависимостей

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_073_narration_forms.py -q     # WP-A, SC-005
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_narration_coverage.py -q           # WP-A, без изменений
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_narration_exclusion_070.py -q      # WP-A, без изменений
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_generation.py -q                   # WP-A, протечка контекста
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_073_prompt_rules.py -q       # WP-B
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_audiobook_prompt.py -q             # WP-B, гарды промпта
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_070_request_golden.py -q      # WP-B, перевод/редактура побайтно
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_073_narration_minimax.py -q   # WP-G, SC-006
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_073_result_group.py -q        # WP-J
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_073_result_screen.py -q       # WP-K
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_result_screen.py -q       # WP-K, экран 072 без изменений
```

Ожидаемо: зелёные; характеристические тесты зелёные ДО и ПОСЛЕ правки.

## 2. Волна 2 — латиница, разделитель, словарь

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_073_latin_residue.py -q       # WP-C, SC-001 форма, SC-007 одна попытка
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_narration_residue.py -q            # WP-C
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_audiobook_repair.py -q             # WP-C
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_073_scene_breaks.py -q        # WP-D, SC-006 (сборка)
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_narration_groups.py -q    # WP-D, золотой .tts.txt 072
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_audiobook_pass.py -q               # WP-D
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_073_reading_glossary.py -q    # WP-E, SC-007 (словарь)
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_glossary_pass.py -q                # WP-E, 063 без изменений
```

## 3. Волна 3 — проводка словаря и поздний этап

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_073_reading_glossary_delivery.py -vv   # WP-F, SC-007 (секции блоков)
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_document_pipeline.py -q                       # WP-F, WP-H
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_073_late_phase.py -vv                   # WP-H, SC-006 (TXT = MiniMax без меток), FR-009
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_late_phase_exports.py -q            # WP-H, 072 без изменений
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_late_phases_finalize_gate_persistence.py -q  # WP-H
```

## 4. Волна 4 — раннер, гард событий, документы (WP-I)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_agent_contract_consistency.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_documentation_links.py -q
```

## 5. Приёмка (оркестратор, главное дерево)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/ -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_072_exports_system.py -q -m system_deps
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_status_consistency.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_where_we_are_freshness.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_typecheck.py -q
git status --porcelain
git diff --check
```

`test_typecheck.py` (pyright) идёт 40–120 с — timeout ≥ 180 000 мс. Перед «всё зелёное» вывод `git status --porcelain`
пуст.

**Проверка экрана в браузере (Streamlit Layout Contract).** Задача VS Code `Start Project`, во встроенном браузере —
короткий переведённый DOCX (`tests/sources/translated/rm_ch3_translated_ru.docx`) в режиме «Подготовка аудиокниги»
(платный вызов модели, ≈ 0,03 $ — **только с согласия владельца**; без согласия оркестратор пишет прямо, что экран
проверен только рендер-тестом WP-K). Проверить: строка «Текст для озвучки» — DOCX, PDF, TXT, «TXT для MiniMax», кнопки
растянуты; скачанный `<stem>.tts.minimax.txt` — метки `<#1.5#>` после названия главы и `<#0.8#>` после подзаголовков;
перевод и редактура — экран как до спеки.

## 6. FR-012 — замер (оркестратор, ПЛАТНО ≈ 0,42 $, только с согласия владельца)

**Сначала — проверка базы (бесплатно, research R14).** В главном дереве:

```bash
git log --since=2026-11-10T07:00:00Z --format="%h %cI %s" -- src/docxaicorrector/resources/prompts src/docxaicorrector/text src/docxaicorrector/document/narration_exclusion.py src/docxaicorrector/pipeline/audiobook_pass.py src/docxaicorrector/pipeline/audiobook_repair.py src/docxaicorrector/pipeline/narration_postprocess.py src/docxaicorrector/generation/_generation.py
```

Ожидаемо: `6379154`, `a1543bf`, `fa2a33e` и коммиты 073. Любой другой коммит, меняющий текст озвучки, — сначала новая
база (≈ 0,39 $, отдельное согласие). Базовые прогоны (gitignored, главное дерево
`tests/artifacts/real_document_pipeline/runs/`): `20261110T080357Z_41448_rm_ch3_translated_ru`,
`20261110T080639Z_41645_money_ch3_translated_ru`, `20261110T145422Z_18201_money_full_standard_translated_ru`.

Прогоны с 073 (по одному, дожидаясь окончания каждого):

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "DOCXAI_REAL_DOCUMENT_PROFILE=audiobook-rm-ch3-translated DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-standalone-audiobook bash scripts/run-real-document-validation.sh"
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "DOCXAI_REAL_DOCUMENT_PROFILE=audiobook-money-ch3-translated DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-standalone-audiobook bash scripts/run-real-document-validation.sh"
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "DOCXAI_REAL_DOCUMENT_PROFILE=audiobook-money-full-standard-translated DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-standalone-audiobook bash scripts/run-real-document-validation.sh"
```

Читать в `tests/artifacts/real_document_pipeline/runs/<run_id>/` и отчёте профиля:

| Что | Где | Ожидание / прогноз |
|---|---|---|
| латиница | `narration_artifact.latin_source_unit_count`, `residue_before_by_class.latin`, `residue_after_by_class.latin` | знаменатель 5 / 44 / 528 (R2); после — 0 (SC-001) |
| словарь | `reading_glossary_*`, `<basename>.reading_glossary.json` | найдено 4 / 17 / 68, принято ≈ всё; отброшено пределом 0 (R4) |
| одно чтение (SC-002) | скрипт оркестратора по образцу `D:\Temp\docxai-research\073\baseline_forms.py`: для каждого принятого кандидата — все вхождения в выходе и их формы | одна форма у каждого; TRC (база: 12 форм, две разные расшифровки) и CoR-EU — одна |
| номера разделов (SC-003) | тот же скрипт, заголовки с «N.» | 36 на полной Money, 5 в главе Money — одна форма; база — пять форм, в 9 из 36 добавлено «глава» (R3) |
| ударения (SC-004) | `stress_mark_count`, `stress_marks_per_1000_words`; 30 пар на главу — чтение | база 1 знак на книгу; набор омографов составляет читающий |
| разделители | `scene_break_count`, `minimax_pause_counts` | полная Money: 2; метки 23 / 132 / 2 (R9) |
| файлы | `output_artifacts.tts_minimax_path`, `reading_glossary_path` | есть; MiniMax без меток = `.tts.txt` (скрипт: удалить три вида меток) |
| цена | `model_accounting_stage_*_cost_usd` | всего ≈ 0,42 $; стадия словаря ≈ 0,004 $ на полной Money (R13) |
| покрытие | `coverage_low_count` до/после | может вырасти из-за транслитерации — review data |

При падении профиля — сначала свежий run report: `failed_checks` дословно с `actual` / `threshold` и отношением, только
потом гипотезы (AGENTS.md, Real-document failure analysis contract). Затем владелец слушает главу в ElevenLabs
(`.tts.docx`) и в Voice Studio (`.tts.minimax.txt`). Итоги — в Changelog спеки как есть (неудача критерия фиксируется, не
ретушируется).
