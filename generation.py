import tempfile
import time
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pypandoc
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from image_shared import is_retryable_error

if TYPE_CHECKING:
    from openai import OpenAI


@lru_cache(maxsize=1)
def ensure_pandoc_available() -> None:
    try:
        pypandoc.get_pandoc_version()
    except OSError as exc:
        raise RuntimeError(
            "Pandoc не найден. Для Windows PowerShell установите его командой: "
            "winget install --id JohnMacFarlane.Pandoc -e"
        ) from exc


def normalize_model_output(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:].strip()
        else:
            cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned


def _normalize_context_text(text: str | None) -> str:
    if text is None:
        return "[контекст отсутствует]"
    cleaned = text.strip()
    return cleaned or "[контекст отсутствует]"


def _extract_response_output_text(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text is None:
        return ""
    if not isinstance(output_text, str):
        raise RuntimeError("Модель вернула ответ в неподдерживаемом формате.")
    return output_text

def generate_markdown_block(
    client: "OpenAI",
    model: str,
    system_prompt: str,
    target_text: str,
    context_before: str,
    context_after: str,
    max_retries: int,
) -> str:
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise TypeError("max_retries должен быть целым числом.")
    if max_retries < 1:
        raise ValueError("max_retries должен быть не меньше 1.")

    context_before_text = _normalize_context_text(context_before)
    context_after_text = _normalize_context_text(context_after)
    user_prompt = (
        "Ниже передан целевой блок документа и соседний контекст.\n"
        "Используй соседний контекст только для понимания смысла, терминологии и связности.\n"
        "Редактируй только целевой блок и верни только его итоговый текст.\n\n"
        f"[CONTEXT BEFORE]\n{context_before_text}\n\n"
        f"[TARGET BLOCK]\n{target_text}\n\n"
        f"[CONTEXT AFTER]\n{context_after_text}"
    )
    payload: Any = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": user_prompt}],
        },
    ]

    for attempt in range(1, max_retries + 1):
        try:
            response = client.responses.create(model=model, input=payload)
            markdown = normalize_model_output(_extract_response_output_text(response))
            if not markdown:
                raise RuntimeError("Модель вернула пустой ответ.")
            return markdown
        except Exception as exc:
            should_retry = attempt < max_retries and is_retryable_error(exc)
            if not should_retry:
                raise
            time.sleep(min(2 ** (attempt - 1), 8))

    raise RuntimeError("Не удалось получить ответ модели.")


def convert_markdown_to_docx_bytes(markdown_text: str) -> bytes:
    ensure_pandoc_available()
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            markdown_path = temp_path / "result.md"
            docx_path = temp_path / "result.docx"
            reference_docx_path = temp_path / "reference.docx"
            markdown_path.write_text(markdown_text, encoding="utf-8")
            _build_reference_docx(reference_docx_path)
            pypandoc.convert_file(
                str(markdown_path),
                to="docx",
                format="md",
                outputfile=str(docx_path),
                extra_args=[f"--reference-doc={reference_docx_path}"],
            )
            return docx_path.read_bytes()
    except Exception as exc:
        raise RuntimeError(f"Ошибка при сборке DOCX: {exc}") from exc


def _build_reference_docx(reference_docx_path: Path) -> None:
    reference_document = Document()
    styles = reference_document.styles

    _configure_paragraph_style(styles["Normal"], font_name="Aptos", font_size=11, space_after=8, line_spacing=1.15)

    if "Body Text" in styles:
        _configure_paragraph_style(styles["Body Text"], font_name="Aptos", font_size=11, space_after=8, line_spacing=1.15)

    _configure_paragraph_style(
        styles["Heading 1"],
        font_name="Aptos Display",
        font_size=18,
        bold=True,
        space_before=18,
        space_after=8,
        keep_with_next=True,
    )
    _configure_paragraph_style(
        styles["Heading 2"],
        font_name="Aptos Display",
        font_size=15,
        bold=True,
        space_before=14,
        space_after=6,
        keep_with_next=True,
    )
    _configure_paragraph_style(
        styles["Heading 3"],
        font_name="Aptos Display",
        font_size=12,
        bold=True,
        space_before=12,
        space_after=4,
        keep_with_next=True,
    )

    if "Caption" in styles:
        _configure_paragraph_style(
            styles["Caption"],
            font_name="Aptos",
            font_size=10,
            italic=True,
            space_before=4,
            space_after=10,
            alignment=WD_ALIGN_PARAGRAPH.CENTER,
        )

    if "List Paragraph" in styles:
        _configure_paragraph_style(styles["List Paragraph"], font_name="Aptos", font_size=11, space_after=4, line_spacing=1.1)

    if "Table Grid" in styles:
        table_grid_style = cast(Any, styles["Table Grid"])
        table_grid_style.font.name = "Aptos"
        table_grid_style.font.size = Pt(10)

    reference_document.save(str(reference_docx_path))


def _configure_paragraph_style(
    style,
    *,
    font_name: str,
    font_size: int,
    bold: bool | None = None,
    italic: bool | None = None,
    space_before: int | None = None,
    space_after: int | None = None,
    line_spacing: float | None = None,
    keep_with_next: bool | None = None,
    alignment=None,
) -> None:
    style.font.name = font_name
    style.font.size = Pt(font_size)
    if bold is not None:
        style.font.bold = bold
    if italic is not None:
        style.font.italic = italic

    paragraph_format = style.paragraph_format
    if space_before is not None:
        paragraph_format.space_before = Pt(space_before)
    if space_after is not None:
        paragraph_format.space_after = Pt(space_after)
    if line_spacing is not None:
        paragraph_format.line_spacing = line_spacing
    if keep_with_next is not None:
        paragraph_format.keep_with_next = keep_with_next
    if alignment is not None:
        paragraph_format.alignment = alignment


def build_output_filename(filename: str) -> str:
    return f"{Path(filename).stem}_edited.docx"


def build_markdown_filename(filename: str) -> str:
    return f"{Path(filename).stem}_edited.md"
