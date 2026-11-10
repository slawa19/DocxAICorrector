"""Spec 072 WP-D: narration PDF export (FR-005), CI part.

No LibreOffice needed: ``runner`` and ``find_soffice`` are substituted. The real-PDF
checks live in ``tests/test_spec_072_narration_pdf_system.py``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from docxaicorrector.generation import narration_pdf
from docxaicorrector.generation.narration_pdf import (
    NARRATION_PDF_FILTER,
    NARRATION_PDF_TIMEOUT_SECONDS,
    NARRATION_PDF_UNAVAILABLE_REASONS,
    NarrationPdfOutcome,
    export_narration_pdf,
)
from docxaicorrector.runtime import external_process

REPO_ROOT = Path(__file__).resolve().parent.parent
FAKE_SOFFICE = "/fake/bin/soffice"


def _find_ok() -> str:
    return FAKE_SOFFICE


class RecordingRunner:
    """Stands in for ``run_completed_process``; optionally writes an output file."""

    def __init__(self, *, output: bytes | None = None, raises: BaseException | None = None):
        self.output = output
        self.raises = raises
        self.calls: list[tuple[list[str], dict]] = []
        self.input_bytes_at_call: bytes | None = None
        self.profile_dirs: list[str] = []
        self.tmp_dirs: list[Path] = []

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), dict(kwargs)))
        docx_path = Path(command[-1])
        self.input_bytes_at_call = docx_path.read_bytes()
        self.tmp_dirs.append(docx_path.parent)
        profile_arg = next(a for a in command if a.startswith("-env:UserInstallation="))
        self.profile_dirs.append(profile_arg)
        if self.raises is not None:
            raise self.raises
        if self.output is not None:
            outdir = Path(command[command.index("--outdir") + 1])
            (outdir / (docx_path.stem + ".pdf")).write_bytes(self.output)
        return subprocess.CompletedProcess(command, 0, "", "")


# --- T-D1 -----------------------------------------------------------------------------


def test_command_shape_and_runner_kwargs():
    runner = RecordingRunner(output=b"%PDF-1.7 fake")
    outcome = export_narration_pdf(b"DOCX-BYTES", stem="book", runner=runner, find_soffice=_find_ok)

    assert outcome.reason is None
    assert len(runner.calls) == 1
    command, kwargs = runner.calls[0]
    tmp = runner.tmp_dirs[0]
    assert command == [
        FAKE_SOFFICE,
        f"-env:UserInstallation={(tmp / 'lo_profile').as_uri()}",
        "--headless",
        "--norestore",
        "--convert-to",
        NARRATION_PDF_FILTER,
        "--outdir",
        str(tmp),
        str(tmp / "book.tts.docx"),
    ]
    assert kwargs["cleanup_process_group"] is True
    assert kwargs["timeout_seconds"] == 60
    assert runner.input_bytes_at_call == b"DOCX-BYTES"


def test_filter_constant_is_the_measured_bookmarks_filter():
    assert NARRATION_PDF_FILTER == (
        'pdf:writer_pdf_Export:{"ExportBookmarks":{"type":"boolean","value":"true"}}'
    )
    # the JSON part must stay valid JSON
    json.loads(NARRATION_PDF_FILTER.split(":", 2)[2])
    assert NARRATION_PDF_TIMEOUT_SECONDS == 60


# --- T-D2 -----------------------------------------------------------------------------


@pytest.mark.parametrize("output", [b"%PDF-1.7 ok", None], ids=["success", "failure"])
def test_profile_dirs_are_unique_and_temp_dir_is_removed(output):
    runner = RecordingRunner(output=output)
    export_narration_pdf(b"x", stem="a", runner=runner, find_soffice=_find_ok)
    export_narration_pdf(b"x", stem="a", runner=runner, find_soffice=_find_ok)

    assert len(runner.profile_dirs) == 2
    assert runner.profile_dirs[0] != runner.profile_dirs[1]
    for tmp in runner.tmp_dirs:
        assert not tmp.exists()


def test_temp_dir_is_removed_when_runner_raises():
    runner = RecordingRunner(raises=RuntimeError("boom"))
    export_narration_pdf(b"x", stem="a", runner=runner, find_soffice=_find_ok)
    assert runner.tmp_dirs and not runner.tmp_dirs[0].exists()


# --- T-D3 -----------------------------------------------------------------------------


def test_soffice_not_found_does_not_call_runner():
    runner = RecordingRunner(output=b"%PDF-")
    outcome = export_narration_pdf(b"x", stem="a", runner=runner, find_soffice=lambda: None)
    assert outcome.pdf_bytes is None
    assert outcome.reason == "soffice_not_found"
    assert outcome.seconds == 0.0
    assert runner.calls == []


def test_timeout_reason():
    runner = RecordingRunner(raises=RuntimeError("Не удалось. Превышено время ожидания 60 сек."))
    outcome = export_narration_pdf(b"x", stem="a", runner=runner, find_soffice=_find_ok)
    assert (outcome.pdf_bytes, outcome.reason) == (None, "timeout")
    assert "Превышено время ожидания" in outcome.detail


@pytest.mark.parametrize(
    "exc",
    [RuntimeError("exit_code=1"), OSError("cannot exec")],
    ids=["runtime_error", "os_error"],
)
def test_failed_reason(exc):
    runner = RecordingRunner(raises=exc)
    outcome = export_narration_pdf(b"x", stem="a", runner=runner, find_soffice=_find_ok)
    assert (outcome.pdf_bytes, outcome.reason) == (None, "failed")


def test_missing_output_reason():
    outcome = export_narration_pdf(b"x", stem="a", runner=RecordingRunner(output=None), find_soffice=_find_ok)
    assert (outcome.pdf_bytes, outcome.reason) == (None, "missing_output")


def test_empty_output_reason():
    outcome = export_narration_pdf(b"x", stem="a", runner=RecordingRunner(output=b""), find_soffice=_find_ok)
    assert (outcome.pdf_bytes, outcome.reason) == (None, "empty_output")


def test_not_pdf_reason():
    outcome = export_narration_pdf(
        b"x", stem="a", runner=RecordingRunner(output=b"<html>nope</html>"), find_soffice=_find_ok
    )
    assert (outcome.pdf_bytes, outcome.reason) == (None, "not_pdf")


def test_success_returns_bytes_and_reason_none():
    outcome = export_narration_pdf(
        b"x", stem="a", runner=RecordingRunner(output=b"%PDF-1.7 body"), find_soffice=_find_ok
    )
    assert outcome.pdf_bytes == b"%PDF-1.7 body"
    assert outcome.reason is None


def test_success_seconds_positive_without_monkeypatch():
    outcome = export_narration_pdf(
        b"x", stem="a", runner=RecordingRunner(output=b"%PDF-1.7 body"), find_soffice=_find_ok
    )
    assert outcome.seconds > 0


def test_detail_is_capped_and_outcome_is_frozen():
    runner = RecordingRunner(raises=RuntimeError("e" * 1000))
    outcome = export_narration_pdf(b"x", stem="a", runner=runner, find_soffice=_find_ok)
    assert len(outcome.detail) <= 300
    with pytest.raises(Exception):
        outcome.reason = "x"  # type: ignore[misc]


def test_reason_vocabulary_is_the_closed_set_of_seven():
    assert NARRATION_PDF_UNAVAILABLE_REASONS == (
        "docx_not_built",
        "soffice_not_found",
        "timeout",
        "failed",
        "missing_output",
        "empty_output",
        "not_pdf",
    )
    assert NarrationPdfOutcome(pdf_bytes=None, reason="failed", seconds=0.0, detail="").reason == "failed"


# --- T-D4 -----------------------------------------------------------------------------


def test_run_completed_process_cleans_process_group_on_timeout(monkeypatch):
    process_instances = []
    terminated = []

    class PopenStub:
        pid = 1234
        returncode = None

        def __init__(self, command, **kwargs):
            self.command = command
            self.kwargs = kwargs
            self.communicate_calls = 0
            process_instances.append(self)

        def communicate(self, timeout=None):
            self.communicate_calls += 1
            if self.communicate_calls == 1:
                raise subprocess.TimeoutExpired(cmd=self.command, timeout=float(timeout or 0))
            self.returncode = -15
            return "", ""

    monkeypatch.setattr(external_process.subprocess, "Popen", PopenStub)
    monkeypatch.setattr(external_process, "terminate_process_tree", lambda process: terminated.append(process))

    with pytest.raises(RuntimeError, match="Превышено время ожидания"):
        external_process.run_completed_process(
            ["soffice"], error_message="boom", cleanup_process_group=True, timeout_seconds=1
        )

    assert terminated == process_instances
    assert process_instances[0].communicate_calls == 2


def test_run_completed_process_default_timeout_is_120():
    import inspect

    sig = inspect.signature(external_process.run_completed_process)
    assert sig.parameters["timeout_seconds"].default == 120


def test_find_soffice_binary_prefers_soffice_then_libreoffice_then_none(monkeypatch):
    available = {"soffice": "/usr/bin/soffice", "libreoffice": "/usr/bin/libreoffice"}
    monkeypatch.setattr(external_process.shutil, "which", lambda name: available.get(name))
    assert external_process.find_soffice_binary() == "/usr/bin/soffice"

    available.pop("soffice")
    assert external_process.find_soffice_binary() == "/usr/bin/libreoffice"

    available.pop("libreoffice")
    assert external_process.find_soffice_binary() is None


# --- T-D5 -----------------------------------------------------------------------------


def test_apt_requirements_list_fonts_liberation():
    lines = (REPO_ROOT / "system-requirements.apt").read_text(encoding="utf-8").splitlines()
    packages = {line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")}
    assert "fonts-liberation" in packages


def test_setup_script_verifies_cyrillic_liberation_serif():
    setup_script = (REPO_ROOT / "scripts" / "setup-wsl.sh").read_text(encoding="utf-8")
    assert 'fc-list ":lang=ru:family=Liberation Serif"' in setup_script
