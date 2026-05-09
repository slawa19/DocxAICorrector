# OpenRouter Text Provider Integration Spec

Date: 2026-05-05
Status: proposed

## Goal

Безопасно добавить поддержку моделей OpenRouter в текущий production pipeline DocxAICorrector так, чтобы:

1. пользователь мог выбирать OpenRouter text-модели в основном UI;
2. pipeline мог выполнять text processing через OpenRouter без изменения пользовательского контракта обработки документов;
3. текущий OpenAI-based production path оставался полностью рабочим и обратносovместимым;
4. image pipeline, startup contract, logging contract и WSL-first runtime contract не деградировали;
5. будущая promotion benchmark-winner модели в default происходила отдельным решением, а не как побочный эффект подключения нового provider.

Главный практический мотив: текущие benchmark artifacts и итоговая статья показывают, что через OpenRouter появились production-relevant text candidates для `en -> ru` перевода: `google/gemini-3-flash-preview` лидирует по качеству, а `google/gemini-3.1-flash-lite-preview` лидирует по соотношению качества и стоимости. Но текущий основной pipeline не умеет безопасно работать с OpenRouter-моделями.

## Problem Statement

Сейчас в репозитории есть разрыв между benchmark runtime и production runtime.

В benchmark-проекте OpenRouter уже используется как отдельный transport layer для model comparison.

В основном приложении runtime пока OpenAI-only:

1. `src/docxaicorrector/core/config.py` создаёт singleton client только из `OPENAI_API_KEY`.
2. `get_client()` вызывает `OpenAI(api_key=...)` без `base_url` и без provider-specific headers.
3. UI, config loader и pipeline передают модель как обычную строку без понятия provider.
4. Text pipeline, structure recognition, paragraph-boundary AI review и image pipeline используют один и тот же OpenAI-compatible client contract, но не различают capability surface провайдера.
5. README и тесты документируют и страхуют OpenAI-only contract как текущий baseline.

Из-за этого простая замена `models.text.default` на `google/gemini-3.1-flash-lite-preview` небезопасна: строка модели попадёт в OpenAI client path, который не знает ни OpenRouter base URL, ни `OPENROUTER_API_KEY`, ни required headers.

## Evidence From Current Codebase

### 1. Current client ownership

Текущий singleton client живёт в `src/docxaicorrector/core/config.py`:

1. `get_client()` лениво загружает `.env`.
2. Читает только `OPENAI_API_KEY`.
3. Создаёт `OpenAI(api_key=api_key)`.
4. Кеширует клиента process-wide.

Следствие: любой provider, кроме прямого OpenAI, сейчас вне основного runtime contract.

### 2. Current model registry shape

Текущий canonical registry описан строковыми model names:

```toml
[models.text]
default = "gpt-5.4-mini"
options = ["gpt-5.4", "gpt-5.4-mini", "gpt-5-mini"]
```

Это подтверждается в:

1. `config.toml`
2. `.env.example`
3. `README.md`
4. `src/docxaicorrector/core/config.py`
5. `src/docxaicorrector/core/config_model_registry.py`
6. `tests/test_config.py`

Registry пока не хранит provider отдельно от model id.

### 3. Current UI path

В `src/docxaicorrector/ui/_ui.py` sidebar:

1. берёт `models.text.options`;
2. определяет `default_model`;
3. отдаёт выбранную строку как `model` дальше в pipeline.

UI contract сейчас предполагает, что модель равна готовому runtime model name.

### 4. Current processing path

Дальнейший flow выглядит так:

1. `src/docxaicorrector/ui/_app.py` передаёт `model` в background processing.
2. `src/docxaicorrector/pipeline/_pipeline.py` и `pipeline/setup.py` передают ту же строку в processing context.
3. `pipeline/setup.py` получает один client через `dependencies.get_client()`.
4. `src/docxaicorrector/generation/_generation.py` вызывает `client.responses.create(...)` с `model=<эта же строка>`.

Это означает, что routing provider-а нигде явно не происходит.

### 5. Secondary text paths that also depend on the same contract

Текущий текстовый runtime не ограничивается только основным translate/edit block path. На него опираются также:

1. `translation_second_pass_model` в `src/docxaicorrector/pipeline/block_execution.py`;
2. audiobook postprocess fallback на `audiobook_model` и основную text model;
3. real-document validation run profiles в `src/docxaicorrector/validation/profiles.py`;
4. paragraph-boundary AI review в `src/docxaicorrector/document/boundary_review.py`;
5. optional structure recognition и другие `responses.create`-ориентированные AI paths.

Поэтому любое provider-aware изменение должно проектироваться не только на UI selectbox, но и на весь text-runtime contract.

### 6. Image path is not equivalent to text path

Image pipeline использует не только `responses.create`, но и `images.generate` / `images.edit`.

Это видно в:

1. `src/docxaicorrector/image/generation.py`
2. `src/docxaicorrector/image/analysis.py`
3. `src/docxaicorrector/image/validation.py`

Следствие: безопасное подключение OpenRouter для text path не означает автоматическую готовность OpenRouter для image roles.

### 7. Current pipeline initialization shares one client across phases

Текущий `pipeline/setup.py` получает один `client = dependencies.get_client()` на старте обработки и передаёт его дальше как `initialization.client`.

Этот client затем используется не только основным text block path, но и:

1. `translation_second_pass_model` в `pipeline/block_execution.py`;
2. audiobook postprocess в `pipeline/late_phases.py` через отдельный `dependencies.get_client()`;
3. image late phases, где нужны `responses.create`, `images.generate` и `images.edit`.

