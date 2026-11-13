# Implementation Plan: картинки PDF — такими, какими их видит читатель страницы

**Branch**: `082-composite-figure` (от `main` @ `9b5db10`) | **Date**: 2026-11-13 (раунд 2, после ревью дизайна) |
**Spec**: [spec.md](spec.md)

**Input**: `spec.md` (срезы A и B); решения — [research.md](research.md) (R1, R18–R24 действуют; R2–R7, R9, R11, R17 —
данные первой редакции среза B); сущности — [data-model.md](data-model.md); контракты —
[contracts/events.md](contracts/events.md), [contracts/import-output.md](contracts/import-output.md); проверка —
[quickstart.md](quickstart.md); задачи — [tasks.md](tasks.md).

**База**: `main` @ `9b5db10`; ссылки `file:line` сверены 2026-11-13. Если ветка уйдёт вперёд — сверить заново
(Конституция VIII).

## Summary

**Срез A (строится сейчас).** Импорт PDF по текстовому слою узнаёт выданную картинку, чьи байты по определению формата —
не вид страницы (цветовое пространство краски `Separation`/`DeviceN`), и заменяет её байты PNG-отрисовкой её собственной
рамки страницы (`pypdfium2`), если поверх рамки нет чужого текста и чужой картинки. Рамка округляется наружу, плотность =
плотность источника — пикселей не меньше, чем у источника; размер в DOCX задаётся явно. Текст не трогается вовсе; при
любом сбое — исходные байты и ERROR. На корпусе: 32 фото Rethinking перестают быть негативами, остальное — побайтно то же.

**Срез B (только дизайн, ревью раунда 2).** Составная иллюстрация: «рисовать» и «удалять текст» разделены; удаление —
только по уликам E1–E7 (spec FR-B2). Строится после ревью и решения Q-4.

## Technical Context

**Language/Version**: Python 3.13.5 (WSL `.venv`), CI — 3.12.
**Primary Dependencies**: `pdfminer.six` 20260107 (есть); **новая** `pypdfium2==5.15.2` (R1); Pillow 12.3.0; python-docx 1.2.0.
**Storage**: нет новых артефактов; замены живут в промежуточном DOCX моста; события — `app.log`.
**Testing**: pytest через `bash scripts/test.sh` под WSL; синтетический PDF, собранный тестом байтами (`tests/pdf_synthetic.py`);
тест корпуса `integration_local` на Rethinking; замерный скрипт четырёх книг с sha1 — при приёмке.
**Target Platform**: WSL Debian x86_64; CI ubuntu-latest.
**Performance Goals**: + ≤ 5 с на импорт Rethinking (замер: 33 рамки ≈ 1,9 с); на книгах без кандидатов — 0 (документ
pdfium не открывается).
**Constraints**: текст не меняется (срез A); не меньше пикселей, чем у источника; нет системного пакета; нет
пользовательской ветки деградации; `pdf_import/logical_import.py` — только чтение (его меняет другая ветка).
**Scale/Scope**: 2 новых модуля (`page_render.py`, `image_frames.py`), правки `images.py`, `__init__.py`,
`processing_runtime.py` (путь картинок), 3 новых тестовых файла + помощник, правки `tests/test_processing_runtime.py`,
1 замерный скрипт, документы.

## Constitution Check

- **I/II — PASS.** Замеры — `.venv` под WSL; проверки — `scripts/test.sh` через `wsl.exe -d Debian`.
- **III — PASS, полный цикл**: новые модули, зависимость, поля событий; порядок модулей важен (опись → решение →
  отрисовка → мост).
- **IV — PASS.** Корпус — вход офлайн-замера без модели.
- **V — PASS.** События — `contracts/events.md`; документ логирования — задача T014.
- **VI — PASS.** Задачи называют свои файлы; `processing_runtime.py` — только путь картинок (T003, T004, T009–T011).
- **VII — PASS.** Триггер — свойство формата PDF без числа; отказ — пересечение площадей; разрешение — плотность самой
  картинки; потолок — константы конвейера. Ни литерала книги. Тесты — вымышленные.
- **VIII — PASS.** Каждое число спеки — из файла замера этого дерева (R18–R22); находки ревью проверены по коду и данным
  (Changelog спеки).

## Project Structure

```text
specs/082-composite-figure-region/   spec.md plan.md research.md data-model.md quickstart.md tasks.md
                                     contracts/{events.md,import-output.md} checklists/requirements.md

src/docxaicorrector/pdf_import/
├── images.py          # ИЗМ.: опись (PdfDiscoveredImage, skip_reason, colour_space_family), PdfImageExtraction,
│                      #       новые поля PdfImageObject, extract_pdf_images_and_inventory,
│                      #       log_pdf_image_extraction_outcome; extract_pdf_images_with_pdfminer удалена
├── page_render.py     # НОВ.: layout_cropbox, frame_geometry (чистые), render_frames (pypdfium2, замок, PNG)
├── image_frames.py    # НОВ.: plan_frame_replacements (чистое), apply_frame_replacements (отрисовка, события)
└── __init__.py        # ИЗМ.: экспорт новой точки входа
src/docxaicorrector/processing/processing_runtime.py
                       # ИЗМ.: _run_pdf_parse_stages (опись → план → замены → итоговое событие);
                       #       _append_pdf_image_to_docx/_append_image_bytes_to_docx (явный размер, откат);
                       #       pdf_text_layer_import_succeeded (+1 ключ)
requirements.txt, pyproject.toml, scripts/setup-wsl.sh, scripts/_list_log_events.py, scripts/README.md
scripts/measure-pdf-image-frames.py          # НОВ.: четыре книги до/после, sha1, побочные PNG
tests/pdf_synthetic.py                       # НОВ.: помощник (не тестовый файл)
tests/test_pdf_page_render.py                # НОВ. (Unit-Contract)
tests/test_pdf_image_frames.py               # НОВ. (Unit-Contract)
tests/test_pdf_image_frames_corpus.py        # НОВ. (Integration-Local)
tests/test_processing_runtime.py             # ИЗМ.
docs/LOGGING_AND_ARTIFACT_RETENTION.md, docs/WORKFLOW_AND_IMAGE_MODES.md, AGENTS.md,
docs/testing/TEST_TIER_INVENTORY.md          # ИЗМ.
```

