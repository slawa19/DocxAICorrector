# IMAGE_PIPELINE_V2_SPEC: Deterministic Image Reconstruction Pipeline

> Статус: archived historical spike/spec. Текущий runtime позже был уточнён: поля `prefer_deterministic_reconstruction`, `reconstruction_model` и `ImageAsset.reconstruction_scene_graph` не являются каноническим текущим runtime-contract репозитория. Для актуального workflow/image-mode контракта используйте `docs/WORKFLOW_AND_IMAGE_MODES.md`.

## Статус: Реализовано (Phase 1)

---

## 1. Проблема

Текущий pipeline `analysis → semantic redraw (gpt-image-1) → validation` систематически порождает **структурные галлюцинации**: вместо точного воспроизведения схем, таблиц и диаграмм DALL-E генерирует случайные абстрактные изображения с искажённой геометрией, потерянным текстом и изменённой структурой.

### 1.1 Точки отказа текущего подхода

| Точка отказа | Причина | Последствие |
|---|---|---|
| **Text-to-image для структурированных данных** | Генеративные модели оптимизированы для «творческой» генерации, а не для точного воспроизведения | Текст искажается, блоки перемещаются, стрелки теряются |
| **Prompt-only управление layout** | Prompt не может детерминированно описать координаты, размеры и стили 50+ элементов | Модель «угадывает» layout, создавая визуальный шум |
| **Отсутствие промежуточного представления** | Нет структурного слоя между анализом и рендерингом | Невозможно верифицировать отдельные элементы |
| **Heuristic-only классификация** | Pixel-level анализ не извлекает семантику | Нет данных о содержимом для детерминированного восстановления |
| **Validation без ground truth** | Post-check сравнивает метаданные анализа, а не реальное содержимое | False accept для визуально некорректных результатов |

### 1.2 Почему semantic redraw через text-to-image системно ненадёжен

Генеративные image-модели (DALL-E 3, gpt-image-1, Midjourney, Stable Diffusion) оптимизированы для **creative generation**: они максимизируют perceptual quality и diversity, а не structural fidelity. Для структурированного контента (таблица 5×7 с конкретными числами, flowchart с 12 блоками) это приводит к:

1. **Hallucination текста**: модель «рисует» символы, которые выглядят как текст, но содержат случайные символы
2. **Layout drift**: блоки смещаются, таблицы теряют строки/столбцы, стрелки указывают в неверных направлениях
3. **Semantic conflation**: модель объединяет несколько элементов в один или разбивает один на несколько
4. **Style imposition**: модель навязывает свой «стиль» вместо воспроизведения оригинального

---

## 2. Решение: Deterministic Reconstruction Pipeline

### 2.1 Архитектурный принцип

**«Не перерисовать по смыслу, а реконструировать layout и содержимое»**

Вместо передачи изображения генеративной модели и надежды на корректный результат:

1. **Извлечь** структурированное представление из изображения (JSON scene graph)
2. **Отрендерить** это представление детерминированно (PIL/SVG)
3. **Верифицировать** результат на каждом этапе

Генеративные модели используются **только на этапе 1** (VLM для computer vision), но **никогда на этапе 2** (рендеринг).

### 2.2 Поток данных

```
┌──────────────┐    ┌───────────────────┐    ┌────────────────────┐    ┌─────────────┐
│ Input Image  │───▶│ VLM Scene Graph   │───▶│ PIL Deterministic  │───▶│ Output PNG  │
│ (bytes)      │    │ Extraction        │    │ Rendering          │    │ (bytes)     │
│              │    │ (gpt-4.1 vision)  │    │ (no AI)            │    │             │
└──────────────┘    └───────────────────┘    └────────────────────┘    └─────────────┘
                           │                        │
                           ▼                        ▼
                    ┌──────────────┐         ┌──────────────┐
                    │ JSON Scene   │         │ Validation   │
                    │ Graph        │         │ (structural) │
                    └──────────────┘         └──────────────┘
```

---

## 3. Компоненты

### 3.1 Классификация (image_analysis.py)

**Без изменений в логике классификации.** Изменён `render_strategy`:

| Image Type | Render Strategy (было) | Render Strategy (стало) |
|---|---|---|
| diagram | `semantic_redraw_structured` | `deterministic_reconstruction` |
| infographic | `semantic_redraw_direct` | `deterministic_reconstruction` |
| photo | `safe_mode` | `safe_mode` (без изменений) |
| mixed/ambiguous | `safe_mode` | `safe_mode` (без изменений) |

### 3.2 Scene Graph Extraction (image_reconstruction.py)

**Технология**: Multimodal VLM (GPT-4.1 с vision)

**Вход**: Image bytes + extraction prompt

**Выход**: JSON scene graph

**Почему VLM, а не classical CV**: Для structured documents (схемы, инфографики) нужно одновременно:
- распознать текст (OCR)
- определить типы примитивов (rect, arrow, table, ...)
- извлечь стили (цвета, шрифты, размеры)
- установить иерархию и связи

VLM делает это в одном вызове, тогда как classical CV pipeline потребовал бы 5-7 специализированных моделей.

**Ключевое отличие от semantic redraw**: VLM используется **только для извлечения структуры** (output = JSON), а не для генерации пикселей. JSON детерминирован и верифицируем.

#### 3.2.1 Scene Graph Schema

```json
{
  "canvas": {
    "width": 800,
    "height": 600,
    "background_color": "#FFFFFF"
  },
  "elements": [
    {
      "id": "e1",
      "type": "rect|rounded_rect|ellipse|circle|diamond|text|line|arrow|table|group|icon_placeholder",
      "x": 100, "y": 50,
      "width": 200, "height": 80,
      "fill": "#E3F2FD",
      "stroke": "#1565C0",
      "stroke_width": 2,
      "corner_radius": 8,
      "z_index": 1,
      "opacity": 1.0,
      "text_content": "Текст элемента",
      "font_size": 14,
      "font_weight": "bold",
      "font_color": "#212121",
      "text_align": "center",
      "children": [],
      "x1": null, "y1": null, "x2": null, "y2": null,
      "marker_end": "arrowhead",
      "cells": [],
      "rows": null, "cols": null
    }
  ]
}
```

#### 3.2.2 Поддерживаемые типы элементов

| Type | Описание | Rendering |
|---|---|---|
| `rect` | Прямоугольник | `ImageDraw.rectangle` |
| `rounded_rect` | Скруглённый прямоугольник | `ImageDraw.rounded_rectangle` |
| `ellipse` | Эллипс | `ImageDraw.ellipse` |
| `circle` | Круг | `ImageDraw.ellipse` |
| `diamond` | Ромб (decision block) | `ImageDraw.polygon` |
| `text` | Свободный текст | `ImageDraw.text` |
| `line` | Линия | `ImageDraw.line` |
| `arrow` | Стрелка с наконечником | `ImageDraw.line` + polygon arrowhead |
| `table` | Таблица с ячейками | Grid rendering + per-cell text |
| `group` | Группа вложенных элементов | Рекурсивный рендеринг |
| `icon_placeholder` | Иконка/изображение (заглушка) | X-box placeholder |

### 3.3 Deterministic Rendering (image_reconstruction.py)

**Технология**: Pillow (PIL) — уже в зависимостях проекта

**Принцип**: Каждый элемент scene graph отрисовывается детерминированно по координатам. Никакой «творческой интерпретации».

**Порядок рендеринга**:
1. Создать RGBA canvas заданного размера с background_color
2. Отсортировать elements по z_index
3. Для каждого элемента вызвать соответствующий renderer
4. Для текста — попытаться использовать DejaVu Sans (системный шрифт), fallback на default
5. Resize до original_size если canvas отличается
6. Сохранить как PNG

**Anti-hallucination**: PIL рисует ровно то, что указано в JSON. Нет stochastic sampling, нет latent space.

### 3.4 Routing (image_generation.py)

```python
if requested_mode == "safe":
    → _generate_safe_candidate (PIL enhancement)
elif analysis.render_strategy == "deterministic_reconstruction":
    → _generate_reconstructed_candidate (VLM + PIL)
    → fallback to _generate_safe_candidate on any error
else:
    → _generate_semantic_candidate (OpenAI Images Edit API)
```

