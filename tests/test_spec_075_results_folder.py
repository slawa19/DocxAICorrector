"""Spec 075: the durable results folder (FR-001..FR-003) and the studio handoff (FR-004), offline.

* SC-001 -- the folder after a delivered run, through the real late phase and the real result-group
  writer: exactly the built files under the download-button names; a blocked result is not
  published; an identical file is not rewritten; a locked file gets ``(новая)``; nothing raises out.
* SC-002 -- ``/mnt/<letter>/...`` shown as ``<LETTER>:\\...``.
* SC-003 -- ``Open in studio`` with a replaced HTTP layer and a replaced start script: no network,
  no real subprocess.

``tests/conftest.py`` points ``runtime.results_folder.PROJECT_ROOT`` at a throwaway directory for
every test (autouse), so none of these may touch ``<project root>/translations``.
"""

from __future__ import annotations

import json
import logging
import urllib.error
from pathlib import Path
from types import SimpleNamespace

from typing import Any, cast

import pytest

import docxaicorrector.core.config as config
import docxaicorrector.pipeline.late_phases as late_phases
import docxaicorrector.runtime.results_folder as results_folder
import docxaicorrector.runtime.studio_handoff as studio_handoff
import docxaicorrector.ui._ui as ui
from docxaicorrector.pipeline.contracts import ProcessingState
from docxaicorrector.ui.i18n import t
from tests.test_spec_072_late_phase_exports import (
    _Dependencies,
    _Emitters,
    _audiobook_state,
    _context,
    _docx_phase,
    _install_stubs,
    _record,
    _install_stubs as _install_072_stubs,
)

_PUBLISH_FLAG = results_folder.PUBLISH_FLAG_KEY
_BOOK_JSON = '{"schema": "invented-form", "items": []}'
_MARKDOWN = "Итоговый текст для проверки."


def _run(monkeypatch, tmp_path, *, operation, state, publish: bool = True):
    """The 072 harness run, as a UI-launched run (the UI start path sets the publish flag in the run's
    app config) unless ``publish`` is False -- which is what the console validator's run looks like."""
    _install_072_stubs(monkeypatch, markdown=_MARKDOWN)
    dependencies = _Dependencies(tmp_path / "ui_results")
    emitters = _Emitters()
    context = _context(operation)
    context.app_config = {_PUBLISH_FLAG: True} if publish else {}
    result = late_phases.finalize_processing_success(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        docx_phase=_docx_phase(_MARKDOWN),
        job_count=1,
        current_markdown_fn=lambda chunks: "",
    )
    return result, emitters, dependencies


# ---------------------------------------------------------------------------------------------------------------
# FR-001: the setting
# ---------------------------------------------------------------------------------------------------------------


def test_settings_have_defaults_in_config_toml(monkeypatch):
    for name in ("DOCX_AI_RESULTS_DIR", "DOCX_AI_STUDIO_URL", "DOCX_AI_STUDIO_DIR"):
        monkeypatch.delenv(name, raising=False)
    config.reset_app_config_cache()

    app_config = config.load_app_config()

    assert app_config["results_dir"] == "translations"
    assert app_config["studio_url"] == "http://127.0.0.1:8601"
    assert app_config["studio_dir"] == "../AudiobookStudio"


def test_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("DOCX_AI_RESULTS_DIR", "D:\\Books\\done")
    monkeypatch.setenv("DOCX_AI_STUDIO_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("DOCX_AI_STUDIO_DIR", "/opt/studio")
    config.reset_app_config_cache()

    app_config = config.load_app_config()

    assert app_config["results_dir"] == "D:\\Books\\done"
    assert app_config["studio_url"] == "http://127.0.0.1:9999"
    assert app_config["studio_dir"] == "/opt/studio"
    config.reset_app_config_cache()


def test_env_example_and_gitignore_carry_the_setting():
    root = Path(__file__).resolve().parents[1]
    assert "DOCX_AI_RESULTS_DIR" in (root / ".env.example").read_text(encoding="utf-8")
    gitignore = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "translations/" in gitignore


def test_default_results_dir_is_under_the_isolated_project_root(isolate_results_folder):
    # The autouse fixture is what keeps the suite out of the owner's <project root>/translations.
    resolved = results_folder.resolve_results_dir({})
    assert resolved == isolate_results_folder / "translations"
    assert resolved != Path(results_folder.BASE_DIR) / "translations"


def test_relative_absolute_and_windows_style_results_dir(isolate_results_folder, tmp_path):
    assert results_folder.resolve_results_dir({"results_dir": "out/books"}) == isolate_results_folder / "out" / "books"
    assert results_folder.resolve_results_dir({"results_dir": str(tmp_path / "abs")}) == tmp_path / "abs"
    assert results_folder.resolve_results_dir({"results_dir": "D:\\Books\\done"}) == Path("/mnt/d/Books/done")
    assert (
        results_folder.resolve_project_path("../AudiobookStudio", default="x")
        == isolate_results_folder.parent / "AudiobookStudio"
    )


# ---------------------------------------------------------------------------------------------------------------
# SC-002: the path shown to the person
# ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "shown"),
    [
        ("/mnt/d/a/b", "D:\\a\\b"),
        ("/mnt/c/Users/me/translations/My Book", "C:\\Users\\me\\translations\\My Book"),
        ("/mnt/d", "D:\\"),
        ("/home/user/translations", "/home/user/translations"),
        ("D:\\already\\windows", "D:\\already\\windows"),
        ("/mnt/data/x", "/mnt/data/x"),
    ],
)
def test_windows_display_path(given, shown):
    assert results_folder.windows_display_path(given) == shown


