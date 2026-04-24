import generation


def test_strip_markdown_for_narration_removes_markdown_and_placeholders_but_preserves_tags():
    source = (
        "# Chapter 1\n\n"
        "[thoughtful] **Bold** and *italic* text with [link](https://example.com).\n\n"
        "> Quoted line\n\n"
        "1. First item\n"
        "- Second item\n\n"
        "`inline code` [[DOCX_PARA_p0001]] [[DOCX_IMAGE_img_001]]"
    )

    stripped = generation.strip_markdown_for_narration(source)

    assert stripped == (
        "Chapter 1\n\n"
        "[thoughtful] Bold and italic text with link.\n"
        "Quoted line\n"
        "First item\n"
        "Second item\n\n"
        "inline code"
    )


def test_strip_markdown_for_narration_is_idempotent():
    source = "## Title\n\n[curious] Text with **emphasis** and [link](https://example.com)."

    once = generation.strip_markdown_for_narration(source)
    twice = generation.strip_markdown_for_narration(once)

    assert once == twice


def test_strip_markdown_for_narration_removes_raw_urls_and_normalizes_internal_whitespace():
    source = "[thoughtful]\tText   with raw URL https://example.com/path and www.example.org\tinside."

    stripped = generation.strip_markdown_for_narration(source)

    assert stripped == "[thoughtful] Text with raw URL and inside."