Следствие: phase-1 implementation не может просто заменить стартовый client на OpenRouter client. Нужно явно разделить text clients и OpenAI service/image client, иначе выбор OpenRouter text model может случайно увести image pipeline на provider без image capabilities.

## Non-Goals

Этот change-set не должен пытаться решить всё сразу.

Вне scope этой спецификации:

1. немедленное переключение default text model на Gemini;
2. подключение OpenRouter к image generation/edit pipeline;
3. автоматическое изменение service-level image defaults;
4. автоматическое продвижение benchmark winner в production defaults;
5. removal legacy config aliases;
6. перестройка benchmark-проекта;
7. изменение WSL-first workflow, startup contract или test workflow contract.

## Design Constraints

Любое решение обязано соблюдать следующие репозиторные инварианты.

### 1. No startup regression

Подключение OpenRouter не должно:

1. добавлять network bootstrap на старте приложения;
2. заставлять `load_app_config()` проверять живые provider endpoints;
3. ломать singleton/caching contract для client initialization;
4. добавлять тяжёлую синхронную работу до первого полезного экрана.

### 2. WSL-first runtime stays unchanged

Никакой Windows-first provider bootstrap, PowerShell-only path или обходной runtime не допускается.

### 3. Centralized model registry remains canonical

Нельзя возвращаться к разрозненным model literals в runtime modules. Все production model assignments должны продолжать проходить через centralized registry.

### 4. Logging remains centralized

Новые provider-aware ветки должны логироваться через существующий `log_event()` contract, без ad-hoc логгеров.

### 5. Images stay on OpenAI in phase 1

Для снижения blast radius OpenRouter подключается сначала только к text-transform surface. Image-related роли сохраняют текущий OpenAI contract.

## Proposed Solution

### Summary

Рекомендуемое решение для безопасного MVP-подключения OpenRouter:

1. ввести provider-qualified text model selector string;
2. добавить provider runtime config для `openai` и `openrouter`;
3. заменить единый `get_client()` на provider-aware client factory с кешированием по provider;
4. оставить `get_client()` как backward-compatible alias к `openai` client;
5. подключить provider-aware resolution только к text processing surface в первой фазе;
6. запретить OpenRouter assignments для image roles на уровне config validation;
7. оставить promotion `Gemini` в default как отдельный последующий шаг после integration verification.

## Design Decision: Provider-Qualified Selector Strings

### Chosen shape

Вместо полной замены registry shape на вложенные таблицы с `{ provider, model }` предлагается использовать квалифицированную строку-селектор.

Формат:

```text
<provider>:<model_id>
```

Примеры:

```text
gpt-5.4-mini
openai:gpt-5.4-mini
openrouter:google/gemini-3.1-flash-lite-preview
openrouter:anthropic/claude-haiku-4.5
```

### Resolution rules

1. Если префикс отсутствует, селектор считается `openai` для backward compatibility.
2. Если префикс указан, он должен быть одним из поддерживаемых provider ids.
3. В runtime селектор разбирается на:
   - `raw_selector`
   - `canonical_selector`
   - `provider`
   - `model_id`
4. В UI и config canonical stored value остаётся строкой, а не таблицей.
5. `canonical_selector` всегда хранится в явном виде `<provider>:<model_id>`.
6. Для bare OpenAI input `canonical_selector = "openai:<raw_model>"`, но legacy user-facing fields могут продолжать показывать bare selector там, где это нужно для backward compatibility.

### Why this shape is preferred

Это решение минимизирует churn в существующем коде:

1. `models.text.options` остаётся списком строк;
2. env override `DOCX_AI_MODELS_TEXT_OPTIONS` остаётся CSV-строкой;
3. sidebar contract не ломается на уровне типа данных;
4. run profiles и custom model input могут использовать тот же string syntax;
5. migration cost существенно ниже, чем для полной замены registry на nested objects.

### Rejected alternative: object-based model registry

Форма вида:

```toml
default = { provider = "openrouter", model = "google/gemini-3.1-flash-lite-preview" }
```

не рекомендуется для первой фазы, потому что она одновременно ломает:

1. `models.text.options` parser;
2. CSV env override contract;
3. UI selectbox assumptions;
4. test fixtures и helper contracts;
5. current minimal migration surface.

Такой переход может быть рассмотрен позже только как отдельный refactor со своей спецификацией.

## Provider Runtime Contract

### New canonical config section

Нужно добавить provider config surface в `config.toml`.

Предлагаемая форма:

```toml
[providers.openai]
enabled = true
api_key_env = "OPENAI_API_KEY"

[providers.openrouter]
enabled = false
api_key_env = "OPENROUTER_API_KEY"
base_url = "https://openrouter.ai/api/v1"
referer = "DocxAICorrector"
title = "DocxAICorrector"
```

### Required config data model

Provider config должен быть first-class частью resolved application config, а не ad-hoc чтением env внутри client factory.

Минимальная shape:

```python
@dataclass(frozen=True)
class ProviderConfig:
    name: str
    enabled: bool
    api_key_env: str
    base_url: str | None = None
    referer: str | None = None
    title: str | None = None

@dataclass(frozen=True)
class ProviderRegistry:
    openai: ProviderConfig
    openrouter: ProviderConfig
```

Integration requirements:

1. `AppConfig` получает поле `providers: ProviderRegistry`.
2. `build_app_config_payload()` обязан включать `providers` в returned payload.
3. Mapping access через `app_config.get("providers")` должен работать так же, как для `models`.
4. Parsing providers остаётся pure config/env parsing без client construction и без network calls.
5. Если секция `[providers]` отсутствует, default registry создаётся из hard-coded defaults выше.
6. Unsupported provider tables в TOML должны приводить к явной config error, а не silently ignored config.

