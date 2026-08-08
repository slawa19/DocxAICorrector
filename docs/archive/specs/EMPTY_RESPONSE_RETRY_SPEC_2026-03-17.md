# Спецификация: retry для пустых ответов модели (`empty_response`)

**Дата:** 2026-03-17  
**Статус:** Реализовано в коде, UI-подтверждение pending  
**Триггер:** два UI-прогона с ошибками `empty_response` на разных блоках одного документа

## Статус выполнения

- [x] В `generation.py` добавлен адресный retry для `empty_response` и `collapsed_output`.
- [x] В `generation.py` добавлено диагностическое логирование response shape через `logger.log_event()`.
- [x] В [tests/test_generation.py](tests/test_generation.py) добавлены тесты на retry-path, exhaustion-path и logging-path.
- [x] Выполнен пользовательски видимый регрессионный прогон через VS Code task `Run Full Pytest`: `371 passed, 4 skipped`.
- [ ] UI-прогон на проблемном документе пока не выполнен.

---

## 1. Вывод по актуальности

Спецификация в целом **актуальна по сути проблемы**: текущий код действительно не ретраит `empty_response` и `collapsed_output`, а значит transient-пустой ответ модели немедленно валит обработку блока и всего документа.

При этом исходная версия плана требовала уточнений, чтобы не расходиться с реальным кодом:

- `max_retries` в проекте означает **общее число попыток**, а не число дополнительных retry.
- Значение `max_retries` **конфигурируется** и затем clamp-ится в диапазон `1..5`; дефолт остаётся `3`, но это не жёстко прошитый контракт.
- Диагностическое логирование через `logging.getLogger(__name__)` в этом репозитории не является лучшим вариантом: проект уже использует централизованный логгер через `logger.log_event()` и файл `.run/app.log`.
- Риск с `len(list(output_items))` в логировании лишний: так можно случайно потребить одноразовый iterable. Для диагностики лучше логировать длину только если объект реализует `Sized`.
- В `tests/test_generation.py` уже есть базовые негативные тесты на `empty_response`, `collapsed_output` и `unsupported_response_shape`; спецификации не хватало явного разделения между уже существующим покрытием и новым покрытием для retry/logging.

---

## 2. Подтверждённое текущее состояние кода

### 2.1. Где находится дефект

