"""Spec 075, acceptance review round 1: the six findings, each with a test that fails without its fix.

1. the studio handoff never raises into the result screen;
2. only a UI-launched run publishes (the console validator must not);
3. a rerun leaves no stale managed files next to the new result;
4. published file names are the download-button names;
5. the studio starts with a minimal environment;
6. the session-level guard on ``<project root>/translations``.

Helpers and fixtures are the ones of ``test_spec_075_results_folder.py``.
"""

from __future__ import annotations

import http.client
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import docxaicorrector.core.config as config
import docxaicorrector.runtime.results_folder as results_folder
import docxaicorrector.runtime.studio_handoff as studio_handoff
import docxaicorrector.ui._ui as ui
from docxaicorrector.pipeline.contracts import ProcessingState
from docxaicorrector.ui.i18n import t
from tests.test_spec_072_late_phase_exports import _audiobook_state, _record
from tests.test_spec_075_results_folder import (  # noqa: F401  (fixtures are used by name)
    _PUBLISH_FLAG,
    _FakePost,
    _fake_send,
    _group,
    _refused,
    _render_audiobook,
    _run,
    _Screen,
    _studio_dir,
    logged,
    screen,
)

# ---------------------------------------------------------------------------------------------------------------
# 1. the handoff never raises into the result screen
# ---------------------------------------------------------------------------------------------------------------


def test_http_layer_turns_a_malformed_url_into_a_connection_error():
    # ``urllib.request.Request`` itself raises ValueError for a URL without a scheme: no network involved.
    with pytest.raises(studio_handoff.StudioConnectionError) as error:
        studio_handoff.post_json_bytes("not a url", b"{}", 1.0)
    assert error.value.refused is False
    assert "ValueError" in error.value.reason


@pytest.mark.parametrize(
    "torn",
    [
        http.client.IncompleteRead(b"partial"),
        http.client.BadStatusLine("garbage"),
        http.client.RemoteDisconnected("closed"),
    ],
    ids=["IncompleteRead", "BadStatusLine", "RemoteDisconnected"],
)
def test_http_layer_turns_http_client_failures_into_connection_errors(monkeypatch, torn):
    def fail(request, timeout):
        raise torn

    monkeypatch.setattr(studio_handoff.urllib.request, "urlopen", fail)

    with pytest.raises(studio_handoff.StudioConnectionError) as error:
        studio_handoff.post_json_bytes("http://127.0.0.1:8601/api/books", b"{}", 1.0)
    assert error.value.refused is False


def test_a_torn_error_body_keeps_the_status(monkeypatch):
    class _TornBody:
        def read(self, *args):
            raise http.client.IncompleteRead(b"x")

        def close(self) -> None:
            return None

    def bad_request(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, _TornBody())  # type: ignore[arg-type]

    monkeypatch.setattr(studio_handoff.urllib.request, "urlopen", bad_request)

    reply = studio_handoff.post_json_bytes("http://127.0.0.1:8601/api/books", b"{}", 1.0)

    assert reply.status == 400 and reply.body == b""


@pytest.mark.parametrize("where", ["post", "start"])
def test_send_book_to_studio_never_raises(tmp_path, where):
    def exploding_post(url, body, timeout):
        raise RuntimeError("post broke")

    def exploding_start(directory):
        raise RuntimeError("start broke")

    post = exploding_post if where == "post" else _FakePost(_refused())

    outcome = studio_handoff.send_book_to_studio(
        b"{}", studio_url="http://127.0.0.1:8601", studio_dir=_studio_dir(tmp_path),
        post=post, start_studio=exploding_start,
    )

    assert not outcome.ok
    assert outcome.error_code == "unreachable"
    assert "broke" in outcome.error_detail


