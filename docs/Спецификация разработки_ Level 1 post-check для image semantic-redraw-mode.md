# Спецификация разработки: Level 1 post-check для `image semantic-redraw-mode`

## 0. Назначение документа

Этот документ переводит продуктовую спецификацию image v1/v2 в **реализуемую разработческую
спецификацию** для первого уровня semantic post-check после `semantic_redraw`.

Документ опирается на:

- текущую архитектуру проекта (`app.py`, `document.py`, `generation.py`, `config.py`, `ui.py`);
- текущую image-спецификацию:
  `/home/runner/work/DocxAICorrector/DocxAICorrector/docs/Спецификация v1_ сохранение и улучшение изображений в DOCX.md`;
- практику проекта: минимальные расширения поверх существующего pipeline, явные fallback-ветки,
  JSON-логирование и pytest-регрессии на ключевые контракты.

Главная цель Level 1 — добавить **обязательный, но легковесный validator** для результата
`semantic_redraw_*`, не вводя на первом этапе тяжелый OCR / graph-extraction pipeline.

---

## 1. Контекст текущей архитектуры

На текущем этапе проект уже декомпозирован по зонам ответственности:

- `app.py` — orchestration и основной run-loop;
- `config.py` — загрузка конфигурации, env-overrides, OpenAI client;
- `document.py` — разбор `.docx`, извлечение текста, сборка смысловых блоков;
- `generation.py` — OpenAI text generation и сборка DOCX через Pandoc;
- `logger.py` — единый способ логирования и user-facing ошибок;
- `state.py` — статус выполнения и run-state в `st.session_state`;
- `ui.py` — sidebar, прогресс, результат, run-log;
- `models.py` — базовые dataclass-модели документа.

Это означает, что реализация image-v2 и post-check **не должна**:

1. возвращать проект к монолитному `app.py`;
2. смешивать image-analysis, image-generation и validator-логику с текстовой генерацией блоков;
3. ломать текущий контракт текстового pipeline:
   `DOCX -> semantic blocks -> OpenAI text editing -> Markdown -> Pandoc -> DOCX`.

Следствие: image-v2 должен встраиваться как **дополнительный orchestration-layer** вокруг
существующего текстового pipeline, а не переписывать его.

---

## 2. Scope разработки

## 2.1. Что входит в реализацию

В рамках этой разработки должны быть подготовлены и реализованы:

1. модели данных для image-analysis и image-validation;
2. конфигурация для включения/выключения post-check и его thresholds;
3. модуль `image_validation.py`;
4. orchestration flow:
   - `analysis -> redraw -> post-check -> accept/fallback`;
5. логирование validator-решений;
6. unit и integration tests на Level 1 post-check;
7. минимальное отражение статуса в UI / run-log.

## 2.2. Что не входит в Level 1

В эту реализацию **не входят**:

- полноценный OCR-конвейер;
- восстановление точного графа стрелок и узлов;
- сравнение SVG/Graphviz/Mermaid-структур на уровне proof-system;
- поддержка всех Word media-объектов beyond inline images;
- обучение своей модели или CV-пайплайна;
- гарантия идеального совпадения всех надписей.

Level 1 — это **production-friendly heuristic guardrail**, а не строгий semantic proof layer.

---

## 3. Целевое место в архитектуре

## 3.1. Новые и расширяемые модули

Рекомендуемая структура для image-v2 и post-check:

```text
app.py
document.py
generation.py
config.py
ui.py
models.py
logger.py
state.py

+ image_analysis.py
+ image_generation.py
+ image_validation.py
+ image_prompts.py   (или prompt-registry секция в config.py)
```

## 3.2. Принцип распределения ответственности

### `document.py`

Отвечает за:

- извлечение текста;
- извлечение inline images и их порядка в body flow;
- подстановку placeholder-ов;
- reinsertion в итоговый DOCX.

Не должен отвечать за:

- выбор image prompt;
- работу validator-а;
- выбор fallback strategy.

### `image_analysis.py`

Отвечает за:

- vision-анализ исходного изображения;
- определение `image_type`, `contains_text`, `structure_summary`;
- выбор `prompt_key`;
- выбор `render_strategy`;
- решение, допустим ли semantic redraw.