def test_published_names_are_the_download_button_names():
    suffix_of = dict(results_folder.PUBLISHED_FILE_SUFFIXES)
    stem = "My Book.v2"
    builders = {
        "docx_path": ui._build_output_filename,
        "tts_text_path": ui._build_narration_filename,
        "tts_docx_path": ui._build_narration_docx_filename,
        "tts_pdf_path": ui._build_narration_pdf_filename,
        "narration_book_path": ui._build_narration_book_filename,
    }
    assert set(suffix_of) == set(builders)
    for key, builder in builders.items():
        assert f"{stem}{suffix_of[key]}" == builder(f"{stem}.docx")


# ---------------------------------------------------------------------------------------------------------------
# SC-001: the folder, at the helper level
# ---------------------------------------------------------------------------------------------------------------


def _group(tmp_path: Path, **files: bytes) -> dict[str, str]:
    paths: dict[str, str] = {}
    for key, data in files.items():
        path = tmp_path / "group" / f"{key}.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        paths[key] = str(path)
    return paths


def test_publish_copies_only_the_user_visible_files(tmp_path):
    artifacts = _group(
        tmp_path,
        markdown_path=b"# md",
        docx_path=b"docx",
        tts_text_path=b"tts",
        tts_docx_path=b"ttsdocx",
        tts_pdf_path=b"%PDF",
        narration_book_path=b"{}",
        metadata_path=b"{}",
        manifest_path=b"{}",
        formatting_review_path=b"review",
    )

    outcome = results_folder.publish_result_files(
        source_name="My Book.docx", artifact_paths=artifacts, results_dir=tmp_path / "out"
    )

    folder = tmp_path / "out" / "My Book"
    assert outcome.folder == folder
    assert sorted(p.name for p in folder.iterdir()) == [
        "My Book.narration.json",
        "My Book.tts.docx",
        "My Book.tts.pdf",
        "My Book.tts.txt",
        "My Book_edited.docx",
    ]
    assert (folder / "My Book_edited.docx").read_bytes() == b"docx"
    assert outcome.failed == ()


def test_publish_edit_result_is_the_docx_alone(tmp_path):
    artifacts = _group(tmp_path, markdown_path=b"# md", docx_path=b"docx")
    outcome = results_folder.publish_result_files(
        source_name="a.docx", artifact_paths=artifacts, results_dir=tmp_path / "out"
    )
    assert [Path(p).name for p in outcome.paths] == ["a_edited.docx"]


def test_rerun_replaces_a_file_and_identical_content_is_not_rewritten(tmp_path, monkeypatch):
    out = tmp_path / "out"
    first = _group(tmp_path, docx_path=b"first")
    results_folder.publish_result_files(source_name="a.docx", artifact_paths=first, results_dir=out)
    target = out / "a" / "a_edited.docx"
    assert target.read_bytes() == b"first"

    writes: list[Path] = []
    real_write = results_folder._write_atomic
    monkeypatch.setattr(results_folder, "_write_atomic", lambda path, data: (writes.append(path), real_write(path, data))[1])

    same = results_folder.publish_result_files(source_name="a.docx", artifact_paths=first, results_dir=out)
    assert writes == []
    assert same.unchanged == (str(target),)

    second = _group(tmp_path, docx_path=b"second")
    replaced = results_folder.publish_result_files(source_name="a.docx", artifact_paths=second, results_dir=out)
    assert target.read_bytes() == b"second"
    assert replaced.written == (str(target),)
    assert sorted(p.name for p in target.parent.iterdir()) == ["a_edited.docx"]  # no staging leftovers


def test_a_locked_file_gets_the_new_marker_and_nothing_raises(tmp_path, monkeypatch):
    out = tmp_path / "out"
    target_dir = out / "a"
    target_dir.mkdir(parents=True)
    (target_dir / "a_edited.docx").write_bytes(b"open in Word")
    real_write = results_folder._write_atomic

    def locked(path: Path, data: bytes) -> None:
        if path.name == "a_edited.docx":
            raise PermissionError(13, "in use")
        real_write(path, data)

    monkeypatch.setattr(results_folder, "_write_atomic", locked)
    artifacts = _group(tmp_path, docx_path=b"new result")

    outcome = results_folder.publish_result_files(source_name="a.docx", artifact_paths=artifacts, results_dir=out)

    assert (target_dir / "a_edited.docx").read_bytes() == b"open in Word"
    renamed = target_dir / "a_edited (новая).docx"
    assert renamed.read_bytes() == b"new result"
    assert outcome.renamed == (str(renamed),)
    assert outcome.paths == (str(renamed),)
    assert outcome.failed == ()


