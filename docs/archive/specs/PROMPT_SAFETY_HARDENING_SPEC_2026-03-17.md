# Prompt Safety Hardening — Спецификация

**Дата:** 2026-03-17
**Статус:** draft
**Триггер:** Стабильные `empty_response` от gpt-5-mini при наличии `[[DOCX_IMAGE_img_NNN]]` токенов в контексте промпта.

---

## 1. Корневая проблема

### Что произошло

При обработке документа `Лиетар глава1.docx` модель gpt-5-mini стабильно возвращала пустые ответы (`response_status: "incomplete"`, единственный output-item с `type: "reasoning"`, без текста) для блоков, в чей context_before/context_after попадали image-placeholder токены `[[DOCX_IMAGE_img_005]]`.

### Почему это случилось

1. В `document.py` → `build_editing_jobs()` контекстные выжимки (`context_before`, `context_after`) берутся из _текста соседних блоков_ как есть — включая inline-image-placeholder токены.
2. Эти токены — внутренний формат pipeline (`[[DOCX_IMAGE_img_NNN]]`), не имеющий смысла для языковой модели.
3. Модель интерпретирует их как повреждённый ввод, начинает reasoning, но не генерирует текстовый ответ → `status: "incomplete"`.

### Что уже исправлено (commit pending)

- `_strip_image_placeholders()` удаляет `[[DOCX_IMAGE_img_*]]` из `context_before`/`context_after` перед отправкой.
- Retry на `empty_response` / `collapsed_output` (до `max_retries` попыток).
- Recovery-путь `_recover_from_persistent_empty_response()` — вызов без контекста после исчерпания retry.
- Расширенная диагностика в `_log_empty_response_shape()` (response_status, first_output_item summary).

### Что НЕ закрыто

Текущий фикс реактивный — убирает _один_ известный паттерн токсичного контента. Нужна системная защита от _класса проблем_: любой неконсистентный или «чужеродный» контент в промпте, приводящий к пустому ответу модели.

---

## 2. Инвентаризация точек вызова API

| # | Файл | Функция | API | Промпт содержит | Риск |
|---|------|---------|-----|-----------------|------|
| 1 | generation.py | `generate_markdown_block` | responses.create | target_text + context_before/after | **ВЫСОКИЙ** — основной текстовый путь |
| 2 | generation.py | `_recover_from_persistent_empty_response` | responses.create | target_text only | Средний — recovery без контекста |
| 3 | image_analysis.py | `_extract_vision_analysis` | responses.create | base64 image + шаблон | Низкий — fallback на heuristic |
| 4 | image_reconstruction.py | `extract_scene_graph` | responses.create | base64 image + шаблон | Низкий |
| 5 | image_generation.py | `_extract_structured_layout_description` | responses.create | image + analysis metadata | Средний |
| 6 | image_generation.py | `_extract_creative_redraw_brief` | responses.create | image + analysis metadata | Средний |
| 7 | image_generation.py | `_generate_direct_semantic_candidate` | images.edit | prompt + image | Низкий |
| 8 | image_generation.py | `_generate_creative_candidate` | images.generate | prompt text | Низкий |
| 9 | image_generation.py | `_generate_structured_candidate` | images.generate | prompt text | Низкий |

**Scope этой спецификации: точка #1** (`generate_markdown_block`) — единственное место, где в промпт попадает DOCX-content и контекст из соседних блоков, и единственное место с наблюдаемой проблемой. Точки #5-6 имеют теоретический риск через `analysis.structure_summary`, но на практике vision-fallback защищает от мусора.

---

## 3. План защиты — три уровня

### Уровень 1: Санитизация входов (preventive)

**Цель:** не допускать попадания «чужеродных» или пустых данных в промпт.

#### 1A. Guard: target_text не должен быть image-only `[NEW]`

**Обоснование:** `build_editing_jobs()` в `document.py` уже ставит `job_kind="passthrough"` для блоков, где все параграфы имеют `role="image"`. Но если passthrough-маршрут пропущен (баг, ручной вызов, будущий рефакторинг), generation.py отправит в модель текст вида `[[DOCX_IMAGE_img_001]]\n\n[[DOCX_IMAGE_img_002]]` — гарантированно получив пустой ответ.

**Реализация:**
- В `generate_markdown_block()` перед retry-loop добавить проверку:
  ```python
  if _is_image_only_target(target_text):
      return target_text  # passthrough — нечего редактировать
  ```
- Функция `_is_image_only_target()` использует паттерн `^(\s*\[\[DOCX_IMAGE_img_\d+\]\]\s*)+$` (аналог `IMAGE_ONLY_PATTERN` из document.py, но локальная копия в generation.py чтобы не вводить зависимость).
- Логирование: `log_event(WARNING, "image_only_target_passthrough", ...)`.

**Обоснование отдельного паттерна:** generation.py не должен зависеть от document.py (он уже сейчас не импортирует его). Паттерн тривиальный и стабильный.

#### 1B. Guard: target_text содержит минимум реального текста `[NEW]`