def test_a_handler_whose_logger_raises_still_renders_the_whole_screen(screen, monkeypatch):
    _fake_send(
        monkeypatch,
        studio_handoff.StudioHandoffOutcome(ok=True, book_id="abc", link="http://localhost:8601/#book=abc"),
    )

    def broken_log(*args, **kwargs):
        raise RuntimeError("logger broke")

    monkeypatch.setattr(ui, "log_event", broken_log)
    screen.pressed.add("studio_handoff_button")

    _render_audiobook()

    assert screen.column_counts == [4, 2]  # the narration row AND the review row below it
    assert screen.links == [(t("result.studio_open_book_link"), "http://localhost:8601/#book=abc")]


@pytest.mark.parametrize("broken", ["send", "settings"])
def test_a_handler_whose_send_or_settings_raise_shows_the_error_and_the_rest(screen, monkeypatch, logged, broken):
    def boom(*args, **kwargs):
        raise RuntimeError(f"{broken} broke")

    monkeypatch.setattr(ui, "send_book_to_studio" if broken == "send" else "_studio_settings", boom)
    screen.pressed.add("studio_handoff_button")

    _render_audiobook()

    assert screen.column_counts == [4, 2]
    assert len(screen.errors) == 1
    assert f"{broken} broke" in screen.errors[0]
    assert t("result.studio_error.failed", detail="").strip() in screen.errors[0]
    (event,) = [e for e in logged if e[1] == "studio_handoff_failed"]
    assert event[2]["reason"] == "failed"


# ---------------------------------------------------------------------------------------------------------------
# 2. only a UI-launched run publishes
# ---------------------------------------------------------------------------------------------------------------


def test_a_run_without_the_ui_flag_does_not_publish(monkeypatch, tmp_path, isolate_results_folder):
    result, emitters, dependencies = _run(
        monkeypatch, tmp_path, operation="edit", state=ProcessingState(processed_chunks=["текст"]), publish=False
    )

    assert result == "succeeded"
    assert not (isolate_results_folder / "translations").exists()
    assert dependencies.named("ui_results_published") == []
    assert dependencies.named("ui_results_publish_failed") == []
    assert not any("latest_results_folder" in call for call in emitters.state_calls)
    assert len(dependencies.named("ui_result_artifacts_saved")) == 1  # the .run group is written as before


@pytest.mark.parametrize("value", [None, False, "true", 1])
def test_only_a_literal_true_flag_enables_publication(value):
    assert results_folder.publishing_enabled({_PUBLISH_FLAG: value}) is False
    assert results_folder.publishing_enabled({}) is False
    assert results_folder.publishing_enabled(None) is False
    assert results_folder.publishing_enabled({_PUBLISH_FLAG: True}) is True


