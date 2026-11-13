# Data Model: составная иллюстрация PDF приходит одной картинкой

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-11-13

Все рамки — `(x0, top, x1, bottom)` в pt, x от левого края `MediaBox`, y от верхнего края, как у `PdfTextSpan`
(`pdf_import/text_layer_quality.py:104-120`) и `PdfImageObject` (`pdf_import/images.py:20-32`). Все сущности —
`@dataclass(frozen=True)`, пиклятся (результат разбора идёт из дочернего процесса, `processing_runtime.py:661-666`).

## §1. Опись графики страницы (`pdf_import/images.py`)

```python
@dataclass(frozen=True)
class PdfPageGraphic:
    kind: str                       # "image" | "path"
    x0: float
    top: float
    x1: float
    bottom: float
    emittable: bool = False         # image: извлекатель отдаёт его байты (images.py:69-76); path: False
    ink_space: bool = False         # image: семейство цветового пространства Separation или DeviceN
    source_px: tuple[int, int] | None = None   # image: srcsize
    stroke_half_width: float = 0.0  # path, который обводится: linewidth / 2
    discovery_index: int | None = None         # image: номер в обходе страницы (связь с PdfImageObject)


@dataclass(frozen=True)
class PdfPageGraphics:
    page_number: int
    page_width: float
    page_height: float
    graphics: tuple[PdfPageGraphic, ...]


@dataclass(frozen=True)
class PdfImageExtraction:
    images: tuple[PdfImageObject, ...]          # как сегодня: отдаваемые, по (page, top, x0)
    seed_pages: tuple[PdfPageGraphics, ...]     # ТОЛЬКО страницы, где есть картинка-семя (FR-003)
    discovered: int
    skipped_no_image_bytes: int
    skipped_unknown_mime: int
    pages_truncated: bool
```

Правила:
- Путь — `LTCurve` и его подклассы `LTLine`, `LTRect` на любой глубине `LTFigure`; текстовые контейнеры не
  обходятся (как `_iter_pdfminer_images`, `images.py:129-143`).
- Семя определяется уже в обходе (US1: `not emittable`; US2: `ink_space`), поэтому опись путей хранится только для
  страниц с семенем — на корпусе это одна страница (US1) или 33 (US1 + US2) из 917.
- `ink_space`: первый элемент массива `ColorSpace` (или имя) — `Separation` или `DeviceN`, после `resolve1`; так же,
  как `scan.py::_name` замера.

## §2. Типографика тела (`pdf_import/logical_import.py`)

```python
@dataclass(frozen=True)
class BodyTypography:
    body_font_size: float
    body_column_width: float


def measure_body_typography(spans: Sequence[PdfTextSpan]) -> BodyTypography | None:
    """body_font_size и body_right_x1 - body_left_x0 профиля импортёра (_build_heading_layout_profile,
    :740-789) на тех же спанах, что пойдут в сборку; None, если профиль их не знает (тогда правило не
    срабатывает на книге, FR-005)."""
```

Повторное использование, не копия: правило вызывает `_font_sizes_match` (`:3452-3457`), `_looks_like_caption`
(`:1636-1637`) и читает `_FULL_LINE_FILL_RATIO` (`:74-78`) — одно определение чисел на модуль.

## §3. Область (`pdf_import/figure_regions.py`, чистый модуль)

