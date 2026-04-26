# PDF Source Import Specification

Дата: 2026-04-26

## Цель

Добавить поддержку PDF как входного источника для текущего AI DOCX Editor без создания параллельного PDF-pipeline. PDF должен импортироваться через нормализацию в канонический DOCX, после чего существующие этапы разбора, подготовки, AI-обработки, восстановления форматирования, вставки изображений и сохранения артефактов продолжают работать по текущему DOCX-контракту.

## Ключевое Архитектурное Решение

PDF является только input format, но не internal document model.

Канонический поток:

```text
uploaded PDF
  -> processing_runtime.resolve_upload_contract()
  -> processing_runtime.normalize_uploaded_document()
  -> normalized DOCX bytes
  -> validate_docx_source_bytes()
  -> extract_document_content_with_normalization_reports()
  -> prepare_document_for_processing()
  -> run_document_processing()
  -> output Markdown/DOCX artifacts
```

Запрещенный поток:

```text
uploaded PDF
  -> direct PDF extraction
  -> separate ParagraphUnit/ImageAsset builder
  -> separate formatting restoration path
```

Такой поток не входит в эту доработку, потому что создаст второй document model и продублирует сложную DOCX-специфику: абзацы, стили, заголовки, списки, таблицы, изображения, captions, relations, paragraph properties и source-to-target formatting restoration.

## Область Изменений

### Основные файлы

- `processing_runtime.py`
- `app.py`
- `constants.py` при необходимости отдельного лимита PDF
- `tests/test_processing_runtime.py`
- `tests/test_app_preparation.py` или ближайший существующий UI/upload тест

### Файлы, которые не должны получать PDF-specific логику в MVP

- `document_extraction.py`
- `document.py`
- `formatting_transfer.py`
- `document_pipeline.py`
- `preparation.py`, кроме случаев, когда потребуется только отображение source metadata без изменения pipeline-контракта

## Функциональные Требования

### FR-1. UI должен принимать PDF

В `app.py` загрузчик должен принимать `.pdf` наряду с `.docx` и `.doc`.

Текущий контракт:

```python
st.file_uploader("Загрузите DOCX/DOC-файл", type=["docx", "doc"])
```

Целевой контракт:

```python
st.file_uploader("Загрузите DOCX/DOC/PDF-файл", type=["docx", "doc", "pdf"])
```

Дополнительно UI должен показывать пользователю понятное ограничение: PDF импортируется через преобразование в DOCX, а качество сохранения структуры зависит от качества PDF и backend-конвертера.

### FR-2. Runtime должен распознавать PDF

В `processing_runtime.py` нужно добавить PDF magic bytes:

```python
_PDF_MAGIC = b"%PDF-"
```

Функция `_detect_uploaded_document_format()` должна возвращать `"pdf"`, если:

- bytes начинаются с `%PDF-`; или
- расширение файла `.pdf`, если magic bytes не распознаны, но имя явно PDF.

Приоритет detection должен оставаться безопасным:

1. DOCX zip magic.
2. Legacy DOC magic.
3. PDF magic.
4. Расширения `.docx`, `.doc`, `.pdf`.
5. `unknown`.

Примечание MVP: detection по magic bytes использует только проверку `source_bytes.startswith(b"%PDF-")`.

PDF-спецификация формально допускает наличие до 1024 байт префиксного мусора перед `%PDF-`, но такие случаи не входят в обязательный ingestion contract MVP и могут распознаваться только по расширению `.pdf`.

### FR-3. PDF должен нормализоваться в DOCX

`normalize_uploaded_document()` должен обрабатывать `source_format == "pdf"` аналогично legacy `.doc`:

- построить normalized filename через `_build_normalized_docx_filename(filename)`;
- вызвать PDF converter;
- вернуть `NormalizedUploadedDocument` с:
  - `original_filename`: исходное имя PDF;
  - `filename`: имя с `.docx`;
  - `content_bytes`: bytes полученного DOCX;
  - `source_format`: `"pdf"`;
  - `conversion_backend`: имя backend-а, например `"libreoffice"`.

### FR-4. Downstream должен получать только DOCX bytes