def test_the_ui_start_path_sets_the_publish_flag_without_touching_the_callers_config(monkeypatch):
    import docxaicorrector.ui._app as app

    captured: dict[str, Any] = {}

    class FakeService:
        def run_processing_worker(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        app,
        "start_background_processing",
        lambda **kwargs: kwargs["worker_target"](
            runtime=object(),
            uploaded_filename=kwargs["uploaded_filename"],
            prepared_source_key=kwargs["prepared_source_key"],
            structure_fingerprint=kwargs["structure_fingerprint"],
            jobs=kwargs["jobs"],
            selected_segment_ids=kwargs["selected_segment_ids"],
            output_mode=kwargs["output_mode"],
            include_front_matter=kwargs["include_front_matter"],
            include_toc=kwargs["include_toc"],
            source_paragraphs=kwargs["source_paragraphs"],
            image_assets=kwargs["image_assets"],
            image_mode=kwargs["image_mode"],
            app_config=kwargs["app_config"],
            model=kwargs["model"],
            max_retries=kwargs["max_retries"],
            processing_operation=kwargs["processing_operation"],
            source_language=kwargs["source_language"],
            target_language=kwargs["target_language"],
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "docxaicorrector.processing.processing_service",
        SimpleNamespace(get_processing_service=lambda: FakeService()),
    )
    callers_config: dict[str, object] = {"chunk_size": 6000}

    app._start_background_processing(
        uploaded_filename="report.docx", uploaded_token="token", source_bytes=b"source",
        prepared_source_key="prep", structure_fingerprint="fp",
        jobs=[], output_mode="legacy_full_document", source_paragraphs=[], image_assets=[], image_mode="safe",
        app_config=callers_config, model="gpt-5.4", max_retries=1,
    )

    assert captured["app_config"][_PUBLISH_FLAG] is True
    assert captured["app_config"]["chunk_size"] == 6000
    assert _PUBLISH_FLAG not in callers_config


def test_the_validation_runners_resolved_config_never_carries_the_flag():
    import docxaicorrector.validation.profiles as validation_profiles

    app_config = config.load_app_config()
    registry = validation_profiles.load_validation_registry()
    assert registry.run_profiles
    for profile in registry.run_profiles:
        resolution = validation_profiles.resolve_runtime_resolution(app_config, profile)
        applied = validation_profiles.apply_runtime_resolution_to_app_config(app_config, resolution)
        assert results_folder.publishing_enabled(applied) is False
        assert _PUBLISH_FLAG not in applied


# ---------------------------------------------------------------------------------------------------------------
# 3. no stale managed files next to a newer result
# ---------------------------------------------------------------------------------------------------------------


def test_audiobook_then_plain_edit_leaves_only_the_new_docx_and_foreign_files_survive(tmp_path):
    out = tmp_path / "out"
    five = _group(
        tmp_path,
        docx_path=b"docx 1",
        tts_text_path=b"t",
        tts_docx_path=b"td",
        tts_pdf_path=b"%PDF",
        narration_book_path=b'{"old": "book"}',
    )
    results_folder.publish_result_files(source_name="a.docx", artifact_paths=five, results_dir=out)
    folder = out / "a"
    (folder / "notes.txt").write_text("mine", encoding="utf-8")
    (folder / "a.tts (новая).txt").write_bytes(b"stale variant")
    (folder / "other_edited.docx").write_bytes(b"another book")
    assert len(list(folder.iterdir())) == 8

    edit_only = _group(tmp_path / "second", docx_path=b"docx 2")
    outcome = results_folder.publish_result_files(source_name="a.docx", artifact_paths=edit_only, results_dir=out)

    assert sorted(p.name for p in folder.iterdir()) == ["a_edited.docx", "notes.txt", "other_edited.docx"]
    assert (folder / "a_edited.docx").read_bytes() == b"docx 2"
    assert (folder / "notes.txt").read_text(encoding="utf-8") == "mine"
    assert sorted(Path(p).name for p in outcome.removed) == [
        "a.narration.json", "a.tts (новая).txt", "a.tts.docx", "a.tts.pdf", "a.tts.txt",
    ]
    assert outcome.stale_remove_failed == ()


def test_a_stale_new_marker_variant_goes_when_the_main_name_is_written(tmp_path):
    out = tmp_path / "out"
    folder = out / "a"
    folder.mkdir(parents=True)
    (folder / "a_edited (новая).docx").write_bytes(b"left from a locked day")

    results_folder.publish_result_files(
        source_name="a.docx", artifact_paths=_group(tmp_path, docx_path=b"fresh"), results_dir=out
    )

    assert [p.name for p in folder.iterdir()] == ["a_edited.docx"]


def test_the_refused_main_file_is_not_deleted_when_its_replacement_went_next_to_it(tmp_path, monkeypatch):
    out = tmp_path / "out"
    folder = out / "a"
    folder.mkdir(parents=True)
    (folder / "a_edited.docx").write_bytes(b"open in Word")
    real_write = results_folder._write_atomic

    def locked(path: Path, data: bytes) -> None:
        if path.name == "a_edited.docx":
            raise PermissionError(13, "in use")
        real_write(path, data)

    monkeypatch.setattr(results_folder, "_write_atomic", locked)

    results_folder.publish_result_files(
        source_name="a.docx", artifact_paths=_group(tmp_path, docx_path=b"new"), results_dir=out
    )

    assert sorted(p.name for p in folder.iterdir()) == ["a_edited (новая).docx", "a_edited.docx"]


def test_a_stale_file_that_cannot_be_removed_is_reported_and_the_rest_goes(tmp_path, monkeypatch):
    out = tmp_path / "out"
    five = _group(tmp_path, docx_path=b"d", tts_text_path=b"t", narration_book_path=b"{}")
    results_folder.publish_result_files(source_name="a.docx", artifact_paths=five, results_dir=out)
    folder = out / "a"
    real_unlink = Path.unlink

    def locked_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        if self.name == "a.tts.txt":
            raise PermissionError(13, "in use")
        real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked_unlink)

    outcome = results_folder.publish_result_files(
        source_name="a.docx", artifact_paths=_group(tmp_path / "s", docx_path=b"d2"), results_dir=out
    )

    assert sorted(p.name for p in folder.iterdir()) == ["a.tts.txt", "a_edited.docx"]
    assert [name for name, _error in outcome.stale_remove_failed] == ["a.tts.txt"]
    assert [Path(p).name for p in outcome.removed] == ["a.narration.json"]


