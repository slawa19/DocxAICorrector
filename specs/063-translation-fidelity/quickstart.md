# Quickstart: P2 спеки 063 — глоссарий прогона

Все команды — из Windows-shell через транспорт WSL (`AGENTS.md`, Runtime Contract); в боковом
дереве подставьте его путь вместо `D:\Work\Projects\DocxAICorrector`.

## 1. Детерминированные тесты (без модели)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_glossary_pass.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_config.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_document_pipeline.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_real_document_pipeline_validation.py -q
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash scripts/test.sh tests/test_script_contract_static.py -q
```

Ожидается: извлечение по форме ловит синтетические имена/термины и не ловит служебные слова;
богословский путь рендерится как прежде; фаза для `translate` дописывает раздел в промпт, для
`edit`/`audiobook` не делает ничего; сбой вызова не роняет прогон и даёт `run_glossary_failed`;
раннер пишет `run_glossary_*`.

## 2. Кандидаты на книге (WSL, без модели)

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc ". .venv/bin/activate && export PYTHONPATH=\$PWD/src:\$PWD && python scripts/measure-glossary-candidates.py --document-profile money-sustainability-pdf-full-heldout --reviewer-terminology /mnt/d/Temp/docxai-runs/2026-11-07-translate/money_sustainability/review/terminology.json --out /mnt/d/Temp/claude/glossary-evidence/money.candidates.json"
```

Ожидается: ~400 кандидатов; строка `reviewer terms in candidates: 21/24` (research R3).

## 3. Один живой вызов извлечения (тратит API, ≤ $0,50)

Тот же скрипт с `--live`; печатает число записей, `prompt_tokens`, `completion_tokens`,
`cost_usd`, символы раздела промпта и отношение символов запроса к входным токенам. Полную книгу
не прогонять: full-book — milestone (SC-006), а не шаг проверки.

## 4. Согласованность передач по записанному прогону (без репозитория)

```bash
python3 -I scripts/measure-glossary-consistency.py --pairs /mnt/d/Temp/docxai-runs/2026-11-07-translate/money_sustainability/pairs.jsonl --glossary <артефакт .run/run_glossaries/….json>
```

Ожидается: по каждому термину — пары с термином в источнике, доля пар с закреплённой передачей и
номера `idx` остальных. Тот же глоссарий по прогону без глоссария (2026-11-07) и по прогону с ним
(SC-006) — это сравнение «с глоссарием и без».

## 5. Где смотреть после настоящего прогона

- `.run/run_glossaries/*.json` — глоссарий, кандидаты, учёт вызова;
- `.run/app.log` — `run_glossary_built` / `run_glossary_failed`;
- отчёт real-document прогона — секция `run_glossary`; summary — строки `run_glossary_*`;
- экран результата — уведомление «Глоссарий книги: N терминов…».

## 6. Финальная проверка

`git diff --check`; `tests/test_spec_status_consistency.py`; pyright (`tests/test_typecheck.py`,
таймаут ≥ 180 с); полный прогон `scripts/test.sh tests/ -q` в рабочем дереве; `git status --porcelain`
пуст перед утверждением «зелёное».