**Обоснование:** Помимо image-only, возможны блоки, состоящие в основном из placeholder-разметки с минимальным текстом. Если target_text после удаления всех `[[DOCX_IMAGE_img_*]]` содержит < 1 символа реального текста — нет смысла вызывать модель.

**Реализация:**
- В той же guard-проверке:
  ```python
  stripped = _CONTEXT_IMAGE_PLACEHOLDER_PATTERN.sub("", target_text).strip()
  if not stripped:
      return target_text
  ```
- Объединяется с 1A в одну функцию `_should_passthrough_target(target_text) -> bool`.

#### 1C. Контекст: уже реализовано `[DONE]`

- `_strip_image_placeholders()` → убирает `[[DOCX_IMAGE_img_*]]` из context_before/after.
- `_normalize_context_text()` → пустой контекст → `"[контекст отсутствует]"`.

---

### Уровень 2: Валидация ответа модели (detective)

**Цель:** раннее обнаружение паттернов «модель не смогла ответить» до обработки пустого текста.

#### 2A. Обнаружение `response.status == "incomplete"` `[NEW]`

**Обоснование:** Из логов валидационного прогона видно: модель возвращает `response_status: "incomplete"` с `first_output_item.type: "reasoning"`. Сейчас это ловится косвенно — через пустой `output_text` → `RuntimeError("empty_response")`. Явная проверка `response.status` позволяет:
1. Раньше обнаруживать проблему (до итерации по output items).
2. Давать точный `error_code` для диагностики (не `empty_response`, а `incomplete_response`).
3. Правильно классифицировать как retriable — `incomplete` почти наверняка транзиентная проблема.

**Важно:** Только `"incomplete"` считается retryable. Другие non-completed статусы (например `"failed"`, `"cancelled"`) — это hard failure: логировать с отдельным error_code `"non_completed_response"` и поднимать как non-retryable `RuntimeError`. Если мы встретим такие статусы на практике, добавим обработку по реальным кейсам.

**Реализация:**
- В `_extract_normalized_markdown()`, перед вызовом `_extract_response_output_text()`:
  ```python
  response_status = _read_response_field(response, "status")
  if response_status == "incomplete":
      _log_empty_response_shape(response, "", error_code="incomplete_response")
      raise RuntimeError("Модель не завершила генерацию (incomplete_response).")
  if isinstance(response_status, str) and response_status != "completed":
      _log_empty_response_shape(response, "", error_code="non_completed_response")
      raise RuntimeError(f"Модель вернула неожиданный статус ответа: {response_status} (non_completed_response).")
  ```
- Добавить `"incomplete_response"` (но НЕ `"non_completed_response"`) в `_is_retryable_empty_generation_error()`:
  ```python
  def _is_retryable_empty_generation_error(exc: Exception) -> bool:
      return isinstance(exc, RuntimeError) and any(
          marker in str(exc)
          for marker in ("empty_response", "collapsed_output", "incomplete_response")
      )
  ```
- `"non_completed_response"` НЕ retryable — будет проброшен как hard failure.

#### 2B. Обнаружение reasoning-only ответа `[NEW]`

**Обоснование:** Из логов: модель возвращает один output-item с `type: "reasoning"`, без `type: "message"`. Это новый паттерн, который не ловится через `output_text` (он может быть `""` или вообще missing). Текущий код косвенно это обрабатывает (пустой output_text → empty_response), но без явной диагностики.

**Решение:** Не делать отдельную проверку — достаточно #2A. Если `response.status == "incomplete"`, то причина (reasoning-only, timeout, etc.) не важна — ответ всё равно бесполезен. Reasoning-only case уже залогирован через `first_output_item.type: "reasoning"` в `_log_empty_response_shape()`.

---

### Уровень 3: Архитектурная защита (structural)

**Цель:** централизовать валидацию контента промпта, чтобы будущие изменения не могли случайно отправить «токсичный» промпт.

#### 3A. Pre-flight prompt validation `[NEW]`

**Обоснование:** Сейчас каждый вызов `generate_markdown_block` полагается на то, что вызывающий код (document_pipeline) передаст чистые данные. Но generation.py — это публичный API модуля, который может вызываться из тестов, скриптов, будущих модулей. Нужна «последняя линия обороны» внутри generation.py.

**Реализация:**
- Новая функция `_validate_prompt_inputs(target_text, context_before, context_after) -> list[str]`:
  - Возвращает список предупреждений (непустой = проблемы обнаружены).
  - Проверки:
    1. `target_text` пуст после strip → предупреждение.
    2. `target_text` image-only → предупреждение (уже покрыто 1A guard, но здесь для единообразия логирования).
  - Предупреждения логируются через `log_event(WARNING, "prompt_quality_warning", ...)`.
  - Функция **не блокирует** вызов — только предупреждает. Блокировка реализуется через guards (1A, 1B).

**Убранные проверки (по результатам ревью):**
- ~~Доля placeholder-токенов > 50%~~ — placeholders в target_text нормальны (нужны для image reinsertion). Детерминистический случай (нет реального текста) уже покрыт guard 1B. Ratio — шумный эвристический сигнал.
- ~~Суммарная длина > 32000 символов~~ — сырая длина "target + context" не отражает реальный payload (system_prompt + служебные маркеры не учтены). Валидировать собранный prompt — overengineering для warning-only сигнала.

