from types import SimpleNamespace

import generation


class RetryableError(Exception):
    status_code = 429


def test_generate_markdown_block_retries_once_then_returns(monkeypatch):
    attempts = []
    sleep_calls = []

    def create_response(*, model, input):
        attempts.append((model, input))
        if len(attempts) == 1:
            raise RetryableError("rate limited")
        return SimpleNamespace(output_text="```markdown\nИсправленный текст\n```")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)

    result = generation.generate_markdown_block(
        client=client,
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="",
        context_after="",
        max_retries=2,
    )

    assert result == "Исправленный текст"
    assert len(attempts) == 2
    assert sleep_calls == [1]
    user_payload = attempts[0][1][1]["content"][0]["text"]
    assert "[CONTEXT BEFORE]\n[контекст отсутствует]" in user_payload
    assert "[TARGET BLOCK]\ntarget" in user_payload
    assert "[CONTEXT AFTER]\n[контекст отсутствует]" in user_payload


def test_generate_markdown_block_raises_on_empty_model_output():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="```\n\n```"))
    )

    try:
        generation.generate_markdown_block(
            client=client,
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=1,
        )
    except RuntimeError as exc:
        assert "пустой ответ" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for an empty model response")


def test_ensure_pandoc_available_converts_os_error(monkeypatch):
    def raise_os_error():
        raise OSError("pandoc missing")

    monkeypatch.setattr(generation.pypandoc, "get_pandoc_version", raise_os_error)

    try:
        generation.ensure_pandoc_available()
    except RuntimeError as exc:
        assert "Pandoc не найден" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when pandoc is unavailable")