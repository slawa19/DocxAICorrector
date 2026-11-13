# Data Model: картинки PDF — такими, какими их видит читатель страницы

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-11-13 (раунд 2)

Рамки — `(x0, top, x1, bottom)` в pt в пространстве макета `pdfminer` (x от левого края показанного `MediaBox`, y от
верхнего края), как у `PdfTextSpan` (`pdf_import/text_layer_quality.py:104-120`) и `PdfImageObject`
(`pdf_import/images.py:20-32`). Все сущности — `@dataclass(frozen=True)` и пиклятся (результат разбора идёт из дочернего
процесса, `processing_runtime.py:661-666`).

## Срез A

### §1. Обнаруженная картинка (`pdf_import/images.py`)

```python
SKIP_NO_IMAGE_BYTES = "no_image_bytes"
SKIP_UNKNOWN_MIME = "unknown_mime"


@dataclass(frozen=True)
class PdfDiscoveredImage:
    page_number: int
    discovery_index: int          # номер LTImage в обходе страницы (0-based); ключ — (page_number, discovery_index)
    x0: float
    top: float
    x1: float
    bottom: float
    colour_space_family: str | None   # первый элемент ColorSpace после resolve1: "DeviceRGB", "Separation", ...
    skip_reason: str | None           # None — выдана; SKIP_* — почему нет


@dataclass(frozen=True)
class PdfImageExtraction:
    images: tuple[PdfImageObject, ...]          # выданные, по (page, top, x0) — как сегодня
    discovered: tuple[PdfDiscoveredImage, ...]  # все LTImage книги
    pages_truncated: bool
```

Счётчики итогового события выводятся из `discovered` (`skip_reason`), а не хранятся отдельно — они не могут разойтись.

### §2. Выданная картинка (`PdfImageObject`, новые поля с умолчаниями)

```python
@dataclass(frozen=True)
class PdfImageObject:
    ...                                       # поля images.py:22-32 без изменений
    discovery_index: int | None = None        # связь с PdfDiscoveredImage (вместе с page_number)
    colour_space_family: str | None = None
    display_width_points: float | None = None   # только у замены: размер в DOCX задаётся явно (FR-A6)
    display_height_points: float | None = None
    original_image_bytes: bytes | None = None   # только у замены: исходные байты для отката (FR-A9)
    original_mime_type: str | None = None
```

Замена — та же картинка (`page_number`, рамка, `source_index`, `discovery_index` те же) с `image_bytes` = PNG
отрисовки, `mime_type="image/png"`, `display_*` = размер фактической рамки отрисовки и `original_*` = прежние байты.
Признак «это замена» — `original_image_bytes is not None`.

### §3. Решение по картинке (`pdf_import/image_frames.py`, чистое решение + применение)

```python
DECLINE_TEXT_OVER_FRAME = "text_over_frame"
DECLINE_IMAGE_OVER_FRAME = "image_over_frame"
DECLINE_EXCEEDS_PIXEL_BUDGET = "exceeds_pixel_budget"
DECLINE_OUTSIDE_CROP_BOX = "outside_crop_box"


def colour_space_is_ink(family: str | None) -> bool: ...   # Separation | DeviceN


@dataclass(frozen=True)
class FrameCandidate:
    image: PdfImageObject
    scale: float                 # px на pt = плотность источника / 72


@dataclass(frozen=True)
class FrameDecline:
    image: PdfImageObject
    reason: str                  # DECLINE_*
    detail: str                  # начало строки / ключ другой картинки, <= 120 знаков


@dataclass(frozen=True)
class FramePlan:
    candidates: tuple[FrameCandidate, ...]
    declines: tuple[FrameDecline, ...]


def plan_frame_replacements(extraction: PdfImageExtraction, spans: Sequence[PdfTextSpan]) -> FramePlan: ...
```

Отказы по геометрии рамки (`exceeds_pixel_budget`, `outside_crop_box`) решаются при отрисовке, когда известны
`MediaBox`/`CropBox`, — тоже `FrameDecline`.

### §4. Геометрия и отрисовка (`pdf_import/page_render.py`)

```python
@dataclass(frozen=True)
class FrameGeometry:
    left_px: int                 # в пиксельной сетке показанного CropBox при масштабе scale
    top_px: int
    right_px: int
    bottom_px: int
    scale: float
    frame_width_points: float    # (right_px - left_px) / scale — фактическая рамка
    frame_height_points: float


def frame_geometry(box, *, layout_cropbox, scale) -> FrameGeometry | None:
    """Чистая: рамка макета pdfminer -> пиксели в CropBox; округление НАРУЖУ; None — вне CropBox."""


def layout_cropbox(mediabox, cropbox, rotation) -> tuple[float, float, float, float]:
    """Чистая: CropBox в пространстве макета pdfminer (с учётом /Rotate, как pdfminer поворачивает MediaBox)."""


@dataclass(frozen=True)
class RenderedFrame:
    png_bytes: bytes
    geometry: FrameGeometry
    grayscale: bool
```

## Срез B (дизайн раунда 2, не строится)

Сущности первой редакции (`PdfPageGraphic`, `FigureRegion`, `FigureRegionPlan`) сохраняются по смыслу, с изменениями по
ревью: у области — `graphics_hull` (оболочка графики) отдельно от `picture_box` (рамка картинки с ростом по строкам);
у строки — улики E1–E7 (`work-082/sliceB/p151_lines.json` — образец полей); у плана страницы — атомарный исход (все
области страницы применены или ни одна); у отказа — `seed_kind`; удалённые строки хранятся в результате разбора для
восстановления (FR-B5). Подготовка профиля — публичной функцией `logical_import.py`, повторяющей
`build_paragraph_units_from_text_spans:152-174` (согласовать с веткой, меняющей этот модуль).
