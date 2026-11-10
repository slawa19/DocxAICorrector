# Контракт: группа результата, имена файлов, экспорт PDF (спека 072)

## 1. Файлы на диске (`.run/ui_results/`, FR-007)

Основа имени — `<YYYYmmdd_HHMMSS>_<санированная основа исходника>_<run_id>.result` (`runtime/artifacts.py:163-169`).

| Файл | Ключ результата писателя | Условие | Содержимое |
|---|---|---|---|
| `<основа>.md` | `markdown_path` | всегда | как сейчас |
| `<основа>.docx` | `docx_path` | всегда | DOCX для проверки (spec 070 R4), без изменений |
| `<основа>.tts.txt` | `tts_text_path` | есть текст озвучки | побайтно как до спеки (SC-004) |
| `<основа>.tts.docx` | `tts_docx_path` | `narration_docx_bytes` непуст | `.tts.docx` (FR-003, FR-004) |
| `<основа>.tts.pdf` | `tts_pdf_path` | `narration_pdf_bytes` непуст | `.tts.pdf` (FR-005) |
| `.meta.json`, `.manifest.json`, `.formatting_review.txt` | как сейчас | как сейчас | как сейчас |

- Писатель: `write_ui_result_artifacts(..., narration_docx_bytes: bytes | None = None, narration_pdf_bytes: bytes | None =
  None)`; протокол `ResultArtifactWriter` (`pipeline/contracts.py:151-165`) — те же два аргумента с `None` по умолчанию
  (вызовы с прежним набором аргументов работают).
- Весь выбранный состав — ОДИН вызов `_atomic_write_group` (`runtime/artifacts.py:192-232`): сбой записи любого
  члена откатывает группу (гарантия спеки 023, Non-goals: абсолютной атомарности при аварии процесса нет).
- Перевод и редактура байты озвучки не передают — их группа побайтно прежняя (Anti-regression 2).
- Хранение: `_UI_RESULT_GROUP_SUFFIXES` (`runtime/artifact_retention.py:90-97`) += `.result.tts.docx`,
  `.result.tts.pdf`; группа удаляется целиком. Файл без зарегистрированного суффикса не удаляется никогда
  (`:206-209`) — поэтому суффиксы обязательны (research R12).

## 2. Скачивание с экрана (FR-009)

| Кнопка | Имя файла | MIME | Метка (ru) |
|---|---|---|---|
| DOCX озвучки | `<основа исходника>.tts.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `result.narration_docx` — «DOCX для ElevenLabs Studio» |
| PDF озвучки | `<основа исходника>.tts.pdf` | `application/pdf` | `result.narration_pdf` — «PDF» |
| TXT озвучки | `<основа исходника>.tts.txt` (`ui/_ui.py:92-93`, без изменений) | `text/plain` | `result.narration_elevenlabs` — без изменений |
| DOCX для проверки | `<основа>_edited.docx` (`:84-85`, без изменений) | как сейчас | `result.docx_inspection` |
| Markdown | `<основа>_edited.md` (`:88-89`, без изменений) | `text/markdown` | `result.markdown_inspection` |

«Основа исходника» — `Path(original_filename).stem`, как у `_build_narration_filename`.

## 3. Экспорт PDF (FR-005)

Команда (одна строка списка аргументов, без shell):

```text
<find_soffice_binary()>
  -env:UserInstallation=<Path(tmp)/"lo_profile">.as_uri()
  --headless
  --norestore
  --convert-to pdf:writer_pdf_Export:{"ExportBookmarks":{"type":"boolean","value":"true"}}
  --outdir <tmp>
  <tmp>/<stem>.tts.docx
```

- `tmp` — `tempfile.TemporaryDirectory(prefix="docxaicorrector_tts_pdf_")`, удаляется вместе с профилем и файлами в
  любом исходе; профиль НОВЫЙ на каждую конвертацию (общий профиль: 5 из 10 параллельных конвертаций без PDF,
  research R7).
- Ожидание — `run_completed_process(..., cleanup_process_group=True, timeout_seconds=60)`; тайм-аут завершает группу
  процессов.
- Результат принимается, если `<tmp>/<stem>.tts.pdf` существует, непуст и начинается с `b"%PDF-"`; иначе причина
  `data-model.md` §4.
- Поиск бинаря — `find_soffice_binary()` (`runtime/external_process.py`); импорт PDF/DOC зовёт ту же функцию
  (сейчас три копии, `processing/processing_runtime.py:454`, `:1244`, `:1282`).

## 4. Содержимое `.tts.docx` (FR-003, FR-004)

- Шаблон python-docx; стили только `Normal` и `Heading 1`, оба со шрифтом `Times New Roman` во всех слотах `w:rFonts`.
- Один абзац DOCX на абзац плана; один run; одиночный `\n` → `<w:br/>` (python-docx), `paragraph.text` возвращает
  строку плана байт в байт (включая U+0301, регистр, `*`, `_`, `#`, `<`, `>`, тире).
- Нет: пустых абзацев, колонтитулов (`word/header*.xml`, `word/footer*.xml` в zip отсутствуют), поля оглавления,
  картинок, таблиц, стилей `Heading 2`…`Heading 9`.
- Свойства: `title`, `author`, `comments` — пустые (непустой `title` Studio вставляет первым озвучиваемым абзацем — проба владельца 2026-11-10).
