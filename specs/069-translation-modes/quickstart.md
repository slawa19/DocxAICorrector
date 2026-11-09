# Quickstart: проверка спеки 069

Все команды — канонический путь AGENTS.md: из не-WSL shell через `wsl.exe -d Debian --cd
"D:\Work\Projects\DocxAICorrector" -- …`; selector идёт до опций pytest. Финальное «зелёное» — только полный прогон в
ГЛАВНОМ дереве при пустом `git status --porcelain`. Скрипты `D:\Temp\docxai-research\069-plan\` — DEBUG-ONLY.

## 0. Готовность окружения

```bash
wsl.exe -l -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "uname; pwd; test -f scripts/test.sh; test -f .venv/bin/activate; echo READY"
```

## 1. Пакеты волны 1 — точечные тесты

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_translation_modes.py -q          # WP-1
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_generation_request_profile.py -q # WP-2
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_output_budget.py -q             # WP-2
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_model_accounting_069.py -q      # WP-3
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_polish_checks.py -q             # WP-4
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_cost_estimate.py -q             # WP-7
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_price_list.py -q                # WP-7
```

Ожидаемо: зелёные; золотой тест SC-006 (WP-2) зелёный ДО и ПОСЛЕ правки генератора — запросы `edit`, `audiobook`,
`translate` без профиля побайтно прежние.

## 2. Второй проход через обычный вход блока (WP-6)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_literary_polish.py -vv
```

Ожидаемо: принятая шлифовка доставлена и видна реестру, сноскам, аудиопроекции; каждый предикат даёт откат, строку
`.run/literary_polish_rollbacks/<run_id>.jsonl` (схема `contracts/literary-polish-rollbacks.schema.json`) и событие
`literary_polish_paragraph_rolled_back`; Stop во время шлифовки последнего блока — блок доставлен первым проходом,
прогон остановлен; счётчики disposition первого прохода одинаковы со шлифовкой и без.

## 3. Примечания и шлюз (WP-5)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_069_notes_gate.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_spec_069_notes_apparatus.py -q
```

Ожидаемо: цепочка примечаний считается по непереведённой части; анти-вакуум — цепочка с непереведёнными определениями
(форма Haiku D) по-прежнему блокирует документ; порог 2 000 символов / 2 % прежний. Соседние существующие наборы — `tests/test_gate_detectors_stage2.py`, `tests/test_spec_067_apparatus_in_body.py` — тоже зелёные. (Окончательные имена тестовых файлов уточнит
`tasks.md` по фактическому расположению тестов шлюза и исполнения блока.)

Офлайн-повтор на данных bake-off (DEBUG-ONLY, после слияния WP-5 — та же арифметика должна дать 346–348 у Gemini-
вариантов Money и ≈ 3 656 у D):

```bash
MSYS_NO_PATHCONV=1 wsl.exe -d Debian -- /mnt/d/Work/Projects/DocxAICorrector/.venv/bin/python -I /mnt/d/Temp/docxai-research/069-plan/fr005_gate_replay.py
```

## 4. UI (WP-8)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_ui_translation_modes.py -vv
```

Ручная проверка во встроенном браузере (Streamlit Layout Contract AGENTS.md): операция «Перевод» → радио «Стандарт»
(выбрано) / «Качество»; селектора модели в «Дополнительно» нет; до загрузки — без цены; после подготовки — «≈ X–Y $»;
после прогона — факт рядом с оценкой, подпись «без картинок». Операция «Редактирование» — всё как раньше.

## 5. Полный прогон и приёмка

```bash
git status --porcelain            # пусто
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/ -q
git diff --check
```

Затем — расширенное ревью Codex по всем затронутым поверхностям (AGENTS.md, «Обязательная приёмка оркестратора»),
отчёт в `docs/reviews/CODEX_REVIEW_069_<YYYY-MM-DD>.md`.

## 6. FR-008 — платный замер (только после согласия владельца на сумму ≈ 5–6 $)

Коэффициенты `resources/cost_estimate_coefficients.json` заморожены ДО прогонов (версия попадает в отчёт).

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-full-benchmark DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-benchmark-standard bash scripts/run-real-document-validation.sh"
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-full-benchmark DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-benchmark-quality bash scripts/run-real-document-validation.sh"
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "DOCXAI_REAL_DOCUMENT_PROFILE=money-sustainability-pdf-full-heldout DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-benchmark-standard bash scripts/run-real-document-validation.sh"
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc "DOCXAI_REAL_DOCUMENT_PROFILE=money-sustainability-pdf-full-heldout DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-benchmark-quality bash scripts/run-real-document-validation.sh"
```

Что читать в `tests/artifacts/real_document_pipeline/runs/<run_id>/`:

| Критерий | Где |
|---|---|
| режим и эффективные модели/рассуждение обоих проходов | `report.json` runtime-config, `run_summary.txt` `runtime_overrides` |
| SC-002: 0 токенов рассуждения, 0 `incomplete` («Качество») | `run_summary.txt`: рассуждение по стадиям, `retry_reason_counts` |
| SC-001: знаменатель и каждый откат | `model_accounting.literary_polish` (`sent_paragraph_count`, `rollback_reason_counts`), `literary_polish_rollbacks.jsonl` |
| SC-003: Money гл. III доставлена, (а)–(в) FR-005 | `delivered.md` примечания главы III; `untranslated_body_text_samples` отчёта |
| SC-004: глоссарий без обрезанных вызовов, ±15 % терминов | секция `run_glossary` (`calls[].completion_tokens` против `max_output_tokens`) |
| SC-005: оценка против факта | секция `cost_estimate`, событие `cost_estimate_vs_actual` в `events.jsonl` |
| причина скидки | `stages.*.cached_tokens`, `cache_discount_usd`, `cache_fields_reported_call_count` |
| Anti-regression 2 (инварианты 063–068) | `failed_checks` отчёта; при падении — контракт «Real-document failure analysis» AGENTS.md до любой гипотезы |

Слепое чтение (SC-001/SC-002): для каждой главы bake-off — ОДИН рецензент в ОДНОМ раунде: новые тексты обоих режимов
против замороженных якорей C, G-low-cons, A плюс 10 абзацев, повторённых под другим кодом (контроль воспроизводимости);
сравнение — только внутри раунда. Тексты глав берутся из полных прогонов по диапазонам абзацев
`D:\Temp\docxai-research\069-bakeoff\chapters.md` §1 (RM p0257–p0359, Money p0390–p0501 соответствующих прогонов;
номера сверить по `source_paragraphs.json` нового прогона) — отдельные платные прогоны глав не нужны.