После `freeze_uploaded_file()` и `freeze_resolved_upload()` все downstream-этапы должны получать normalized DOCX bytes.

`application_flow._prepare_run_context_core()` должен продолжать вызывать:

```python
validate_docx_source_bytes(uploaded_file_bytes)
```

Для PDF это должна быть проверка уже конвертированного DOCX, а не исходного PDF.

### FR-5. Source identity для PDF должен строиться по исходным PDF bytes

Сейчас `_build_uploaded_file_token_components()` использует source bytes для `.doc`, но normalized bytes для остальных форматов.

Целевой контракт:

```python
identity_bytes = (
    source_bytes
    if normalized_document.source_format in {"doc", "pdf"}
    else normalized_document.content_bytes
)
```

Обоснование: повторная загрузка того же PDF должна давать тот же source token независимо от версии LibreOffice, платформы или minor-различий в DOCX-конвертации.

### FR-6. Ошибка отсутствующего converter должна быть пользовательски понятной

Если PDF загружен, но converter недоступен, runtime должен выбрасывать `RuntimeError` с понятным сообщением на русском языке.

Пример:

```text
Загружен PDF-файл, но автоконвертация недоступна. Установите LibreOffice (`soffice`) внутри WSL.
```

Ошибка должна проходить через существующий механизм `present_error()` / preparation failure без отдельного UI-пути.

### FR-6a. Некорректный или поврежденный PDF может завершиться ошибкой конвертации

MVP не обязан выполнять отдельную структурную pre-validation PDF beyond format detection.

Следствие:

- файл с расширением `.pdf` или magic bytes PDF может быть принят upload boundary;
- но поврежденный, частично битый или фактически невалидный PDF может завершиться ошибкой на этапе LibreOffice conversion;
- такая ошибка считается корректным MVP-поведением и должна проходить через существующий preparation failure path без отдельного special-case UI.

### FR-7. Сканированные PDF не входят в MVP

MVP не обязан выполнять OCR.

Если LibreOffice создает пустой или непригодный DOCX, текущая downstream-валидация и подготовка должны завершиться ошибкой или нулевым числом jobs. Допускается улучшить сообщение, но OCR не добавляется в рамках этой спецификации.

### FR-8. Password-protected PDF не поддерживаются

Password-protected / encrypted PDF не поддерживаются в MVP.

Ожидаемое поведение: converter или downstream preparation завершается понятной ошибкой через существующий error path без отдельного UI-flow для ввода пароля.

## Нефункциональные Требования

### NFR-1. Минимальность изменений

Доработка должна быть максимально локализована в upload normalization boundary. Нельзя добавлять PDF-specific ветвления в document extraction, formatting restoration и document pipeline без отдельного обоснования.

### NFR-2. Совместимость с текущим DOCX/DOC поведением

Поведение `.docx` и `.doc` не должно измениться, кроме безопасного refactor-а detection/token logic.

### NFR-3. WSL-first runtime

Реальная конвертация и интеграционные проверки должны выполняться через canonical WSL runtime по правилам `AGENTS.md`.

Канонический тестовый entry point:

```bash
bash scripts/test.sh tests/test_processing_runtime.py -vv
```

Если агентский shell не WSL, использовать transport:

```bash
echo START && wsl.exe -d Debian bash -c "cd /mnt/d/www/projects/2025/DocxAICorrector && . .venv/bin/activate && pytest tests/test_processing_runtime.py -vv --tb=short 2>&1" && echo DONE
```

### NFR-4. Безопасность временных файлов

PDF converter должен использовать `tempfile.TemporaryDirectory()` и не писать исходные или промежуточные файлы в project root.

Все temporary files должны удаляться автоматически после конвертации.

### NFR-5. Deterministic cache identity

Кеш подготовки и restart-source semantics должны зависеть от исходного PDF, а не от nondeterministic DOCX output converter-а.

### NFR-6. File size handling for PDF import

В MVP PDF использует тот же project-wide upload limit, что и DOCX/DOC, если отдельный лимит не согласован явно.

Нужно учитывать два разных барьера:

1. Streamlit upload limit (`server.maxUploadSize`) и ранняя UI-проверка размера.
2. Downstream DOCX archive validation для уже конвертированного DOCX.