def test_a_file_that_cannot_be_placed_at_all_is_reported_and_the_rest_still_go(tmp_path, monkeypatch):
    real_write = results_folder._write_atomic

    def broken(path: Path, data: bytes) -> None:
        if "tts" in path.name:
            raise OSError(28, "no space")
        real_write(path, data)

    monkeypatch.setattr(results_folder, "_write_atomic", broken)
    artifacts = _group(tmp_path, docx_path=b"d", tts_text_path=b"t")

    outcome = results_folder.publish_result_files(
        source_name="a.docx", artifact_paths=artifacts, results_dir=tmp_path / "out"
    )

    assert [Path(p).name for p in outcome.paths] == ["a_edited.docx"]
    assert [name for name, _error in outcome.failed] == ["a.tts.txt"]


def test_source_name_with_forbidden_characters_still_makes_a_folder(tmp_path):
    outcome = results_folder.publish_result_files(
        source_name='What? "Now": a|b.docx', artifact_paths=_group(tmp_path, docx_path=b"d"), results_dir=tmp_path / "out"
    )
    assert outcome.folder is not None
    assert outcome.folder.parent == tmp_path / "out"
    assert not set('<>:"/\\|?*') & set(outcome.folder.name)


# ---------------------------------------------------------------------------------------------------------------
# SC-001: through the real late phase (delivered, blocked, failing)
# ---------------------------------------------------------------------------------------------------------------


def _expected_folder_files(artifact_paths: dict[str, str], stem: str) -> dict[str, bytes]:
    suffix_of = dict(results_folder.PUBLISHED_FILE_SUFFIXES)
    return {
        f"{stem}{suffix_of[key]}": Path(path).read_bytes()
        for key, path in artifact_paths.items()
        if key in suffix_of
    }


def _saved_artifact_paths(dependencies: _Dependencies) -> dict[str, str]:
    (event,) = dependencies.named("ui_result_artifacts_saved")
    return dict(cast(dict[str, str], event[1]["artifact_paths"]))


def test_delivered_audiobook_run_publishes_exactly_the_built_files(monkeypatch, tmp_path, isolate_results_folder):
    records = [_record("p1", "Первый абзац книги."), _record("p2", "Второй абзац книги.")]

    result, emitters, dependencies = _run(
        monkeypatch, tmp_path, operation="audiobook", state=_audiobook_state(records)
    )

    assert result == "succeeded"
    folder = isolate_results_folder / "translations" / "book"
    expected = _expected_folder_files(_saved_artifact_paths(dependencies), "book")
    assert "book.tts.txt" in expected and "book.tts.docx" in expected and "book_edited.docx" in expected
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == expected
    published = dependencies.named("ui_results_published")
    assert len(published) == 1
    assert published[0][0] == logging.INFO
    assert published[0][1]["folder"] == str(folder)
    assert sorted(cast(list[str], published[0][1]["paths"])) == sorted(str(folder / name) for name in expected)
    assert [c["latest_results_folder"] for c in emitters.state_calls if "latest_results_folder" in c] == [str(folder)]
    # the .run group is untouched: markdown and the other diagnostics are still there
    assert "markdown_path" in _saved_artifact_paths(dependencies)


def test_delivered_edit_run_publishes_the_docx_for_every_mode(monkeypatch, tmp_path, isolate_results_folder):
    result, emitters, dependencies = _run(
        monkeypatch, tmp_path, operation="edit", state=ProcessingState(processed_chunks=["текст"])
    )

    assert result == "succeeded"
    folder = isolate_results_folder / "translations" / "book"
    assert [p.name for p in folder.iterdir()] == ["book_edited.docx"]
    assert [c["latest_results_folder"] for c in emitters.state_calls if "latest_results_folder" in c] == [str(folder)]


def test_second_identical_run_leaves_the_folder_files_alone(monkeypatch, tmp_path, isolate_results_folder):
    state = ProcessingState(processed_chunks=["текст"])
    _run(monkeypatch, tmp_path, operation="edit", state=state)
    target = isolate_results_folder / "translations" / "book" / "book_edited.docx"
    stamp = target.stat().st_mtime_ns

    writes: list[Path] = []
    real_write = results_folder._write_atomic
    monkeypatch.setattr(results_folder, "_write_atomic", lambda path, data: (writes.append(path), real_write(path, data))[1])
    result, _emitters, dependencies = _run(monkeypatch, tmp_path, operation="edit", state=state)

    assert result == "succeeded"
    assert writes == []
    assert target.stat().st_mtime_ns == stamp
    (event,) = dependencies.named("ui_results_published")
    assert event[1]["unchanged_count"] == 1


def test_locked_file_in_a_run_gets_the_new_marker_and_the_run_still_succeeds(monkeypatch, tmp_path, isolate_results_folder):
    folder = isolate_results_folder / "translations" / "book"
    folder.mkdir(parents=True)
    (folder / "book_edited.docx").write_bytes(b"an older result open in Word")
    real_write = results_folder._write_atomic

    def locked(path: Path, data: bytes) -> None:
        if path.name == "book_edited.docx":
            raise PermissionError(13, "in use")
        real_write(path, data)

    monkeypatch.setattr(results_folder, "_write_atomic", locked)

    result, emitters, dependencies = _run(
        monkeypatch, tmp_path, operation="edit", state=ProcessingState(processed_chunks=["текст"])
    )

    assert result == "succeeded"
    assert (folder / "book_edited.docx").read_bytes() == b"an older result open in Word"
    assert (folder / "book_edited (новая).docx").read_bytes() == b"PK\x03\x04 review docx bytes"
    assert dependencies.named("ui_results_publish_failed") == []
    assert [c["latest_results_folder"] for c in emitters.state_calls if "latest_results_folder" in c] == [str(folder)]


