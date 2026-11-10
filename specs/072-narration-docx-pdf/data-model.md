# Data Model: текст для озвучки в DOCX и PDF

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

Сущности новые или меняющиеся. Пути — относительно `src/docxaicorrector/`; ссылки сверены на `f6de2fd`. Все словари
значений ЗАКРЫТЫ: неизвестное значение — ошибка теста, не молчаливое «прочее». Полные тексты в лог не идут
(LOGGING §1.5): в событиях — ID, числа и коды причин.

## 1. Запись озвучки: уровень заголовка (FR-002, research R1)

`pipeline/audiobook_pass.py`:

```text
NarrationParagraphRecord(frozen)          # :116-126, поле добавляется ПОСЛЕДНИМ
    ...существующие поля без изменений...
    heading_level: int | None = None      # 1..6 — только при роли "heading" и префиксе исходника; иначе None

narration_heading_level(*, role: str, source_text: str) -> int | None
    role.strip().casefold() == "heading" и ^(#{1,6})[ \t]+\S в source_text.lstrip() → len(#); иначе None

FinalizedAudiobookBlock(frozen)           # :148-154
    ...существующие поля...
    heading_levels_by_id: Mapping[str, int]   # только ID с уровнем; рядом с texts_by_id
```

Правила: уровень вычисляется ОДИН раз — в `finalize_audiobook_block` при создании записи; неадресуемая запись
(`paragraph_id == ""`) уровень получает так же (по своему `role`/`source_text`; у неё `source_text == ""` → `None`).
`rebuild_block_with_narration_texts(..., heading_levels_by_id=...)` ставит префикс `"#" * level` перед текстом
озвучки ровно в тех случаях, что и сегодня (текст непуст и не начинается с `#`); характеристический тест закрепляет
равенство старого и нового текста блока.

## 2. Группа сборки (FR-001, research R2)

`pipeline/narration_postprocess.py`:

```text
NarrationGroup(frozen)
    paragraph_ids: tuple[str, ...]   # ID записей абзаца после детерминированных склеек, по порядку ("" — неадресуемая)
    role: str                        # роль первой записи ("body", "heading", ...)
    heading_level: int | None        # уровень первой записи, если role == "heading"; иначе None
    text: str                        # РОВНО group_text, из которого собирается .tts.txt

NarrationAssembly(frozen)            # :100-106
    text: str
    join_pairs, boundary_check, parsed_paragraph_count, first_mismatch_paragraph_id   # без изменений
    groups: tuple[NarrationGroup, ...]                                                 # новое, последним
```

Инварианты (тесты): `text == "\n\n".join(g.text for g in groups)`; группа с ролью `heading` состоит из одной записи;
сумма `len(g.paragraph_ids)` = число записей. Состояние прогона: `ProcessingState.narration_groups:
list[NarrationGroup]` (`pipeline/contracts.py:260`, рядом с `narration_joined_paragraph_id_pairs`), пишет
`_build_narration_text`, по умолчанию `[]`.

## 3. План документа озвучки (FR-003, FR-006, research R3)

`pipeline/narration_document.py` (новый, чистый):

