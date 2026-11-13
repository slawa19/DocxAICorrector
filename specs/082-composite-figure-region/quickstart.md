# Quickstart: проверка спеки 082 (срез A)

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
