# Код-ревью рефакторинга state / preparation / runtime

Дата: 2026-03-11
Тесты: 181 passed, 4 skipped

## Summary
Рефакторинг в целом сильный: orchestration вынесен из app-entrypoint, runtime events типизированы, restart-flow и preparation-flow стали понятнее.
После доработок warning-проблемы из этого отчёта закрыты; остаётся одна memory-ориентированная рекомендация по `completed_source`.

## Issues Found
| Severity | File:Line | Issue | Status |
|---|---|---|---|
| WARNING | application_flow.py:78 | has_restartable_source() не проверяет реальное существование restart-файла и может показывать ложное restartable-состояние после внешней очистки `.run/`. | Closed in current branch |
| WARNING | preparation.py:78 | На cache miss heavy prepared document копируется в cache и затем ещё раз клонируется на выдачу, что создаёт лишний пик памяти и object churn. | Closed in current branch |
| WARNING | tests/test_app.py:147 | Тест `test_has_restartable_source_does_not_materialize_restart_bytes()` не мокает `load_restart_source_bytes()` и даёт false positive. | Closed in current branch |
| SUGGESTION | processing_runtime.py:180 | completed_source хранит полный исходный DOCX в session_state, что решает rerun UX ценой дополнительной памяти. | Addressed in current branch |
| WARNING | app.py:140 | Повторный запуск успешного результата без повторной загрузки был потерян в первой версии рефакторинга. | Closed in current branch |
| WARNING | processing_runtime.py:179 | Временный restart-файл сначала не очищался после successful run и оставлял лишнюю копию исходного DOCX на диске. | Closed in current branch |

## Detailed Findings
### 1. Stale restart metadata
application_flow.py:78
- Confidence: 94%
- Problem: predicate now cheap, but it trusts metadata only. If `.run/` was cleaned externally, UI can still announce restartability although restore will fail.
- Recommendation: add cheap `Path(storage_path).is_file()` check or clear stale restart_source on first failed read.

### 2. Double copy on preparation cache miss
preparation.py:78
- Confidence: 88%
- Problem: session cache is now bounded and much better than global LRU, but miss path still duplicates large prepared structures twice in one rerun.
- Recommendation: keep one independent returned copy, but avoid the second transient deepcopy on miss.

### 3. False-positive test
tests/test_app.py:147
- Confidence: 96%
- Problem: test name claims it checks that restart bytes are not materialized, but the body never wires load tracking into application_flow and therefore cannot fail for the wrong reason.
- Recommendation: monkeypatch `application_flow.load_restart_source_bytes` to append into a shared list and assert zero calls.

### 4. completed_source memory tradeoff
processing_runtime.py:180
- Confidence: 81%
- Problem: successful session now keeps source DOCX, final DOCX and markdown at once.
- Recommendation: if large real-world documents show memory pressure, add size limits or first-rerun cleanup policy.

## Recommendation
APPROVED WITH FOLLOW-UP IDEA