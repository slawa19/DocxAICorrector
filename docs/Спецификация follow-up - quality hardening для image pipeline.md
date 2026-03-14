# Спецификация v3: Quality Hardening для Image Pipeline (Архитектура 2026)

> Статус: archived follow-up spec. Документ сохранён как historical spike/follow-up и не является текущим source of truth по image modes. Для актуального контракта используйте `docs/WORKFLOW_AND_IMAGE_MODES.md`.

## 0. Назначение документа
Этот документ описывает модернизацию пайплайна перерисовки изображений с учетом перехода OpenAI на нативную мультимодальную генерацию (модель `gpt-image-1` на базе архитектуры GPT-4o). 

Исторические ограничения (отсутствие прозрачности для `edit`, неспособность DALL-E 3 рендерить текст) больше не являются непреодолимым препятствием, однако требуют изменения API-сигнатур и обновления стратегий.

---

## 1. Scope этапа модернизации
1. Перевод генерации с `dall-e-3` на `gpt-image-1`.
2. Внедрение **Smart Routing (Умный Bypass)** для защиты от перерасхода API на сверхплотных таблицах.
3. Отказ от костылей с `images.edit` (DALL-E 2) и переход на чистый `images.generate` с новым промптингом.
4. Оптимизация промптов под новую типографическую точность модели.

---

## 2. Архитектурные изменения (2026 Standards)

### 2.1. Переход на модель gpt-image-1
**Почему:** DALL-E 3 является "слепой" к точному тексту моделью. `gpt-image-1` — это нативная часть GPT-4o, которая идеально понимает типографику, удерживает десятки текстовых узлов и поддерживает кириллицу.
**Реализация:**
Вместо попыток использовать `images.edit` или DALL-E 3, пайплайн `semantic_redraw_structured` теперь использует `gpt-image-1`.

```python
# Пример целевого вызова для image_generation.py
response = client.images.generate(
    model="gpt-image-1", 
    prompt=final_prompt, # Промпт теперь может содержать огромные блоки текста
    size="1024x1024",
    response_format="b64_json"
)
```

### 2.2. Smart Routing 2.0 (Умный Bypass)
Хотя `gpt-image-1` отлично пишет текст, у него есть лимит внимания. Если на картинке более 30 текстовых узлов или это сплошной текст (документ), генерация нецелесообразна.

**Решение:** На этапе `analyze_image` (Vision) добавляется классификатор:
*   `diagram` (до 20-25 узлов) -> отправляется в `gpt-image-1` (модель справится).
*   `dense_document_or_table` -> активирует Bypass (сохранение оригинала).

---

## 3. Практические промпты (Best Practices для gpt-image-1)

Новая модель требует другого подхода к промптам. Если DALL-E 3 нужно было уговаривать "нарисовать схему", то `gpt-image-1` нужно давать жесткую разметку.

### 3.1. Промпт для Vision (Извлечение структуры для gpt-image-1)
Используется в `gpt-4.1` или `gpt-4o` для подготовки данных:

```text
Ты — эксперт по анализу данных. Конвертируй приложенную инфографику в структурированное описание для нативной генерации.
Правила:
1. Выпиши АБСОЛЮТНО ВЕСЬ текст (на оригинальном языке).
2. Используй формат Markdown для описания связей:
   [Узел А: "Текст"] --> (Стрелка) --> [Узел Б: "Текст"]
3. Опиши общую композицию (фон, цвета узлов).
```

### 3.2. Промпт для Генерации (Ввод для gpt-image-1)
Модель `gpt-image-1` отлично понимает прямое цитирование:

```text
Нарисуй профессиональную векторную инфографику (flat design, corporate style, white background).
СТРОГО используй следующую структуру и ДОСЛОВНО размести указанный текст на узлах:

<Сюда вставляется результат из шага 3.1>

ВНИМАНИЕ: Рендеринг текста должен быть идеально четким, типографически верным, без орфографических ошибок.
```

---

## 4. План миграции кода

1. **Обновление SDK:** Убедиться, что на сервере установлен свежий пакет `openai` (версии конца 2025/начала 2026), поддерживающий вызов `gpt-image-1`.
2. **Рефакторинг `image_generation.py`:** Заменить вызовы `images.edit` и `dall-e-3` на единую функцию `generate_via_gpt_image_1()`.
3. **Тестирование кириллицы:** Прогнать тестовый набор украинских/русских схем (включая проблемную "Факты vs Манипуляции"), чтобы откалибровать порог срабатывания Bypass-маршрутизатора. (Вполне вероятно, что `gpt-image-1` сможет отрисовать даже её).



# --- ПРИМЕР 1: Внедрение Smart Routing в image_analysis.py ---
# Этот код определяет, можно ли вообще перерисовывать картинку.

import json
from openai import OpenAI
from models import ImageAnalysisResult # Из твоей архитектуры

