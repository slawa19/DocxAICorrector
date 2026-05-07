from types import SimpleNamespace

import pytest

import docxaicorrector.ui.structure_review_panel as structure_review_panel
from conftest import SessionState as SessionState  # noqa: F811
from docxaicorrector.document.segments import DocumentSegment


@pytest.fixture(autouse=True)
def _session_state_factory(make_session_state):
    globals()["SessionState"] = make_session_state


def _segment(segment_id: str, ordinal: int) -> DocumentSegment:
    return DocumentSegment(
        segment_id=segment_id,
        ordinal=ordinal,
        level=1,
        title=f"Chapter {ordinal}",
        normalized_title=f"chapter {ordinal}",
        start_paragraph_index=ordinal - 1,
        end_paragraph_index=ordinal - 1,
        start_paragraph_id=f"p{ordinal:04d}",
        end_paragraph_id=f"p{ordinal:04d}",
        paragraph_ids=(f"p{ordinal:04d}",),
        paragraph_count=1,
        char_count=50,
        word_count=10,
        estimated_token_count=15,
        structural_role="chapter",
        confidence="high",
        boundary_fingerprint=f"fp-{segment_id}",
    )


def test_sync_structure_review_state_invalidates_confirmation_when_segment_ids_change(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(structure_review_panel.st, "session_state", session_state)

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(structure_review_panel, "get_segments_loaded_for_source_token", lambda: "file-token")
    monkeypatch.setattr(structure_review_panel, "get_selected_segment_ids", lambda: ["seg_0001", "seg_0002"])
    monkeypatch.setattr(structure_review_panel, "set_selected_segment_ids", lambda segment_ids: None)
    monkeypatch.setattr(structure_review_panel, "get_structure_confirmed", lambda: True)
    monkeypatch.setattr(structure_review_panel, "get_confirmed_structure_fingerprint", lambda: "structure-fp")
    monkeypatch.setattr(structure_review_panel, "get_confirmed_structure_segment_ids", lambda: ["seg_0002", "seg_0001"])
    monkeypatch.setattr(structure_review_panel, "get_confirmed_at_settings_hash", lambda: "settings-fp")
    monkeypatch.setattr(structure_review_panel, "set_structure_confirmation_state", lambda **kwargs: calls.append(kwargs))

    prepared_run_context = SimpleNamespace(
        segments=[_segment("seg_0001", 1), _segment("seg_0002", 2)],
        structure_fingerprint="structure-fp",
    )

    review_state = structure_review_panel._sync_structure_review_state(
        prepared_run_context=prepared_run_context,
        uploaded_file_token="file-token",
        chunk_size=6000,
        app_config={},
        build_structure_settings_hash_fn=lambda **kwargs: "settings-fp",
    )

    assert review_state["structure_confirmed"] is False
    assert review_state["confirmation_invalidated"] is True
    assert review_state["segment_ids_changed"] is True
    assert calls == [
        {
            "structure_confirmed": False,
            "confirmed_structure_fingerprint": "",
            "confirmed_segment_ids": [],
            "confirmed_at_settings_hash": "",
            "segments_loaded_for_source_token": "file-token",
        }
    ]
