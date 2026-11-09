# Контракт: параметр рассуждения по путям API

Владелец: WP-2 (`generation/_generation.py`, `image/shared.py`); учёт — WP-3 (`core/model_accounting.py`).
Проверено по коду 2026-11-09 (`64f8856`).

## 1. Какие вызовы несут уровень прохода

| Вызов | Где | Профиль |
|---|---|---|
| попытки блока | `generate_markdown_block` → `_build_request_kwargs` (`_generation.py:2243`) | прохода (первого или второго) |
| повтор с поднятым бюджетом | `_boost_request_output_budget` (`:2262`) — копирует запрос | тот же |
| восстановление после исчерпания | `_recover_from_persistent_empty_response` (`:2357`) | тот же |
| лестница деградации | `_attempt_degradation_ladder` → `_ladder_translate_unit` → `_ladder_model_answer` (`:2911`) | тот же |
| восстановление пары (`_merged_pair_repair_fallback`) | без вызова модели | — |
| глоссарий прогона | `request_text_completion` (`:2322`) из `pipeline/glossary_phase.py` | первого прохода |
| проверка границ абзацев, картинки | `call_responses_create_with_retry` напрямую | НЕ несут (свои модели) |

`request_profile=None` (по умолчанию) → запрос побайтно прежний: ключа `reasoning` нет, лимит прежний, стадия
`text_generation` (или переданная `usage_stage` у `request_text_completion`).

## 2. Форма запроса

| Путь | Условие | Как передаётся | Удаление при отказе |
|---|---|---|---|
| Responses API (основной) | клиент с `responses.create` | `request_kwargs["reasoning"] = {"effort": "<e>"}` | `_call_responses_create` добавляет `"reasoning"` в `retryable_optional_params`; `drop_rejected_optional_param` снимает ключ, WARNING `model_call_param_dropped` (`param=reasoning`) |
| OpenRouter Chat Completions (запасной) | `_is_openrouter_responses_compatibility_error` | `payload["extra_body"] = {"reasoning": {"effort": "<e>"}}` | `drop_rejected_optional_param` ищет названный параметр сначала на верхнем уровне, затем в `payload["extra_body"]`; снимает вложенный ключ (пустой `extra_body` удаляется), WARNING тот же |
| Нативный Anthropic | `_is_anthropic_client` | не передаётся | — ; WARNING `reasoning_effort_not_supported_for_provider` один раз на (модель, уровень) в процессе |

Распознавание отказа — существующий `extract_unsupported_parameter_name` (`image/shared.py:79`): `Unsupported
parameter: '…'`, `Unknown parameter: '…'`, `unexpected keyword argument '…'`, `does not support the '…'`. Ответ
провайдера «Reasoning is mandatory … cannot be disabled» (bake-off, costs.md §4) параметр не называет и сюда не
относится: отключение рассуждения не отправляется никогда.

## 3. Учёт

| Путь | Поле токенов рассуждения | Поле кеша |
|---|---|---|
| Responses | `usage.output_tokens_details.reasoning_tokens` | `usage.input_tokens_details.cached_tokens` |
| Chat | `usage.completion_tokens_details.reasoning_tokens` | `usage.prompt_tokens_details.cached_tokens`, `…cache_write_tokens` |
| Anthropic | нет | нет (кеш Anthropic — явный, не используется) |
| OpenRouter (любой путь) | — | `usage.cache_discount` (если отдан) |

Поля нет → `None` («неизвестно»), счётчик `reasoning_unreported_call_count` стадии растёт; ноль пишется только если
провайдер сам прислал ноль. Снимок `model_usage_accounted` показывает по стадиям `reasoning_tokens`,
`reasoning_reported_call_count`, `reasoning_unreported_call_count`, `cached_tokens`, `cache_write_tokens`,
`cache_discount_usd`, `cache_fields_reported_call_count`.

## 4. Значения режимов v1

| Режим | Первый проход | Второй проход |
|---|---|---|
| `standard` | flash-lite, без параметра | haiku-5.5, без параметра (как замер C) |
| `quality` | gemini-3.7-flash, `low` | — |
| `single` | как сегодня, без параметра | — |