### Environment overrides

Нужно поддержать следующие override values:

```env
OPENROUTER_API_KEY=...
DOCX_AI_PROVIDERS_OPENROUTER_ENABLED=true
DOCX_AI_PROVIDERS_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DOCX_AI_PROVIDERS_OPENROUTER_REFERER=DocxAICorrector
DOCX_AI_PROVIDERS_OPENROUTER_TITLE=DocxAICorrector
```

`OPENAI_API_KEY` и существующий OpenAI path остаются без изменений.

### Provider config semantics

1. `enabled = false` означает, что provider нельзя использовать даже если в `.env` есть ключ.
2. Отсутствие `OPENROUTER_API_KEY` не должно ломать startup, пока OpenRouter selector фактически не используется.
3. Provider credential resolution должна быть lazy.
4. Provider config parsing должна быть deterministic и pure-config-only, без network preflight.
5. `providers.openai.enabled = true` является required default для backward compatibility.
6. Если пользователь явно задаёт `providers.openai.enabled = false`, bare model selectors и `openai:<model>` должны валиться при validation как disabled provider.
7. `get_client()` как alias к `get_provider_client("openai")` обязан уважать `providers.openai.enabled`; это допустимое explicit opt-out, но не default behavior.
8. `OPENAI_API_KEY` остаётся достаточным для OpenAI-only baseline при отсутствии любых `[providers.*]` overrides.

### Credential availability helper

UI и early run validation не должны создавать client только для проверки ключей.

Нужно добавить pure helper:

```python
describe_provider_availability(selector: str, *, app_config: AppConfig | Mapping[str, object]) -> ProviderAvailability
```

Минимальная returned shape:

```python
@dataclass(frozen=True)
class ProviderAvailability:
    selector: ResolvedModelSelector
    provider: ProviderConfig
    enabled: bool
    api_key_env: str
    has_api_key: bool
    error_message: str | None
```

Rules:

1. Helper читает только resolved config и environment variables.
2. Helper не импортирует OpenAI SDK, не создаёт client и не делает network preflight.
3. UI sidebar should call helper when rendering the currently selected text model so provider issues are visible before pressing Start.
4. UI should call helper again when the selected model changes, including custom selector input.
5. Processing start should call the same helper or an equivalent validation path again as final preflight before background run init.
6. Final runtime authority всё равно остаётся `get_provider_client(...)`, потому что env мог измениться между UI warning и actual run.

## Provider Capability Model

Чтобы подключение было безопасным, одного `provider` недостаточно. Нужна capability matrix, принадлежащая коду, а не пользовательскому TOML.

### Required capabilities

В первой фазе достаточно следующих capability labels:

1. `responses_text`
2. `responses_vision`
3. `images_generate`
4. `images_edit`

### Phase-1 capability map

| Provider | responses_text | responses_vision | images_generate | images_edit |
| --- | --- | --- | --- | --- |
| `openai` | yes | yes | yes | yes |
| `openrouter` | yes | no | no | no |

Обоснование:

1. текущая задача касается text models;
2. benchmark validation для OpenRouter пока покрывает text-only path;
3. image contract и multimodal service-level contracts требуют отдельной валидации.

### Enforcement rules

1. `models.text.default`, `models.text.options`, `models.audiobook.default`, `translation_second_pass_model`, UI custom text input и run-profile `model` могут использовать provider с capability `responses_text`.
2. `models.image_analysis.default`, `models.image_validation.default`, `models.image_reconstruction.default`, `models.image_generation.default`, `models.image_edit.default`, `models.image_generation_vision.default` не могут быть привязаны к provider without corresponding capability.
3. Если конфиг присваивает OpenRouter image role, `load_app_config()` должен падать с явной ошибкой конфигурации.

## Client Factory Refactor

### Current issue

Сейчас проект имеет один глобальный `_CLIENT`, который implicitly means OpenAI.

### Required target shape

Нужно ввести provider-aware singleton registry:

```text
_CLIENTS_BY_PROVIDER: dict[str, OpenAIClient]
```

Новая публичная поверхность:

1. `get_provider_client(provider_name: str)`
2. `get_client_for_model_selector(selector: str, required_capability: str)`
3. `resolve_model_selector(selector: str, required_capability: str | None = None)`

Backward-compatible alias:

1. `get_client()` остаётся, но становится alias к `get_provider_client("openai")`

### OpenRouter client construction

OpenRouter client должен строиться через тот же OpenAI SDK, но с provider-specific runtime settings:

```python
OpenAI(
    api_key=openrouter_api_key,
    base_url=openrouter_base_url,
    default_headers={
        "HTTP-Referer": openrouter_referer,
        "X-OpenRouter-Title": openrouter_title,
    },
)
```

Note: OpenRouter documentation uses `X-OpenRouter-Title`; older examples sometimes show `X-Title`. Phase 1 must use `X-OpenRouter-Title` unless targeted verification proves another header is required.

### Lazy initialization rules

1. Клиент создаётся только при первом фактическом использовании provider.
2. Ошибка отсутствующего ключа поднимается только при попытке использовать provider.
3. Startup path и `load_app_config()` не должны пытаться создать OpenRouter client заранее.
4. Singleton locking semantics должны сохраниться для каждого provider отдельно.

### OpenRouter Responses API dialect

Current production text generation uses `client.responses.create(...)`, not `chat.completions.create(...)`.

OpenRouter documents `POST /responses` in OpenResponses format at `https://openrouter.ai/api/v1/responses`, so phase 1 may keep the existing Responses API call shape only if targeted smoke verification confirms compatibility for the chosen OpenRouter model.

