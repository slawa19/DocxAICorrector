# Data Model: картинки PDF — такими, какими их видит читатель страницы

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-11-13 (раунд 2; срез B — редакция по D-6, §5–§7)

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
    placement_matrix: tuple[float, float, float, float, float, float] | None = None
    # матрица LTFigure, в которую pdfminer завернул Do картинки, в пространстве макета (с поворотом страницы)
    # раунд 2/3 приёмочного ревью (research R28, R29):
    frame_box: tuple[float, float, float, float] | None = None   # истинная рамка (x0, top, x1, bottom), НЕ прижатая
                                                                 # к странице; top/bottom выше — прижаты (ключ порядка)
    ink_space: bool | None = None             # причина: Separation | DeviceN | Indexed над ними; None — не читалось
    mask: str | None = None                   # "SMask" | "Mask" из словаря картинки; "unreadable" — словарь не читается
```

`ink_space` и `mask` читает обход (`images._is_ink_space`, `images._image_mask`) из словаря потока, который pdfminer уже
даёт; оба никогда не бросают. Запись, построенная без `ink_space` (тесты решения), получает причину по имени семейства.
Поля раунда 2 `clips` и `PdfImageExtraction.painted` (`PdfPaintedRegion`) удалены вместе с наблюдателем краски (раунд 3).

Замена — та же картинка (`page_number`, рамка, `source_index`, `discovery_index` те же) с `image_bytes` = PNG
отрисовки, `mime_type="image/png"`, `display_*` = размер фактической рамки отрисовки и `original_*` = прежние байты.
Признак «это замена» — `original_image_bytes is not None`.

### §3. Решение по картинке (`pdf_import/image_frames.py`, чистое решение + применение)

```python
DECLINE_TEXT_OVER_FRAME = "text_over_frame"
DECLINE_IMAGE_OVER_FRAME = "image_over_frame"
DECLINE_UNSUPPORTED_PLACEMENT = "unsupported_placement"   # не прямой масштаб a 0 0 d, a, d > 0
DECLINE_UNREADABLE_SOURCE = "unreadable_source"           # заголовок файла не читается или рамка пуста
DECLINE_USER_UNIT = "user_unit"                           # /UserUnit != 1
DECLINE_OUTSIDE_CROP_BOX = "outside_crop_box"             # рамка не целиком внутри CropBox
DECLINE_EXCEEDS_PIXEL_BUDGET = "exceeds_pixel_budget"
DECLINE_PAGE_GEOMETRY_DISAGREES = "page_geometry_disagrees"
DECLINE_FLAT_IMAGE = "flat_image"
DECLINE_MASKED_IMAGE = "masked_image"                     # /SMask или /Mask в словаре картинки
DECLINE_NOT_INK_SPACE = "not_ink_space"                   # раунд 3: причины нет — пространство не краска
INK_SPACE_FAMILIES = frozenset({"Separation", "DeviceN"})


def is_upright_scale(matrix) -> bool: ...
def is_ink_space(image: PdfImageObject) -> bool: ...      # причина (FR-A1)
def correlation_with_page(image_bytes: bytes, rendered) -> float | None: ...   # свидетельство; None — плоская


@dataclass(frozen=True)
class FrameCandidate:
    image: PdfImageObject
    source_width_px: int
    source_height_px: int
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


@dataclass(frozen=True)
class FrameOutcome:
    images: tuple[PdfImageObject, ...]
    checked: int
    replaced: int
    declined: int
    failed: int