В [generation.py](generation.py#L155) retry-цикл внутри `generate_markdown_block()` опирается только на [image_shared.py](image_shared.py#L45) `is_retryable_error()`.

Сейчас retryable считаются только:

- HTTP-коды `408`, `409`, `429`, `>=500`
- SDK-классы `APIConnectionError`, `APITimeoutError`, `RateLimitError`, `InternalServerError`

Если `_extract_normalized_markdown()` в [generation.py](generation.py#L137) выбрасывает:

- `RuntimeError("...empty_response...")`
- `RuntimeError("...collapsed_output...")`

то такой `RuntimeError` не проходит через `is_retryable_error()` и сразу поднимается наверх.

### 2.2. Что уже покрыто тестами

В [tests/test_generation.py](tests/test_generation.py) уже есть подтверждённое покрытие текущего поведения:

- блок падает на `collapsed_output`
- блок падает на `empty_response`
- `unsupported_response_shape` не маскируется
- retry работает для обычной retryable-ошибки (`429`-подобный сценарий)

Что было добавлено в рамках реализации:

- retry для `empty_response`
- retry для `collapsed_output`
- проверка исчерпания retry-бюджета на persistent `empty_response`
- проверка диагностического логирования

### 2.3. Что важно для реализации

- `DEFAULT_MAX_RETRIES = 3` задан в [constants.py](constants.py#L13).
- Реальное значение поступает из конфигурации и clamp-ится до диапазона `1..5` в [config.py](config.py#L363).
- Ошибка блока поднимается в pipeline без дополнительного block-level fallback в [document_pipeline.py](document_pipeline.py#L413).

---

## 3. Проблема

При обработке документа модель иногда возвращает пустой ответ без текстового содержимого. Из-за отсутствия адресного retry это считается фатальной ошибкой блока, после чего pipeline завершает обработку документа с ошибкой.

### Наблюдаемое поведение

- Прогон 1: блоки 1–3 OK, блок 4/11 — `empty_response`, обработка остановлена.
- Прогон 2: блоки 1–6 OK, включая проблемный ранее блок 4; блок 7/11 — `empty_response`, обработка остановлена.
- Один и тот же документ, одна и та же модель (`gpt-5-mini`), тот же prompt.
- Сбой мигрирует между блоками, значит проблема выглядит как transient provider/model behavior, а не как детерминированный дефект конкретного входного блока.

### Что было до hardening-коммита

Исходная уязвимость существовала и раньше: пустой ответ модели уже тогда не считался retryable. Hardening-коммит не создал дефект, но и не устранил его.

---

## 4. Область изменений

### Входит в спецификацию

1. Ограниченный retry для `empty_response` в `generate_markdown_block()`.
2. Ограниченный retry для `collapsed_output` в `generate_markdown_block()`.
3. Диагностическое логирование response shape для пустого или схлопнувшегося ответа.
4. Новые unit-тесты на retry-path и logging-path.

### Не входит в спецификацию

- Изменения prompt-а или системного prompt-а.
- Pipeline-level fallback с пропуском неудачного блока и продолжением обработки.
- Изменение контракта `is_retryable_error()` для HTTP/SDK-ошибок.
- Изменения в `document_pipeline.py` и пользовательском UX ошибки.

---

## 5. Целевое решение

### Этап 1: адресный retry для `empty_response` и `collapsed_output`

**Файл:** `generation.py`  
**Функция:** `generate_markdown_block()`

Текущий участок:

```python
except Exception as exc:
    should_retry = attempt < max_retries and is_retryable_error(exc)
    if not should_retry:
        raise
    time.sleep(min(2 ** (attempt - 1), 8))
```

Целевое поведение:

```python
except Exception as exc:
    is_empty_or_collapsed = isinstance(exc, RuntimeError) and (
        "empty_response" in str(exc) or "collapsed_output" in str(exc)
    )
    should_retry = attempt < max_retries and (
        is_retryable_error(exc) or is_empty_or_collapsed
    )
    if not should_retry:
        raise
    time.sleep(min(2 ** (attempt - 1), 8))
```

### Уточнение по реализации

Рекомендуется не оставлять эту проверку inline, а вынести в маленький helper рядом с retry-циклом, например:

```python
def _is_retryable_empty_generation_error(exc: Exception) -> bool:
    return isinstance(exc, RuntimeError) and (
        "empty_response" in str(exc) or "collapsed_output" in str(exc)
    )
```

Это даст три преимущества:

- retry-условие останется читаемым
- тесты можно будет привязывать к стабильной внутренней семантике
- если позже появится отдельный error code, место замены будет одно

### Обоснование

- Изменение локальное и не затрагивает общий HTTP/SDK retry-контракт.
- `unsupported_response_shape`, `TypeError`, `ValueError` и прочие нерелевантные ошибки по-прежнему не будут ретраиться.
- Используется уже существующий retry-бюджет, без добавления новых настроек.
- `collapsed_output` должен считаться той же transient-категорией, что и `empty_response`: модель формально ответила, но полезного результата не вернула.

---

## 6. Диагностическое логирование

### Почему исходная версия плана требует уточнения

В проекте для рабочих логов уже используется централизованный логгер через [logger.py](logger.py). Поэтому `logging.getLogger(__name__)` нежелателен как основной путь диагностики: такой лог может не попасть в основной поток приложения так последовательно, как `logger.log_event()`.

### Целевой подход

Добавить в `generation.py` небольшой helper для диагностики, который будет вызываться перед выбросом `empty_response` или `collapsed_output`:

```python
from collections.abc import Iterable, Mapping, Sized
from logger import log_event
```

Пример целевого helper-а:

```python
def _log_empty_response_shape(response: object, raw_output_text: str, *, error_code: str) -> None:
    output_items = _read_response_field(response, "output")
    output_items_len = len(output_items) if isinstance(output_items, Sized) else None
    log_event(
        logging.WARNING,
        "model_empty_response_shape",
        "Модель вернула пустой или схлопнувшийся текстовый ответ",
        error_code=error_code,
        has_output_text_attr=getattr(response, "output_text", None) is not None,
        raw_output_len=len(raw_output_text),
        output_items_type=type(output_items).__name__ if output_items is not None else "None",
        output_items_len=output_items_len,
    )
```

И использовать его так:

```python
def _extract_normalized_markdown(response: object) -> str:
    raw_output_text = _extract_response_output_text(response)
    markdown = normalize_model_output(raw_output_text)
    if markdown:
        return markdown
    error_code = "collapsed_output" if raw_output_text else "empty_response"
    _log_empty_response_shape(response, raw_output_text, error_code=error_code)
    if raw_output_text:
        raise RuntimeError("Модель вернула ответ, который схлопнулся после нормализации (collapsed_output).")
    raise RuntimeError("Модель вернула пустой ответ (empty_response).")
```

### Важные ограничения

- Не вызывать `len(list(output_items))`: это может потребить одноразовый iterable.
- Длина `output_items` логируется только если объект реализует `Sized`; иначе логируется `None`.
- Логирование должно быть чисто диагностическим и не менять control flow.

### Что именно должно быть видно в логе

- `error_code`: `empty_response` или `collapsed_output`
- наличие `output_text`
- длина `raw_output_text`
- тип `response.output`
- длина `response.output`, если она доступна безопасно

Опционально, если захочется чуть богаче диагностика без роста риска:

- `response_type`
- `has_output_field`

Не нужно логировать полный текст ответа или большие фрагменты контента.

---

## 7. Тестирование

### 7.1. Новые тесты в `tests/test_generation.py`

1. `test_generate_markdown_block_retries_on_empty_response`

Первая попытка возвращает пустой `output_text`, вторая — валидный markdown.  
Ожидание: функция возвращает итоговый текст, `sleep` вызывается один раз с `1`.

2. `test_generate_markdown_block_retries_on_collapsed_output`

Первая попытка возвращает fenced block, который после `normalize_model_output()` схлопывается в пустую строку, вторая — валидный markdown.  
Ожидание: функция возвращает итоговый текст, ошибка не поднимается.

3. `test_generate_markdown_block_raises_after_persistent_empty_response`

Все попытки возвращают пустой ответ.  
Ожидание: после исчерпания бюджета поднимается `RuntimeError` с `empty_response`, а `sleep` отражает фактический backoff для заданного `max_retries`.

4. `test_generate_markdown_block_does_not_retry_unsupported_response_shape`

Ответ имеет unsupported shape или нестроковый `output_text`.  
Ожидание: ошибка поднимается сразу, `sleep` не вызывается.

5. `test_extract_normalized_markdown_logs_empty_response_shape`

Пустой ответ вызывает диагностический лог.  
Ожидание: вызван `log_event()` с `event="model_empty_response_shape"` и `error_code="empty_response"`.

6. `test_extract_normalized_markdown_logs_collapsed_output_shape`

Схлопнувшийся ответ также вызывает диагностический лог.  
Ожидание: `error_code="collapsed_output"`.

### 7.2. Уже существующие тесты, которые должны остаться зелёными

- существующий retry для обычной retryable-ошибки
- existing negative tests на `empty_response`
- existing negative tests на `collapsed_output`
- existing negative tests на `unsupported_response_shape`

### 7.3. Проверка backoff-контракта

Нужно явно зафиксировать в тестах фактическую семантику `max_retries`:

- при `max_retries=1` retry нет вообще
- при `max_retries=2` возможен один sleep: `[1]`
- при `max_retries=3` возможны sleep: `[1, 2]`

Это важно, потому что в исходной версии спецификации задержка была посчитана как если бы `max_retries` означал число повторов, а не число попыток.

### 7.4. Финальная верификация

Для пользовательски видимой финальной проверки использовать существующие VS Code task-ы, а не только agent-side shell:

1. `Run Current Test File` для [tests/test_generation.py](tests/test_generation.py)
2. `Run Full Pytest` для полного регрессионного прогона

Если для локальной отладки дополнительно используются shell-запуски, финальное подтверждение всё равно должно быть повторено через task.

---

## 8. Порядок внедрения

1. [x] В `generation.py` добавить helper для классификации retryable empty/collapsed ошибок.
2. [x] В `generation.py` добавить диагностический helper для безопасного логирования response shape через `logger.log_event()`.
3. [x] Обновить retry-цикл в `generate_markdown_block()` так, чтобы он ретраил `empty_response` и `collapsed_output`, но не ретраил `unsupported_response_shape`.
4. [x] Добавить unit-тесты на retry-path, exhaustion-path и logging-path в [tests/test_generation.py](tests/test_generation.py).
5. [ ] Прогнать финальную верификацию через task `Run Current Test File`.
6. [x] Прогнать финальную регрессию через task `Run Full Pytest`.
7. [ ] После этого выполнить UI-прогон на проблемном документе и проверить, что transient empty response больше не завершает весь документ с первого сбоя.

---

## 9. Критерии приёмки

Изменение считается завершённым, если выполняются все условия:

1. `empty_response` ретраится в пределах существующего `max_retries`.
2. `collapsed_output` ретраится в пределах существующего `max_retries`.
3. `unsupported_response_shape` не начинает ретраиться.
4. В логах появляется диагностическая запись о response shape для пустого или схлопнувшегося ответа.
5. Все тесты в [tests/test_generation.py](tests/test_generation.py) зелёные.
6. Полный pytest-регресс не показывает побочных падений.
7. UI-прогон подтверждает, что transient empty response больше не валит документ с первой неудачной попытки.

---

## 10. Риски и ограничения

- **Увеличение latency на проблемном блоке.** При дефолтном `max_retries=3` дополнительная задержка составит до `1 + 2 = 3` сек на блок. При верхнем clamp `max_retries=5` — до `1 + 2 + 4 + 8 = 15` сек.
- **Не решает систематические provider/model failures.** Если модель стабильно возвращает пустой ответ на конкретный класс входов, адресный retry не устранит корень проблемы.
- **Не решает pipeline-level resilience.** Если все попытки исчерпаны, pipeline по-прежнему завершится ошибкой блока; это сознательно остаётся вне области этой задачи.
- **Логирование должно остаться безопасным.** Нельзя ради диагностики потреблять iterable-данные или логировать большие payload-ы.
- **Классификация по подстроке остаётся техническим долгом.** Она приемлема для минимального изменения, но в будущем лучше перейти на явные internal error codes или отдельные exception types.

---

## 11. Рекомендация по следующему шагу

Кодовая реализация завершена. Следующий практический шаг — UI-прогон на проблемном документе, чтобы подтвердить, что transient `empty_response` больше не завершает обработку всего документа с первой неудачной попытки.