Implementation requirement:

1. Add provider capability `responses_text` as a code-owned capability, but also document it as `Responses API dialect: openai_responses` for both OpenAI and OpenRouter in phase 1.
2. Introduce an explicit adapter boundary near text generation code, for example `call_text_generation_api(...)`, instead of routing providers directly inside pipeline modules.
3. Adapter default path is `client.responses.create(...)` with the existing request shape.
4. If `responses.create` returns a provider-compatibility failure for a concrete OpenRouter model, the adapter may transparently fall back to `client.chat.completions.create(...)` with explicit request transformation.
5. Compatibility fallback is allowed only inside the adapter boundary. Pipeline, UI, config, and logging layers must remain unaware of whether the concrete provider call used Responses or Chat Completions.
6. The adapter boundary must preserve current `generate_markdown_block(...)` contract for existing OpenAI tests.
7. If OpenRouter requires provider-specific request params for the selected model, add them inside the adapter rather than sprinkling provider conditionals across pipeline modules.
8. Verification must include at least one real or mocked `client.responses.create(...)` call through OpenRouter client construction.
9. If fallback is activated for a model/provider pair, runtime must log an explicit adapter event such as `provider_text_api_fallback_engaged` with selector/provider/api_surface context.

### Adapter fallback contract

The fallback path exists to keep phase 1 implementable if OpenRouter model compatibility with Responses API turns out to be partial.

Fallback trigger examples:

1. OpenRouter returns a structured error indicating unsupported Responses API parameters.
2. OpenRouter returns a provider-specific incompatibility for the Responses endpoint.
3. Targeted verification proves that the selected model works only via `chat.completions.create(...)`.

Fallback rules:

1. Fallback is provider-specific and model-specific, not a global switch for the whole app.
2. Fallback is allowed only for `openrouter` in phase 1; OpenAI keeps the existing Responses path.
3. Adapter must map current prompt contract into chat-completions messages deterministically.
4. Adapter must preserve retry/error taxonomy as much as possible so higher layers do not branch on API surface.
5. If neither Responses nor Chat Completions path is compatible for a selected OpenRouter model, processing must fail with an explicit provider compatibility error rather than silent downgrade.

## Runtime Resolution Flow

### Current state

Сейчас pipeline передаёт строку `model` и отдельно получает единый client.

### Proposed phase-1 flow

1. UI возвращает `raw_selector`.
2. Pipeline context сохраняет `raw_selector` как user-facing model selection.
3. Перед началом processing run вызывается `resolve_model_selector(raw_selector, required_capability="responses_text")`.
4. По resolved provider получается provider-specific text client.
5. В `generate_markdown_block(...)` передаётся уже `client` нужного provider и `model_id` без provider prefix.
6. Для OpenAI-only service/image roles отдельно используется OpenAI client, а не text client.
7. В логи сохраняются оба значения:
   - `model_selector`
   - `canonical_model_selector`
   - `model_provider`
   - `model_id`

### Proposed runtime data shape

В processing context нужно ввести отдельные поля:

1. `model_selector`: исходное пользовательское значение
2. `canonical_model_selector`: явное `<provider>:<model_id>`
3. `model_provider`: `openai` или `openrouter`
4. `model_id`: реальный provider-specific model id

Это safer, чем продолжать перегружать одно поле `model` сразу тремя значениями.

### Why this matters

Это позволяет:

1. показывать пользователю именно выбранный selector;
2. логировать реальный provider отдельно;
3. не ломать future fallback logic для second-pass и audiobook branches;
4. не путать OpenRouter selector string с actual provider model id.

## Pipeline Contract Changes

Phase 1 должна зафиксировать новые поля в pipeline contracts, иначе implementation будет вынужден гадать, где хранить resolved provider state.

### ProcessingContext

`ProcessingContext` должен получить explicit text model fields:

1. `model_selector`: raw user/config selector, например `openrouter:google/gemini-3.1-flash-lite-preview`.
2. `canonical_model_selector`: normalized selector, например `openai:gpt-5.4-mini`.
3. `model_provider`: provider id.
4. `model_id`: provider-specific model id without prefix.

Backward compatibility:

1. Existing `context.model` может временно остаться alias к `model_selector` для old logs/tests.
2. New code должен использовать `model_id` при вызове provider client.
3. New logs должны писать both old `model` and new provider-aware fields during migration.

### ProcessingInitialization

`ProcessingInitialization` не должен хранить один ambiguous `client` как единственный runtime client.

Target shape:

1. `text_client`: provider-specific client для основного text selector.
2. `text_model_id`: provider-specific model id для основного text selector.
3. `openai_client`: OpenAI client для phase-1 service/image roles.
4. `job_count`: existing field.

Compatibility bridge:

1. `initialization.client` может временно alias-иться к `text_client` only for existing text block code.
2. Image code must use `initialization.openai_client` or an explicitly named service/image client.

### ProcessingDependencies

Current zero-argument `get_client` dependency is insufficient for provider-aware text runtime.

Required dependency surface:

1. `get_provider_client(provider_name: str)`
2. `get_client_for_model_selector(selector: str, required_capability: str)`
3. `resolve_model_selector(selector: str, required_capability: str)`
4. `get_client()` remains OpenAI alias for legacy/service roles.

Tests/mocks must be updated so old tests can keep using `get_client()` while new provider-aware tests can assert provider routing.

### Per-call Text Model Resolution

Not every text call is guaranteed to use the same provider as the main run.

Rules:

1. Main block processing uses `context.model_selector` resolved into `context.model_provider` + `context.model_id`.
2. `translation_second_pass_model = ""` is a sentinel meaning `reuse main text selector`; it must not be passed into `resolve_model_selector(...)`.
3. `translation_second_pass_model` is resolved independently only when it is a non-empty string after trimming.
4. `audiobook_model` is resolved independently for standalone audiobook and audiobook postprocess; if absent, it reuses the main resolved selector/client/model id.
5. Each independent selector must call `get_client_for_model_selector(..., required_capability="responses_text")`.
6. Logs for second-pass and audiobook chunks must include selector/provider/model_id for that specific call, not only the main run model.

### Image And Service Client Separation

Phase 1 images stay on OpenAI even when text model is OpenRouter.

Required rules:

1. Image analysis, validation, reconstruction, generation, edit and generation-vision roles always resolve through OpenAI-capable clients in phase 1.
2. Image late phases must not receive `text_client` implicitly.
3. If image mode requires a model role and `providers.openai.enabled = false`, config validation or processing init must fail with an explicit OpenAI service-role error.
4. Structure recognition and paragraph-boundary AI review remain OpenAI service roles in phase 1. If enabled, they require OpenAI provider availability even when user text selector is OpenRouter.
5. OpenRouter-only text usage without `OPENAI_API_KEY` is supported only when all OpenAI service/image roles that need runtime clients are disabled for that run.

## Text Surface Coverage

### Phase 1 must cover

В первой фазе provider-aware resolution должна работать для всех user-facing text transform paths:

1. основной `edit` path;
2. основной `translate` path;
3. standalone `audiobook` path;
4. `audiobook_postprocess_enabled` path;
5. `translation_second_pass_model` override;
6. validation run profiles, где используется поле `model`.

### Audiobook model ownership

`models.audiobook.default` currently is not part of `ModelRegistry`; it is resolved separately into `AppConfig.audiobook_model`.

Phase 1 decision:

1. Do not add `audiobook` to `ModelRegistry` in this MVP.
2. Keep `models.audiobook.default` parsed by text runtime config as today.
3. Validate `audiobook_model` with `responses_text` capability using the same selector parser.
4. Reconsider first-class `models.audiobook` registry role only in a later registry refactor.

### Why these paths belong together

Это один и тот же text pipeline surface, и пользователь ожидает, что selected text model будет последовательно работать во всех его режимах.

### Phase 1 does not have to cover

Следующие AI paths не должны автоматически переключаться на OpenRouter в первой фазе:

1. `models.structure_recognition.default`
2. paragraph-boundary AI review
3. service-level multimodal image analysis/validation

Причина: они технически ближе к internal service roles и расширяют blast radius без необходимости для первой production integration.

### Phase 2 extension

После успешной первой фазы можно отдельно рассмотреть расширение provider-aware resolution на text-only service roles:

1. structure recognition
2. paragraph-boundary AI review

Но только после отдельной validation matrix и без автоматического изменения defaults.

## Config Validation Rules

### Parsing rules

`load_app_config()` должен валидировать:

1. корректный синтаксис selector string;
2. известность provider id;
3. соответствие роли требуемой capability;
4. отсутствие пустых selector values;
5. отсутствие duplicate values в `models.text.options` после normalization;
6. disabled provider usage in any configured selector;
7. OpenAI service-role availability when enabled runtime sections require OpenAI-only capabilities.

### Normalization rules

1. `gpt-5.4-mini` и `openai:gpt-5.4-mini` считаются эквивалентными canonical target values;
2. canonical stored form для resolved selector всегда `openai:gpt-5.4-mini`;
3. UI options dedupe должны работать после provider normalization, чтобы избежать скрытых дублей;
4. если `models.text.options = ["gpt-5.4-mini", "openai:gpt-5.4-mini"]`, config load должен падать как duplicate normalized selector;
5. если `models.text.default = "gpt-5.4-mini"`, а options содержит только `"openai:gpt-5.4-mini"`, default считается present после normalization и не должен auto-insert duplicate raw value;
6. `TextModelConfig.default` и `TextModelConfig.options` могут сохранить raw configured values for UI compatibility, но `model_registry_resolved` обязан дополнительно логировать normalized/canonical values.

### Failure examples

Примеры обязательных явных ошибок:

1. `Некорректный селектор модели: expected '<provider>:<model>' or bare OpenAI model.`
2. `Неизвестный provider 'foo' в models.text.default.`
3. `Provider 'openrouter' не поддерживает image role 'models.image_generation.default'.`
4. `Для модели 'openrouter:google/gemini-3.1-flash-lite-preview' не найден OPENROUTER_API_KEY.`
5. `Provider 'openai' отключён, но selector 'gpt-5.4-mini' требует OpenAI.`
6. `OpenAI service role 'structure_recognition' включён, но provider openai недоступен.`

### Error catalog

Phase 1 implementation should keep one explicit error catalog for provider-aware configuration and runtime initialization.