**Обоснование "warn, don't block":** Мы не можем точно знать, что модель не справится с конкретным промптом. False positives при блокировке хуже, чем лишнее предупреждение в логах. Блокировку делают только guards с абсолютными условиями (image-only target, пустой target).

---

## 4. Декомпозиция изменений

### Файлы, которые затрагиваются

| Файл | Изменения |
|------|-----------|
| `generation.py` | Все три уровня — guards, response.status check, pre-flight validation |
| `tests/test_generation.py` | Новые тесты для каждого нового поведения |

### Порядок реализации

1. **Уровень 1A+1B:** `_should_passthrough_target()` + guard в `generate_markdown_block()`.
2. **Уровень 2A:** `response.status` check в `_extract_normalized_markdown()` + расширение `_is_retryable_empty_generation_error()`.
3. **Уровень 3A:** `_validate_prompt_inputs()` + вызов в `generate_markdown_block()`.
4. **Тесты:** по одному тесту на каждое новое поведение.

### Что НЕ меняется

- `document.py` — `build_editing_jobs()` уже корректно ставит `job_kind="passthrough"` для image-only блоков. Дублированный guard в generation.py — это defence-in-depth, не замена.
- `document_pipeline.py` — pipeline-уровень обработки не меняется.
- `image_shared.py` — `is_retryable_error()` остаётся для HTTP-ошибок. `_is_retryable_empty_generation_error()` остаётся для content-ошибок. Это разные классы ошибок.
- Image pipeline файлы — низкий риск, не в scope.

---

## 5. Тест-план

| Тест | Покрывает | Уровень |
|------|-----------|---------|
| `test_generate_markdown_block_passthrough_for_image_only_target` | target = `[[DOCX_IMAGE_img_001]]` → возвращает as-is без API call | 1A |
| `test_generate_markdown_block_passthrough_for_placeholder_only_target` | target = `[[DOCX_IMAGE_img_001]] [[DOCX_IMAGE_img_002]]` → passthrough | 1B |
| `test_generate_markdown_block_processes_mixed_text_and_placeholders` | target = `Текст [[DOCX_IMAGE_img_001]] продолжение` → нормальный вызов API | 1A neg |
| `test_extract_normalized_markdown_raises_on_incomplete_response` | response.status = "incomplete" → `RuntimeError("incomplete_response")` | 2A |
| `test_extract_normalized_markdown_raises_hard_on_non_completed_response` | response.status = "failed" → `RuntimeError("non_completed_response")`, NOT retryable | 2A |
| `test_incomplete_response_is_retryable` | `_is_retryable_empty_generation_error` возвращает True для incomplete_response | 2A |
| `test_non_completed_response_is_not_retryable` | `_is_retryable_empty_generation_error` возвращает False для non_completed_response | 2A |
| `test_generate_markdown_block_retries_on_incomplete_response` | response.status = "incomplete" → retry → success | 2A integ |
| `test_validate_prompt_inputs_warns_on_empty_target` | пустой target_text → warning в логах | 3A |
| `test_validate_prompt_inputs_warns_on_image_only_target` | image-only target_text → warning в логах | 3A |

---

## 6. Рефакторинг

### Консолидация retry-предикатов

Сейчас в generation.py два предиката:
- `is_retryable_error(exc)` — HTTP-ошибки (из image_shared.py)
- `_is_retryable_empty_generation_error(exc)` — content-ошибки (локальная)

Это правильное разделение — они проверяют разные классы ошибок. НЕ объединяем.

### Именование

Новые функции следуют конвенции модуля:
- `_should_passthrough_target(target_text: str) -> bool` — private, prefixed
- `_validate_prompt_inputs(target_text, context_before, context_after) -> list[str]` — private, returns warnings
- Все public API остаются без изменений

### Размещение кода

Все новые функции размещаются в generation.py:
- `_should_passthrough_target` — рядом с `_strip_image_placeholders` (related concerns)
- Проверка `response.status` — внутри `_extract_normalized_markdown` (related scope)
- `_validate_prompt_inputs` — перед `generate_markdown_block` (called from it)

---

## 7. Риски и ограничения

| Риск | Митигация |
|------|-----------|
| False positive passthrough: блок содержит image-placeholders + реальный текст, но `_should_passthrough_target` пропускает его | Проверка через `_CONTEXT_IMAGE_PLACEHOLDER_PATTERN.sub("", text).strip()` — если после удаления placeholders остаётся текст, блок обрабатывается нормально |
| `response.status` API может измениться в будущих версиях SDK | Только `"incomplete"` → retryable. Неизвестные non-completed статусы → hard failure с логированием. Не маскируем unknown errors под retryable |
| Pre-flight validation логирует false warnings | Warning-only, не блокирует. Можно отключить или настроить порог |
| Overhead на валидацию | Все проверки O(len(target_text)) — пренебрежимо мало на фоне API latency |