def analyze_image(image_bytes: bytes, model: str, mime_type: str) -> ImageAnalysisResult:
    """
    Анализирует изображение с помощью Vision-модели (gpt-4o) и решает,
    направлять ли его на перерисовку (dall-e-3 / gpt-image-1) или оставить оригинал (bypass).
    """
    client = OpenAI()
    
    # Системный промпт-классификатор (взят из лучших практик RAG-пайплайнов)
    SYSTEM_PROMPT = """
    Ты — эксперт по анализу документов. Оцени приложенное изображение.
    Определи, сможет ли генеративная модель перерисовать его, сохранив ВЕСЬ текст без искажений.
    
    ПРАВИЛО ОТБРАКОВКИ (BYPASS):
    Если на картинке больше 15 текстовых узлов, либо это сложная инфографика с метафорами 
    (клубок ниток, дерево), либо плотная таблица — модель с этим НЕ справится.
    
    Ответь строго в JSON формате:
    {
      "image_type": "diagram" | "photo" | "table" | "dense_infographic",
      "text_node_count": <int>,
      "semantic_redraw_allowed": <bool>,
      "recommended_route": "gpt-image-1" | "bypass",
      "extracted_text": "<ВЕСЬ текст с картинки для передачи в генератор>"
    }
    """
    
    # Формируем Data URI
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    data_uri = f"data:{mime_type};base64,{base64_image}"

    response = client.chat.completions.create(
        model="gpt-4o", # Актуальная Vision-модель
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Оцени эту картинку для перерисовки."},
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ]
            }
        ]
    )
    
    result = json.loads(response.choices[0].message.content)
    
    # Возвращаем твой объект ImageAnalysisResult (расширенный)
    return ImageAnalysisResult(
        image_type=result["image_type"],
        contains_text=result["text_node_count"] > 0,
        semantic_redraw_allowed=result["semantic_redraw_allowed"],
        extracted_text=result.get("extracted_text", ""),
        render_strategy=result["recommended_route"] # Важный флаг для роутера!
    )


# --- ПРИМЕР 2: Генерация в image_generation.py ---
# Отказ от images.edit. Переход на прямую генерацию с переносом структуры.

def generate_image_candidate(original_bytes: bytes, analysis: ImageAnalysisResult, mode: str) -> bytes:
    """
    Генерирует новую версию картинки.
    Если routing сказал "bypass" (или mode == 'safe'), возвращаем оригинал (или просто улучшаем резкость).
    """
    if analysis.render_strategy == "bypass" or mode == "safe":
        # Логируем, что картинка слишком сложная для перерисовки
        # В твоем коде здесь может быть логика safe-mode (OpenCV/Pillow)
        return original_bytes 

    client = OpenAI()

    # Формируем жесткий промпт с подстановкой текста, который извлек Vision
    # Это решает проблему потери подписей на украинском/русском языках
    GENERATION_PROMPT = f"""
    Нарисуй профессиональную векторную диаграмму (flat design, corporate style, white background).
    
    СТРОГOE ПРАВИЛО:
    Размести на диаграмме следующий текст ДОСЛОВНО. Не переводи и не сокращай.
    
    [ТЕКСТ ДЛЯ РАЗМЕЩЕНИЯ]:
    {analysis.extracted_text}
    
    Сделай структуру аккуратной, используй приятную цветовую палитру (синий, зеленый, серый).
    """

    # Вызов актуального эндпоинта генерации
    # Если gpt-image-1 недоступен в твоем tier, здесь будет dall-e-3
    response = client.images.generate(
        model="gpt-image-1", # Или "dall-e-3"
        prompt=GENERATION_PROMPT,
        size="1024x1024",
        quality="hd",
        response_format="b64_json"
    )

    image_b64 = response.data[0].b64_json
    return base64.b64decode(image_b64)


# --- ПРИМЕР 3: Обработка сложных графов (Опционально: Mermaid.js Fallback) ---
# Если тебе кровь из носу нужно перерисовать "Клубок ниток" в читаемый вид

