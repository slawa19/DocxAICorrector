# Контракт: ключ состояния, bundle результата, экран аудиокниги (спека 072, FR-008, FR-009)

## 1. Ключ состояния

| Ключ | Где разрешён | Значение | Очищается |
|---|---|---|---|
| `latest_narration_exports` | `_ALLOWED_SET_STATE_EVENT_KEYS` (`processing/processing_runtime.py:164-180`) | словарь `data-model.md` §5 или `None` | `init_session_state` (`runtime/state.py:602-615`, `setdefault(None)`), `reset_run_state` (`:658`, рядом с `:737`) — в начале каждого запуска; аварийный обработчик рабочего потока до доставки (`processing/processing_service.py:375-381`) |

- Пишется ОДИН раз за прогон: в том же `emit_state`, что и `latest_narration_text` (`pipeline/late_phases.py:1372-1391`),
  только у операции `audiobook` и только при `narration_text is not None`. Перевод и редактура ключ не пишут.
- Stop до публикации — ключ не появляется (граница R9); Stop после публикации — результат остаётся, как сейчас.

## 2. Bundle результата

`build_result_bundle(..., narration_exports: Mapping[str, object] | None = None)` (`processing/processing_runtime.py:1689`):

| Ключ bundle | Значение |
|---|---|
| `narration_exports` | `None` или `{docx_bytes, pdf_bytes, docx_unavailable_reason, pdf_unavailable_reason}` — нормализовано: только эти четыре ключа; не-`bytes`/пустые байты → `None`; причины — `str` или `None` |

`get_current_result_bundle` (`:1778-1842`) передаёт `st.session_state.get("latest_narration_exports")` ТОЛЬКО если
`latest_narration_text is not None` (правило пары — research R10); иначе `None`.

## 3. Экран результата аудиокниги (`ui/_ui.py:render_result_bundle`, `:1078`; вызов — `ui/_app.py:895-920`)

`render_result_bundle(..., narration_exports: Mapping[str, object] | None = None)`; `_render_completed_result_view`
передаёт `result.get("narration_exports")`.

При `operation == "audiobook"` и `narration_text is not None`:

1. Подпись `result.narration_section_title` («Текст для озвучки»).
2. `st.columns(n)`, `n` = число собранных форматов из (DOCX, PDF, TXT) в этом порядке; DOCX — `type="primary"`
   (при `blocked` — все `secondary`, как сейчас, `:1186-1194`), PDF и TXT — `secondary`; все `width="stretch"`,
   `on_click="ignore"`.
3. Если `pdf_unavailable_reason` или `docx_unavailable_reason` не `None` — `st.caption` с
   `result.narration_pdf_unavailable.<reason>` / `result.narration_docx_unavailable` сразу под строкой.
4. Подпись `result.review_section_title` («Для проверки»); `st.columns(2)`: DOCX для проверки, Markdown —
   `secondary`, `width="stretch"`.
5. Блок проверки оформления — как сейчас (`_render_formatting_review_block`).

`narration_exports is None` (старый bundle, SC-007): строка «Текст для озвучки» — одна кнопка TXT; строка «Для
проверки» — как в п. 4. Ошибок нет.

Перевод и редактура (`narration_text is None`): ветвь `ui/_ui.py:1239-1264` не меняется — ни новых кнопок, ни подписей.

Только штатные примитивы Streamlit (`st.columns`, `st.caption`, `width="stretch"`); `use_container_width` и CSS не
используются (AGENTS.md, Streamlit Layout Contract).

## 4. Новые ключи локалей (`ui/locales/ru.json`, `en.json`, одинаковые наборы)

`result.narration_section_title`, `result.review_section_title`, `result.narration_docx`, `result.narration_pdf`,
`result.narration_docx_unavailable`, `result.narration_pdf_unavailable.docx_not_built`,
`…soffice_not_found`, `…timeout`, `…failed`, `…missing_output`, `…empty_output`, `…not_pdf`,
`result.audiobook_studio_limits_exceeded`. Существующие гарды: `tests/test_ui_i18n.py:101` (JSON валиден), `:108`
(ru — надмножество ключей, на которые ссылается код, и ключей en); новый тест пакета проверяет, что каждый новый ключ
есть в ОБОИХ каталогах.