| Condition | Error class/category | Required message shape |
| --- | --- | --- |
| Empty selector for required role | config_validation_error | `Некорректный селектор модели: ожидается непустая строка.` |
| Invalid selector syntax | config_validation_error | `Некорректный селектор модели: expected '<provider>:<model>' or bare OpenAI model.` |
| Unknown provider id | config_validation_error | `Неизвестный provider '<id>' в <config_path>.` |
| Disabled provider used by selector | config_validation_error | `Provider '<provider>' отключён, но selector '<selector>' требует его использования.` |
| Missing provider capability for role | config_validation_error | `Provider '<provider>' не поддерживает role '<role>' / capability '<capability>'.` |
| Duplicate normalized text option | config_validation_error | `models.text.options содержит duplicate normalized selectors.` |
| Missing OpenRouter API key at actual use | provider_credentials_error | `Для модели '<selector>' не найден <ENV_NAME>.` |
| Obviously invalid OpenRouter key shape | provider_credentials_error | `Некорректный формат OPENROUTER_API_KEY.` |
| OpenAI service role required but unavailable | provider_availability_error | `OpenAI service role '<role>' включён, но provider openai недоступен.` |
| OpenRouter Responses incompatibility with no fallback path | provider_compatibility_error | `Provider '<provider>' не поддерживает required text API surface для selector '<selector>'.` |
| OpenRouter Responses incompatibility with fallback failure | provider_compatibility_error | `Не удалось выполнить text request через Responses API и Chat Completions fallback для selector '<selector>'.` |
| Rate limit exhausted after retries | provider_runtime_error | `Provider '<provider>' временно недоступен из-за rate limit; retries exhausted.` |
| Unauthorized provider call with present key | provider_runtime_error | `Provider '<provider>' отклонил аутентификацию для selector '<selector>'.` |

The exact Python exception hierarchy may remain implementation-defined, but message taxonomy and log context must follow this table.

### API key format validation

Key validation should stay lightweight and local.

Rules:

1. `OPENROUTER_API_KEY` format check is optional-but-recommended early validation, not a network preflight.
2. If a non-empty OpenRouter key does not match the currently documented OpenRouter key prefix/shape, runtime may fail early with `Некорректный формат OPENROUTER_API_KEY.`
3. Format validation must be conservative: it may reject obviously wrong values, but should not reject unknown future valid formats aggressively.
4. A value equal to the current `OPENAI_API_KEY` or clearly shaped like an OpenAI-only key may be flagged as suspicious in UI warning text even if hard rejection is not applied.

## UI Contract Changes

### Sidebar behavior

Sidebar в `src/docxaicorrector/ui/_ui.py` не должен менять общий UX pattern, но должен стать provider-aware.

### Required UI changes

1. `models.text.options` продолжают быть source of truth.
2. UI должен отображать selector value не как внутренний raw prefix, а как user-readable label.
3. Для `custom` input нужно явно поддержать ввод `openrouter:<model_id>`.
4. Если выбран provider с отсутствующим credential, UI должен выдавать понятное предупреждение до запуска run или при старте run.
5. Warning должен использовать pure credential availability helper, а не client construction.
6. Если OpenRouter provider disabled, UI должен отличать disabled provider от missing API key.

### Recommended display format

Внутреннее значение:

```text
openrouter:google/gemini-3.1-flash-lite-preview
```

Пользовательская подпись:

```text
google/gemini-3.1-flash-lite-preview (OpenRouter)
```

### Why labels matter

Без этого user-facing dropdown быстро станет непонятным и будет смешивать provider transport с model identity.

## Logging And Observability

### Required log enrichment

Новые provider-aware ветки должны расширить существующие runtime events, а не плодить дублирующие event families.

Минимальный набор изменений:

1. `model_registry_resolved` должен логировать provider-aware resolved values для text defaults/options.
2. `processing_started` должен включать:
    - `model_selector`
    - `canonical_model_selector`
    - `model_provider`
    - `model_id`
3. `processing_init_failed` при provider/credential ошибках должен включать provider context.

### New events allowed if needed

Если существующих events недостаточно, допустимы следующие новые имена:

1. `provider_client_resolved`
2. `provider_client_resolution_failed`
3. `model_selector_validation_failed`

Но только если контекст нельзя аккуратно встроить в существующие события.

### Logging rules

1. Никогда не логировать API keys.
2. Не логировать полный request body.
3. Для provider ошибок логировать только provider name, env variable name, model selector и class/message ошибки.

## Provider Runtime Behavior

### Rate-limit and transient failure handling

Production OpenRouter behavior should align with the existing retry semantics already used for transient OpenAI-compatible failures.

Rules:

1. HTTP `408`, `409`, `429` and `5xx` from OpenRouter are treated as transient retryable provider errors, consistent with the existing `is_retryable_error(...)` contract.
2. Phase 1 should reuse the current bounded exponential backoff pattern instead of introducing a second retry policy for OpenRouter.
3. When retries are exhausted, user-visible error text must explicitly mention provider temporary unavailability or rate limit exhaustion rather than generic unknown failure.
4. Rate-limit handling must remain provider-agnostic at the retry policy level, but logs should include provider context.
5. If future OpenRouter-specific headers expose reset timing, they may be logged as numeric metadata only; phase 1 does not require a provider-specific scheduler.

### Header policy

Phase 1 should not block implementation on a separate header verification task.

Rules:

1. Use `HTTP-Referer` and `X-OpenRouter-Title` as canonical OpenRouter headers in phase 1.
2. Do not make header name runtime-configurable in this MVP.
3. If targeted verification later shows that an alternate title header is required for ranking/analytics, that should be treated as a follow-up compatibility patch, not a blocker for the provider integration plumbing.

## Backward Compatibility Contract

### Existing OpenAI-only setups

Текущие пользователи с конфигом вида:

```toml
[models.text]
default = "gpt-5.4-mini"
options = ["gpt-5.4", "gpt-5.4-mini", "gpt-5-mini"]
```

не должны увидеть никаких behavioural regressions.

### Compatibility rules

1. Bare model strings продолжают работать как implicit OpenAI selectors.
2. `OPENAI_API_KEY` остаётся достаточным для текущего baseline.
3. `get_client()` остаётся совместимым для existing OpenAI call sites.
4. Если OpenRouter не используется, startup, runtime и tests должны вести себя как раньше.
5. Если OpenAI provider явно disabled, это intentional config change и backward compatibility не применяется к этому конкретному config.

