import tempfile
import time
from pathlib import Path

import pypandoc
from openai import OpenAI


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
    if cleaned.startswith("```markdown"):
        cleaned = cleaned[len("```markdown"):].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned


def is_retryable_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in {408, 409, 429}:
        return True
    if isinstance(status_code, int) and status_code >= 500:
        return True
    return exc.__class__.__name__ in {"APIConnectionError", "APITimeoutError"}


def generate_markdown_block(
    client: OpenAI,
    model: str,
    system_prompt: str,
    target_text: str,
    context_before: str,
    context_after: str,
    max_retries: int,
) -> str:
    context_before_text = context_before or "[контекст отсутствует]"
    context_after_text = context_after or "[контекст отсутствует]"
    user_prompt = (
        "Ниже передан целевой блок документа и соседний контекст.\n"
        "Используй соседний контекст только для понимания смысла, терминологии и связности.\n"
        "Редактируй только целевой блок и верни только его итоговый текст.\n\n"
        f"[CONTEXT BEFORE]\n{context_before_text}\n\n"
        f"[TARGET BLOCK]\n{target_text}\n\n"
        f"[CONTEXT AFTER]\n{context_after_text}"
    )
    payload = [
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
            markdown = normalize_model_output(response.output_text)
            if not markdown:
                raise RuntimeError("Модель вернула пустой ответ.")
            return markdown
        except Exception as exc:
            should_retry = attempt < max_retries and is_retryable_error(exc)
            if not should_retry:
                raise
            time.sleep(min(2 ** (attempt - 1), 8))


def convert_markdown_to_docx_bytes(markdown_text: str) -> bytes:
    ensure_pandoc_available()
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            markdown_path = temp_path / "result.md"
            docx_path = temp_path / "result.docx"
            markdown_path.write_text(markdown_text, encoding="utf-8")
            pypandoc.convert_file(
                str(markdown_path),
                to="docx",
                format="md",
                outputfile=str(docx_path),
            )
            return docx_path.read_bytes()
    except Exception as exc:
        raise RuntimeError(f"Ошибка при сборке DOCX: {exc}") from exc


def build_output_filename(filename: str) -> str:
    return f"{Path(filename).stem}_edited.docx"


def build_markdown_filename(filename: str) -> str:
    return f"{Path(filename).stem}_edited.md"