Следствия:

- при изменении лимита нужно синхронно обновлять Streamlit upload configuration и соответствующую app-константу ранней проверки размера;
- PDF может быть успешно принят uploader-ом, но resulting DOCX после conversion может быть отклонен downstream-валидацией как слишком большой или неподдерживаемый архив;
- scanned PDF имеют повышенный риск large-memory / oversized-DOCX поведения, и это считается допустимым ограничением MVP.

### NFR-7. Converter timeout cleanup

При таймауте PDF-конвертации runtime не должен оставлять висячие LibreOffice-процессы в WSL/project runtime.

Если текущая обертка `subprocess.run(..., timeout=...)` не гарантирует cleanup всего process tree `soffice`, реализация должна использовать запуск в отдельной process group/session и завершать всю группу по timeout.

Проверка этого поведения должна выполняться в canonical WSL runtime, а не только в unit tests.

## Предлагаемая Реализация

### Шаг 1. Добавить PDF detection

Файл: `processing_runtime.py`

Добавить рядом с `_DOCX_ZIP_MAGIC` и `_LEGACY_DOC_MAGIC`:

```python
_PDF_MAGIC = b"%PDF-"
```

Обновить `_detect_uploaded_document_format()`:

```python
def _detect_uploaded_document_format(*, filename: str, source_bytes: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if source_bytes.startswith(_DOCX_ZIP_MAGIC):
        return "docx"
    if source_bytes.startswith(_LEGACY_DOC_MAGIC):
        return "doc" if suffix == ".doc" else "unknown"
    if source_bytes.startswith(_PDF_MAGIC):
        return "pdf"
    if suffix == ".docx":
        return "docx"
    if suffix == ".doc":
        return "doc"
    if suffix == ".pdf":
        return "pdf"
    return "unknown"
```

Явно не требуется поддержка PDF с префиксным мусором перед `%PDF-` beyond suffix fallback.

### Шаг 2. Добавить PDF converter

Файл: `processing_runtime.py`

Добавить функцию рядом с legacy DOC converters:

```python
def _convert_pdf_to_docx(*, filename: str, source_bytes: bytes) -> tuple[bytes, str]:
    soffice_path = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice_path:
        raise RuntimeError(
            "Загружен PDF-файл, но автоконвертация недоступна. "
            "Установите LibreOffice (`soffice`) внутри WSL."
        )

    normalized_filename = _build_normalized_docx_filename(filename)
    with tempfile.TemporaryDirectory(prefix="docxaicorrector_pdf_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        input_path = temp_dir / (Path(filename).name or "document.pdf")
        output_path = temp_dir / Path(normalized_filename).name
        input_path.write_bytes(source_bytes)
        _run_completed_process(
            [
                soffice_path,
                "--headless",
                "--infilter=writer_pdf_import",
                "--convert-to",
                "docx",
                "--outdir",
                str(temp_dir),
                str(input_path),
            ],
            error_message="Не удалось конвертировать PDF через LibreOffice.",
        )
        if not output_path.exists():
            raise RuntimeError("Не удалось конвертировать PDF через LibreOffice: выходной DOCX не создан.")
        output_bytes = output_path.read_bytes()
        if not output_bytes:
            raise RuntimeError("Не удалось конвертировать PDF через LibreOffice: выходной DOCX пуст.")
        return output_bytes, "libreoffice"
```

Дополнительные требования реализации:

- converter не должен писать input/output за пределы `tempfile.TemporaryDirectory()`;
- LibreOffice PDF conversion должен использовать Writer PDF import filter `--infilter=writer_pdf_import`; без него `soffice --convert-to docx source.pdf` может завершиться `no export filter` и не создать DOCX;
- timeout path не должен оставлять висячие `soffice`-процессы в runtime;
- если LibreOffice фактически создает файл с другим basename, реализация должна иметь fallback поиска единственного `.docx` в `temp_dir`, а не падать сразу по exact-name mismatch.

### Шаг 3. Подключить PDF в `normalize_uploaded_document()`

Файл: `processing_runtime.py`

Изменить normalized filename condition:

```python
normalized_filename = _build_normalized_docx_filename(filename) if source_format in {"doc", "docx", "pdf"} else filename
```