### `image_generation.py`

Отвечает за:

- `safe_mode` non-generative enhancement;
- `semantic_redraw_direct`;
- при необходимости `semantic_redraw_structured`;
- возврат candidate-image для validator-а.

### `image_validation.py`

Отвечает за:

- повторный анализ candidate-image;
- rule-based compare с `analysis_before`;
- решение `accept` / `fallback_safe` / `fallback_original`;
- возврат `ImageValidationResult` без фатального exception наружу.

### `app.py`

Отвечает за orchestration:

- reading user mode from UI;
- routing image asset through correct branch;
- применение validator decision;
- сбор финального результата и его логирование.

### `generation.py`

Должен сохранить текущую ответственность только за text-generation и Markdown->DOCX сборку.
Перенос image-v2 логики в `generation.py` допустим только как временный thin adapter, но не как
основная точка расширения.

---

## 4. Разрабатываемые модели данных

## 4.1. Базовая модель `ImageAsset`

В `models.py` должна быть добавлена отдельная модель `ImageAsset` или совместимый dataclass,
который описывает один image-asset в document flow.

Минимальный контракт:

```python
@dataclass
class ImageAsset:
    image_id: str
    placeholder: str
    original_bytes: bytes
    mime_type: str | None
    position_index: int

    mode_requested: str | None = None
    analysis_result: "ImageAnalysisResult | dict | None" = None
    prompt_key: str | None = None
    render_strategy: str | None = None

    safe_bytes: bytes | None = None
    redrawn_bytes: bytes | None = None

    validation_result: "ImageValidationResult | dict | None" = None
    validation_status: str = "pending"
    final_decision: str | None = None
    final_variant: str | None = None
    final_reason: str | None = None
```

## 4.2. `ImageAnalysisResult`

Если модель уже введена в продуктовой спецификации, в коде она должна быть формализована как
отдельный dataclass:

```python
@dataclass
class ImageAnalysisResult:
    image_type: str
    image_subtype: str | None
    contains_text: bool
    semantic_redraw_allowed: bool
    confidence: float
    structured_parse_confidence: float
    prompt_key: str
    render_strategy: str
    structure_summary: str
    extracted_labels: list[str]
    fallback_reason: str | None = None
```

## 4.3. `ImageValidationResult`

Обязательный контракт Level 1:

```python
@dataclass
class ImageValidationResult:
    validation_passed: bool
    decision: str  # "accept" | "fallback_safe" | "fallback_original"
    semantic_match_score: float
    text_match_score: float
    structure_match_score: float
    validator_confidence: float
    missing_labels: list[str]
    added_entities_detected: bool
    suspicious_reasons: list[str]
```

## 4.4. Требования к сериализации

Так как проект сейчас не использует БД, модели должны быть:

- удобны для хранения в памяти;
- сериализуемы для логирования;
- безопасны для `st.session_state` и JSON-like log context.

Практически это означает:

1. dataclass preferred;
2. при логировании использовать явное преобразование в `dict`;
3. не хранить в логах сырые большие `bytes`, только metadata.

---

## 5. Изменения конфигурации

## 5.1. Конфигурация в `config.toml`

В `config.toml` должны появиться новые поля:

```toml
image_mode_default = "safe"
enable_post_redraw_validation = true
validation_model = "gpt-4.1"
min_semantic_match_score = 0.75
min_text_match_score = 0.80
min_structure_match_score = 0.70
validator_confidence_threshold = 0.75
allow_accept_with_partial_text_loss = false
prefer_structured_redraw = true
```

Значения приведены как стартовые и могут быть скорректированы.

## 5.2. Env overrides

По аналогии с текущими настройками, `config.py` должен поддержать:

- `DOCX_AI_IMAGE_MODE_DEFAULT`
- `DOCX_AI_ENABLE_POST_REDRAW_VALIDATION`
- `DOCX_AI_VALIDATION_MODEL`
- `DOCX_AI_MIN_SEMANTIC_MATCH_SCORE`
- `DOCX_AI_MIN_TEXT_MATCH_SCORE`
- `DOCX_AI_MIN_STRUCTURE_MATCH_SCORE`
- `DOCX_AI_VALIDATOR_CONFIDENCE_THRESHOLD`
- `DOCX_AI_ALLOW_ACCEPT_WITH_PARTIAL_TEXT_LOSS`