def plan_frame_replacements(extraction: PdfImageExtraction, spans: Sequence[PdfTextSpan]) -> FramePlan: ...
def apply_frame_replacements(pdf_path, extraction, plan) -> FrameOutcome: ...
```

Отказы, которым нужна страница (`user_unit`, `outside_crop_box`, `exceeds_pixel_budget`, `page_geometry_disagrees`,
`flat_image`), решаются при отрисовке — тоже `FrameDecline`.

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


def frame_geometry(box, *, crop, scale) -> FrameGeometry | None:   # crop = PdfPageGeometry.layout_cropbox
    """Чистая: рамка макета pdfminer -> пиксели в CropBox; округление НАРУЖУ; None — рамка не целиком внутри."""


def layout_cropbox(mediabox, cropbox, rotation) -> tuple[float, float, float, float]:
    """Чистая: CropBox в пространстве макета pdfminer (с учётом /Rotate, как pdfminer поворачивает MediaBox)."""


@dataclass(frozen=True)
class PdfPageGeometry:            # единственный источник границ — pdfminer (наследование разрешено)
    mediabox: Box
    cropbox: Box
    rotation: int
    user_unit: float = 1.0


def read_page_geometry(pdf_path, page_numbers) -> dict[int, PdfPageGeometry]: ...
def render_frame(document, *, page_number, page_geometry, geometry) -> "PIL.Image.Image":
    """Сверяет размер и поворот страницы PDFium с pdfminer (иначе PageGeometryMismatch), рисует рамку."""


@dataclass(frozen=True)
class EncodedFrame:
    png_bytes: bytes
    grayscale: bool
```

## Срез B (дизайн, редакция 2026-11-13 по решению владельца D-6; не строится до ревью)

### §5. Картинка области (`PdfImageObject`, новое поле)

```python
@dataclass(frozen=True)
class PdfImageObject:
    ...                                                     # поля §2 без изменений
    region_members: tuple["PdfImageObject", ...] | None = None
    # None — обычная картинка; кортеж — картинка области: N выданных объектов (как их выдал срез A), которые она
    # заменяет; () — область без выданных членов (N = 0, одиночная непередаваемая картинка); откат = они
```

Картинка области: `page_number`; `x0, top, x1, bottom` = рамка области (пересечённая с `CropBox`; `top` прижат к 0, как
у картинок); `frame_box` = та же рамка без прижатия; `source_index = max(0, (page_number − 1) · 10000 + round(top))`;
`image_bytes` = PNG отрисовки; `mime_type = "image/png"`; `display_width_points` / `display_height_points` = рамка
отрисовки в pt (явный размер в DOCX); `width_points` / `height_points` = рамка области; `discovery_index = None`;
`original_image_bytes = None` (это не замена одной картинки — откат идёт к членам). Признак — `region_members is not None` (ревью дизайна раунда 2, находка 5).
Пиклится: члены — те же frozen-объекты.

### §6. Опись графики страницы (`pdf_import/figure_regions.py`)

```python
@dataclass(frozen=True)
class PageGraphic:
    box: tuple[float, float, float, float]        # (x0, top, x1, bottom) макета pdfminer, НЕ прижата к странице
    kind: str                                     # "image" | "path"
    discovery_index: int | None = None            # у картинки — номер LTImage в обходе страницы (как у описи)
    source_px: tuple[int, int] | None = None      # у картинки — LTImage.srcsize


@dataclass(frozen=True)
class PageGraphics:
    page_number: int
    graphics: tuple[PageGraphic, ...]


def read_page_graphics(pdf_path, page_numbers: Iterable[int]) -> dict[int, PageGraphics]:
    """Отдельный pdfminer-проход только по page_numbers; рамка пути — по всем операндам original_path.
    Никогда не бросает наружу: сбой -> {} (вызывающий пишет ERROR stage="inventory")."""
```

### §7. Решение и исход (`pdf_import/figure_regions.py`)