def test_publish_failure_never_hides_the_delivered_result(monkeypatch, tmp_path):
    # A regular file where the project root should be: creating <root>/translations fails.
    not_a_directory = tmp_path / "plain_file"
    not_a_directory.write_text("x", encoding="utf-8")
    monkeypatch.setattr(results_folder, "PROJECT_ROOT", not_a_directory)

    result, emitters, dependencies = _run(
        monkeypatch, tmp_path, operation="edit", state=ProcessingState(processed_chunks=["текст"])
    )

    assert result == "succeeded"
    (failed,) = dependencies.named("ui_results_publish_failed")
    assert failed[0] == logging.WARNING
    assert failed[1]["error_type"]
    assert dependencies.named("ui_results_published") == []
    assert not any("latest_results_folder" in call for call in emitters.state_calls)
    # the delivered result itself is still announced and still in state
    assert len(dependencies.named("ui_result_artifacts_saved")) == 1
    assert any(call.get("latest_delivery_disposition") for call in emitters.state_calls)


def test_a_blocked_result_is_not_published(monkeypatch, tmp_path, isolate_results_folder):
    markdown = _MARKDOWN
    _install_stubs(monkeypatch, markdown=markdown)
    monkeypatch.setattr(
        late_phases,
        "_build_translation_quality_report",
        lambda **k: {"quality_status": "fail", "gate_reasons": ["synthetic_gate_reason"]},
    )
    monkeypatch.setattr(late_phases, "_format_translation_quality_gate_failure_message", lambda reasons: "blocked")
    dependencies = _Dependencies(tmp_path / "ui_results")
    emitters = _Emitters()
    ui_context = _context("edit")
    ui_context.app_config = {_PUBLISH_FLAG: True}

    late_phases.finalize_processing_success(
        context=ui_context,
        dependencies=dependencies,
        emitters=emitters,
        state=ProcessingState(processed_chunks=["текст"]),
        docx_phase={**_docx_phase(markdown), "docx_bytes": b"PK blocked docx bytes"},
        job_count=1,
        current_markdown_fn=lambda chunks: "",
    )

    assert any(
        cast(dict[str, object], call.get("latest_delivery_disposition") or {}).get("status") == "blocked"
        for call in emitters.state_calls
    )
    assert not (isolate_results_folder / "translations").exists()
    assert dependencies.named("ui_results_published") == []
    assert not any("latest_results_folder" in call for call in emitters.state_calls)


def test_the_project_root_is_replaced_for_every_test():
    # The autouse fixture replaced the root; the real default would be BASE_DIR/translations. The
    # session-level proof that nothing was written there is ``test_zz_the_session_did_not_touch_...``.
    assert results_folder.PROJECT_ROOT != results_folder.BASE_DIR


# ---------------------------------------------------------------------------------------------------------------
# the state transport: bundle and reset
# ---------------------------------------------------------------------------------------------------------------


def test_result_bundle_carries_the_results_folder():
    from docxaicorrector.processing.processing_runtime import build_result_bundle

    bundle = build_result_bundle(
        source_name="a.docx",
        source_token="t",
        docx_bytes=b"d",
        markdown_text="m",
        results_folder="/mnt/d/x",
    )
    assert bundle["results_folder"] == "/mnt/d/x"
    assert build_result_bundle(source_name="a", source_token="t", docx_bytes=b"d", markdown_text="m")["results_folder"] is None


def test_state_key_is_allowed_for_set_state_events():
    from docxaicorrector.processing import processing_runtime

    assert "latest_results_folder" in processing_runtime._ALLOWED_SET_STATE_EVENT_KEYS


# ---------------------------------------------------------------------------------------------------------------
# FR-003: the result screen
# ---------------------------------------------------------------------------------------------------------------


class _Screen:
    def __init__(self) -> None:
        self.markdowns: list[str] = []
        self.buttons: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.successes: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.pressed: set[str] = set()
        self.column_counts: list[int] = []

    def markdown(self, text, *a, **k) -> None:
        self.markdowns.append(str(text))

    def button(self, label, *a, **k) -> bool:
        self.buttons.append({"label": label, **k})
        return k.get("key") in self.pressed

    def error(self, text, *a, **k) -> None:
        self.errors.append(str(text))

    def success(self, text, *a, **k) -> None:
        self.successes.append(str(text))

    def link_button(self, label, url, *a, **k) -> None:
        self.links.append((str(label), str(url)))

    def caption(self, *a, **k) -> None:
        return None

    def download_button(self, *a, **k) -> None:
        return None

    def columns(self, n, *a, **k):
        count = n if isinstance(n, int) else len(n)
        self.column_counts.append(count)
        return [self for _ in range(count)]

    def spinner(self, *a, **k):
        from contextlib import nullcontext

        return nullcontext()