def test_nothing_is_removed_when_a_file_failed_to_publish(tmp_path, monkeypatch):
    out = tmp_path / "out"
    results_folder.publish_result_files(
        source_name="a.docx", artifact_paths=_group(tmp_path, docx_path=b"d", tts_text_path=b"t"), results_dir=out
    )

    def broken(path: Path, data: bytes) -> None:
        raise OSError(28, "no space")

    monkeypatch.setattr(results_folder, "_write_atomic", broken)
    outcome = results_folder.publish_result_files(
        source_name="a.docx", artifact_paths=_group(tmp_path / "s", docx_path=b"d2"), results_dir=out
    )

    assert outcome.failed and outcome.removed == ()
    assert (out / "a" / "a.tts.txt").exists()


def test_audiobook_run_then_edit_run_of_the_same_source_through_the_late_phase(
    monkeypatch, tmp_path, isolate_results_folder
):
    records = [_record("p1", "Первый абзац книги."), _record("p2", "Второй абзац книги.")]
    _run(monkeypatch, tmp_path, operation="audiobook", state=_audiobook_state(records))
    folder = isolate_results_folder / "translations" / "book"
    assert "book.tts.txt" in {p.name for p in folder.iterdir()}

    result, _emitters, dependencies = _run(
        monkeypatch, tmp_path, operation="edit", state=ProcessingState(processed_chunks=["текст"])
    )

    assert result == "succeeded"
    assert [p.name for p in folder.iterdir()] == ["book_edited.docx"]
    (event,) = dependencies.named("ui_results_published")
    assert any(str(path).endswith("book.tts.txt") for path in event[1]["removed_paths"])  # type: ignore[attr-defined]
    assert event[1]["stale_remove_failed"] == []


# ---------------------------------------------------------------------------------------------------------------
# 4. published names are the download names
# ---------------------------------------------------------------------------------------------------------------

_FORBIDDEN = set('<>:"/\\|?*')


@pytest.mark.parametrize("source_name", ["sample..docx", " lead.docx", ".pdf", ".doc", "trail .docx", "a:b.docx"])
def test_published_names_equal_the_download_button_names(tmp_path, source_name):
    artifacts = _group(
        tmp_path,
        docx_path=b"d", tts_text_path=b"t", tts_docx_path=b"td", tts_pdf_path=b"p", narration_book_path=b"{}",
    )

    outcome = results_folder.publish_result_files(
        source_name=source_name, artifact_paths=artifacts, results_dir=tmp_path / "out"
    )

    def button_name(raw: str) -> str:
        return "".join("_" if char in _FORBIDDEN else char for char in raw)

    expected = sorted(
        button_name(builder(source_name))
        for builder in (
            ui._build_output_filename,
            ui._build_narration_filename,
            ui._build_narration_docx_filename,
            ui._build_narration_pdf_filename,
            ui._build_narration_book_filename,
        )
    )
    assert sorted(Path(path).name for path in outcome.paths) == expected
    assert outcome.folder is not None and not (_FORBIDDEN & set(outcome.folder.name))
    assert outcome.folder.name not in {"", ".", ".."}