Добавить ветку:

```python
if source_format == "pdf":
    converted_bytes, conversion_backend = _convert_pdf_to_docx(
        filename=filename,
        source_bytes=source_bytes,
    )
    return NormalizedUploadedDocument(
        original_filename=filename,
        filename=normalized_filename,
        content_bytes=converted_bytes,
        source_format=source_format,
        conversion_backend=conversion_backend,
    )
```

### Шаг 4. Обновить source token identity

Файл: `processing_runtime.py`

Изменить `_build_uploaded_file_token_components()`:

```python
def _build_uploaded_file_token_components(*, normalized_document: NormalizedUploadedDocument, source_bytes: bytes) -> tuple[int, str]:
    identity_bytes = source_bytes if normalized_document.source_format in {"doc", "pdf"} else normalized_document.content_bytes
    identity_hash = hashlib.sha256(identity_bytes).hexdigest()[:16]
    return len(identity_bytes), identity_hash
```

### Шаг 5. Обновить UI uploader

Файл: `app.py`

Изменить:

```python
uploaded_widget_file = st.file_uploader("Загрузите DOCX/DOC-файл", type=["docx", "doc"])
```

На:

```python
uploaded_widget_file = st.file_uploader("Загрузите DOCX/DOC/PDF-файл", type=["docx", "doc", "pdf"])
```

Добавить короткий `st.caption()` или существующий UI-note рядом с uploader:

```python
st.caption("PDF импортируется через преобразование в DOCX; качество структуры и форматирования зависит от исходного PDF.")
```

Если caption визуально нежелателен, можно добавить текст в existing help/intro block.

Дополнительно нужно синхронно обновить остальной user-facing copy рядом с upload flow, чтобы UI не оставался DOCX/DOC-only по формулировкам:

- title/intro text;
- size limit error text;
- любые nearby hints, где перечисляются поддерживаемые форматы.

### Шаг 6. Добавить tests для runtime normalization

Файл: `tests/test_processing_runtime.py`

Нужно покрыть:

1. PDF detection по magic bytes.
2. PDF detection по suffix `.pdf`.
3. `normalize_uploaded_document()` для PDF возвращает DOCX filename и conversion metadata.
4. `resolve_upload_contract()` для PDF строит token по исходным PDF bytes.
5. Отсутствие LibreOffice дает понятный `RuntimeError`.
6. PDF token остается стабильным при разных converter outputs.
7. Fallback по `.pdf` suffix работает, даже если magic bytes не распознаны.
8. При filename mismatch converter output implementation либо находит единственный `.docx`, либо тестом зафиксировано ожидаемое поведение fallback-а.
9. malformed `.pdf` / converter failure проходит через ожидаемый `RuntimeError` path.

Тесты не должны запускать реальный LibreOffice в unit path. Нужно monkeypatch-ить:

- `shutil.which`;
- `_run_completed_process`;
- при необходимости временный output file через fake runner, который пишет DOCX bytes в ожидаемый path.

Пример сценария:

```python
def test_normalize_uploaded_pdf_converts_to_docx(monkeypatch):
    pdf_bytes = b"%PDF-1.7\ncontent"
    docx_bytes = b"PK\x03\x04converted-docx"

    monkeypatch.setattr(processing_runtime.shutil, "which", lambda name: "/usr/bin/soffice" if name == "soffice" else None)

    def fake_run_completed_process(command, *, error_message, text=True, timeout_seconds=120):
        outdir = Path(command[command.index("--outdir") + 1])
        input_path = Path(command[-1])
        output_path = outdir / input_path.with_suffix(".docx").name
        output_path.write_bytes(docx_bytes)
        return object()

    monkeypatch.setattr(processing_runtime, "_run_completed_process", fake_run_completed_process)

    normalized = processing_runtime.normalize_uploaded_document(filename="source.pdf", source_bytes=pdf_bytes)

    assert normalized.original_filename == "source.pdf"
    assert normalized.filename == "source.docx"
    assert normalized.content_bytes == docx_bytes
    assert normalized.source_format == "pdf"
    assert normalized.conversion_backend == "libreoffice"
```

### Шаг 7. Добавить UI/upload test

