# Quickstart: проверка спеки 082

**Spec**: [spec.md](spec.md) | **Tasks**: [tasks.md](tasks.md)

Всё — под WSL Debian, через `scripts/test.sh`, одна команда на один selector, selector до опций. Из Git Bash —
транспорт `wsl.exe -d Debian --cd "<дерево>" -- ...`, только литеральные пути (AGENTS.md). Ничего платного.

## 1. Зависимость на месте

```bash
wsl.exe -d Debian --cd "D:\Work\Projects\DocxAICorrector" -- bash -lc ". .venv/bin/activate && python -I -c 'import pypdfium2, pypdfium2.version as v; print(v.PYPDFIUM_INFO, v.PDFIUM_INFO)'"
```

Ожидаемо: `5.15.2 159.0.8149.0@…`. В новом окружении — `bash scripts/setup-wsl.sh` (ставит `requirements.txt`,
`verify_runtime` импортирует `pypdfium2`).

## 2. Правило и отрисовка — синтетика (CI)

```bash
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_pdf_figure_regions.py -q
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_pdf_figure_render.py -q
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_processing_runtime.py -q
```

Ожидаемо: зелёные; каждый страж — тест с мутацией (спека SC-005), записанной в Changelog спеки при реализации.

## 3. Корпус — тест Rethinking (CI, `integration_local`)

```bash
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_pdf_figure_regions_corpus.py -q
```

Ожидаемо: стр. 151 — одна область `[42.2, 68.2, 353.8, 499.5]` (±0,1), 283 поглощённых картинки, 54 убранных строки,
528 знаков; других областей в книге нет (US1) или ещё 32 рамки фото (US1 + US2).

## 4. Корпус — замер четырёх книг (приёмка, ≈ 2 мин)

```bash
wsl.exe -d Debian --cd "<дерево>" -- bash -lc ". .venv/bin/activate && python -I scripts/measure-composite-figure-regions.py"
```

Ожидаемо — таблица `research.md` R17: Money / Creating / Value — 0 областей, последовательность абзацев и картинок
равна импорту без правила; Rethinking — абзацы 2651 → 2603, картинки 55 → 34. Расхождение — дефект реализации или
спеки (Конституция VIII), не «шум».

## 5. Глазами

Загрузка Rethinking в приложении (задача `Start Project`; достаточно подготовки документа, обработку моделью не
запускать) → в `.run/app.log` событие `pdf_figure_region_rendered` (`page_number: 151`),
итог `pdf_image_extraction_summary` (INFO, `skipped: 0`). Промежуточный DOCX моста без модели —
`scripts/measure-composite-figure-regions.py --save-docx <каталог>` (вызывает `_convert_pdf_text_layer_to_docx`): на
месте Figure 7.1 одна картинка шириной ≈ 4,33 дюйма, её Alt Text — подписи схемы на английском.

## 6. Гарды документов

```bash
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_script_contract_static.py -q
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_documentation_links.py -q
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_spec_status_consistency.py -q
wsl.exe -d Debian --cd "<дерево>" -- bash scripts/test.sh tests/test_typecheck.py -q
```

`test_typecheck.py` — 40–120 с (timeout ≥ 180000 мс): `pypdfium2` теперь в окружении, новые модули типизированы.
