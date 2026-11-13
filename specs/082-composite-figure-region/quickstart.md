# Quickstart: проверка спеки 082 (срез A; срез B — пункт 7)

**Spec**: [spec.md](spec.md) | **Tasks**: [tasks.md](tasks.md)

Всё — под WSL Debian, через `scripts/test.sh`, одна команда на selector, selector до опций. Из Git Bash — транспорт
`wsl.exe -d Debian --cd "<дерево>" -- ...`, только литеральные пути (AGENTS.md). Ничего платного.

## 1. Зависимость

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc ". .venv/bin/activate && python -I -c 'import pypdfium2.version as v; print(v.PYPDFIUM_INFO, v.PDFIUM_INFO)'"
```

Ожидаемо: `5.15.2 159.0.8149.0@…`. Новое окружение — `bash scripts/setup-wsl.sh`.

## 2. Синтетика (CI)

```bash
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_pdf_page_render.py -q
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_pdf_image_frames.py -q
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_processing_runtime.py -q
```

## 3. Корпус — Rethinking (CI, `integration_local`)

```bash
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_pdf_image_frames_corpus.py -q
```

Ожидаемо: 32 замены на страницах `research.md` R20, 22 отказа на стр. 151, 33 сравнения.

## 4. Четыре книги — до/после (приёмка), с сохранением полных последовательностей

База — отдельный worktree на коммите `main`, в который влита ветка (например `D:\Temp\claude\wt-082-base`):

```bash
wsl.exe -d Debian --cd "<дерево>" -- bash -lc ". .venv/bin/activate && python -I scripts/measure-pdf-image-frames.py run --src /mnt/d/Temp/claude/wt-082-base/src --label base --commit <sha main> --out <dir> tests/sources/book/*.pdf"
wsl.exe -d Debian --cd "<дерево>" -- bash -lc ". .venv/bin/activate && python -I scripts/measure-pdf-image-frames.py run --src src --label branch --commit <sha ветки> --out <dir> tests/sources/book/*.pdf"
wsl.exe -d Debian --cd "<дерево>" -- bash -lc ". .venv/bin/activate && python -I scripts/measure-pdf-image-frames.py compare <dir>/base.json <dir>/branch.json --out <dir>/compare.json"
```

`base.json`/`branch.json` содержат все абзацы (текст, стиль) и все картинки (sha1, байты, EMU) по порядку и происхождение
прогона. Ожидаемо: Money, Creating, Value — 0 различий; Rethinking — 0 различий абзацев, картинки отличаются ровно в 32
местах (страницы R20); в `<dir>/branch_side_by_side/` — тройки «было | стало | страница», просмотреть глазами.

## 5. Лог

В `app.log` прогона: 32 `pdf_image_frame_rendered` (у каждого `correlation` < 0), 22 `pdf_image_frame_render_declined`
(стр. 151), итог `pdf_image_extraction_dropped_images` с `frame_render_checked: 33`, `frame_render_replaced: 32`.

## 6. Гарды

```bash
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_script_contract_static.py -q
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_documentation_links.py -q
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_spec_status_consistency.py -q
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_typecheck.py -q
```

## 7. Срез B (после постройки; редакция 2026-11-13 по решению владельца D-6)

Синтетика и правило (CI):

```bash
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_pdf_figure_regions.py -q
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_pdf_figure_regions_render.py -q
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_processing_runtime.py -q
```

Корпус (`integration_local`): одна область на Rethinking стр. 151 — рамка `[42,2; 68,2; 353,8; 499,5]`, 22 выдаваемых члена,
261 семя, 2365 путей; других областей нет. Тест среза A (`tests/test_pdf_image_frames_corpus.py`) — те же 32 замены и
22 отказа на стр. 151.

```bash
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_pdf_figure_regions_corpus.py -q
```

Четыре книги до/после — пункт 4 (тот же скрипт, база — `main` без среза B). Ожидаемо (research R34): Money 1390 / 43,
Creating 1757 / 62, Value 1945 / 42 — 0 различий; Rethinking 2639 абзацев — 0 различий, картинки 55 → 34 (позиции 18–39
уходят, одна добавлена на месте 18, остальные 33 — байт в байт). Картинку области открыть глазами
(`<dir>/branch_side_by_side/`): схема целиком, 12 кружков и восьмиугольник — белые, как на странице.

Подготовка аудиокниги Rethinking, до/после (без модели; образец — `D:\Temp\claude\work-082b\sim_b.py --prep`): 2603
неизображённых абзаца с теми же текстом, ролью, причиной исключения; строк-картинок 55 → 34.

Лог (`app.log`): `pdf_figure_region_rendered` — 1 (стр. 151, `members_emitted: 22`); итог
`pdf_image_extraction_dropped_images` с `figure_region_rendered: 1`, `figure_region_images_absorbed: 22` и прежними
`frame_render_*`; `pdf_text_layer_import_succeeded` с `figure_regions_inserted: 1`, `image_count: 34`.
