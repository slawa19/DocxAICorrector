# Code Review — Round 10 (2026-07-20)

- **Date:** 2026-07-20
- **Commit reviewed:** `main` @ `23020a9` (spec 043 merged, PR #5)
- **Scope:** архитектура и взаимодействие ключевых модулей end-to-end (UI → processing → pipeline → document/pdf_import/structure → generation/image → reader cleanup → validation/gates → runtime state/artifacts → config)
- **Method:** обязательный контекст (AGENTS.md, constitution v1.1.1, README, WORKFLOW_AND_IMAGE_MODES, STARTUP_PERFORMANCE_CONTRACT, LOGGING_AND_ARTIFACT_RETENTION, спеки 024–043) → 6 параллельных ревью-агентов по границам подсистем → личная верификация каждого P1 и ключевых P2 по текущему коду (static trace, grep, чтение точных строк). Тесты не запускались.
- **Status:** findings задокументированы; **исправления НЕ применялись**. Спеки/план/код не создавались.
- **Constitution:** соблюдены VII (universal rules, coverage = review data) и VIII (evidence fresher than fix) — все живые claim'ы проверены против текущего кода, а не сохранённых отчётов.

> Замечание о достижимости: F4 (мёртвый переключатель reader cleanup в UI) означает, что «deferred build path» спеки 043 сейчас достижим **только** в validation harness. Несколько findings (F7 и часть P2) сегодня проявляются в harness-прогонах; после фикса F4 они становятся mainline.

---

## 1. Краткий вывод

Взаимодействие подсистем после девяти раундов ревью в целом зрелое: порядок стадий корректен, гейты после спек 037–043 судят финальный документ, Constitution VII в валидации соблюдена, секреты не текут, детерминизм подготовки чистый. Главный системный риск сместился на «последнюю милю»: между pipeline и пользователем корректно заблокированный или деградированный результат становится неотличим от успеха — UI рендерит gate-fail как зелёный успех, marker-fallback доставляет служебные маркеры в итоговый DOCX мимо review-механики, advisory-падение cleanup затирается пустым `last_error`. Второй системный риск — расхождение harness/production: reader cleanup из-за несовпадения ключей конфига работает только в валидационном harness и никогда — в UI-запусках. Третий — одно живое нарушение Constitution VII в `roles.py` и тихая порча двухколоночных PDF. Архитектурный рефакторинг не нужен: все findings устраняются локальными S/M-фиксами; три P1 требуют Spec Kit, остальное — узкие исправления с очевидным ожидаемым поведением.

---

## 2. Карта основного workflow

```
ui/_app.py ──freeze_uploaded_file──▶ processing_runtime (normalization boundary:
  │   token = sha(SOURCE bytes) для doc/pdf; payload = normalized DOCX bytes)
  ├─▶ application_flow ──▶ preparation.py (2-tier cache: session + shared,
  │     key = token:chunk_size[:cid]; deterministic roles/segments)
  │       └─▶ document/extraction → roles → boundaries → semantic_blocks
  │            ▲ pdf_import/logical_import → generated DOCX (роли схлопываются
  │              до Heading N / List Bullet, re-derive в extraction)
  ├─▶ processing_service ──worker──▶ pipeline/setup.execute_processing_run
  │       blocks (block_execution → generation._generation, marker mode)
  │       → image phase → placeholder-integrity gate → docx build
  │         (deferred если reader cleanup) → late_phases.finalize:
  │         pre-gate → reader_cleanup_postprocess → rebuild → re-collect
  │         diagnostics → caption/markdown re-gate → narration →
  │         emit_state → write_ui_result_artifacts → "completed"
  └─◀ SetStateEvent (allowlist) ◀── drain_processing_events ◀── worker
        session_state → рендер результата / restart_* / completed_* store
```

Ключевые контракты: `FrozenUploadPayload` (token ≠ payload bytes для pdf/doc), `prepared_source_key`, marker registry (`[[DOCX_PARA_id]]`), `formatting_diagnostics` артефакты (mtime-окно), `SetStateEvent` allowlist, `latest_result_notice`, acceptance verdict в quality report.

---

## 3. Findings

Приоритеты: P0 — потеря/повреждение данных или систематический срыв основного workflow; P1 — вероятный дефект ключевого сценария / серьёзное нарушение контракта; P2 — реальная ограниченная проблема, чинится локально.

### [P1] F1 — Marker-mode fallback доставляет литеральные `[[DOCX_PARA_…]]` в итоговый DOCX и обходит review-механику

- **Код:** `src/docxaicorrector/generation/_generation.py:1059`, `:1086`, `:1104` (корректный образец рядом — `:1073` возвращает `target_text_for_leakage`); вход `src/docxaicorrector/pipeline/block_execution.py:438`; классификация `src/docxaicorrector/pipeline/output_validation.py:287-295`.
- **Взаимодействие:** `block_execution → generation → output_validation → reassembly → Pandoc DOCX`.
- **Сценарий:** любой edit/translate с дефолтами (`enable_paragraph_markers = true`), один блок с повторной empty/incomplete/non-completed ошибкой модели, recovery тоже падает → fallback возвращает обёрнутый маркерами текст.
- **Почему реально:** маркеры снимает только сам `generate_markdown_block` на нормальном пути; downstream `[[DOCX_PARA_` нигде не вычищается (grep). `is_source_text_fallback_output` требует точного равенства с чистым `payload.target_text` — маркер-префиксы делают строки неравными, блок классифицируется `valid`, controlled-fallback review пропускается.
- **Последствие:** видимые служебные строки в доставленном DOCX (по одной на абзац блока); для translate — untranslated-блок мимо review.
- **Вероятность:** средняя. **Ущерб:** высокий (тихая порча документа).
- **Минимальное исправление:** в трёх ветках возвращать `target_text_for_leakage`. **Стоимость:** S.
- **Проверка:** unit-тест `generate_markdown_block(marker_mode=True, …)` со всегда-падающим клиент-стабом → в ответе нет `[[DOCX_PARA_`.

### [P1] F2 — UI рендерит заблокированный quality-gate результат как зелёный «Документ обработан»; `latest_result_notice` — мёртвый канал

- **Код:** `src/docxaicorrector/pipeline/late_phases.py:692-702`, `:907` (fail-ветка кладёт `latest_docx_bytes` + error-notice); `src/docxaicorrector/ui/_app.py:1000-1003` (`has_completed_result` смотрит только на байты+токен), `:692`; grep: `latest_result_notice` не читается ни одним модулем `ui/`.
- **Взаимодействие:** `late_phases → SetStateEvent → drain → session_state → ui/_app → render_result_bundle`.
- **Сценарий:** translate-прогон с фатальной причиной гейта (untranslated body выше порога либо caption→heading конфликт из спек 042/043). Гейт блокирует доставку на диск (`.run/ui_results` пуст), но session state получает байты, и на следующем кадре UI показывает красный `last_error` и одновременно зелёный success-блок с primary-кнопками скачивания отклонённого DOCX.
- **Последствие:** пользователь скачивает документ, который гейт классифицировал как дефектный, со статусом «успех»; аудит («blocked») противоречит фактической доставке.
- **Вероятность:** средняя (спеки 041–043 сделали фатальные причины чаще). **Ущерб:** высокий — обесценивается сам delivery gate.
- **Минимальное исправление:** в `_render_completed_result_view`/`main` читать `latest_result_notice` (level=error → `st.error`, без success-обёртки) и/или гейтить `has_completed_result` на `processing_outcome != FAILED`. **Стоимость:** S.
- **Проверка:** UI-тест: seed session state как fail-ветка → кадр не содержит `result.success_document_processed`, содержит block-notice.

### [P1] F3 — Для PDF/DOC persisted source хранит DOCX-байты под токеном исходника; восстановление пересчитывает другой токен и уничтожает готовый результат

- **Код:** `src/docxaicorrector/processing/processing_runtime.py:1266` (identity по source-байтам для doc/pdf), `src/docxaicorrector/processing/application_flow.py:198-203` (в UI уходит `payload.content_bytes` = DOCX), `src/docxaicorrector/ui/_app.py:1040` → `processing_runtime.py:1932-1938` (store с этим токеном, но DOCX-байтами), `src/docxaicorrector/ui/application_flow.py:160-184` (восстановление in-memory файла из DOCX-байтов), `processing/application_flow.py:206-216` (mismatch → `reset_run_state(keep_restart_source=False)`).
- **Взаимодействие:** `ui → processing_runtime (freeze) → restart_store → ui/application_flow (reload) → freeze снова → sync_selected_file_context`.
- **Сценарий:** загрузить PDF/legacy-DOC → успешная обработка → снять файл с uploader'а (штатный сценарий, ради которого `completed_source` существует; для DOCX работает). Пересчитанный по DOCX-байтам токен не совпадает с сохранённым → полный reset: `latest_docx_bytes` стёрт, completed-файл удалён; бонус — гарантированный miss preparation cache и синхронная полная переподготовка на render-потоке без live-статуса (`_app.py:901-915`, нарушение инварианта 1 STARTUP_PERFORMANCE_CONTRACT). То же бьёт restart-поток после stop/fail PDF-прогона.
- **Последствие:** потеря готового результата, удаление persisted source, многоминутный фриз UI, противоречивое состояние сессии.
- **Вероятность:** средняя. **Ущерб:** высокий.
- **Минимальное исправление:** при восстановлении из store доверять сохранённому токену (payload с `file_token` из `restart_source["token"]`, минуя re-derivation) — либо хранить исходные source-байты. **Стоимость:** M.
- **Проверка:** тест `resolve_effective_uploaded_file` + `prepare_run_context` с completed_source, чей token построен из PDF-байтов, а сохранены DOCX-байты → reset не происходит, `latest_docx_bytes` живы.

### [P1] F4 — Переключатель reader cleanup мёртв в UI: конфиг пишет `reader_cleanup_default`, pipeline читает `reader_cleanup_enabled`

- **Код:** `src/docxaicorrector/core/config_runtime_sections.py:83-85` (env `DOCX_AI_READER_CLEANUP_ENABLED` → `reader_cleanup_default`), `src/docxaicorrector/pipeline/reader_cleanup_rebuild.py:45-48` и `src/docxaicorrector/reader_cleanup_mvp/_config.py:23` (гейт читает `reader_cleanup_enabled`), `src/docxaicorrector/ui/_app.py:725-730` (маппинга нет); единственный, кто маппит — `src/docxaicorrector/validation/profiles.py:328` (harness).
- **Взаимодействие:** `config → ui/_app (dict(AppConfig)) → pipeline gate`.
- **Сценарий:** оператор ставит `DOCX_AI_READER_CLEANUP_ENABLED=true` (или `reader_cleanup_default=true`) и запускает translate через приложение — post-pass тихо не выполняется. Верифицировано grep-ом: `reader_cleanup_enabled` в UI-пути не выставляется нигде.
- **Почему важно системно:** весь «deferred build path» спеки 043 достижим только в harness; поведение, провалидированное на 4 книгах, не доезжает до пользователей.
- **Последствие:** тихое отсутствие оплаченной фичи + harness/production divergence.
- **Вероятность:** гарантированно при использовании переключателя. **Ущерб:** средний.
- **Минимальное исправление:** в `_app.py` рядом с остальными sidebar-ключами добавить `app_config["reader_cleanup_enabled"] = bool(app_config.get("reader_cleanup_default", False))`, либо fallback в `_should_run_reader_cleanup`/`resolve_reader_cleanup_config`. **Стоимость:** S.
- **Проверка:** env=true → `load_app_config` → сборка `app_config` как в `_app.main` → `_should_run_reader_cleanup(...)` == True (сегодня False).

### [P1] F5 — `promote_short_standalone_headings`: «≤4 слова без точки ⇒ заголовок» без типографского сигнала — живое нарушение Constitution VII

- **Код:** `src/docxaicorrector/document/roles.py:230-236` (very-short ветка промоутит без проверки шрифта; соседняя ветка 5–6 слов на `:238-254` требует шрифтовую дельту), предикат `:464-469`; вызывается безусловно для каждого документа из `src/docxaicorrector/document/extraction.py:234-238`.
- **Взаимодействие:** `extraction → roles → rendered_text (## …) → Pandoc DOCX + segments`.
- **Сценарий:** атрибуция эпиграфа «— Джон Мейнард Кейнс», подпись, однострочная строка письма/стиха между body-абзацами. Единственный guard (`_is_short_centered_epigraph_attribution_candidate`) требует `alignment=center` И ALL-CAPS — PDF-derived абзацы приходят с `alignment=None`, а AI-стадия, ставившая `attribution`, удалена 2026-06-22.
- **Почему нарушение:** Constitution VII v1.1.1 дословно запрещает реконструкцию структуры из «length, position, capitalisation»; запретный пример из конституции — эта ветка минус цифра.
- **Последствие:** body-строки рендерятся заголовками, портя outline, сегментацию, formatting mapping.
- **Вероятность:** средняя (любая книга с эпиграфами/атрибуциями). **Ущерб:** средний, структурный.
- **Минимальное исправление (VII-совместимое):** требовать для ≤4-словной ветки ту же типографскую корреборацию, что и для 5–6-словной (шрифтовая дельта ИЛИ strong format). **Стоимость:** S. Поведение закреплено тестами → нужен Spec Kit.
- **Проверка:** три body-абзаца 11pt без alignment, средний «— Джон Кейнс» → остаётся `role="body"` (сейчас — heading h2).

### [P1] F6 — Двухколоночные selectable-text PDF: чтение перемешивается, а quality gate пропускает их как «promising»

- **Код:** `src/docxaicorrector/pdf_import/logical_import.py:121` — `sorted(..., key=(page_number, top, x0))` глобально по странице; `src/docxaicorrector/pdf_import/text_layer_quality.py:497-538` — в решении гейта нет колоночного сигнала.
- **Взаимодействие:** `processing_runtime → pdf_import gate → build_paragraph_units → extraction → весь pipeline`.
- **Сценарий:** пользователь загружает обычный двухколоночный PDF (статья, отчёт). Сортировка чередует строки колонок; merge-эвристики склеивают их в абзацы перемешанной прозы; гейт видит плотный текст со структурными сигналами → `promising` → «успешный» импорт без предупреждения.
- **Последствие:** оплаченный edit/translate поверх мусора; на выходе — испорченный документ, тихо. Корпус (4 одноколоночные книги) этот класс не проверяет.
- **Вероятность:** средняя для произвольных загрузок (для текущего корпуса не проявляется). **Ущерб:** тотальный для затронутого документа.
- **Минимальное исправление (geometry-general, VII-safe):** детекция двух доминирующих x0-кластеров с вертикальным перекрытием → причина `multi_column_layout` → typed refusal `insufficient`. **Стоимость:** M, через Spec Kit.
- **Проверка:** синтетические спаны двух колонок → гейт отказывает (или абзацы не чередуют колонки).

### [P2] F7 — Недодел спеки 043: refreshed acceptance verdict на ветке «deferred + unchanged markdown» строится из stale-пустого списка диагностик

- **Код:** `src/docxaicorrector/pipeline/late_phases.py:955` использует `formatting_diagnostics_artifacts` (пустой при deferred), тогда как соседняя ветка `:848` корректно берёт `post_cleanup_formatting_diagnostics_artifacts` (свежесобранный на `:794-797`). Спека 043 текстуально требует именно этого.
- **Сценарий:** самый частый harness-прогон — cleanup включён, no-op, конфликтов нет → сохранённый verdict утверждает `caption_heading_conflict_absent: applicable=False, reason="no_formatting_diagnostics"` при реально существующих на диске диагностиках финального DOCX. Доставка не затронута, портится аудиторская запись.
- **Смежные honesty-гэпы того же семейства:** вакуумный pass `reader_cleanup_stage_completed` (`quality_gate.py:1164` хардкодит `reader_cleanup_evidence={}` → `acceptance.py:420-435` пропускает при пустом статусе); невыпущенный user-notice по диагностикам на deferred-пути.
- **Достижимость:** сегодня harness; после фикса F4 — mainline.
- **Вероятность:** высокая (дефолтная конфигурация harness). **Ущерб:** средний (честность отчёта).
- **Исправление:** на `:955` подставить `post_cleanup_formatting_diagnostics_artifacts` (в non-deferred случае — алиас, поведение байт-идентично). **Стоимость:** S.
- **Проверка:** deferred-прогон, no-op cleanup, артефакт диагностики от финального билда → в сохранённом verdict `caption_heading_conflict_absent.applicable == True`, `failed_checks` без изменений.

### [P2] F8 — Stop игнорируется во всём «хвосте» pipeline; остановленный прогон завершается как succeeded

- **Код:** единственные проверки — `src/docxaicorrector/pipeline/block_execution.py:1104` и `src/docxaicorrector/pipeline/setup.py:357`; в `late_phases`/`reader_cleanup_postprocess`/`narration_postprocess` предиката нет.
- **Сценарий:** Stop через секунду после последнего блока на большой книге с cleanup+audiobook → минуты оплаченных LLM-вызовов, терминальный статус «Документ обработан полностью» при `processing_stop_requested=True`.
- **Вероятность:** средняя. **Ущерб:** средний (расход API после отмены + ложный статус).
- **Исправление:** проверки стопа перед docx-build фазой, в chunk-провайдерах cleanup и перед narration. **Стоимость:** M.
- **Проверка:** фейковый `should_stop_processing`, True после блочного цикла → результат `stopped`, cleanup-LLM не вызывался, артефакты не записаны.

### [P2] F9 — Advisory-падение reader cleanup невидимо: `result_notice=None`, а `last_error` затирается терминальным emit'ом

- **Код:** `src/docxaicorrector/pipeline/reader_cleanup_postprocess.py:444-449` (notice только для strict), `:470-478` (`last_error` выставлен) → `src/docxaicorrector/pipeline/late_phases.py:1111` перезаписывает `last_error=narration_error_message` (`""`).
- **Сценарий:** LLM/schema-ошибка в cleanup при дефолтной advisory-политике → пользователь получает сырой результат, считая его вычищенным; след — только в серверных логах. Контраст: audiobook-ветка тот же случай честно доносит (`late_phases.py:1003-1021`).
- **Вероятность:** средняя (когда cleanup включён — см. F4). **Ущерб:** низко-средний.
- **Исправление:** зеркалить audiobook-паттерн — `last_error=narration_error_message or reader_cleanup_error_message`, и/или notice для advisory. **Стоимость:** S.
- **Проверка:** offline-finalize с падающим `run_reader_cleanup` (advisory) → терминальное состояние несёт непустой `last_error` или notice.

### [P2] F10 — Inline-форматирование в Pandoc round-trip: underline теряется всегда; `**bold **` и `^note 1^` доезжают литеральными символами

- **Код:** `src/docxaicorrector/document/extraction.py:1421-1422` эмитит `<u>…</u>`, который `src/docxaicorrector/generation/_generation.py:1154-1165` не транслирует (только sup/sub/br); `extraction.py:1400-1427` оборачивает run-текст без выноса краевых пробелов (`**bold **` — невалидный strong), `^note 1^` с пробелом — невалидный superscript.
- **Сценарий:** любой документ с подчёркиванием (потеря гарантированная, не видна даже как review data — emphasis-диагностика считает только bold/italic) или с trailing-пробелом внутри bold-run (очень частый DOCX-случай) → видимые `**`/`^` в доставленном документе.
- **Вероятность:** высокая по покрытию. **Ущерб:** низко-средний, но user-visible.
- **Исправление:** `<u>` → `[…]{.underline}`; выносить lead/trail пробелы за обёртку; экранировать пробелы в `^…^`. **Стоимость:** S.
- **Проверка:** `convert_markdown_to_docx_bytes("a <u>b</u> c")` → run с underline; bold-run `"bold "` → нет литеральных `*`.

### [P2] F11 — Маркер подготовки не включает языки: смена языка после preparation кормит модель контекст-промптом с неверной языковой парой

- **Код:** `src/docxaicorrector/processing/processing_runtime.py:1605-1608` (marker = token+chunk_size+operation), `src/docxaicorrector/document/segments.py:160-163` (промпт «Языки: X -> Y»), свежие языки уходят в прогон (`src/docxaicorrector/ui/_app.py:1053-1055`).
- **Сценарий:** загрузить книгу, выбрать translate, сменить target ru→de, Start → противоречивые инструкции (метаданные/стиль/глоссарий под ru при `target_language=de`); также триггерится автоматикой рекомендаций, двигающей языковые виджеты после подготовки.
- **Вероятность:** средняя (translate). **Ущерб:** средний.
- **Исправление:** включить `source:target` в `build_preparation_request_marker` для translate/audiobook. **Стоимость:** S.
- **Проверка:** маркеры для одинакового payload с разными target_language различаются.

### [P2] F12 — Общий каталог `formatting_diagnostics/` без run-идентичности: конкурентный прогон может фатально заблокировать доставку чужого документа

- **Код:** `src/docxaicorrector/generation/formatting_diagnostics_retention.py:19-32` (фильтр только по mtime), стемы без run/source identity; потребители — `src/docxaicorrector/pipeline/late_phases.py:794-797` и фатальная агрегация `src/docxaicorrector/pipeline/quality_gate.py:1223-1227`.
- **Сценарий:** два документа обрабатываются одновременно на одной машине; caption-конфликт документа A попадает в mtime-окно документа B → B фатально отклонён (`_FATAL_DOCUMENT_GATE_REASONS`), артефакты не публикуются; review data B несёт числа A.
- **Вероятность:** низкая сегодня (single-tenant), растёт с SaaS-направлением. **Ущерб:** ложная блокировка чистого документа.
- **Исправление:** неймспейсить стем run-идентичностью и фильтровать сбор по ней; логика гейта байт-идентична. **Стоимость:** M.
- **Проверка:** два артефакта с разными run-префиксами, один с конфликтом → сбор для другого run даёт 0.

### Дополнительно подтверждённые P2 (не в топ-12)

Все верифицированы против текущего кода, большинство — S-фиксы:

- `latest_controlled_block_fallback_artifact` эмитится pipeline'ом (`block_execution.py:894`), но отсутствует в allowlist `SetStateEvent` (`processing_runtime.py:165-178`) → спурьевый WARNING + расхождение тестов и продакшена.
- Narration/TTS строится из до-cleanup чанков (`narration_postprocess.py:45`) — удалённая из DOCX «мебель» и untranslated fallback-текст остаются в аудиокниге.
- `split_block` применяется к оригинальному тексту блока (`reader_cleanup_mvp/_apply.py:386-398`), воскрешая уже удалённый noise.
- `structure_repair` мутирует TOC-роли до валидации региона (`document/structure_repair.py:218-240`).
- PDF-импортёр разжалует все bare «Chapter N» после первого «Notes»-заголовка (`pdf_import/logical_import.py:1600-1609`).
- Rewrite `[[DOCX_IMAGE_]] текст` по substring-совпадению заголовка молча удаляет caption-остаток (`pipeline/runtime_display_markdown.py:136-145`).
- Config: `reader_verifier_model` не парсится вообще (verifier молча работает на Gemini вместо сконфигурированного Sonnet); legacy env-алиасы моделей мертвы при shipped config и обещанные warnings не срабатывают (README утверждает обратное); `load_app_config()` не кеширован вне Streamlit-слоя; boundary AI review шлёт сырой `openai:model` селектор как API `model` (silent fail-open); лог `model_registry_resolved` маркирует anthropic-селекторы как `openai:anthropic:...`.

---

## 4. Межмодульные риски (только доказанные)

- **UI ↔ processing:** мёртвый канал `latest_result_notice` + outcome-слепой `has_completed_result` (F2); token/payload в разных системах координат для PDF/DOC (F3); синхронная переподготовка на render-потоке в restart-fallback (`_app.py:901-915`).
- **processing ↔ pipeline:** `SetStateEvent` allowlist пропускает один эмитируемый ключ; Stop-предикат не доходит до поздних фаз (F8).
- **extraction/import ↔ structure:** PDF→DOCX hop по дизайну схлопывает роли, а re-derivation слой содержит единственное живое VII-нарушение (F5) и premature-мутацию TOC; колоночная геометрия не доходит до quality gate (F6).
- **block execution ↔ generation:** fallback-контракт «возвращай чистый текст» нарушен в 3 из 4 веток (F1); классификация fallback опирается на точное равенство строк — хрупко к любому префиксу.
- **reader cleanup ↔ reassembly:** связка корректна (rebuild повторяет полную цепочку restore→reinsert), но failure-сигналы advisory-ветки гаснут на границе с finalize (F9), а narration-канал не синхронизирован с cleanup-результатом.
- **formatting/image restoration ↔ validation:** диагностики связываются с прогоном через mtime-окно общего каталога — единственная нерун-скоупная связь в этой границе (F12).
- **pipeline ↔ runtime state/artifacts:** доставка на диск блокируется гейтом честно, но session-state канал доставляет те же байты без пометки (F2) — две «правды» об одном результате.
- **config ↔ подсистемы:** пара `reader_cleanup_default`/`reader_cleanup_enabled` — единственный разорванный ключ из ~60 просмотренных (F4); остальная precedence env > .env > TOML выдержана.

---

## 5. Что не следует рефакторить

- **`generation/formatting_mapping.py` (2932 строки)** — осознанное решение спек 029/033/036 (F28b): каждый fuzzy-pass evidence-gated с uniqueness-маржами, закреплён golden-тестом; декомпозиция = высокий риск регрессии correctness-критичного кода при нулевой пользе.
- **`output_validation.py` / `quality_gate.py` (~2 KLOC)** — сателлиты уже извлечены (спека 036), ядро связное; дробление ради строк запрещено.
- **Двухуровневый preparation cache с tenant-identity** — свежепройденные спеки 040–042 (explicit-or-bypass) реализованы корректно; не трогать без нового tenant-сценария.
- **PDF-импортёрные typography-эвристики** (font clusters, gated promotions) — санкционированные import-side сигналы, F23-remediation на месте; «улучшение» без нового корпусного доказательства — путь к per-book тюнингу.
- **`_pipeline.py` как delegation shim** — трение минимально, поля контрактов пробрасываются полностью (вплоть до spec-043 полей).
- **Admission/worker-механика и restart_store** — спеки 041 P1-2 и 023 реализованы корректно; конфайнмент удалений на месте.
- **Anchor-лексиконы регионов** (references/содержание/глава…) — признанный конституцией language-coverage residual.

---

## 6. Рекомендуемый порядок исправлений

**Сделать сейчас** (узкие фиксы, Spec Kit не нужен — очевидное ожидаемое поведение):

1. F1 — три `return target_text_for_leakage` (S).
2. F2 — UI читает `latest_result_notice`/outcome (S).
3. F4 — маппинг `reader_cleanup_default → reader_cleanup_enabled` (S); заодно решить с владельцем дефолт включения cleanup в UI.
4. F7 — одна подстановка идентификатора на `late_phases.py:955` (S, завершение спеки 043).
5. F9 — донести advisory-ошибку cleanup до терминального состояния (S).

**Требуют Spec Kit** (P1 с архитектурным/поведенческим решением):

- F3 — контракт identity persisted source (несколько модулей, выбор между «доверять сохранённому токену» и «хранить исходные байты»).
- F5 — изменение structure-эвристики (Constitution III + закрепляющие тесты; спека фиксирует VII-совместимое правило).
- F6 — колоночный сигнал в PDF quality gate (выбор refusal vs column-aware сортировка).

**Сделать при следующем изменении соответствующего модуля:** F8 (stop-предикаты в хвосте), F10 (underline + краевые пробелы), F11 (языки в маркере подготовки), F12 (run-неймспейс диагностик — вместе с любой следующей SaaS-волной), allowlist-ключ, narration-из-cleanup, конфиг-пачка (reader_verifier_model, legacy-алиасы+README, кеш load_app_config, селектор boundary review).

**Не делать без нового доказательства:** полную колонко-aware пересортировку PDF (сначала refusal-гейт), переработку `positional_toc_fallback` в mapper'е (триггер не продемонстрирован), `split_block`-фикс (нужен реальный дубль-пропозал от LLM), заголовок `X-OpenRouter-Title` vs `X-Title` (внешний контракт не проверен), атомарную запись restart-source (отклонено в раунде 7), выравнивание narration с диагностиками в quality report сверх спеки 043 (осознанный non-goal владельца).

---

## Осознанно не рекомендовано (проверено, дефектом не является)

- Reader cleanup удаляет/портит image-placeholder'ы — отклонено: `delete_block` с placeholder запрещён (`reader_cleanup_mvp/_validate.py:369-370`), rebuild восстанавливает пропавшие placeholder'ы.
- `image_placeholder_integrity_failed` только логируется — отклонено: это hard delivery gate (`late_phases.py:331-387`, wired at `_pipeline.py:481`).
- Post-Pandoc проходы перезаписывают друг друга / устаревают после cleanup — отклонено: cleanup-путь пересобирает с нуля полную цепочку.
- Формат применяется к неверному абзацу mapper'ом — в основном отклонено: fuzzy-проходы evidence-gated с uniqueness-маржами.
- Empty/garbage-ответ модели доставляется как edited — отклонено (кроме marker-residue = F1): пустой/collapsed/incomplete поднимают исключение, fallback scoped per-block.
- Hyperlink relationship IDs ломаются rebuild'ами — отклонено: pPr-замена не трогает runs, reinsertion консервативно отказывается от пересечения placeholder с hyperlink.
- compare_all / keep_all_image_variants metadata печатается как текст — отклонено: метки только в `docPr/@descr`.
- Effective image mode тихо отличается от выбора пользователя — отклонено: все downgrade проходят документированный analysis/policy route.
- Env > .env > defaults precedence — держится (единственная инверсия — мёртвые legacy-алиасы, отдельный P2).
- Секреты в логах/артефактах — путей утечки не найдено (только sha256-фингерпринты, имена env-переменных).
- Client singleton / rotation — держится (спека 041, TOCTOU-safe rekey).
- Cross-tenant shared preparation cache — KNOWN-OPEN в спеке 039, не пересообщается; bypass спеки 042 разведён корректно.
- Детерминизм подготовки — чистый (font-mode tie-break, deterministic k-means init, order-independent demote set, total sort keys).

---

_Файл сгенерирован как исторический снапшот раунда 10. Для последующих раундов сверять живость каждого claim'а с текущим кодом (Constitution VIII): сохранённый отчёт доказывает только то, что было верно на `23020a9`._
