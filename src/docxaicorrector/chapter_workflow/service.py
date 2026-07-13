from __future__ import annotations


def build_document_context_prompt(*, prepared_run_context: object) -> str:
    document_context_profile = getattr(prepared_run_context, "document_context_profile", None)
    prompt_builder = getattr(document_context_profile, "to_prompt_text", None)
    if callable(prompt_builder):
        return str(prompt_builder() or "").strip()
    return ""