## Дизайн среза A

- **Опись (`images.py`).** Обход `_iter_pdfminer_images` (`:129-143`) остаётся; для каждой `LTImage` — `PdfDiscoveredImage`
  (ключ, рамка, семейство пространства через `resolve1` словаря потока, `skip_reason`); выданная `PdfImageObject` получает
  `discovery_index` и `colour_space_family`. Итоговое событие уходит из извлекателя в `log_pdf_image_extraction_outcome`
  (счётчики из описи + исход замен). Без совместимого псевдонима: `extract_pdf_images_with_pdfminer` вызывал только
  `processing_runtime.py:529,581`; подмены в тестах переводятся.
- **Решение (`image_frames.plan_frame_replacements`).** Для выданной картинки с семейством краски: пересечение
  положительной площади с любым спаном страницы → `text_over_frame`; с любой другой обнаруженной картинкой страницы →
  `image_over_frame`; иначе кандидат с `scale = max(px_w / w_pt, px_h / h_pt)` (пиксели — из заголовка файла картинки
  через Pillow, без декодирования).
- **Отрисовка (`page_render`).** `layout_cropbox`: CropBox переводится в пространство макета pdfminer той же матрицей,
  которой pdfminer поворачивает страницу (`PDFPageInterpreter.process_page`). `frame_geometry`: пиксельная рамка
  `floor/ceil` наружу в сетке `ceil(W·scale) × ceil(H·scale)`, пересечение с CropBox; пусто → `outside_crop_box`; больше
  `MAX_IMAGE_DIMENSION_PX`/`MAX_IMAGE_MEGAPIXELS` → `exceeds_pixel_budget`. Отрисовка: `page.render(scale, crop=…)` с обрезкой
  `(px − 0,5)/scale` (pypdfium2 берёт `ceil(c·scale)` — так целые пиксели точны при любой погрешности float),
  `draw_annots=False`, `may_draw_forms=False`; PNG `L`, если каналы совпадают; `pHYs` = scale·72. Документ открывается
  один раз на книгу и только при непустом плане; `threading.Lock` модуля.
- **Применение (`image_frames.apply_frame_replacements`).** Для кандидата: геометрия, отрисовка (исключение →
  `pdf_image_frame_render_failed`, картинка как есть), замена через `dataclasses.replace` (байты, mime, `display_*`,
  `original_*`), событие `pdf_image_frame_rendered`; отказы — `pdf_image_frame_render_declined`.
- **Мост (`processing_runtime.py`).** `_run_pdf_parse_stages` (`:580-592`): `extraction = extract_pdf_images_and_inventory(input_path)`
  → `plan = plan_frame_replacements(extraction, spans)` → `images, outcome = apply_frame_replacements(input_path, extraction, plan)`
  → `log_pdf_image_extraction_outcome(...)` → лимит картинок. Исключение извлечения — как сегодня (`:582-590`: WARNING и
  импорт без картинок). Исключение в шаге замен (вне отрисовки одной картинки) книгу картинок не лишает: ловится, список
  картинок — исходный, событие ERROR `pdf_image_frame_render_failed` (тест). Вставка:
  `_append_image_bytes_to_docx(document, bytes, width_pt=None, height_pt=None)`; для замены — явный размер; сбой →
  исходные байты прежним путём + ERROR `pdf_image_replacement_insert_failed`.

## Срез B

Только дизайн (spec FR-B1…FR-B8, research R23–R24, Q-4). План и задачи пишутся после ревью раунда 2.

## Порядок реализации

```text
Setup:        T001–T003   зависимость; синтетический PDF; характеристика ДО правки
Foundational: T004        опись и новая точка входа (поведение прежнее)
Срез A:       T005–T013   геометрия → отрисовка → решение → применение → мост → DOCX → корпус → замер
Polish:       T014–T021   документы, инвентарь, pyright, Changelog, прогоны; оркестратор — полный прогон и Codex
```

## Риски

| Риск | Чем закрыт |
|---|---|
| Замена хуже исходного | триггер только по семейству краски; отказ при чужом тексте/картинке; глазами все 32 пары (T013) |
| Меньше пикселей | округление наружу, масштаб = плотность источника; тест + замер всех 32 |
| Неверный размер в DOCX | явный `width/height`; тест дробной плотности и обрезки `CropBox` |
| Сдвиг рамки (`CropBox`, поворот) | `layout_cropbox` + тест пикселей на синтетике с `CropBox` и `/Rotate 90` |
| Сбой отрисовки / вставки | исходные байты + ERROR; тесты подменой |
| Регрессия на книгах без кандидатов | документ не открывается; sha1 и абзацы четырёх книг (T013) |
| PDFium в потоках тестового пути | замок модуля |
| pyright-ратчет | типизация; `test_typecheck.py` (T017) |

## Сохраняемые контракты AGENTS.md

WSL — источник истины; `scripts/test.sh` через `wsl.exe -d Debian`; боковой worktree (`.venv` — симлинк, git — из Git
Bash); LF и `git diff --check`; тема коммита называет спеку 082; `log_event`, текст ≤ 120 знаков; `git status
--porcelain` пуст перед «зелёным»; полный прогон в главном дереве и приёмочное ревью Codex — за оркестратором.