```text
NarrationGroupLike(Protocol): paragraph_ids, role, heading_level, text

NARRATION_DOCUMENT_STYLE_HEADING_1 = "Heading 1"
NARRATION_DOCUMENT_STYLE_NORMAL = "Normal"

NarrationDocumentParagraph(frozen)
    style: Literal["Heading 1", "Normal"]
    text: str
    paragraph_ids: tuple[str, ...]
    source_heading_level: int | None   # минимальный уровень серии, для абзаца-заголовка (в т.ч. ставшего Normal); иначе None

HeadingMerge(frozen)
    paragraph_ids: tuple[str, ...]     # все ID членов серии
    levels: tuple[int, ...]            # уровни членов по порядку, напр. (2, 1)
    style: Literal["Heading 1", "Normal"]

StudioLimits(frozen)
    heading1_count: int
    chapter_count_for_limits: int          # отрезков для лимита 400 (с «вступительной» главой, если она непуста; без заголовков — 1)
    max_chapter_paragraph_count: int       # без самого абзаца Heading 1
    max_paragraph_chars: int               # len(text) по всем абзацам плана
    exceeded: tuple[str, ...]              # подмножество ("chapters", "chapter_paragraphs", "paragraph_chars") в этом порядке

NarrationDocumentPlan(frozen)
    paragraphs: tuple[NarrationDocumentParagraph, ...]
    chapter_level: int | None              # минимальный уровень среди групп-заголовков с уровнем
    heading_levels_present: tuple[int, ...]   # отсортированные различные уровни
    heading_merges: tuple[HeadingMerge, ...]
    demoted_heading_count: int             # абзацев плана из заголовков, ставших Normal (серия считается один раз)
    studio_limits: StudioLimits

STUDIO_MAX_CHAPTERS = 500; STUDIO_MAX_CHAPTER_PARAGRAPHS = 400; STUDIO_MAX_PARAGRAPH_CHARS = 5000   # строго больше → exceeded

build_narration_document_plan(groups: Sequence[NarrationGroupLike]) -> NarrationDocumentPlan
```

Правила (FR-003 в редакции 2026-11-10): серия — подряд идущие группы-заголовки С уровнем, член принимается, если
его уровень `<=` минимуму вошедших; иначе новая серия. Тело и заголовок без уровня закрывают серию и идут `Normal`.
Текст серии — части через `". "`; если часть уже кончается на `.`, добавляется только пробел. Стиль серии —
`Heading 1` при `min(levels) == chapter_level`, иначе `Normal`. Ни одно правило не читает слова текста (VII).

Таблица примеров (обязательна в тестах SC-002; уровни → абзацы плана):

| Вход (уровни подряд, без тела между) | Абзацы плана |
|---|---|
| `{1}` один заголовок, тело | H1, Normal… |
| `2 → 1` (при `chapter_level = 1`) | один H1 «A. B», merge `(2, 1)` |
| `1 → 1` | один H1, merge `(1, 1)` |
| `1 → 2` | H1, затем Normal (уровень 2, не слит) |
| `1 → 2 → 1` | H1; затем H1 «B. C», merge `(2, 1)` |
| уровни книги `{2, 4}`: `2`, тело, `4`, тело | H1, Normal, Normal (из 4), Normal |
| `3 → 3` при `chapter_level = 1` | один Normal «A. B», merge `(3, 3)`, style `Normal` |
| заголовок в конце книги | остаётся (H1 или Normal по уровню) |
| роль `heading`, уровень `None` | Normal, серию не продолжает и не начинает |
| ни одного заголовка | все Normal; `heading1_count = 0`, одна глава для лимита 400 |

## 4. Экспорт PDF (FR-005, research R6–R8)

`runtime/external_process.py` (новый): `find_soffice_binary() -> str | None`; `run_completed_process(command, *,
error_message, text=True, timeout_seconds=120, cleanup_process_group=False)` и `terminate_process_tree(process)` —
дословный перенос из `processing/processing_runtime.py:321-410`.

`generation/narration_pdf.py` (новый):

```text
NARRATION_PDF_TIMEOUT_SECONDS = 60
NARRATION_PDF_FILTER = 'pdf:writer_pdf_Export:{"ExportBookmarks":{"type":"boolean","value":"true"}}'

NARRATION_PDF_UNAVAILABLE_REASONS = (
    "docx_not_built",      # DOCX озвучки не собран — PDF не пробуется
    "soffice_not_found",   # find_soffice_binary() -> None
    "timeout",             # RuntimeError помощника с превышением времени (группа процессов завершена)
    "failed",              # ненулевой код / OSError запуска
    "missing_output",      # процесс завершился, файла <stem>.tts.pdf нет
    "empty_output",        # файл есть, 0 байт
    "not_pdf",             # файл не начинается с b"%PDF-"
)

NarrationPdfOutcome(frozen)
    pdf_bytes: bytes | None
    reason: str | None           # None ⇔ pdf_bytes непуст
    seconds: float               # стена конвертации (0.0, если не запускалась)
    detail: str                  # ≤ 300 знаков хвоста stderr/сообщения; никаких текстов книги

export_narration_pdf(docx_bytes, *, stem, timeout_seconds=60, runner=run_completed_process,
                     find_soffice=find_soffice_binary) -> NarrationPdfOutcome
```

