# Quickstart: проверка спеки 070

Все команды — канонический путь AGENTS.md: из не-WSL shell через `wsl.exe -d Debian --cd
"D:\Work\Projects\DocxAICorrector" -- …`; один selector на команду, selector ДО опций pytest. Финальное «зелёное» —
только полный прогон в ГЛАВНОМ дереве при пустом `git status --porcelain`. В боковом worktree заменить путь в `--cd` на
`D:\Temp\claude\wt-070-<slug>` (`.venv` — симлинк на главное дерево). Голый `python`, `.venv-win`, `py -m pytest`
запрещены; debug-путь помечается `debug-only`.

## 0. Готовность окружения

```bash
wsl.exe -l -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "uname; pwd; test -f scripts/test.sh; test -f .venv/bin/activate; echo READY"
```

## 1. Волна 1 — точечные тесты пакетов

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_070_postpass_removed.py -q     # WP-A
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_config_keys_are_read.py -q          # WP-A, гард
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_070_request_golden.py -q       # WP-C, SC-004
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_audiobook_prompt.py -q              # WP-C
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_generation_request_profile.py -q    # WP-C (069, случай audiobook)
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_narration_exclusion_070.py -q       # WP-D
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_audiobook_plan.py -q                # WP-D
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_narration_cleanup.py -q             # WP-E
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_unicode_emoji_data.py -q            # WP-E
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_narration_residue.py -q             # WP-E
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_narration_coverage.py -q            # WP-E
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_audiobook_repair.py -q              # WP-F
```

Ожидаемо: зелёные; `test_spec_070_request_golden.py` зелёный ДО и ПОСЛЕ правок WP-C (переводы и редактура побайтно
прежние).

## 2. Волна 2 — режим без языков и модель (WP-B)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_audiobook_language_free.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_audiobook_model.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_ui.py -q
```

Ручная проверка во встроенном браузере (Streamlit Layout Contract AGENTS.md): «Перевод» → выбрать языки → переключить
на «Подготовка аудиокниги»: селекторов «Целевой язык» и «Язык оригинала» нет, рекомендаций по языку нет, в
«Дополнительно» — модель `[models.audiobook]` (или `[models.text]`); «Перевод» и «Редактура» — флажка ElevenLabs нет.

## 3. Волна 3 — проход блока целиком (WP-G)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_audiobook_pass.py -vv
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_narration_markdown.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_document_pipeline.py -q
```

Ожидаемо: через обычный вход блока с двойником генератора — исключённые абзацы не отправлены и стоят в DOCX
исходником; пустой ответ → исходный текст + `needs_review`; остаток → ровно один вызов исправления, сломанный ответ →
прежний текст; итоговый `.tts.txt` разбирается обратно в ожидаемые ID; детерминированные склейки — с парами ID.

## 4. Волна 4 — раннер, отчёт, логирование (WP-H)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_real_document_validation_corpus.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_script_contract_static.py -q
```

## 5. Полный прогон и приёмка (главное дерево, интеграционная ветка)

```bash
git status --porcelain            # пусто
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/ -q
git diff --check
```

Гарды отдельными командами: `tests/test_spec_status_consistency.py`, `tests/test_where_we_are_freshness.py`,
`tests/test_documentation_links.py`, `tests/test_prompts_carry_no_corpus_literals.py`, `tests/test_typecheck.py`
(pyright 40–120 с; timeout ≥ 180000 мс). Затем — расширенное ревью Codex по всем затронутым поверхностям (AGENTS.md,
«Обязательная приёмка оркестратора»), отчёт `docs/reviews/CODEX_REVIEW_070_<YYYY-MM-DD>.md`.

## 6. FR-009 — платный замер (только после слияния в `main` и подтверждения суммы владельцем; бюджет спеки ≈ 1 $)

### 6.1 До прогона — snapshot исключений (LLM-free, бесплатно)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/run-structural-preparation-diagnostic.sh audiobook-rm-ch3-translated > .run/070_snapshot_rm_ch3.json
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/run-structural-preparation-diagnostic.sh audiobook-money-ch3-translated > .run/070_snapshot_money_ch3.json
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/run-structural-preparation-diagnostic.sh audiobook-money-full-standard-translated > .run/070_snapshot_money_full.json
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc ". .venv/bin/activate && export PYTHONPATH=\"\$PWD/src:\$PWD\" && python scripts/measure-narration-exclusion.py --operation audiobook --per-paragraph tests/sources/translated/rm_ch3_ru.docx tests/sources/translated/money_ch3_ru.docx tests/sources/translated/money_full_standard_ru.docx > .run/070_exclusions.json"
```

(Последняя команда передаёт `$PWD` внутрь `bash -lc` с экранированием — на границе Git Bash → `wsl.exe` неэкранированный
`$VAR` схлопывается, AGENTS.md «Боковые worktree».) Читать: каждый абзац с причиной `fragment` — глазами (SC-001:
ни один заголовок, эпиграф, проза); заголовок главы, эпиграф и атрибуция начала главы — без причины.

### 6.2 Прогоны (канонический раннер; полный прогон — веха, не цикл настройки)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "DOCXAI_REAL_DOCUMENT_PROFILE=audiobook-rm-ch3-translated DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-standalone-audiobook bash scripts/run-real-document-validation.sh"
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "DOCXAI_REAL_DOCUMENT_PROFILE=audiobook-money-ch3-translated DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-standalone-audiobook bash scripts/run-real-document-validation.sh"
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "DOCXAI_REAL_DOCUMENT_PROFILE=audiobook-money-full-standard-translated DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-standalone-audiobook bash scripts/run-real-document-validation.sh"
```

При падении профиля — сначала свежий run report: дословно `failed_checks` с `actual` / `threshold` и overage ratio
(AGENTS.md «Real-document failure analysis contract»), только потом гипотезы.

### 6.3 Что читать в `tests/artifacts/real_document_pipeline/runs/<run_id>/`

| Критерий | Где |
|---|---|
| SC-001: распознанное не звучит; 0 HTML/эмодзи/тегов; каждое `fragment` прочитано | `narration_artifact.excluded_by_reason`, `excluded_paragraph_ids_by_reason`; `residue_after_by_class.html_left/emoji_left/tag_form`; snapshot §6.1 |
| SC-002: цифры после исправления ≤ 1 % озвучиваемых ID; до/после по классам | `residue_before_by_class`, `residue_after_by_class`, `expected_paragraph_count`; каждое `needs_review` с `residue` — прочитать |
| SC-003: 0 потерянных ID, 0 склеек модели, склейки с адресами, нет утраченных чисел/отрицаний | `missing_paragraph_ids`, `paragraph_boundary_check`, `deterministic_join_pairs`; выборка 30 абзацев на главу против входа (оркестратор) |
| SC-005: цена основного прохода и исправления | `model_accounting.stages.text_generation`, `stages.audiobook_repair` (полная книга) |
| `needs_review` | событие `audiobook_needs_review` в `events.jsonl` (адреса и образцы) |

Выборка 30 абзацев на главу: равномерно по `expected` ID (каждый `⌊N/30⌋`-й), плюс все абзацы с `needs_review`;
читать вход (DOCX перевода) против `.result.tts.txt`. Прослушивание трёх глав в ElevenLabs — шаг владельца, результат —
в Changelog спеки.