```python
REGION_DECLINE_RUNNING_TEXT = "running_text_inside"       # G1
REGION_DECLINE_FULL_LINE = "full_line_inside"             # G2
REGION_DECLINE_INVENTORY_MISMATCH = "inventory_mismatch"  # проход описи и опись картинок расходятся
REGION_DECLINE_OUTSIDE_CROP_BOX = "outside_crop_box"      # пересечение с CropBox пусто
REGION_DECLINE_IMAGE_ENCLOSES_TEXT = "image_encloses_page_text"   # картинка содержит > половины строк страницы
REGION_DECLINE_TYPOGRAPHY_UNKNOWN = "typography_unknown"  # T1
REGION_DECLINE_TYPOGRAPHY_DISAGREES = "typography_disagrees"  # T2
REGION_DECLINE_TEXT_BLOCK = "text_block_inside"           # T3
REGION_DECLINE_MEMBER_OUTSIDE = "member_outside_crop_box" # M
REGION_DECLINE_UNKNOWN_DENSITY = "unknown_density"        # ни у одной картинки области нет размера в пикселях
REGION_DECLINE_IMAGE_COUNT_CAP = "image_count_cap"        # итог B превысил бы лимит картинок (N = 0)
# при отрисовке (те же имена, что у среза A): "user_unit", "page_geometry_disagrees", "exceeds_pixel_budget"


@dataclass(frozen=True)
class PdfBodyTypography:                         # публичная функция logical_import (Q-5)
    body_font_size: float | None
    body_left_x0: float | None
    body_right_x1: float | None


@dataclass(frozen=True)
class FigureRegion:
    page_number: int
    box: tuple[float, float, float, float]        # окончательная рамка ∩ CropBox
    member_keys: tuple[tuple[int, int], ...]      # (page_number, discovery_index) выданных картинок внутри
    seed_count: int                               # непередаваемых картинок внутри
    image_count: int
    path_count: int
    grown_line_count: int                         # строк мельче тела, по которым рамка выросла
    seed_density: float | None                    # px на pt: взвешенная по площади медиана плотностей семян
    # плотность отрисовки = max(seed_density, наибольшая плотность выданных членов в images_a) — при применении


@dataclass(frozen=True)
class RegionDecline:
    page_number: int
    box: tuple[float, float, float, float] | None
    reason: str
    detail: str = ""                               # начало строки-стража / текст расхождения, <= 120 знаков
    seed_count: int = 0


@dataclass(frozen=True)
class FigureRegionPlan:
    seed_pages: tuple[int, ...]
    regions: tuple[FigureRegion, ...]
    declines: tuple[RegionDecline, ...]


@dataclass(frozen=True)
class FigureRegionOutcome:
    images: tuple[PdfImageObject, ...]            # images_A − члены + картинки областей, по (page, top, x0)
    rendered: int
    declined: int                                  # отказов (по областям; страница отказывает целиком — FR-B8)
    failed: int
    images_absorbed: int                           # выданных картинок, ушедших в области
    absorbed_frame_renders: int                    # из них — уже заменённых срезом A (не доставляются)


def plan_figure_regions(extraction, spans, graphics: dict[int, PageGraphics], typography: PdfBodyTypography,
                        crop_boxes: dict[int, Box]) -> FigureRegionPlan: ...   # чистая
def apply_figure_regions(pdf_path, images_a: Sequence[PdfImageObject], plan: FigureRegionPlan) -> FigureRegionOutcome: ...
```

Счётчики итогового события выводятся из исхода (не хранятся отдельно). Члены области находятся в `images_a` по ключу
`(page_number, discovery_index)` — у выданной картинки он есть с FR-A10, у замены среза A — тот же.

### Отклонённый проект (раунд 2, удаление подписей, не действует)

Сущности первой редакции (`PdfPageGraphic`, `FigureRegion`, `FigureRegionPlan`) сохраняются по смыслу, с изменениями по
ревью: у области — `graphics_hull` (оболочка графики) отдельно от `picture_box` (рамка картинки с ростом по строкам);
у строки — улики E1–E7 (`work-082/sliceB/p151_lines.json` — образец полей); у плана страницы — атомарный исход (все
области страницы применены или ни одна); у отказа — `seed_kind`; удалённые строки хранятся в результате разбора для
восстановления (FR-B5). Подготовка профиля — публичной функцией `logical_import.py`, повторяющей
`build_paragraph_units_from_text_spans:152-174` (согласовать с веткой, меняющей этот модуль).