## 5.3. Принципы валидации конфигурации

`config.py` должен:

1. валидировать типы;
2. clamp-ить score thresholds в диапазон `0.0 .. 1.0`;
3. fallback-ить к безопасным default values;
4. выбрасывать `RuntimeError` только при реально некорректной конфигурации.

Для bool-полей рекомендуется добавить helper вида:

```python
def parse_bool_env(name: str, default: bool) -> bool: ...
```

---

## 6. Контракты публичных функций

## 6.1. Анализ изображения

```python
def analyze_image(
    image_bytes: bytes,
    *,
    model: str,
) -> ImageAnalysisResult:
    ...
```

Требования:

- не возвращать `None`;
- при невозможности надежного анализа выставлять низкий `confidence`;
- если redraw нежелателен, заполнять `fallback_reason`.

## 6.2. Генерация изображения

```python
def generate_image_candidate(
    image_bytes: bytes,
    analysis: ImageAnalysisResult,
    *,
    mode: str,
) -> bytes:
    ...
```

Требования:

- вернуть технически валидный image blob;
- не решать самостоятельно final fallback;
- не писать напрямую в DOCX.

## 6.3. Validator

```python
def validate_redraw_result(
    original_image: bytes,
    candidate_image: bytes,
    analysis_before: ImageAnalysisResult,
) -> ImageValidationResult:
    ...
```

Требования:

1. не выбрасывать наружу фатальную ошибку;
2. при внутренней проблеме возвращать консервативный fallback decision;
3. всегда заполнять `suspicious_reasons`;
4. всегда возвращать score-поля в нормализованном диапазоне.

## 6.4. Orchestration helper

Рекомендуемый уровень orchestration в `app.py` или выделенном service-модуле:

```python
def process_image_asset(asset: ImageAsset, *, image_mode: str, config: dict[str, object]) -> ImageAsset:
    ...
```

Функция должна:

1. анализировать изображение;
2. выбирать стратегию;
3. строить candidate result;
4. запускать post-check;
5. принимать final decision;
6. вернуть обновленный `ImageAsset`.

---

## 7. Детальный orchestration flow

## 7.1. High-level pipeline

```text
DOCX
  -> extract text + images + placeholders
  -> build semantic text blocks
  -> process text blocks through existing text pipeline
  -> for each image asset:
       -> analyze_image
       -> choose strategy
       -> generate candidate (safe/direct/structured)
       -> post_redraw_validation
       -> accept/fallback
  -> Markdown -> DOCX
  -> reinsert final image variants by placeholders
  -> result
```

## 7.2. Decision table

### Сценарий A — `safe_mode`

- candidate строится non-generative;
- post-check либо отключен, либо сильно упрощен;
- `final_variant = "safe"` если операция успешна;
- иначе `final_variant = "original"`.

### Сценарий B — `semantic_redraw_direct`

- выполняется image-analysis;
- если `semantic_redraw_allowed = False`, сразу fallback;
- если redraw выполнен успешно, запускается `validate_redraw_result`;
- `accept` -> `final_variant = "redrawn"`;
- `fallback_safe` -> строится/берется safe variant;
- `fallback_original` -> оригинал.

### Сценарий C — `semantic_redraw_structured`

- по умолчанию приоритетнее direct redraw для таблиц, схем и diagram-heavy assets;
- если structured result финально вставляется как изображение, его можно пропускать через
  тот же Level 1 post-check;
- при низкой уверенности structured parse сразу fallback to safe/original.

## 7.3. Консервативное правило

Если хотя бы на одном из этапов:

- анализ неуверен;
- candidate технически битый;
- validator не смог подтвердить базовое соответствие;
- внутренняя ошибка не классифицирована,

система должна предпочитать:

```text
safe_mode -> original
```

а не пытаться сохранить сомнительный redraw.

---