@pytest.fixture
def screen(monkeypatch, make_session_state) -> _Screen:
    fake = _Screen()
    monkeypatch.setattr(ui.st, "session_state", make_session_state())
    for name in ("markdown", "button", "error", "success", "link_button", "caption", "download_button", "columns", "spinner"):
        monkeypatch.setattr(ui.st, name, getattr(fake, name))
    return fake


def _render(**overrides) -> None:
    kwargs: dict[str, Any] = dict(
        docx_bytes=b"docx",
        markdown_text="md",
        original_filename="My Book.docx",
        processing_operation="edit",
        results_folder="/mnt/d/Work/translations/My Book",
    )
    kwargs.update(overrides)
    ui.render_result_bundle(**kwargs)


def test_screen_shows_the_windows_path_and_an_open_button(screen):
    _render()

    assert any("D:\\Work\\translations\\My Book" in text for text in screen.markdowns)
    assert any(text.startswith(t("result.results_folder_line", path="").split("`")[0]) for text in screen.markdowns)
    assert [b["label"] for b in screen.buttons] == [t("result.open_results_folder")]


@pytest.mark.parametrize("operation", ["edit", "translate", "audiobook"])
def test_the_folder_line_is_there_for_every_mode(screen, operation):
    _render(processing_operation=operation, narration_text="n" if operation == "audiobook" else None)

    assert any("D:\\Work\\translations\\My Book" in text for text in screen.markdowns)


@pytest.mark.parametrize("folder", [None, ""])
def test_no_folder_no_line_and_no_button(screen, folder):
    _render(results_folder=folder)

    assert screen.markdowns == []
    assert screen.buttons == []


def test_blocked_result_shows_no_folder_line(screen):
    _render(
        results_folder="/mnt/d/x",
        delivery_disposition={"status": "blocked", "explanation": "blocked", "message_key": ""},
    )

    assert not any("D:\\x" in text for text in screen.markdowns)
    assert screen.buttons == []


def test_open_folder_button_runs_explorer_with_the_windows_path(screen, monkeypatch):
    launched: list[list[str]] = []

    class _Popen:
        def __init__(self, args, **kwargs) -> None:
            launched.append(list(args))

    monkeypatch.setattr(results_folder.subprocess, "Popen", _Popen)
    screen.pressed.add("open_results_folder_button")

    _render()

    assert launched == [["explorer.exe", "D:\\Work\\translations\\My Book"]]
    assert screen.errors == []


def test_open_folder_failure_is_shown_with_its_cause(screen, monkeypatch):
    def _missing(*args, **kwargs):
        raise FileNotFoundError(2, "explorer.exe not found")

    monkeypatch.setattr(results_folder.subprocess, "Popen", _missing)
    screen.pressed.add("open_results_folder_button")

    _render()

    assert len(screen.errors) == 1
    assert "FileNotFoundError" in screen.errors[0]


# ---------------------------------------------------------------------------------------------------------------
# SC-003: Open in studio -- the module, with a replaced HTTP layer and start script
# ---------------------------------------------------------------------------------------------------------------


def _studio_dir(tmp_path: Path) -> Path:
    studio = tmp_path / "AudiobookStudio"
    (studio / "scripts").mkdir(parents=True)
    (studio / "scripts" / "studio.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return studio


class _FakePost:
    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, bytes, float]] = []

    def __call__(self, url: str, body: bytes, timeout: float) -> studio_handoff.HttpReply:
        self.calls.append((url, body, timeout))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer  # type: ignore[return-value]


def _refused() -> studio_handoff.StudioConnectionError:
    return studio_handoff.StudioConnectionError("[Errno 111] Connection refused", refused=True)


def _ok(book_id: str = "0123456789ab") -> studio_handoff.HttpReply:
    return studio_handoff.HttpReply(200, json.dumps({"book_id": book_id}).encode("utf-8"))


def _never_start(_dir: Path) -> studio_handoff.StartResult:  # pragma: no cover - reached only on a bug
    raise AssertionError("the studio must not be started")


def test_success_returns_the_link_with_the_book_id(tmp_path):
    post = _FakePost(_ok("abc123def456"))

    outcome = studio_handoff.send_book_to_studio(
        _BOOK_JSON.encode("utf-8"),
        studio_url="http://127.0.0.1:8601",
        studio_dir=_studio_dir(tmp_path),
        post=post,
        start_studio=_never_start,
    )

    assert outcome.ok and outcome.book_id == "abc123def456"
    assert outcome.link == "http://localhost:8601/#book=abc123def456"
    assert outcome.started_studio is False
    assert post.calls == [("http://127.0.0.1:8601/api/books", _BOOK_JSON.encode("utf-8"), studio_handoff.POST_TIMEOUT_SECONDS)]
    assert studio_handoff.POST_TIMEOUT_SECONDS > 0 and studio_handoff.START_TIMEOUT_SECONDS > 0


def test_browser_link_uses_localhost_and_the_configured_port():
    assert studio_handoff.build_browser_link("http://127.0.0.1:9000/", "id1") == "http://localhost:9000/#book=id1"
    assert studio_handoff.build_browser_link("http://studio.internal", "id1") == "http://localhost/#book=id1"