**Fallback cascade**: Если VLM extraction или PIL rendering не удались (API error, invalid JSON, rendering exception), система fallback-ит на safe mode (PIL enhancement), а не на DALL-E.

### 3.5 Validation (image_validation.py)

Существующий Level 1 post-check работает без изменений для reconstructed images. Дополнительная валидация через scene graph:

- **Element count check**: количество элементов в scene graph соответствует видимым элементам
- **Text preservation**: extracted_labels из scene graph сравниваются с OCR-результатом VLM
- **Structural completeness**: проверка наличия canvas, elements, корректных координат

---

## 4. Конфигурация

### 4.1 Новые параметры config.toml

```toml
prefer_deterministic_reconstruction = true   # Предпочитать реконструкцию вместо DALL-E
reconstruction_model = "gpt-4.1"            # Модель для scene graph extraction
```

### 4.2 Переменные окружения

```
DOCX_AI_PREFER_DETERMINISTIC_RECONSTRUCTION=true
DOCX_AI_RECONSTRUCTION_MODEL=gpt-4.1
```

---

## 5. Метрики качества

### 5.1 Структурная точность

| Метрика | Описание | Цель |
|---|---|---|
| Element count match | Совпадение количества элементов | ≥ 90% |
| Text verbatim match | OCR-текст в результате = тексту из scene graph | ≥ 95% |
| Table cell accuracy | Совпадение rows × cols и содержимого ячеек | ≥ 90% |
| Arrow/connector count | Количество стрелок/связей | ≥ 85% |

### 5.2 Визуальная точность

| Метрика | Описание |
|---|---|
| SSIM (Structural Similarity) | Структурное сходство с оригиналом |
| Perceptual hash distance | Хэш-расстояние для быстрого сравнения |
| Layout overlap IoU | Intersection over Union для bounding boxes |

---

## 6. Когда использовать какой подход

| Тип контента | Подход | Обоснование |
|---|---|---|
| Diagrams, flowcharts | **Deterministic reconstruction** | Чёткая структура, набор примитивов |
| Tables | **Deterministic reconstruction** | Grid-структура, текстовые ячейки |
| Charts (bar, pie, line) | **Deterministic reconstruction** | Оси, метки, геометрические формы |
| Infographics | **Deterministic reconstruction** | Комбинация текста, фигур, иконок |
| Mind-maps | **Deterministic reconstruction** | Иерархическая структура |
| Photos | **Safe mode** (PIL enhancement) | Нет структуры для извлечения |
| Screenshots | **Safe mode** (PIL enhancement) | Пиксельная точность важнее |
| Mixed/ambiguous | **Safe mode** (PIL enhancement) | Недостаточно уверенности |

### 6.1 Когда генеративные модели допустимы

Генеративные модели (DALL-E, gpt-image-1) допустимы **только** для:

1. **Декоративных неструктурных элементов**: фоновые паттерны, градиенты, абстрактные украшения
2. **Иконок**: когда `icon_placeholder` недостаточно и нужна стилизованная иконка
3. **Только с верификацией**: результат генерации проверяется structural validation

В текущей реализации DALL-E **полностью выведен из критического пути** для структурированных изображений.

---

## 7. Fallback-сценарии

```
1. VLM extraction успешна + PIL rendering успешен → Accept reconstructed
2. VLM extraction успешна + PIL rendering failed → Fallback to safe mode
3. VLM extraction failed (API error, invalid JSON) → Fallback to safe mode
4. Image type = photo/screenshot/ambiguous → Direct safe mode (no VLM call)
5. Config: prefer_deterministic_reconstruction = false → Legacy semantic redraw pipeline
```

---

## 8. Поэтапный план внедрения

### Phase 1: MVP (Реализовано)
- [x] Scene graph extraction через GPT-4.1 vision
- [x] PIL rendering для 11 типов элементов
- [x] Routing: structured images → reconstruction, photos → safe
- [x] Fallback cascade: reconstruction → safe → original
- [x] Config: `prefer_deterministic_reconstruction`, `reconstruction_model`
- [x] 29 unit/integration тестов

### Phase 2: Enhanced Extraction
- [ ] Улучшенный prompt для лучшей точности координат
- [ ] Retry logic для VLM extraction (как в semantic redraw)
- [ ] Caching scene graph для повторных попыток
- [ ] Font detection и matching
- [ ] Extended element types: polyline, bezier curve, gradient fill