def extract_complex_diagram_to_mermaid(image_bytes: bytes, mime_type: str) -> str:
    """
    Используется, когда картинка определена как "dense_infographic", 
    но бизнес-требование обязывает её стандартизировать.
    """
    client = OpenAI()
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    PROMPT = """
    Переведи эту сложную инфографику в код Mermaid.js (flowchart TD).
    Сохрани ВСЕ текстовые узлы дословно на оригинальном языке. 
    Используй стилизацию (classDef), чтобы передать цвета узлов (например, зеленый/красный).
    Верни ТОЛЬКО валидный код Mermaid, без маркдаун-оберток.
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": PROMPT},
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}}]
            }
        ]
    )
    
    return response.choices[0].message.content.strip()


Как это ложится на твою архитектуру (из коммитов):
У тебя в app.py и image_validation.py уже заложен отличный логгер (log_event, push_activity). Новый JSON-ответ от Vision (из Примера 1) идеально впишется туда: ты сможешь прямо в UI Streamlit показывать пользователю сообщение: "Изображение 3: Пропущено (слишком высокая плотность текста — 25 узлов)".
В models.py тебе нужно будет лишь добавить поле extracted_text: str и render_strategy: str в датакласс ImageAnalysisResult.
Больше никаких падений API из-за отсутствия альфа-канала у JPEG-файлов, так как client.images.generate принимает только текст, а всю работу с картинкой берет на себя безопасный client.chat.completions (Vision).

---

## 5. Минимальный Spike, внедренный в кодовую базу

Чтобы быстро проверить гипотезу без разрушения текущей архитектуры, в коде закрепляется минимальный совместимый spike:

1. `semantic_redraw_structured` переключается c `dall-e-3` на `gpt-image-1`, но сохраняет текущую схему `responses.create` -> `images.generate`.
2. `ImageAnalysisResult` расширяется только опциональными полями `text_node_count` и `extracted_text`, без ломки существующих вызовов.
3. Vision payload начинает понимать `recommended_route="bypass"`, но внутри текущего приложения это нормализуется в существующий `safe_mode`, а не в новый отдельный enum.
4. Prompt builder для semantic redraw может подставлять `extracted_text` дословно, если Vision его вернул.

Это решение выбрано как минимально рискованное: мы проверяем именно идею `gpt-image-1 + smart routing`, а не переписываем весь image pipeline вокруг новой схемы за один шаг.

## 6. Рекомендации по тестированию Spike

### 6.1. Быстрая локальная проверка

Основной быстрый контур проверки должен запускаться в WSL `.venv`. Для штатных single-file и single-node сценариев приоритетны wrappers/tasks, а для такого multi-file subset допустим низкоуровневый WSL fallback:

```bash
bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests/test_spec_image_followup.py tests/test_image_analysis.py tests/test_image_generation.py tests/test_real_image_pipeline.py -q'
```

Что подтверждает этот запуск:

1. Новый документ согласован с тестируемой спецификацией.
2. `analyze_image()` умеет принимать vision payload с `recommended_route`, `text_node_count`, `extracted_text`.
3. Structured generation действительно использует `gpt-image-1`.
4. Извлеченный текст попадает в generation prompt.
5. Реальные локальные изображения по-прежнему проходят routing и smoke-путь без деградации базовой архитектуры.

### 6.2. Реальный API smoke

После успешного локального контура нужно запускать короткий live smoke только на существующем real-image наборе:

```bash
bash -lc 'cd /mnt/d/www/projects/2025/DocxAICorrector && export DOCX_AI_RUN_LIVE_IMAGE_API_TESTS=1 && . .venv/bin/activate && pytest tests/test_real_image_pipeline.py -q'
```

Минимально рекомендуемые кейсы:

1. diagram-like input;
2. кириллическая схема;
3. кейс `Факты vs Манипуляции`;
4. один заведомо плотный table/document пример, который должен уйти в bypass-equivalent (`safe_mode`).

### 6.3. Что считать успешным результатом spike

Spike считается успешным, если одновременно выполняются все условия:

1. нет регрессии в fast test subset;
2. live smoke не показывает падения structured branch на `gpt-image-1`;
3. кириллические подписи сохраняются заметно лучше, чем в предыдущем structured path;
4. dense-text кейсы не уводят pipeline в лишнюю генерацию и безопасно маршрутизируются в `safe_mode`.

## 7. Будущий рефакторинг, если Spike сработает

Если минимальный spike подтверждает гипотезу, следующий этап должен быть отдельным рефакторингом, а не частью текущей быстрой проверки.

### 7.1. Что выносить в рефакторинг

1. Унифицировать routing-контракт: вместо смешения `render_strategy`, `semantic_redraw_allowed` и model-hint ввести явный enum маршрута уровня pipeline.
2. Разделить модельные поля анализа на две группы: routing metadata и generation metadata.
3. Убрать дублирование между `_build_image_edit_prompt()` и `_build_structured_generate_prompt()` через общий prompt composer.
4. Пересмотреть роль `semantic_redraw_direct`: либо оставить как fallback/legacy branch, либо выделить отдельные условия допуска.
5. При необходимости перевести `analyze_image()` на отдельный vision adapter с versioned schema ответа.

### 7.2. Что не стоит делать в текущем spike

Во время текущего этапа не рекомендуется:

1. полностью переписывать pipeline на `chat.completions.create`, если текущая архитектура уже использует `responses.create`;
2. вводить новый обязательный route enum во всех слоях приложения;
3. удалять direct-branch до получения реальных результатов по качеству и стоимости;
4. внедрять Mermaid fallback как обязательную часть маршрута до завершения базовой проверки `gpt-image-1`.

Итоговая рекомендация: сначала подтвердить, что `gpt-image-1` действительно улучшает кириллицу и dense-text behavior на существующем тестовом наборе, и только потом переходить к большому архитектурному упрощению.