```python
SEED_NON_EMITTABLE = "non_emittable"
SEED_INK_SPACE = "ink_space"
DECLINE_BODY_SIZE_TEXT = "body_size_text"      # G1
DECLINE_FULL_MEASURE_LINE = "full_measure_line"  # G2


@dataclass(frozen=True)
class FigureRegion:
    page_number: int
    x0: float
    top: float
    x1: float
    bottom: float
    seed_kind: str                          # non_emittable, если в области есть оба вида
    graphic_indices: tuple[int, ...]        # в PdfPageGraphics.graphics
    absorbed_discovery_indices: tuple[int, ...]   # все картинки области (для удаления отдаваемых)
    absorbed_image_count: int
    absorbed_emittable_count: int
    absorbed_path_count: int
    suppressed_span_indices: tuple[int, ...]      # в переданном списке спанов, по (top, x0)
    suppressed_char_count: int
    render_pad_pt: float                    # наибольшая stroke_half_width путей области
    raster_density_dpi: float               # FR-008 до потолка: взвешенная по площади медиана


@dataclass(frozen=True)
class DeclinedFigureRegion:
    page_number: int
    x0: float
    top: float
    x1: float
    bottom: float
    reason: str                             # DECLINE_*
    blocking_text_preview: str              # начало строки-причины, <= 120 знаков
    image_count: int


@dataclass(frozen=True)
class FigureRegionPlan:
    regions: tuple[FigureRegion, ...]
    declined: tuple[DeclinedFigureRegion, ...]


def detect_figure_regions(
    pages: Sequence[PdfPageGraphics],
    spans: Sequence[PdfTextSpan],
    typography: BodyTypography | None,
    *,
    seed_kinds: frozenset[str],             # US1: {non_emittable}; US1+US2: оба
) -> FigureRegionPlan: ...
```

Инварианты (каждый — тест):
- область ⊇ рамка каждого своего объекта; каждая убранная строка ⊆ область; ни одна строка формы подписи не убрана;
- две области одной страницы не пересекаются (пересекающиеся слились бы на шаге роста);
- в принятой области нет центра строки с буквой кеглем тела или крупнее и нет полной строки с буквой;
- `typography is None` → план пуст (и `declined` пуст).

## §4. Картинка области (`pdf_import/images.py::PdfImageObject`, новое поле)

```python
@dataclass(frozen=True)
class PdfImageObject:
    ...                                   # поля images.py:22-32 без изменений
    description: str | None = None        # НОВОЕ: текст убранных строк области, порядок (top, x0), через пробел
```

Картинка области: рамка = рамка `FigureRegion` (без раздвижки отрисовки), `image_bytes` — PNG с `pHYs`,
`mime_type="image/png"`, `source_index = max(0, (page − 1) · 10000 + int(round(top)))`, `width_points`/`height_points` —
размеры рамки, `description` — по FR-010 (`None`, если ничего не убрано, как у фото US2).

## §5. Отрисовка (`pdf_import/figure_render.py`)

```python
@dataclass(frozen=True)
class RenderedFigure:
    region: FigureRegion
    image: PdfImageObject
    resolution_dpi: float                 # после потолка FR-008
    width_px: int
    height_px: int
    grayscale: bool


def region_resolution_dpi(raster_density_dpi: float, width_pt: float, height_pt: float, *,
                          max_dimension_px: int, max_megapixels: float) -> float: ...

def region_crop(box_pt, pad_pt, *, mediabox, cropbox, rotation, scale) -> tuple[float, float, float, float] | None:
    """Чистая: обрезка (left, bottom, right, top) в единицах холста pdfium; None — рамка вне CropBox."""

def render_figure_regions(pdf_path, plan: FigureRegionPlan) -> tuple[list[RenderedFigure], list[tuple[FigureRegion, BaseException]]]:
    """Ленивый import pypdfium2; документ открывается, только если plan.regions не пуст; вызовы под замком модуля."""
```

## §6. Результат разбора (`processing_runtime.py::_PdfParseStagesResult`, `:494-508`)

Поля прежние; `spans` — уже без убранных строк, `image_objects` — итоговый список (отдельные + картинки областей,
по `(page, top, x0)`). Новые поля с умолчанием (канонический тестовый результат `:689-702` не меняется):

```python
    figure_regions_rendered: int = 0
    figure_region_lines_suppressed: int = 0
```

Они идут в `pdf_text_layer_import_succeeded` (`:919-933`) — чтобы родитель видел итог без чтения лога ребёнка.