### Phase 3: Verification & Quality
- [ ] Post-render OCR verification: OCR результата → сравнение с scene graph text
- [ ] SSIM/perceptual similarity scoring
- [ ] Layout overlap IoU metrics
- [ ] Confidence scoring на уровне отдельных элементов
- [ ] Human-in-the-loop для low-confidence results

### Phase 4: Advanced Rendering
- [ ] SVG rendering (для масштабируемого вывода)
- [ ] HTML/CSS rendering для таблиц (более точная типографика)
- [ ] PDF rendering backend
- [ ] Multi-page support
- [ ] Template-based rendering для стандартных chart types

### Phase 5: Production Hardening
- [ ] Latency optimization: batch extraction, caching
- [ ] Cost monitoring: VLM API usage tracking
- [ ] A/B testing: reconstruction vs. safe mode quality comparison
- [ ] Logging: scene graph diff tracing
- [ ] Model versioning и reproducibility

---

## 9. Сравнение технологий

### 9.1 VLM для Scene Graph Extraction

| Модель | Качество | Скорость | Стоимость | Рекомендация |
|---|---|---|---|---|
| GPT-4.1 (vision) | Высокое | ~2-5s | $0.01-0.03/image | **Primary choice** |
| GPT-4o | Хорошее | ~1-3s | $0.005-0.015/image | Budget alternative |
| Claude 3.5 Sonnet | Хорошее | ~2-4s | $0.01-0.03/image | Alternative vendor |
| Gemini 1.5 Pro | Хорошее | ~1-3s | $0.005-0.015/image | Alternative vendor |
| Open-source (LLaVA, etc.) | Среднее | ~5-15s | Self-hosted | Cost optimization |

### 9.2 Rendering Engine

| Engine | Качество текста | Векторная графика | Сложность | Рекомендация |
|---|---|---|---|---|
| PIL/Pillow | Среднее | Нет | Минимальная | **Phase 1 (текущий)** |
| SVG (svgwrite) | Высокое | Да | Низкая | Phase 4 |
| HTML/CSS → headless browser | Высокое | Частично | Средняя | Phase 4 (таблицы) |
| Cairo (pycairo) | Высокое | Да | Средняя | Phase 4 (альтернатива) |
| ReportLab | Высокое | Да | Средняя | Phase 4 (PDF) |

---

## 10. Безопасность и ограничения

### 10.1 Ограничения Phase 1

1. **Точность координат**: VLM оценивает координаты, не измеряет пиксельно → ±5-10% drift
2. **Шрифты**: DejaVu Sans (системный) вместо оригинального шрифта
3. **Градиенты**: Не поддерживаются (solid fill only)
4. **Кривые Безье**: Не поддерживаются (прямые линии only)
5. **Сложные иконки**: Заменяются placeholder-ами
6. **Кириллица в VLM**: Зависит от модели; GPT-4.1 хорошо справляется

### 10.2 Когда pipeline выбирает safe mode

- Изображение классифицировано как фото/скриншот/ambiguous
- VLM вернул невалидный JSON
- Canvas dimensions = 0 или отрицательные
- PIL rendering выбросил исключение
- Config: `prefer_deterministic_reconstruction = false`

### 10.3 Data privacy

Scene graph extraction отправляет изображение на API GPT-4.1. Это аналогично существующей отправке на gpt-image-1 для semantic redraw. Никаких новых рисков.

---

## 11. Файлы реализации

| Файл | Роль |
|---|---|
| `image_reconstruction.py` | Core: VLM extraction + PIL rendering |
| `prompts/scene_graph_extraction.txt` | VLM prompt для JSON extraction |
| `image_generation.py` | Routing: reconstruction vs. semantic vs. safe |
| `image_analysis.py` | Classification: `deterministic_reconstruction` strategy |
| `models.py` | `ImageAsset.reconstruction_scene_graph` field |
| `config.toml` | `prefer_deterministic_reconstruction`, `reconstruction_model` |
| `config.py` | Config loading |
| `app.py` | Pipeline integration |
| `tests/test_image_reconstruction.py` | 29 тестов |