## 8. Level 1 validator logic

## 8.1. Что validator обязан проверять

Минимальный набор:

1. **Тип изображения**
2. **Наличие текста**
3. **Ключевые подписи**
4. **Грубую структуру**
5. **Появление новых сущностей**
6. **Читаемость результата**

## 8.2. Правила оценки

### semantic_match_score

Грубая совокупная оценка на основе:

- type consistency;
- absence of new entities;
- coarse structure match.

### text_match_score

Оценка на основе:

- `contains_text` в исходнике;
- подтверждения хотя бы части `extracted_labels`;
- отсутствия полной потери текста.

### structure_match_score

Оценка на основе текстового `structure_summary`, например:

- таблица не стала “картинкой без структуры”;
- diagram не превратился в abstract illustration;
- list of columns / blocks / nodes не исчез полностью.

## 8.3. Fail conditions

Validator должен вернуть fail, если:

- исчез текст при исходном `contains_text = True`;
- пропали ключевые labels;
- базовый тип изображения изменился;
- появились новые смысловые сущности;
- структура явно упростилась или разрушилась;
- `validator_confidence < validator_confidence_threshold`.

## 8.4. Error policy

При exception внутри validator-а:

1. ошибка логируется;
2. pipeline документа не падает;
3. validator возвращает `fallback_safe` или `fallback_original`;
4. причина попадает в `suspicious_reasons`.

---

## 9. Логирование и audit trail

## 9.1. Общие требования

Проект уже использует `logger.py` как единый канал логирования. Реализация image-v2 обязана
использовать именно этот механизм, а не отдельный ad-hoc logger.

## 9.2. События, которые должны логироваться

Минимальный набор event-ов:

- `image_analysis_started`
- `image_analysis_completed`
- `image_candidate_generated`
- `image_validation_started`
- `image_validation_completed`
- `image_validation_failed`
- `image_fallback_applied`
- `image_reinsertion_failed`

## 9.3. Обязательный log context

Для каждого image-related event:

- `image_id`
- `placeholder`
- `image_mode`
- `image_type`
- `prompt_key`
- `render_strategy`
- `validation_status`
- `final_decision`
- `final_variant`
- `semantic_match_score`
- `text_match_score`
- `structure_match_score`
- `suspicious_reasons`

## 9.4. Что не логировать

Запрещено логировать:

- `original_bytes`, `safe_bytes`, `redrawn_bytes`;
- большие prompt-ы целиком без необходимости;
- любые секреты и API keys.

---

## 10. Изменения UI и state

## 10.1. Sidebar

`ui.render_sidebar()` должен быть расширен выбором:

- `image safe-mode`
- `image semantic-redraw-mode`

Значение по умолчанию берется из config.

## 10.2. User-facing transparency

В status-summary и/или run-log желательно показывать:

- `image_id`
- detected image type
- `render_strategy`
- `validation_status`
- `final_decision`

## 10.3. Session state

В `state.py` нужно добавить место для хранения:

- `image_assets`
- `image_processing_summary`
- `image_validation_failures`

и очищать их в `reset_run_state()`.

---

## 11. План изменений по файлам

## 11.1. `models.py`

Добавить:

- `ImageAsset`
- `ImageAnalysisResult`
- `ImageValidationResult`

## 11.2. `config.py`

Добавить:

- чтение image-v2 полей из `config.toml`;
- env overrides;
- helper для bool/float parsing;
- clamping thresholds.

## 11.3. `document.py`

Добавить:

- извлечение inline images;
- placeholder-based representation;
- reinsertion helper.

Не смешивать сюда validator logic.

## 11.4. `image_analysis.py`

Создать новый модуль с:

- prompt для анализа;
- mapping type -> prompt_key;
- классификацией и result object.

## 11.5. `image_generation.py`

Создать новый модуль с:

- safe enhancement branch;
- structured branch;
- direct redraw branch;
- image technical validity checks.

## 11.6. `image_validation.py`

Создать новый модуль с:

- `validate_redraw_result(...)`;
- internal helper-ами compare rules;
- conservative fallback behavior.

## 11.7. `app.py`

Расширить orchestration:

- получать image mode из UI;
- обрабатывать image assets отдельно от text blocks;
- не прерывать весь документ из-за одного image failure.

## 11.8. `ui.py`

Добавить:

- image mode selector;
- run summary по image processing.

## 11.9. `tests/`

Добавить:

- unit tests для config parsing;
- unit tests для validator compare rules;
- integration tests для full image branch.

---

## 12. Тестовая стратегия

## 12.1. Unit tests

Обязательные кейсы:

1. `ImageValidationResult` собирается корректно;
2. validator принимает корректный redraw;
3. validator детектирует потерю текста;
4. validator детектирует смену image type;
5. validator детектирует added entities;
6. validator уходит в conservative fallback при low confidence;
7. validator не роняет pipeline при exception.

## 12.2. Config tests

Нужно проверить:

- default values;
- env override;
- clamping score thresholds;
- invalid env values -> `RuntimeError`.

## 12.3. Integration tests

Минимальные сценарии:

1. `analysis -> redraw -> validation -> accept`
2. `analysis -> redraw -> validation -> fallback_safe`
3. `analysis -> redraw -> validation -> fallback_original`
4. validator exception не ломает сборку финального `.docx`

## 12.4. Regression rule

Текстовый pipeline не должен деградировать:

- существующие тесты на semantic blocks;
- generation retry;
- config loading;
- state management

должны остаться валидными.

---

## 13. Порядок реализации

## Этап 1 — Data contracts

- модели в `models.py`;
- config поля в `config.py`;
- unit tests на config/model contracts.

## Этап 2 — Document media pipeline

- извлечение изображений;
- placeholder insertion;
- reinsertion helpers;
- tests на порядок и fallback.

## Этап 3 — Analysis and generation

- `image_analysis.py`
- `image_generation.py`
- prompt registry

## Этап 4 — Validation Layer

- `image_validation.py`
- thresholds
- validator logging
- decision routing

## Этап 5 — UI / orchestration

- sidebar image mode;
- run summary;
- final integration.

## Этап 6 — Hardening

- regression tests;
- audit logs;
- conservative fallback tuning.

---

## 14. Критерии готовности

Фича считается готовой к merge, если:

1. для `semantic_redraw_direct` post-check выполняется обязательно;
2. validator влияет на `accept/fallback` decision;
3. fallback не ломает сборку финального документа;
4. validator decision логируется через `logger.py`;
5. конфигурация задается через `config.toml` и env-overrides;
6. хотя бы минимальный image status виден пользователю;
7. unit/integration tests покрывают key success and failure paths.

---

## 15. Риски и способы снижения

## Риск 1. Слишком оптимистичный validator

Может пропускать semantic drift.

Снижение:

- консервативные thresholds;
- default fallback;
- логирование подозрительных кейсов.

## Риск 2. Слишком строгий validator

Может излишне часто отправлять в fallback.

Снижение:

- thresholds вынесены в конфиг;
- анализ false positive через run-log.

## Риск 3. Разрастание `app.py`

Снижение:

- image-v2 logic выносить в отдельные модули;
- `app.py` оставлять orchestration-only.

## Риск 4. Ломается существующий text flow

Снижение:

- не менять contracts `build_semantic_blocks`, `generate_markdown_block`,
  `convert_markdown_to_docx_bytes`;
- держать image pipeline как add-on.

---

## 16. Итоговое решение для команды разработки

Для этого проекта рекомендуемый practical path такой:

1. сохранить текущий текстовый pipeline без изменений;
2. ввести image pipeline через placeholder-based media flow;
3. реализовать `ImageAnalysisResult` и `ImageValidationResult` как явные dataclass contracts;
4. сделать Level 1 validator обязательным для `semantic_redraw_direct`;
5. принять правило: **если validator не уверен — fallback, а не “best effort redraw”**;
6. покрыть это не только продуктовой спецификацией, но и unit/integration tests.

Именно такой вариант лучше всего соответствует:

- текущей архитектуре проекта;
- существующему стилю конфигурации и логирования;
- требованию минимальных, контролируемых изменений;
- best practices для поэтапного внедрения рискованной image-feature.