def test_the_dotted_stem_keeps_its_dot_in_the_file_name_but_not_in_the_folder(tmp_path):
    outcome = results_folder.publish_result_files(
        source_name="sample..docx", artifact_paths=_group(tmp_path, docx_path=b"d"), results_dir=tmp_path / "out"
    )
    assert outcome.folder == tmp_path / "out" / "sample"
    assert [Path(p).name for p in outcome.paths] == ["sample._edited.docx"]


# ---------------------------------------------------------------------------------------------------------------
# 5. the studio starts with a minimal environment
# ---------------------------------------------------------------------------------------------------------------


def test_the_studio_start_script_gets_a_minimal_environment(tmp_path, monkeypatch):
    studio = _studio_dir(tmp_path)
    for name, value in {
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "USER": "u",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TERM": "xterm",
        "WSL_DISTRO_NAME": "Debian",
        "WSL_INTEROP": "/run/WSL/1_interop",
        "WSLENV": "A/p",
        "STUDIO_PORT": "9999",
        "GEMINI_API_KEY": "secret-key",
        "PYTHONPATH": "/project/src",
        "VIRTUAL_ENV": "/project/.venv",
        "OPENROUTER_API_KEY": "another-secret",
    }.items():
        monkeypatch.setenv(name, value)
    seen: dict[str, Any] = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=b"ok")

    monkeypatch.setattr(studio_handoff.subprocess, "run", fake_run)

    studio_handoff.run_studio_start_script(studio)

    environment = seen["env"]
    assert environment["PATH"] == "/usr/bin" and environment["HOME"] == "/home/u"
    assert environment["LC_ALL"] == "C.UTF-8" and environment["WSL_INTEROP"] == "/run/WSL/1_interop"
    for leaked in ("STUDIO_PORT", "GEMINI_API_KEY", "PYTHONPATH", "VIRTUAL_ENV", "OPENROUTER_API_KEY"):
        assert leaked not in environment
    allowed = {"PATH", "HOME", "USER", "LOGNAME", "LANG", "TERM", "WSL_DISTRO_NAME", "WSL_INTEROP", "WSLENV"}
    assert all(name in allowed or name.startswith("LC_") for name in environment)


def test_absent_wsl_variables_are_simply_absent():
    assert studio_handoff.minimal_start_environment({"PATH": "/bin", "STUDIO_PORT": "1"}) == {"PATH": "/bin"}


# ---------------------------------------------------------------------------------------------------------------
# 6. the session guard
# ---------------------------------------------------------------------------------------------------------------


def test_the_session_guard_fingerprint_notices_a_created_or_changed_folder(tmp_path):
    from tests.conftest import results_folder_fingerprint

    folder = tmp_path / "translations"
    assert results_folder_fingerprint(folder) is None
    folder.mkdir()
    created = results_folder_fingerprint(folder)
    assert created is not None
    (folder / "Book").mkdir()
    (folder / "Book" / "x.docx").write_bytes(b"x")
    changed = results_folder_fingerprint(folder)
    assert changed != created
    assert results_folder_fingerprint(folder) == changed


def test_the_session_guard_is_registered_and_watches_the_real_project_folder(guard_project_translations_folder):
    # Its teardown (end of the session) fails the run if <project root>/translations changed; here we
    # only prove it is active and looking at the real folder, not at the isolated root.
    from tests.conftest import results_folder_fingerprint

    real_folder = results_folder.BASE_DIR / "translations"
    assert guard_project_translations_folder == results_folder_fingerprint(real_folder)
