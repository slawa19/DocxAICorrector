from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO

from document import (
    build_document_text,
    build_editing_jobs,
    build_semantic_blocks,
    extract_document_content_from_docx,
)


@dataclass
class PreparedDocumentData:
    source_text: str
    paragraphs: list
    image_assets: list
    jobs: list[dict[str, str | int]]
    prepared_source_key: str


def build_prepared_source_key(uploaded_file_token: str, chunk_size: int) -> str:
    return f"{uploaded_file_token}:{chunk_size}"


def _build_in_memory_uploaded_file(*, source_name: str, source_bytes: bytes):
    uploaded_file = BytesIO(source_bytes)
    uploaded_file.name = source_name
    uploaded_file.size = len(source_bytes)
    return uploaded_file


def _prepare_document_for_processing(source_name: str, source_bytes: bytes, chunk_size: int):
    uploaded_file = _build_in_memory_uploaded_file(source_name=source_name, source_bytes=source_bytes)
    paragraphs, image_assets = extract_document_content_from_docx(uploaded_file)
    source_text = build_document_text(paragraphs)
    blocks = build_semantic_blocks(paragraphs, max_chars=chunk_size)
    jobs = build_editing_jobs(blocks, max_chars=chunk_size)
    return PreparedDocumentData(
        source_text=source_text,
        paragraphs=paragraphs,
        image_assets=image_assets,
        jobs=jobs,
        prepared_source_key="",
    )


def _get_preparation_cache(session_state) -> dict[str, PreparedDocumentData]:
    if session_state is None:
        return {}
    cache = session_state.get("preparation_cache")
    if not isinstance(cache, dict):
        cache = {}
        session_state["preparation_cache"] = cache
    return cache


def _clone_prepared_document(data: PreparedDocumentData, prepared_source_key: str) -> PreparedDocumentData:
    return PreparedDocumentData(
        source_text=data.source_text,
        paragraphs=deepcopy(data.paragraphs),
        image_assets=deepcopy(data.image_assets),
        jobs=deepcopy(data.jobs),
        prepared_source_key=prepared_source_key,
    )


def _read_cached_prepared_document(*, session_state, prepared_source_key: str):
    cache = _get_preparation_cache(session_state)
    cached = cache.get(prepared_source_key)
    if cached is None:
        return None
    cache.pop(prepared_source_key)
    cache[prepared_source_key] = cached
    return _clone_prepared_document(cached, prepared_source_key)


def _store_cached_prepared_document(*, session_state, prepared_source_key: str, prepared_document: PreparedDocumentData) -> None:
    if session_state is None:
        return
    cache = _get_preparation_cache(session_state)
    cache.pop(prepared_source_key, None)
    cache[prepared_source_key] = PreparedDocumentData(
        source_text=prepared_document.source_text,
        paragraphs=deepcopy(prepared_document.paragraphs),
        image_assets=deepcopy(prepared_document.image_assets),
        jobs=deepcopy(prepared_document.jobs),
        prepared_source_key="",
    )
    while len(cache) > 2:
        oldest_key = next(iter(cache))
        cache.pop(oldest_key, None)


def clear_preparation_cache(*, session_state=None) -> None:
    if session_state is None:
        return
    session_state["preparation_cache"] = {}


def prepare_document_for_processing(*, uploaded_filename: str, source_bytes: bytes, uploaded_file_token: str, chunk_size: int, session_state=None) -> PreparedDocumentData:
    prepared_source_key = build_prepared_source_key(uploaded_file_token, chunk_size)
    cached = _read_cached_prepared_document(session_state=session_state, prepared_source_key=prepared_source_key)
    if cached is not None:
        return cached

    prepared_document = _prepare_document_for_processing(
        uploaded_filename,
        source_bytes,
        chunk_size,
    )
    _store_cached_prepared_document(
        session_state=session_state,
        prepared_source_key=prepared_source_key,
        prepared_document=prepared_document,
    )
    return _clone_prepared_document(prepared_document, prepared_source_key)