def test_refused_connection_starts_the_studio_and_retries_once(tmp_path):
    studio = _studio_dir(tmp_path)
    post = _FakePost(_refused(), _ok())
    started: list[Path] = []

    def start(directory: Path) -> studio_handoff.StartResult:
        started.append(directory)
        return studio_handoff.StartResult(0, "Студия запущена: http://localhost:8601")

    outcome = studio_handoff.send_book_to_studio(
        b"{}", studio_url="http://127.0.0.1:8601", studio_dir=studio, post=post, start_studio=start
    )

    assert outcome.ok and outcome.started_studio is True
    assert started == [studio]
    assert len(post.calls) == 2


def test_still_refused_after_the_start_is_reported_not_retried_again(tmp_path):
    post = _FakePost(_refused(), _refused())

    outcome = studio_handoff.send_book_to_studio(
        b"{}",
        studio_url="http://127.0.0.1:8601",
        studio_dir=_studio_dir(tmp_path),
        post=post,
        start_studio=lambda d: studio_handoff.StartResult(0, ""),
    )

    assert not outcome.ok and outcome.error_code == "unreachable" and outcome.started_studio is True
    assert len(post.calls) == 2


def test_a_rejected_file_shows_the_studios_detail(tmp_path):
    reply = studio_handoff.HttpReply(400, json.dumps({"detail": "Файл книги не по формату."}).encode("utf-8"))

    outcome = studio_handoff.send_book_to_studio(
        b"{}", studio_url="http://127.0.0.1:8601", studio_dir=_studio_dir(tmp_path),
        post=_FakePost(reply), start_studio=_never_start,
    )

    assert not outcome.ok
    assert outcome.error_code == "rejected" and outcome.http_status == 400
    assert outcome.error_detail == "Файл книги не по формату."


def test_a_non_json_error_body_is_shown_as_text_and_cut(tmp_path):
    reply = studio_handoff.HttpReply(502, b"x" * 1000)

    outcome = studio_handoff.send_book_to_studio(
        b"{}", studio_url="http://127.0.0.1:8601", studio_dir=_studio_dir(tmp_path),
        post=_FakePost(reply), start_studio=_never_start,
    )

    assert outcome.error_code == "rejected" and len(outcome.error_detail) == 300


def test_a_success_without_a_book_id_is_a_bad_response(tmp_path):
    outcome = studio_handoff.send_book_to_studio(
        b"{}", studio_url="http://127.0.0.1:8601", studio_dir=_studio_dir(tmp_path),
        post=_FakePost(studio_handoff.HttpReply(200, b"{}")), start_studio=_never_start,
    )

    assert not outcome.ok and outcome.error_code == "bad_response"


def test_a_missing_studio_folder_is_named_when_the_studio_is_down(tmp_path):
    missing = tmp_path / "no-such-studio"

    outcome = studio_handoff.send_book_to_studio(
        b"{}", studio_url="http://127.0.0.1:8601", studio_dir=missing,
        post=_FakePost(_refused()), start_studio=_never_start,
    )

    assert not outcome.ok and outcome.error_code == "studio_dir_missing"
    assert outcome.error_detail == str(missing)


def test_a_failing_start_script_shows_its_output(tmp_path):
    outcome = studio_handoff.send_book_to_studio(
        b"{}", studio_url="http://127.0.0.1:8601", studio_dir=_studio_dir(tmp_path),
        post=_FakePost(_refused()),
        start_studio=lambda d: studio_handoff.StartResult(2, "Нет .venv/bin/python — сначала bash scripts/setup-wsl.sh"),
    )

    assert not outcome.ok and outcome.error_code == "start_failed"
    assert "setup-wsl.sh" in outcome.error_detail


def test_a_slow_or_reset_connection_is_not_a_reason_to_start_the_studio(tmp_path):
    outcome = studio_handoff.send_book_to_studio(
        b"{}", studio_url="http://127.0.0.1:8601", studio_dir=_studio_dir(tmp_path),
        post=_FakePost(studio_handoff.StudioConnectionError("timed out", refused=False)),
        start_studio=_never_start,
    )

    assert not outcome.ok and outcome.error_code == "unreachable" and outcome.error_detail == "timed out"