## Benchmark Evidence And Promotion Boundary

### Source of benchmark evidence

This integration spec must not rely on stale benchmark assumptions when current benchmark artifacts and current article show newer evidence.

Current documented benchmark evidence in the repo indicates:

1. `google/gemini-3-flash-preview` is the current quality leader in `docs/articles/translation-model-comparative-analysis-2026-05-05.md`.
2. `google/gemini-3.1-flash-lite-preview` remains the best price/quality candidate in the same article.
3. The benchmark corpus evolved beyond the earlier MVP-only assumption that only `mazzucato-audiobook-core` was suitable.
4. `corpus_registry.toml` now contains benchmark-only profile `lietaer-pdf-first-20-benchmark` for the English-source PDF slice used in the updated benchmark/article.

### Promotion boundary

Phase 1 integration does not decide the default production model.

Rules:

1. Adding OpenRouter support does not automatically add any new model into `config.toml` defaults or `models.text.options`.
2. Promotion of any benchmark candidate into canonical UI options or defaults must happen in a separate policy change or PR after integration verification.
3. That follow-up change must cite the current benchmark article and identify whether it optimizes for best quality (`Gemini 3 Flash`) or best price/quality (`Gemini 3.1 Flash Lite`).
4. Until that follow-up change lands, developers may still test OpenRouter models via manual config/env edits or custom UI input using provider-qualified selectors.

### Bridge from benchmark to production model list

The bridge is intentionally manual in phase 1.

Required process:

1. Benchmark project discovers candidate models and writes evidence artifacts.
2. Article or benchmark summary records the decision-oriented interpretation.
3. Integration PR adds provider plumbing only; it may mention candidate models in docs/tests, but must not silently promote them into production defaults.
4. A separate model-policy PR may then add selected provider-qualified models to `config.toml`, `.env.example`, `README.md`, and UI expectations.
5. That separate PR must explicitly state whether the addition is `quality-first`, `price-quality-first`, or `experimental-option-only`.

## Rollout Plan

### Phase 0. Spec only

Подготовить и утвердить эту спецификацию.

### Phase 1. Provider-aware text runtime

Изменения:

1. добавить provider config parsing;
2. добавить selector parsing;
3. добавить provider-aware client factory;
4. разделить text client и OpenAI service/image client в pipeline contracts;
5. подключить provider-aware resolution к основному text pipeline, audiobook path, second-pass path и validation run-profile text model;
6. обновить UI labels и validation errors;
7. оставить OpenAI text default без изменения.

Результат:

1. пользователь может вручную выбрать OpenRouter text model;
2. production OpenAI default остаётся прежним;
3. image pipeline не затрагивается.

### Phase 2. Optional service-level text roles

Отдельно, после проверки phase 1:

1. оценить перенос `structure_recognition` на provider-aware resolution;
2. оценить перенос paragraph-boundary AI review;
3. расширить capability matrix при наличии доказанной совместимости.

### Phase 3. Default promotion

Только после phase 1 и targeted production validation:

1. вынести отдельное решение о переключении `models.text.default` на Gemini или другой OpenRouter candidate;
2. обновить `config.toml`, `.env.example`, `README.md`, archived/current model-role docs, UI expectations и тесты;
3. провести отдельную verification кампанию уже как model policy change, а не как provider plumbing change.

## Required Tests

### Unit / config tests

Нужно добавить тесты на:

1. parsing bare OpenAI selector;
2. parsing qualified OpenRouter selector;
3. invalid provider rejection;
4. invalid selector syntax rejection;
5. image role rejection for OpenRouter selectors;
6. backward compatibility of existing `models.text.default` and `models.text.options`.

### Client factory tests

Нужно добавить тесты на:

1. `get_provider_client("openai")` читает `OPENAI_API_KEY`;
2. `get_provider_client("openrouter")` читает `OPENROUTER_API_KEY`, `base_url` и headers;
3. provider clients кешируются независимо;
4. missing OpenRouter key не ломает startup и app config load;
5. ошибка возникает только при фактическом использовании OpenRouter provider;
6. `get_client()` остаётся OpenAI alias и уважает explicit `providers.openai.enabled = false`;
7. UI credential availability helper не импортирует SDK и не создаёт client.

### Pipeline tests

Нужно добавить тесты на:

1. основной processing run использует provider-aware resolved client;
2. `translation_second_pass_model` может быть qualified selector;
3. audiobook postprocess fallback использует base text selector/provider;
4. validation run profiles принимают qualified text selector;
5. `processing_started` и related events содержат provider-aware context;
6. image late phases получают OpenAI/service client, даже если main text selector OpenRouter;
7. second-pass selector может использовать provider, отличный от main selector;
8. audiobook postprocess selector может использовать provider, отличный от main selector;
9. enabled structure recognition / paragraph-boundary AI review produce explicit OpenAI availability error when OpenAI provider is disabled or key is absent.

### UI tests

Нужно добавить тесты на:

1. default selection в sidebar для qualified selector;
2. user-readable label rendering;
3. `custom` input для `openrouter:<model_id>`;
4. понятное сообщение при missing provider credentials.

### Non-regression tests

Обязательные не-regression проверки:

1. existing OpenAI-only config tests остаются зелёными;
2. startup singleton tests для `get_client()` остаются зелёными;
3. image pipeline tests не требуют OpenRouter и не меняют текущий baseline.

## Verification Plan

После реализации phase 1 минимальный verification scope должен включать:

```bash
bash scripts/test.sh tests/test_config.py -q
bash scripts/test.sh tests/test_document_pipeline.py -q
bash scripts/test.sh tests/test_app.py -q
```

Дополнительно нужны targeted tests для нового provider-aware config/client слоя.

Перед финальной верификацией нужно выполнить `git status --porcelain` и явно отметить, что dirty worktree не является CI-parity proof.

Provider-aware targeted tests должны включать:

```bash
bash scripts/test.sh tests/test_config.py -q
bash scripts/test.sh tests/test_document_pipeline.py -q
bash scripts/test.sh tests/test_ui.py -q
```

Если будут добавлены отдельные файлы `tests/test_provider_config.py` или `tests/test_provider_clients.py`, они должны запускаться через тот же canonical `bash scripts/test.sh ...` entrypoint.

Pre-implementation alignment checks:

1. Treat `docs/articles/translation-model-comparative-analysis-2026-05-05.md` as the current human-readable benchmark conclusion.
2. Treat `corpus_registry.toml` benchmark-only profile `lietaer-pdf-first-20-benchmark` as the current repo evidence for the updated Lietaer benchmark path.
3. Do not treat older benchmark-spec examples mentioning `lietaer-core` as current evidence for production model policy.

Для UI-пути нужна browser verification:

1. приложение стартует без OpenRouter key при OpenAI-only config;
2. sidebar корректно отображает OpenRouter option;
3. при выборе OpenRouter model и наличии `OPENROUTER_API_KEY` запускается успешный text processing run;
4. при выборе OpenRouter model без ключа пользователь получает явную provider-specific ошибку;
5. при выборе OpenRouter text model и image mode requiring image processing image phases остаются на OpenAI client или дают явную OpenAI service-role ошибку, если OpenAI недоступен;
6. targeted OpenRouter run подтверждает compatibility именно через `responses.create`, а не через альтернативный `chat.completions` debug path.

## Documentation Sync Requirements

Если спецификация реализуется, в одном change-set должны быть синхронизированы:

1. `config.toml`
2. `.env.example`
3. `README.md`
4. `src/docxaicorrector/core/config.py`
5. `src/docxaicorrector/core/config_model_registry.py`
6. UI code, использующий `models.text.options` и `models.text.default`
7. relevant tests
8. актуальная canonical doc по model-role policy

Поскольку текущий `MODEL_ROLE_AND_CONFIGURATION_SPEC_2026-04-18.md` находится в `docs/archive/specs/`, при реализации нужно либо:

1. создать новый canonical spec для provider-aware model policy в `docs/specs/`, либо
2. обновить `README.md` так, чтобы archived document больше не выглядел как active source of truth по provider contract.

## Risks

### 1. Hidden provider drift

Если provider information будет храниться partly в model string, partly в client factory hacks, а partly в UI labels, проект быстро снова придёт к configuration drift.

Митигировать через один canonical selector parser и один provider config loader.

### 2. Silent capability mismatch

Если OpenRouter selectors разрешить для image roles, возможны runtime failures в глубине pipeline.

Митигировать через capability validation на этапе config load.

### 3. Startup regression

Если OpenRouter availability check будет добавлен в `load_app_config()` или ранний UI startup, проект нарушит startup contract.

Митигировать через lazy provider client initialization и no-network config parsing.

### 4. Test surface undercoverage

Если изменить только `get_client()` и sidebar, но не покрыть audiobook, second-pass и validation profiles, provider support будет неполной и сломается в непрямых режимах.

Митигировать через явный phase-1 scope для всей user-facing text surface.

### 5. Accidental image-provider regression

Если initialization продолжит передавать один `client` во все late phases, OpenRouter text selection может сломать image analysis/generation/edit.

Митигировать через explicit split `text_client` / `openai_client` в processing initialization и тест, который доказывает, что image phases не используют OpenRouter client.

### 6. Responses API dialect mismatch

OpenRouter поддерживает `/responses`, но фактическая совместимость параметров и response shape может отличаться по модели.

Митигировать через узкий adapter boundary и targeted verification `responses.create` для выбранной OpenRouter модели перед production promotion.

## Acceptance Criteria

Спецификация считается реализованной только если все условия ниже одновременно выполнены.

1. Основной pipeline принимает OpenRouter text selectors без ручного патчинга runtime modules.
2. OpenAI-only baseline остаётся полностью рабочим и backward-compatible.
3. OpenRouter key и provider settings резолвятся lazily, без startup network work.
4. `models.text.default`, `models.text.options`, `models.audiobook.default`, `translation_second_pass_model` и validation run-profile `model` поддерживают provider-qualified selectors.
5. Image roles не принимают OpenRouter selectors в phase 1.
6. Image runtime не получает OpenRouter client из-за выбора OpenRouter text selector.
7. `processing_started` и related provider errors логируются с явным provider/model context.
8. README, `.env.example`, config loader и тесты синхронизированы.
9. Phase-1 OpenRouter integration подтверждена через `responses.create` или spec явно фиксирует adapter/fallback решение перед merge.
10. После реализации всё ещё не происходит автоматическое переключение production default на Gemini без отдельного approval.

## Recommendation

Рекомендуемый следующий шаг после утверждения этой спецификации:

1. реализовать phase 1 provider-aware text runtime;
2. сохранить `gpt-5.4-mini` или другой текущий OpenAI default до отдельного production validation;
3. только после этого принимать отдельное решение о переводе `models.text.default` на `openrouter:google/gemini-3.1-flash-lite-preview`.

Это минимальный безопасный путь, который даёт проекту OpenRouter support без скрытого изменения production behavior и без риска сломать текущий image/OpenAI contract.
