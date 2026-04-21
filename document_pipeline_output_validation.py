import re
from typing import Literal, TypeAlias


ProcessedBlockStatus: TypeAlias = Literal["valid", "empty", "heading_only_output"]


def iter_nonempty_markdown_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def is_markdown_heading_line(line: str) -> bool:
    return bool(re.match(r"#{1,6}\s+\S", line))


def is_heading_only_markdown(text: str) -> bool:
    nonempty_lines = iter_nonempty_markdown_lines(text)
    return bool(nonempty_lines) and all(is_markdown_heading_line(line) for line in nonempty_lines)


def is_heading_like_alpha_token(token: str) -> bool:
    stripped = token.strip("\"'“”‘’()[]{}<>«»,-—–:;,.!?")
    if not stripped:
        return False

    alpha_chars = [char for char in stripped if char.isalpha()]
    if not alpha_chars:
        return False

    if all(char.isupper() for char in alpha_chars):
        return True

    for char in stripped:
        if char.isalpha():
            return char.isupper()
    return False


def is_plaintext_heading_like_line(line: str) -> bool:
    if any(symbol in line for symbol in ".!?;"):
        return False

    tokens = [token for token in re.split(r"[\s\t]+", line.strip()) if token]
    alpha_tokens = [token for token in tokens if any(char.isalpha() for char in token)]
    if not alpha_tokens or len(alpha_tokens) > 14:
        return False

    letters = [char for char in line if char.isalpha()]
    if not letters:
        return False

    uppercase_letters = [char for char in letters if char.isupper()]
    uppercase_ratio = len(uppercase_letters) / len(letters)
    heading_like_token_ratio = sum(1 for token in alpha_tokens if is_heading_like_alpha_token(token)) / len(alpha_tokens)
    if line.count(":") == 1:
        prefix, suffix = [part.strip() for part in line.split(":", maxsplit=1)]
        prefix_tokens = [token for token in re.split(r"[\s\t]+", prefix) if any(char.isalpha() for char in token)]
        suffix_tokens = [token for token in re.split(r"[\s\t]+", suffix) if any(char.isalpha() for char in token)]
        if (
            prefix_tokens
            and suffix_tokens
            and len(prefix_tokens) <= 4
            and len(suffix_tokens) <= 8
            and all(is_heading_like_alpha_token(token) for token in prefix_tokens)
        ):
            return True
    if "\t" in line and uppercase_ratio >= 0.6:
        return True
    if uppercase_ratio >= 0.6:
        return True
    if heading_like_token_ratio >= 0.8:
        return True
    return False


def input_has_body_text_signal(text: str) -> bool:
    nonempty_lines = iter_nonempty_markdown_lines(text)
    body_lines = [line for line in nonempty_lines if not is_markdown_heading_line(line)]
    if not body_lines:
        return False
    if len(body_lines) >= 2:
        return True
    body_line = body_lines[0]
    if is_plaintext_heading_like_line(body_line):
        return False
    if len(body_line) >= 40:
        return True
    if len(body_line.split()) >= 5 and any(symbol in body_line for symbol in ".,;:!?"):
        return True
    return False


def classify_processed_block(target_text: str, processed_chunk: str) -> ProcessedBlockStatus:
    if not processed_chunk.strip():
        return "empty"
    if is_heading_only_markdown(processed_chunk) and input_has_body_text_signal(target_text):
        return "heading_only_output"
    return "valid"