Файл: ближайший существующий test для `app.py`, вероятно `tests/test_app_preparation.py`.

Проверить, что `st.file_uploader()` вызывается с `type=["docx", "doc", "pdf"]`.

Если существующие тесты monkeypatch-ят `st.file_uploader` и не проверяют kwargs, достаточно обновить expected label/supported types там, где они уже проверяются.

Также нужно покрыть, что user-facing copy около upload flow не осталась в состоянии `DOCX/DOC only` после добавления PDF support.

### Шаг 7a. Добавить boundary test для downstream DOCX contract

Файл: `tests/test_application_flow.py`

Нужно покрыть сценарий, аналогичный существующему legacy `.doc` path:

- исходно загружен `source.pdf`;
- `freeze_uploaded_file()` возвращает normalized payload с `.docx` filename и DOCX bytes;
- `application_flow.prepare_run_context()` / `_prepare_run_context_core()` передает в `validate_docx_source_bytes()` именно converted DOCX bytes;
- downstream preparation получает уже normalized DOCX payload, а не исходные PDF bytes.

Этот тест является прямым regression-proof для FR-4 и не должен заменяться только runtime-unit-тестами.

### Шаг 8. Обновить документацию при необходимости

Если в README или user-facing docs явно написано, что поддерживаются только DOCX/DOC, обновить на DOCX/DOC/PDF с ограничением:

```text
PDF поддерживается через импорт в DOCX. Для сканированных PDF OCR не выполняется.
```

Создавать отдельную пользовательскую документацию не обязательно для MVP, если такой список форматов отсутствует.

## Acceptance Criteria

### AC-1. DOCX сохраняет прежнее поведение

Загрузка `.docx` не запускает converter и downstream получает исходные DOCX bytes.

### AC-2. DOC сохраняет прежнее поведение

Загрузка `.doc` продолжает использовать существующую конвертацию через LibreOffice или antiword+pandoc.

### AC-3. PDF распознается

`_detect_uploaded_document_format(filename="x.pdf", source_bytes=b"%PDF-...")` возвращает `"pdf"`.

### AC-4. PDF нормализуется в DOCX

`normalize_uploaded_document(filename="x.pdf", source_bytes=...)` возвращает `NormalizedUploadedDocument` с `filename == "x.docx"`, `source_format == "pdf"` и DOCX bytes.

### AC-5. Downstream получает DOCX

После `freeze_uploaded_file()` для PDF `FrozenUploadPayload.content_bytes` начинается с DOCX zip magic или является валидным DOCX archive в интеграционном сценарии.

Дополнительно `application_flow._prepare_run_context_core()` вызывает `validate_docx_source_bytes()` уже на converted DOCX bytes, а не на исходном PDF.

### AC-6. PDF source token стабилен относительно converter output

Для одного и того же PDF token должен оставаться одинаковым, даже если fake converter возвращает разные DOCX bytes.

### AC-7. Ошибка converter-а понятна

Если `soffice`/`libreoffice` не найден, пользователь получает понятное сообщение о недоступной PDF-конвертации.

### AC-8. UI принимает PDF

Streamlit uploader допускает `.pdf`.

И adjacent user-facing copy в upload flow не противоречит заявленной поддержке PDF.

### AC-8a. Upload и post-conversion size limits определены явно

Спецификация и реализация явно различают:

- входной upload limit для PDF;
- downstream validation limit для resulting DOCX.

Если PDF проходит upload boundary, но resulting DOCX нарушает DOCX archive limits, это трактуется как корректный post-conversion failure path, а не как undefined behavior.

### AC-8b. Timeout cleanup определен явно

При таймауте PDF conversion runtime не оставляет висячие `soffice`-процессы в canonical WSL runtime, либо это явно подтверждено реализацией process-group cleanup.

### AC-9. Нет PDF-specific ветвлений в core pipeline

`document_extraction.py`, `formatting_transfer.py` и `document_pipeline.py` не получают PDF-specific branches в MVP.

## План Реализации

### Этап 1. Runtime support

