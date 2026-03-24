# Спецификация: state-machine и кеш подготовки документа

> Статус: archived implementation spec. Базовая идея этой спецификации реализована. Ниже местами сохранён исторический design context первой refactor-wave; для актуального пользовательского workflow и WSL-first запуска ориентиром служат `README.md`, `docs/WORKFLOW_AND_IMAGE_MODES.md` и `CONTRIBUTING.md`.

## Цели

Этот пакет доработок фиксирует две системные проблемы:

1. UI-состояния в `app.py` были выражены через набор слабо связанных флагов `session_state`.
2. Streamlit rerun повторно парсил DOCX и заново собирал `jobs` даже при изменении только UI-настроек.

Решение должно:

- формализовать состояния idle-экрана;
- сохранить сценарий restart после `Stop` без повторной загрузки файла;
- сократить повторную подготовку документа;
- не менять контракт обычной обработки и stop/restart UX;
- зафиксировать compare-all как режим, где все варианты уже вставляются в итоговый DOCX.

## Новые модули

### `workflow_state.py`

Содержит:

- `ProcessingOutcome`
- `IdleViewState`
- `has_restartable_outcome(outcome)`
- `derive_idle_view_state(...)`

Назначение:

- убрать строковые литералы состояний из `app.py`;
- сделать переходы `empty / file_selected / restartable / completed` явными и тестируемыми.

### `preparation.py`

Содержит:

- `PreparedDocumentData`
- `build_prepared_source_key(uploaded_file_token, chunk_size)`
- `prepare_document_for_processing(...)`
- `clear_preparation_cache()`

В актуальной реализации подготовка документа использует небольшой session-scoped cache по lightweight key, а не process-wide `lru_cache`.

Ключ кеша:

- `uploaded_filename`
- `source_bytes`
- `chunk_size`

`source_bytes` уже участвуют в file token через content hash, поэтому кеш безопасно разделяет файлы даже при одинаковом имени и размере.

### `runtime_events.py`

Содержит dataclass-события для фонового worker/runtime обмена:

- `SetStateEvent`
- `ResetImageStateEvent`
- `SetProcessingStatusEvent`
- `FinalizeProcessingStatusEvent`
- `PushActivityEvent`
- `AppendLogEvent`
- `AppendImageLogEvent`
- `WorkerCompleteEvent`

Назначение:

- убрать строковые event type и неструктурированные dict payload из очереди фоновой обработки;
- сделать dispatch в `processing_runtime.py` явным и тестируемым;
- упростить дальнейшее расширение runtime-событий без поиска строковых литералов по проекту.

### `application_flow.py`

Содержит orchestration-слой между Streamlit UI и runtime/pipeline:

- idle/restart helper-функции
- восстановление restart file из `.run/`
- подготовку `PreparedRunContext` для запуска обработки

Назначение:

- убрать из `app.py` логику выбора restart-source, resettable-state и подготовки документа;
- сохранить `app.py` как UI-entrypoint и thin composition layer;
- упростить unit-тесты на flow-логику без моков Streamlit-рендеринга.

### `processing_service.py`

Содержит facade над обработкой документа и worker-исполнением:

- `process_document_images(...)`
- `run_document_processing(...)`
- `run_processing_worker(...)`
- `build_processing_service()`
- `get_processing_service()`

Назначение:

- убрать из `app.py` knowledge о pipeline dependencies, image pipeline callbacks и runtime event emission;
- держать worker crash-handling рядом с processing contract, а не рядом с UI;
- сделать отдельные service-level тесты без привязки к Streamlit entrypoint.
- держать один production singleton service для UI-композиции и не дублировать wiring по модулям.

## Контракт состояния

### Processing outcome

- `idle` — нет активной обработки;
- `running` — воркер запущен;
- `stopped` — пользователь остановил обработку;
- `failed` — обработка завершилась с ошибкой;
- `succeeded` — документ успешно обработан.

### Idle view state

- `empty` — нет файла, нет результата, нет restartable-сессии;
- `file_selected` — есть активный выбранный файл для старта;
- `restartable` — есть сохранённый source для restart после `stop/failed`;
- `completed` — есть готовый текущий результат.

`app.py` не должен вычислять эти состояния вручную через разрозненные if-условия.

## Контракт restart source

`restart_source` хранится в `session_state` только после фактического старта обработки.

Не допускается создавать `restart_source` просто при выборе файла в uploader.

Поля:

- `session_id`
- `filename`
- `token`
- `storage_path`
- `size`

Очищается:

- при `reset_run_state(keep_restart_source=False)`;
- при смене файла;
- при явном сбросе результатов.

Если запись restart source во временный файл не удалась, запуск обработки не должен падать: обработка продолжается, но restart без повторной загрузки файла отключается для этого запуска.

После `succeeded` временный restart source должен удаляться. Для повторного запуска с новыми настройками в пределах той же UI-сессии разрешён краткоживущий in-memory cache исходного файла.

Проверки restartability должны оставаться cheap: `has_restartable_source()` не читает временный DOCX и не создаёт `BytesIO`, а использует только outcome + наличие restart metadata. Материализация файла разрешена только в пути фактического восстановления источника.

Кеш подготовки документа не должен быть process-wide и не должен использовать `source_bytes` как глобальный cache-key. Допустимый вариант: небольшой session-scoped cache по lightweight key `uploaded_file_token:chunk_size` с жёстко ограниченным размером.

## Контракт compare-all

В режиме `compare_all` итоговый DOCX собирается сразу со всеми доступными вариантами изображения:

- safe
- semantic_redraw_direct
- semantic_redraw_structured

UI не делает дополнительную пересборку финального DOCX. Панель compare-all носит информационный характер и объясняет, что лишние варианты удаляются уже в Word.

## Почему нужен deepcopy поверх кеша

`image_assets` и `jobs` мутируются в ходе пайплайна и UI-работы.
Поэтому cached-результат нельзя отдавать напрямую: каждый вызов `prepare_document_for_processing(...)` обязан возвращать независимые копии данных.

## Тестовое покрытие

Нужны тесты на:

- derive idle view state;
- restartable state detection;
- кеш подготовки документа для одинакового файла;
- независимость объектов, возвращаемых из preparation cache;
- compare-all вставку всех вариантов в итоговый DOCX.

## Ограничения

- Кеш подготовки in-process. После перезапуска Streamlit-процесса он очищается.
- Restart source теперь хранится во временном файле внутри `.run/` и изолируется по session-id; если эта директория очищена внешним процессом, restart для текущей UI-сессии пропадает.