Поведение: `tempfile.TemporaryDirectory(prefix="docxaicorrector_tts_pdf_")`; внутри `<stem>.tts.docx`, каталог профиля
`lo_profile` (URI через `Path.as_uri()`), выход в тот же каталог; команда — research R6; `runner(...,
cleanup_process_group=True, timeout_seconds=timeout_seconds)`. Исключений наружу нет (кроме `BaseException`).

## 5. Экспорт озвучки целиком: состояние и bundle (FR-007, FR-008, research R9, R10)

`pipeline/narration_exports.py` (новый):

```text
NarrationExports(frozen)
    plan: NarrationDocumentPlan | None
    docx_bytes: bytes | None
    docx_error: str | None        # класс исключения рендерера, если DOCX не собран
    pdf: NarrationPdfOutcome

    def state_value(self) -> dict[str, object]     # значение ключа latest_narration_exports
    def event_fields(self) -> dict[str, object]    # поля ui_audiobook_artifact_saved (contracts/events.md)

build_narration_exports(*, groups, source_name, log_event, export_pdf=export_narration_pdf) -> NarrationExports
```

Значение ключа состояния `latest_narration_exports` и поля bundle `narration_exports` (одна форма):

| Ключ | Тип | Смысл |
|---|---|---|
| `docx_bytes` | `bytes \| None` | `.tts.docx` |
| `pdf_bytes` | `bytes \| None` | `.tts.pdf` |
| `docx_unavailable_reason` | `str \| None` | `"render_failed"` или `None` |
| `pdf_unavailable_reason` | `str \| None` | код из §4 или `None` |

Жизненный цикл: `None` после `init_session_state` / `reset_run_state` / аварии рабочего потока до доставки;
словарь — ровно в том `emit_state`, где публикуется `latest_narration_text` (`pipeline/late_phases.py:1372-1391`).
`get_current_result_bundle` кладёт `narration_exports` только при `latest_narration_text is not None` (правило пары).
`build_result_bundle(..., narration_exports=None)` нормализует: лишние ключи отбрасываются, не-`bytes` → `None`.
Старый bundle без ключа → `result.get("narration_exports") is None` → экран как до спеки.

## 6. Группа результата (FR-007, research R12)

| Файл | Ключ `artifact_paths` | Когда |
|---|---|---|
| `<stem>.result.md` | `markdown_path` | всегда |
| `<stem>.result.docx` | `docx_path` | всегда (DOCX для проверки у аудиокниги) |
| `<stem>.result.tts.txt` | `tts_text_path` | есть текст озвучки |
| `<stem>.result.tts.docx` | `tts_docx_path` | собран DOCX озвучки |
| `<stem>.result.tts.pdf` | `tts_pdf_path` | собран PDF озвучки |
| `.meta.json`, `.manifest.json`, `.formatting_review.txt` | как сейчас | как сейчас |

Суффиксы хранения: `_UI_RESULT_GROUP_SUFFIXES` + `.result.tts.docx`, `.result.tts.pdf`.

## 7. Поля `ui_audiobook_artifact_saved` (FR-003 (в), FR-006, FR-007)

Новые ключи — `contracts/events.md`; существующие ключи `data-model.md` §6 спеки 070 не меняются (Anti-regression 6).
Отчёт раннера — те же ключи (research R13).