- [ ] Добавить `_PDF_MAGIC` в `processing_runtime.py`.
- [ ] Обновить `_detect_uploaded_document_format()`.
- [ ] Добавить `_convert_pdf_to_docx()`.
- [ ] Подключить ветку `source_format == "pdf"` в `normalize_uploaded_document()`.
- [ ] Обновить `_build_uploaded_file_token_components()` для PDF source identity.

### Этап 2. UI support

- [ ] Обновить label uploader на `DOCX/DOC/PDF`.
- [ ] Добавить `pdf` в `type=[...]`.
- [ ] Добавить короткое user-facing предупреждение о best-effort PDF import.
- [ ] Синхронно обновить title/intro/size-limit copy рядом с upload flow.

### Этап 3. Unit tests

- [ ] Тест detection по PDF magic bytes.
- [ ] Тест detection по `.pdf` suffix.
- [ ] Тест успешной PDF normalization через monkeypatched LibreOffice runner.
- [ ] Тест отсутствующего LibreOffice.
- [ ] Тест PDF token identity по original bytes.
- [ ] Тест malformed/failing PDF conversion path.
- [ ] Тест fallback поведения при converter output filename mismatch.
- [ ] Тест UI uploader supported types.

### Этап 3a. Boundary tests

- [ ] Тест `application_flow.prepare_run_context()` подтверждает, что для PDF downstream получает converted DOCX bytes.

### Этап 4. Verification

- [ ] Определить shell identity через `uname` и `pwd` перед первым ручным тестовым запуском.
- [ ] Проверить layout `.venv`: `.venv/bin/activate`, `.venv/bin/python`, `.venv/Scripts/python.exe`, `.venv/Scripts/pytest.exe`.
- [ ] Запустить targeted tests через canonical WSL entry point:

```bash
bash scripts/test.sh tests/test_processing_runtime.py -vv
```

- [ ] При изменении app tests запустить соответствующий файл:

```bash
bash scripts/test.sh tests/test_app_preparation.py -vv
```

- [ ] Если shell не WSL, использовать `wsl.exe -d Debian` transport с `echo START` и `echo DONE`.
- [ ] Отдельно проверить timeout/cleanup behavior converter-а в canonical WSL runtime, если меняется subprocess orchestration.

### Этап 5. Optional manual validation

- [ ] Подготовить небольшой текстовый PDF.
- [ ] Загрузить через UI.
- [ ] Убедиться, что preparation доходит до построения jobs.
- [ ] Убедиться, что результат сохраняется в `.run/ui_results/` и лог содержит `ui_result_artifacts_saved` после обработки.
- [ ] Зафиксировать, что сканированный PDF без OCR не является поддержанным сценарием MVP.

## Риски И Ограничения

### R-1. LibreOffice PDF conversion может быть нестабильной

LibreOffice может создавать DOCX с плохими paragraph boundaries, большим числом text boxes или разрывами строк. Это ожидаемый риск MVP.

Митигация: явно маркировать PDF import как best-effort и не обещать DOCX-level formatting preservation.

### R-2. Сканированные PDF не содержат текста

Без OCR pipeline может получить пустой или почти пустой DOCX.

Митигация: OCR не входит в MVP. При необходимости добавить отдельную будущую спецификацию `PDF OCR ingestion`.

### R-3. Converter output может быть nondeterministic

Разные версии LibreOffice могут создавать разные DOCX bytes.

Митигация: source token для PDF строится по original PDF bytes.

### R-4. Большие PDF могут долго конвертироваться

Текущий `_DOC_CONVERSION_TIMEOUT_SECONDS = 120` может быть недостаточен для больших файлов.

Митигация MVP: использовать текущий timeout. Если появятся реальные таймауты, выделить отдельный `_PDF_CONVERSION_TIMEOUT_SECONDS`.

Дополнительно: даже при успешном upload scanned/image-heavy PDF могут приводить к повышенному расходу памяти или oversized DOCX после conversion. Это ограничение принимается в MVP.

### R-5. Filename mismatch после LibreOffice conversion

LibreOffice может создать output filename не строго равный expected `Path(normalized_filename).name`.

Митигация MVP: реализация должна иметь fallback поиска одного `.docx` в temp dir, если exact basename mismatch реально проявляется.

### R-6. Timeout может не прибрать весь LibreOffice process tree