def test_http_layer_maps_urllib_errors(monkeypatch):
    def refuse(request, timeout):
        raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))

    monkeypatch.setattr(studio_handoff.urllib.request, "urlopen", refuse)
    with pytest.raises(studio_handoff.StudioConnectionError) as refused:
        studio_handoff.post_json_bytes("http://127.0.0.1:1/api/books", b"{}", 1.0)
    assert refused.value.refused is True

    def time_out(request, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(studio_handoff.urllib.request, "urlopen", time_out)
    with pytest.raises(studio_handoff.StudioConnectionError) as slow:
        studio_handoff.post_json_bytes("http://127.0.0.1:1/api/books", b"{}", 1.0)
    assert slow.value.refused is False

    import io

    def bad_request(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {}, io.BytesIO('{"detail": "нет"}'.encode("utf-8"))  # type: ignore[arg-type]
        )

    monkeypatch.setattr(studio_handoff.urllib.request, "urlopen", bad_request)
    reply = studio_handoff.post_json_bytes("http://127.0.0.1:1/api/books", b"{}", 1.0)
    assert reply.status == 400 and b"\xd0\xbd\xd0\xb5\xd1\x82" in reply.body


def test_http_layer_posts_the_raw_file_as_json(monkeypatch):
    seen: dict[str, Any] = {}

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            return None

        def read(self) -> bytes:
            return b'{"book_id": "x"}'

    def capture(request, timeout):
        seen.update(url=request.full_url, data=request.data, method=request.get_method(), timeout=timeout,
                    content_type=request.get_header("Content-type"))
        return _Response()

    monkeypatch.setattr(studio_handoff.urllib.request, "urlopen", capture)

    reply = studio_handoff.post_json_bytes("http://127.0.0.1:8601/api/books", b'{"a": 1}', 12.0)

    assert reply.status == 200
    assert seen == {
        "url": "http://127.0.0.1:8601/api/books",
        "data": b'{"a": 1}',
        "method": "POST",
        "timeout": 12.0,
        "content_type": "application/json",
    }


def test_start_script_runner_uses_bash_and_the_studio_script(tmp_path, monkeypatch):
    studio = _studio_dir(tmp_path)
    seen: dict[str, Any] = {}

    def fake_run(command, **kwargs):
        seen.update(command=command, **kwargs)
        return SimpleNamespace(returncode=0, stdout="Студия запущена\n".encode("utf-8"))

    monkeypatch.setattr(studio_handoff.subprocess, "run", fake_run)

    result = studio_handoff.run_studio_start_script(studio)

    assert seen["command"] == ["bash", str(studio / "scripts" / "studio.sh"), "start"]
    assert seen["cwd"] == str(studio)
    assert seen["timeout"] == studio_handoff.START_TIMEOUT_SECONDS
    assert result == studio_handoff.StartResult(0, "Студия запущена")


def test_start_script_runner_reports_timeout_and_missing_bash(tmp_path, monkeypatch):
    studio = _studio_dir(tmp_path)

    def hang(command, **kwargs):
        raise studio_handoff.subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(studio_handoff.subprocess, "run", hang)
    assert studio_handoff.run_studio_start_script(studio).returncode != 0

    def no_bash(command, **kwargs):
        raise FileNotFoundError(2, "bash")

    monkeypatch.setattr(studio_handoff.subprocess, "run", no_bash)
    missing = studio_handoff.run_studio_start_script(studio)
    assert missing.returncode != 0 and "FileNotFoundError" in missing.output


# ---------------------------------------------------------------------------------------------------------------
# SC-003: Open in studio -- the result screen
# ---------------------------------------------------------------------------------------------------------------


def _exports(**overrides) -> dict[str, Any]:
    base: dict[str, Any] = {
        "docx_bytes": b"tts-docx",
        "pdf_bytes": None,
        "docx_unavailable_reason": None,
        "pdf_unavailable_reason": "soffice_not_found",
        "book_json": _BOOK_JSON,
    }
    base.update(overrides)
    return base


def _render_audiobook(**overrides) -> None:
    kwargs: dict[str, Any] = dict(
        docx_bytes=b"review",
        markdown_text="md",
        original_filename="My Book.docx",
        narration_text="narration",
        processing_operation="audiobook",
        narration_exports=_exports(),
        results_folder=None,
    )
    kwargs.update(overrides)
    ui.render_result_bundle(**kwargs)


def _studio_button_labels(screen: _Screen) -> list[str]:
    return [b["label"] for b in screen.buttons if b.get("key") == "studio_handoff_button"]


def test_studio_button_sits_in_the_narration_row_with_the_book(screen):
    _render_audiobook()

    assert _studio_button_labels(screen) == [t("result.studio_open_button")]
    assert t("result.studio_open_button") != "result.studio_open_button"
    # docx + txt + book + studio, then the review row
    assert screen.column_counts == [4, 2]


@pytest.mark.parametrize("missing", [None, ""])
def test_no_studio_button_without_the_book_file(screen, missing):
    _render_audiobook(narration_exports=_exports(book_json=missing))

    assert _studio_button_labels(screen) == []


def test_no_studio_button_on_a_blocked_result(screen):
    _render_audiobook(delivery_disposition={"status": "blocked", "explanation": "blocked", "message_key": ""})

    assert _studio_button_labels(screen) == []


@pytest.mark.parametrize("operation", ["edit", "translate"])
def test_no_studio_button_outside_audiobook(screen, operation):
    _render_audiobook(processing_operation=operation, narration_text="n" if operation == "translate" else None)

    assert _studio_button_labels(screen) == []


def _fake_send(monkeypatch, outcome: studio_handoff.StudioHandoffOutcome) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def send(book_bytes: bytes, **kwargs: Any) -> studio_handoff.StudioHandoffOutcome:
        calls.append({"book_bytes": book_bytes, **kwargs})
        return outcome

    monkeypatch.setattr(ui, "send_book_to_studio", send)
    return calls


@pytest.fixture
def logged(monkeypatch) -> list[tuple[int, str, dict[str, Any]]]:
    events: list[tuple[int, str, dict[str, Any]]] = []
    monkeypatch.setattr(ui, "log_event", lambda level, event, message, **ctx: events.append((level, event, ctx)))
    return events


def test_click_success_shows_the_link_and_logs_the_book_id(screen, monkeypatch, logged):
    outcome = studio_handoff.StudioHandoffOutcome(
        ok=True, book_id="abc123def456", link="http://localhost:8601/#book=abc123def456", started_studio=True
    )
    calls = _fake_send(monkeypatch, outcome)
    screen.pressed.add("studio_handoff_button")

    _render_audiobook()

    assert calls[0]["book_bytes"] == _BOOK_JSON.encode("utf-8")
    assert screen.links == [(t("result.studio_open_book_link"), "http://localhost:8601/#book=abc123def456")]
    assert screen.errors == []
    (event,) = [e for e in logged if e[1] == "studio_handoff_succeeded"]
    assert event[0] == logging.INFO and event[2]["book_id"] == "abc123def456" and event[2]["started_studio"] is True


def test_the_link_stays_on_the_screen_after_the_click_rerun(screen, monkeypatch, logged):
    _fake_send(
        monkeypatch,
        studio_handoff.StudioHandoffOutcome(ok=True, book_id="abc", link="http://localhost:8601/#book=abc"),
    )
    screen.pressed.add("studio_handoff_button")
    _render_audiobook()
    screen.pressed.clear()
    screen.links.clear()

    _render_audiobook()  # the next rerun, no click

    assert screen.links == [(t("result.studio_open_book_link"), "http://localhost:8601/#book=abc")]


def test_the_outcome_is_not_shown_under_another_books_file(screen, monkeypatch, logged):
    _fake_send(
        monkeypatch,
        studio_handoff.StudioHandoffOutcome(ok=True, book_id="abc", link="http://localhost:8601/#book=abc"),
    )
    screen.pressed.add("studio_handoff_button")
    _render_audiobook()
    screen.pressed.clear()
    screen.links.clear()

    _render_audiobook(narration_exports=_exports(book_json='{"another": "book"}'))

    assert screen.links == []


@pytest.mark.parametrize(
    ("outcome", "must_contain"),
    [
        (
            studio_handoff.StudioHandoffOutcome(ok=False, error_code="studio_dir_missing", error_detail="/mnt/d/none"),
            ["DOCX_AI_STUDIO_DIR", "/mnt/d/none"],
        ),
        (
            studio_handoff.StudioHandoffOutcome(ok=False, error_code="start_failed", error_detail="Нет .venv/bin/python"),
            ["Нет .venv/bin/python"],
        ),
        (
            studio_handoff.StudioHandoffOutcome(
                ok=False, error_code="rejected", error_detail="Файл книги не по формату.", http_status=400
            ),
            ["Файл книги не по формату.", "400"],
        ),
        (
            studio_handoff.StudioHandoffOutcome(ok=False, error_code="unreachable", error_detail="timed out"),
            ["timed out", "DOCX_AI_STUDIO_URL"],
        ),
    ],
)
def test_click_failure_is_shown_with_its_cause(screen, monkeypatch, logged, outcome, must_contain):
    _fake_send(monkeypatch, outcome)
    screen.pressed.add("studio_handoff_button")

    _render_audiobook()

    assert len(screen.errors) == 1
    for fragment in must_contain:
        assert fragment in screen.errors[0]
    assert screen.links == []
    (event,) = [e for e in logged if e[1] == "studio_handoff_failed"]
    assert event[0] == logging.WARNING and event[2]["reason"] == outcome.error_code


def test_studio_settings_come_from_the_config_and_resolve_against_the_project_root(isolate_results_folder, monkeypatch):
    monkeypatch.setattr(
        ui, "load_app_config", lambda: {"studio_url": "http://127.0.0.1:9000", "studio_dir": "../AudiobookStudio"}
    )

    url, directory = ui._studio_settings()

    assert url == "http://127.0.0.1:9000"
    assert directory == isolate_results_folder.parent / "AudiobookStudio"


def test_studio_settings_fall_back_to_the_defaults_when_the_config_cannot_load(isolate_results_folder, monkeypatch):
    def broken():
        raise RuntimeError("config unreadable")

    monkeypatch.setattr(ui, "load_app_config", broken)

    url, directory = ui._studio_settings()

    assert url == studio_handoff.DEFAULT_STUDIO_URL
    assert directory == isolate_results_folder.parent / "AudiobookStudio"


@pytest.mark.parametrize("catalog", ["ru.json", "en.json"])
def test_new_ui_strings_are_in_both_catalogs(catalog):
    data = json.loads((Path(ui.__file__).resolve().parent / "locales" / catalog).read_text(encoding="utf-8"))
    keys = [
        "result.results_folder_line",
        "result.open_results_folder",
        "result.open_results_folder_failed",
        "result.studio_open_button",
        "result.studio_sending_spinner",
        "result.studio_handoff_sent",
        "result.studio_open_book_link",
        *ui._STUDIO_ERROR_KEYS.values(),
    ]
    for key in keys:
        assert str(data.get(key, "")).strip(), f"{key} missing from {catalog}"
