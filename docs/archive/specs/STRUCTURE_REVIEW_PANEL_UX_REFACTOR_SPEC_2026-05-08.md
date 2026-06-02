# Спецификация: упрощение страницы выбора глав для перевода

Дата: 2026-05-08
Статус: **Решения зафиксированы — реализация ожидает явного "go" от пользователя**
Затронутый модуль: [src/docxaicorrector/ui/structure_review_panel.py](../../src/docxaicorrector/ui/structure_review_panel.py)
Затронутые тесты: [tests/test_app_preparation.py](../../tests/test_app_preparation.py)
Статический мок: [docs/specs/static_mocks/structure_review_panel_2026-05-08.html](static_mocks/structure_review_panel_2026-05-08.html)

---

## 1. Контекст и цель страницы

DocxAICorrector — Streamlit-приложение для литературного редактирования / перевода / подготовки аудиокниги длинных документов (`.docx` / `.doc` / `.pdf`). Главный сценарий пользователя на этой странице после загрузки и подготовки документа: **выбрать главы и запустить перевод**. Всё остальное на текущей странице — диагностический шум, который перегружает интерфейс и отвлекает.

Текущая страница ([_render_analysis_review_panel](../../src/docxaicorrector/ui/structure_review_panel.py#L925)) рендерит около 27 разнородных элементов на одном уровне и на реальной книге (223 секции в последнем запуске) превращается в стену из чекбоксов, инлайн-превью, captions, фильтров и кнопок. Bulk-кнопки `Select Visible / Clear Visible / Select Entire Book` не работают из-за state-isolation бага `st.checkbox`.

## 2. Что пользователь увидит и как будет управлять

Страница вписывается в **существующую сетку проекта**: тёмная тема (`#0e1117` / `#1a2332` / `#19c6b7` accent), русскоязычный UI, левый sidebar с настройками, основная колонка с заголовком "AI-редактор DOCX/DOC/PDF через Markdown" и `render_intro_layout_styles` ограничением ширины. Никаких новых цветов, шрифтов, иконок и custom-CSS не вводим.

В основной колонке после подготовки документа отображается **ровно три блока** в этом порядке:

1. **Заголовок и сводка** — одна строка `st.subheader` плюс одна строка `st.caption` со счётчиками.
2. **Список глав** — поиск по названию, затем компактный список чекбоксов глав (только chapter-level).
3. **Запуск перевода** — две кнопки в `st.columns(2)` плюс одна строка-сводка.

Всё остальное (терминология, fingerprint, manifest, диагностика, контекст front matter / TOC, retry упавших) либо удаляется совсем, либо перемещается в один свёрнутый `st.expander("Дополнительно", expanded=False)` под кнопками. Retry упавших показывается как небольшое уведомление **только** когда такие главы реально есть.

### 2.1 Блок 1 — Заголовок и сводка

```
Главы для перевода
12 глав · 92 400 слов
```

- `st.subheader("Главы для перевода")`
- `st.caption("12 глав · 92 400 слов")` — одна строка вместо текущих четырёх (`Detected N reviewable sections…`, `Confidence overview…`, `Section status: pending …`, `Visible sections: X/Y`).

Cтрока confidence breakdown (`0 clear / 203 review / 20 uncertain`) уходит в `Дополнительно`. На реальном документе эти цифры всё равно артефакт сломанного детектора (см. §6).

### 2.2 Блок 2 — Список глав

- `st.text_input("Поиск по названию", key="chapter_selector_search_input", placeholder="Например: Введение")` — единственный фильтр. Без 8-state status filter.
- Под ним — список чекбоксов **только chapter-level**. Подглавы не рендерятся вообще. Каждая строка:

  ```
  ☐  Введение: Making versus Taking          136 слов
  ```

  Реализация: один `st.checkbox` на главу с компактным label `"{title}  ·  {words} слов"`. Никаких `| section | under Front Matter | review suggested | pending`. Никаких per-row warnings и инлайн-превью-экспандеров.

  Если глав больше ~50, список оборачивается в `st.container(height=420)` для нативного скролла без потери остальной страницы.

- Над списком, в одной строке `st.columns([1, 1, 4])`:
  - кнопка `Выбрать всё` (вторичная, `use_container_width=True`)
  - кнопка `Снять всё` (вторичная, `use_container_width=True`)
  - пусто (для выравнивания)

  Эти две кнопки заменяют сломанный набор `Select Visible / Clear Visible / Select Entire Book`. Семантика — простая и предсказуемая: оперируют над всем chapter-level списком, без зависимости от фильтра. Если глав 5, пользователь не нуждается в bulk; если глав 200 — две кнопки достаточно.

  Баг `st.checkbox` обходится **записью в `st.session_state` ключей чекбоксов перед вызовом `st.rerun()`**, как описано в §5.

### 2.3 Блок 3 — Запуск перевода

Одна строка `st.caption` со сводкой и одна строка `st.columns(2)` с двумя кнопками:

```
Выбрано: 3 главы · 4 205 слов

[ Перевести выбранное (3) ]   [ Перевести всю книгу ]
```

- `Перевести выбранное (N)` — primary button, `type="primary"`. Disabled когда `N == 0`. Возвращает action `"start_selected"`.
- `Перевести всю книгу` — secondary. Возвращает action `"start_full_book"`.

Подтверждение структуры (`Confirm structure`) делается **неявно** при первом нажатии любой из этих кнопок: код вызывает `set_structure_confirmation_state(...)` ровно так, как это делает текущая кнопка `Confirm Structure`. Если структура была инвалидирована (повторная подготовка с другими настройками), показывается одна строка `st.warning("Структура изменилась, проверьте список глав перед запуском.")` над списком. Никакой отдельной кнопки `Подтвердить структуру` не требуется.

### 2.4 Условный блок — Уведомление об упавших главах

Когда `failed_segment_count > 0` в текущей сессии, **над** кнопками запуска появляется одна строка:

```
⚠ В прошлом запуске не удалось перевести 3 главы.   [ Повторить упавшие ]
```

Реализация: `st.warning(...)` с inline-кнопкой `Повторить упавшие` через `st.columns([5, 1])`. Возвращает action `"start_retry_failed"`. Если упавших нет — блок не рендерится совсем (никаких disabled-кнопок).

### 2.5 Блок 4 — Дополнительно (свёрнутый)

`st.expander("Дополнительно", expanded=False)` под кнопками. Содержит **только то, что реально может пригодиться продвинутому пользователю**:

- Терминология / глоссарий (если детектор её собрал) — текущий `_render_terminology_review`.
- Технические детали структуры: `Structure fingerprint`, `Detector version`, `Manifest path`. Без uploader'а manifest сравнения.
- Confidence breakdown одной строкой.

Manifest JSON uploader, кнопка сравнения, и любые другие диагностические инструменты **удаляются из UI** (код manifest export/compare остаётся для тестов и логов, но не выводится на страницу). Если они потребуются — отдельной спекой будет добавлен developer-режим.

Front Matter / TOC контекст (`Include Front Matter` / `Include TOC`) удаляются. На странице "выбрать главы и запустить перевод" пользователь не должен думать про контекст для модели; включение front matter в перевод покрывается тем, что front matter — это просто ещё одна глава в списке, которую можно отметить чекбоксом.

## 3. Что удаляется из текущей реализации

Удаляются совсем (с UI и из контракта виджетов; runtime-функции остаются нетронутыми):

| Элемент | Причина |
|---|---|
| `Status Filter` selectbox | Один фильтр (поиск) достаточно. Статусы пользователю не нужны на этой странице. |
| `Confirm Structure` кнопка | Подтверждение делается неявно при запуске перевода. |
| `Select Visible` / `Clear Visible` / `Select Entire Book` (3 кнопки) | Заменены на две: `Выбрать всё` / `Снять всё`. |
| `Selected + Context` кнопка и оба чекбокса (`Include Front Matter`, `Include TOC`) | Контекст не выбирается на этой странице. |
| Per-row `Included text preview` экспандер для каждой главы | Загромождает экран. Если потребуется — добавим как hover-tooltip или попап позже. |
| Per-row `st.warning` про low-confidence | Сводится к §2.5 confidence breakdown. |
| `Hierarchy in current view` caption | Не нужен после удаления подглав. |
| `Selection hierarchy / descendant coverage / excluded locked / Ready: confirmed structure` (4 caption) | Сводятся в одну строку §2.3. |
| `Visible sections: X/Y` caption | После удаления фильтра нерелевантно. |
| `Section status: pending …` caption | Не нужен на этой странице. |
| Manifest JSON uploader и кнопка сравнения | Никогда не используется обычным пользователем. |
| `Advanced structure tools` outer expander | Сливается с `Дополнительно`. |
| `Terminology Review (N)` outer expander | Сливается с `Дополнительно`. |
| Подглавы (subsections) | Переводим только chapter-level. Подглавы автоматически включаются вместе с родителем через существующий `_expand_segment_ids_for_selection`. |

## 4. Контракты, которые сохраняются

Слой данных и runtime-контракты не меняются:

- `set_selected_segment_ids` / `selected_segment_ids` — без изменений. Запись чекбокса главы автоматически расширяется на её подглавы через `_expand_segment_ids_for_selection`.
- Возвращаемые action strings: `"start_selected"`, `"start_full_book"`, `"start_retry_failed"`, `None`. Удаляются: `"start_selected_with_context"` (front matter / TOC удалены), `"start_final_book"` (если он используется только из удаляемого UI — проверить и либо сохранить, либо удалить с тестами).
- `chapter_workflow.service` API — без изменений.
- Структурный fingerprint, manifest export, retry-failed eligibility — без изменений (только не выводятся в UI).
- Сессионные ключи `chapter_selector_search` остаётся, `chapter_selector_filter` остаётся валидным значением `"all"` по умолчанию (внешний код не сломается, виджет просто не рендерится).
- Сессионные ключи `selected_context_include_front_matter_checkbox`, `selected_context_include_toc_checkbox` остаются с дефолтом `False`. Виджеты не рендерятся.

## 5. Исправление бага bulk-кнопок (попутно)

Текущий `st.checkbox(value=…, key=f"segment_checkbox_{id}")` после первого рендера игнорирует `value=` и читает state из `st.session_state[key]`. Bulk-обновление переменной `bulk_updated_selection` не доходит до чекбоксов.

Исправление в новой реализации: при клике `Выбрать всё` / `Снять всё` код **сначала пишет в `st.session_state[checkbox_key]` для всех глав**, затем вызывает `set_selected_segment_ids(...)` и `st.rerun()`. На следующем проходе чекбоксы рендерятся с правильным state, потому что Streamlit читает из session_state, который уже обновлён.

```python
def _apply_bulk_chapter_selection(*, chapter_ids: Sequence[str], select: bool) -> None:
    new_set = set(chapter_ids) if select else set()
    for chapter_id in chapter_ids:
        st.session_state[f"chapter_checkbox_{chapter_id}"] = chapter_id in new_set
    expanded = _expand_segment_ids_for_selection(
        segment_ids=list(new_set),
        parent_to_children_map=parent_to_children_map,
        segment_status_by_id=segment_status_by_id,
        include_locked=False,
    )
    set_selected_segment_ids(expanded)
    st.rerun()
```

Ключи чекбоксов меняются с `segment_checkbox_<id>` на `chapter_checkbox_<id>`, чтобы старые "залипшие" значения из предыдущих сессий не конфликтовали с новой семантикой (chapter-level вместо per-segment).

## 6. Pre-existing баг детектора (вне scope)

Snapshot последнего запуска ([.run/ui_snapshots/preparation_page_2026-05-08.html](../../.run/ui_snapshots/preparation_page_2026-05-08.html), 223 секции) показывает, что структурный детектор кладёт **222 настоящие главы под синтетический Front Matter**. Пример из snapshot:

```
Front Matter | 28 words | front matter | includes 222 nested sections
Preface: Stories About Wealth Creation | 5 words | section | under Front Matter
Introduction: Making versus Taking | 136 words | section | under Front Matter
Follow Penguin | 2 words | section | under Front Matter
…
```

Это дефект `chapter-detector`, не задача этой спецификации. Отдельный issue/spec для детектора будет создан позже.

Чтобы новый UI оставался полезным **сегодня**, "глава" определяется по правилу:

> Список глав = `_select_chapter_level_segments(segments)` — наибольший уровень в дереве, на котором ≥2 сегмента. Если на уровне 0 один сегмент (как Front Matter в snapshot), берём его прямых детей. Рекурсивно.

На правильно детектированном документе (Lietaer-core, одна глава) это даст одну строку. На snapshot-документе — 222 строки. Когда детектор починят, поведение UI не изменится. Реализация — чистый builder, отдельно тестируемый.

## 7. Соответствие визуальной сетке проекта

Подтверждённые конвенции, которым следует новый UI:

- Все тексты **на русском** (sidebar, заголовки, кнопки, captions). Английские строки в `_build_*` helper'ах заменяются.
- Тёмная тема (`#0e1117` / `#1a2332` / `#19c6b7`) подхватывается автоматически через Streamlit `[theme]` в [config.toml](../../.streamlit/config.toml).
- Используются только нативные виджеты Streamlit: `st.subheader`, `st.caption`, `st.text_input`, `st.checkbox`, `st.button`, `st.columns`, `st.container`, `st.expander`, `st.warning`. Никакого `unsafe_allow_html`, никакого нового CSS. Существующий `render_intro_layout_styles` (cap ширины основной колонки) уже применён в `_app.py` и продолжает действовать.
- Иконки — только дефолтные Streamlit material icons (для `st.warning` и т.п.). Никаких emoji в captions.
- Терминология русская и согласованная с sidebar: `Перевести` / `Главы` / `Слов`. Не `Sections`, не `Translate`.

## 8. План модулей

Один публичный entry point остаётся: `_render_analysis_review_panel(...)`. Внутри разбивается на чистые блоки:

```
_render_analysis_review_panel
├── _select_chapter_level_segments(segments) -> list[SegmentLike]   # pure
├── _render_summary_header(chapters, total_words)                   # block 1
├── _render_chapter_list(chapters, ...)                             # block 2 (search + bulk + checkboxes)
├── _render_retry_failed_notice(failed_count) -> action | None      # conditional
├── _render_action_bar(selected_count, selected_words) -> action    # block 3
└── _render_advanced_expander(prepared_run_context, review_state)   # block 4
```

Существующие чистые helper'ы (`_expand_segment_ids_for_selection`, `_build_effective_selected_processing_state`, `_build_retry_failed_processing_state`, `_resolve_segment_display_title`, `humanize_segment_warnings`, `_render_terminology_review`) переиспользуются без изменений.

Оценка размера: с 1253 строк до ~500–600.

## 9. Тесты

Удаляются:
- `test_render_analysis_review_panel_renders_bulk_selection_buttons` (старые лейблы кнопок).
- `test_render_analysis_review_panel_filters_segments_by_status_and_search` (фильтр статуса удалён).

Добавляются:
- `test_select_chapter_level_segments_picks_largest_level_with_two_or_more_rows`: pure builder против трёх фикстур.
- `test_chapter_checkbox_toggle_updates_selected_segment_ids_with_descendants`.
- `test_bulk_select_all_writes_session_state_and_persists_selection`: проверяет фикс §5.
- `test_bulk_clear_all_writes_session_state_and_clears_selection`.
- `test_translate_selected_button_returns_start_selected`.
- `test_translate_whole_book_button_returns_start_full_book`.
- `test_retry_failed_notice_only_renders_when_failures_exist`.
- `test_advanced_expander_contains_terminology_and_fingerprint`.
- `test_search_input_filters_chapter_list_by_title`.

Канонические команды верификации:

```bash
bash scripts/test.sh tests/test_app_preparation.py -q
bash scripts/test.sh tests/ -q
```

VS Code task: `Run Current Test File` → `tests/test_app_preparation.py`, затем `Run Full Pytest`.

## 10. Зафиксированные решения (подтверждены 2026-05-08)

1. **Неявное подтверждение структуры** при первом нажатии `Перевести выбранное` / `Перевести всю книгу` — **принято**. Кнопка `Confirm Structure` удаляется. Внутри обработчика action'а вызывается `set_structure_confirmation_state(...)` перед делегацией в `chapter_workflow.service`.
2. **Подглавы не рендерятся совсем** — **принято**. Выбор главы автоматически расширяется на её подглавы через существующий `_expand_segment_ids_for_selection`. Точечное исключение подглавы — out of scope; будет отдельной advanced-фичей при необходимости.
3. **Manifest export / fingerprint / detector version / terminology** прячутся в один свёрнутый `Дополнительно`-expander — **принято**. Manifest comparison **uploader удаляется из UI полностью** (нишевая dev-фича). Manifest **export** (скачать текущий) остаётся в `Дополнительно`.
4. **Action `"start_final_book"`** — **проверить use-sites перед удалением** на этапе реализации. Если упоминается только в удаляемом коде UI и его тестах — удаляется вместе с тестами. Иначе — оставить нетронутым в `chapter_workflow.service`, но из UI всё равно убрать.
5. **Action `"start_selected_with_context"`** — **удаляется** вместе с Front Matter / TOC чекбоксами. Контекст в перевод включается естественным путём: пользователь отмечает соответствующую главу (Front Matter присутствует в списке как обычная chapter-level строка).

## 11. Порядок реализации

1. Чистый builder `_select_chapter_level_segments` + unit-тест.
2. Новые `_render_summary_header`, `_render_chapter_list`, `_render_action_bar`, `_render_retry_failed_notice`, `_render_advanced_expander`.
3. Замена тела `_render_analysis_review_panel` на цепочку этих блоков.
4. Удаление неиспользуемого кода (manifest uploader, status filter, per-segment preview, context checkboxes).
5. Обновление / удаление / добавление тестов.
6. `bash scripts/test.sh tests/ -q` зелёный + визуальная проверка во встроенном браузере на snapshot-документе и на Lietaer-core.