Даже если основной subprocess timeout отрабатывает корректно, `soffice` может оставлять дочерние процессы в WSL runtime.

Митигация: при необходимости использовать process-group/session cleanup и проверять это в canonical runtime.

### R-7. Некоторые валидные PDF с префиксным мусором не будут распознаны по magic bytes

Формально PDF-спецификация допускает небольшой leading garbage перед `%PDF-`.

Митигация MVP: считать это допустимым ограничением и поддерживать такие случаи только через suffix fallback `.pdf`.

## Out Of Scope

- OCR для сканированных PDF.
- Прямое извлечение PDF blocks через PyMuPDF/pdfplumber.
- Восстановление layout PDF как Word formatting.
- Отдельная модель `PdfParagraphUnit`.
- Сохранение PDF как output artifact.
- Поддержка password-protected PDF.
- Поддержка PDF forms/annotations как editable content.

## Будущее Расширение

Если качество LibreOffice окажется недостаточным, следующий архитектурный шаг: выделить `source_ingestion/` слой.

Возможная структура:

```text
source_ingestion/
  __init__.py
  contracts.py
  docx_adapter.py
  legacy_doc_adapter.py
  pdf_adapter.py
```

Возможный контракт:

```python
@dataclass(frozen=True)
class NormalizedSourceDocument:
    original_filename: str
    normalized_filename: str
    normalized_bytes: bytes
    source_format: str
    normalized_format: str
    conversion_backend: str | None
```

Этот refactor не нужен для MVP, потому что текущий `processing_runtime.py` уже является рабочим ingestion boundary.

## Implementation Checklist

- [ ] `processing_runtime.py`: добавлен `_PDF_MAGIC`.
- [ ] `processing_runtime.py`: `_detect_uploaded_document_format()` распознает PDF.
- [ ] `processing_runtime.py`: добавлена `_convert_pdf_to_docx()`.
- [ ] `processing_runtime.py`: `normalize_uploaded_document()` обрабатывает `source_format == "pdf"`.
- [ ] `processing_runtime.py`: PDF token identity использует original PDF bytes.
- [ ] `processing_runtime.py`: timeout path не оставляет висячие LibreOffice-процессы или это явно обеспечено process cleanup logic.
- [ ] `processing_runtime.py`: converter умеет fallback-нуться на единственный `.docx` в temp dir при basename mismatch.
- [ ] `processing_runtime.py`: PDF converter использует LibreOffice Writer PDF import filter `--infilter=writer_pdf_import`.
- [ ] `app.py`: uploader принимает `pdf`.
- [ ] `app.py`: UI сообщает о best-effort PDF import.
- [ ] `app.py`: adjacent upload copy синхронизирован с поддержкой PDF.
- [ ] Size handling: явно сохранен или обновлен project-wide upload limit contract.
- [ ] Tests: PDF detection по magic bytes.
- [ ] Tests: PDF detection по suffix.
- [ ] Tests: успешная PDF normalization.
- [ ] Tests: понятная ошибка при отсутствии converter-а.
- [ ] Tests: стабильный PDF token при разных converter outputs.
- [ ] Tests: failing/malformed PDF conversion path.
- [ ] Tests: filename mismatch fallback или явно зафиксированное fallback behavior.
- [ ] Tests: UI uploader включает `pdf`.
- [ ] Tests: downstream boundary подтверждает DOCX-only contract для PDF.
- [ ] Verification: targeted runtime tests пройдены через canonical path.
- [ ] Verification: затронутые app tests пройдены через canonical path.
- [ ] Verification: size-limit semantics и timeout cleanup semantics проверены и явно задокументированы.
- [ ] Documentation: при наличии user-facing списка форматов он обновлен.

## Definition Of Done

Доработка считается завершенной, когда пользователь может загрузить текстовый PDF через UI, приложение преобразует его в DOCX на upload normalization boundary, существующий pipeline обрабатывает normalized DOCX без PDF-specific ветвлений в core document pipeline, targeted tests подтверждают detection, normalization, downstream DOCX-only boundary, token stability и UI upload contract, а size-limit semantics и timeout cleanup semantics описаны явно и не оставлены как неявное поведение.
