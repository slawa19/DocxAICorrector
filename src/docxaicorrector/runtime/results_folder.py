"""Spec 075: the durable results folder.

``.run/ui_results/`` is a cache that prunes itself (older than seven days, or over 80 groups), so
the files a person actually wants to keep are copied for good into
``<results folder>/<source stem>/`` under the names the result screen's download buttons use.

This module is pure file work, with no Streamlit and no logging: the pipeline logs the outcome
(``ui_results_published`` / ``ui_results_publish_failed``) and the result screen shows the folder.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from docxaicorrector.core.constants import BASE_DIR

# Relative settings (results folder, studio folder) are read from here. A module attribute so
# tests/conftest.py can point it at a temporary directory: the suite must never create
# ``<project root>/translations`` (spec 075 Anti-regression).
PROJECT_ROOT: Path = BASE_DIR
DEFAULT_RESULTS_DIR = "translations"
NEW_FILE_MARKER = " (новая)"

# ``write_ui_result_artifacts`` artifact key -> the suffix the download button gives the file
# (``ui/_ui.py``: ``_build_output_filename`` and the ``_build_narration_*_filename`` helpers).
# ``tests/test_spec_075_results_folder.py`` pins this table to those helpers. Markdown "for
# review", ``meta``, ``manifest`` and the formatting report stay in ``.run/ui_results/``.
PUBLISHED_FILE_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("docx_path", "_edited.docx"),
    ("tts_text_path", ".tts.txt"),
    ("tts_docx_path", ".tts.docx"),
    ("tts_pdf_path", ".tts.pdf"),
    ("narration_book_path", ".narration.json"),
)

_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_WSL_DRIVE_PATH = re.compile(r"^/mnt/([A-Za-z])(?:/(.*))?$")
_INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class PublishOutcome:
    """What one publication did. ``folder`` is None when no file reached the folder."""

    folder: Path | None
    # Final paths of every file now in the folder (written, unchanged or written as "(новая)").
    paths: tuple[str, ...] = ()
    written: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    renamed: tuple[str, ...] = ()
    # ``(file name, error text)`` for files that could not be placed even under the new name.
    failed: tuple[tuple[str, str], ...] = field(default_factory=tuple)


def _config_value(app_config: object, key: str) -> object:
    try:
        return app_config[key]  # type: ignore[index]
    except (KeyError, TypeError, IndexError):
        return None


def resolve_project_path(raw_value: object, *, default: str) -> Path:
    """A settings path: ``~`` expanded, ``D:\\x`` read as ``/mnt/d/x`` under WSL, relative to the project root."""
    raw = str(raw_value or "").strip() or default
    if os.name != "nt":
        drive = _WINDOWS_DRIVE_PATH.match(raw)
        if drive:
            raw = f"/mnt/{raw[0].lower()}/" + raw[3:].replace("\\", "/")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return Path(os.path.normpath(path))


def resolve_results_dir(app_config: object) -> Path:
    return resolve_project_path(_config_value(app_config, "results_dir"), default=DEFAULT_RESULTS_DIR)


def windows_display_path(path: str | Path) -> str:
    """``/mnt/d/a/b`` -> ``D:\\a\\b`` for the person reading the result screen; any other path as is."""
    text = str(path)
    match = _WSL_DRIVE_PATH.match(text)
    if match is None:
        return text
    rest = (match.group(2) or "").replace("/", "\\")
    return f"{match.group(1).upper()}:\\{rest}"


def _safe_name_part(value: str) -> str:
    cleaned = _INVALID_NAME_CHARS.sub("_", value).strip().rstrip(".")
    return cleaned or "result"


def _same_content(path: Path, data: bytes) -> bool:
    try:
        return path.is_file() and path.stat().st_size == len(data) and path.read_bytes() == data
    except OSError:
        return False


def _write_atomic(target: Path, data: bytes) -> None:
    """Stage next to the target, then replace it: a file open in Word or a player refuses the
    replacement (``PermissionError``/``OSError``) instead of being left half-written."""
    handle, staged_name = tempfile.mkstemp(dir=target.parent, prefix=".publish-", suffix=".tmp")
    staged = Path(staged_name)
    try:
        with os.fdopen(handle, "wb") as staged_file:
            staged_file.write(data)
        os.replace(staged, target)
    finally:
        with suppress(OSError):
            staged.unlink()


def _place_file(target: Path, data: bytes) -> tuple[Path, str]:
    if _same_content(target, data):
        return target, "unchanged"
    try:
        _write_atomic(target, data)
        return target, "written"
    except OSError:
        # Locked (open in Word / a player) or otherwise unwritable: keep the new result next to it.
        alternative = target.with_name(f"{target.stem}{NEW_FILE_MARKER}{target.suffix}")
        if _same_content(alternative, data):
            return alternative, "unchanged"
        _write_atomic(alternative, data)
        return alternative, "renamed"


def publish_result_files(
    *,
    source_name: str,
    artifact_paths: Mapping[str, str],
    results_dir: Path,
) -> PublishOutcome:
    """Copy the user-visible result files into ``<results_dir>/<source stem>/``.

    Only files named in ``artifact_paths`` (those that were built) are copied. A file that cannot
    be placed is reported in ``failed`` and the others still go; only the folder itself failing
    to open raises, and the caller treats that as ``ui_results_publish_failed``.
    """
    stem = _safe_name_part(Path(source_name).stem)
    folder = results_dir / stem
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    written: list[str] = []
    unchanged: list[str] = []
    renamed: list[str] = []
    failed: list[tuple[str, str]] = []
    for artifact_key, suffix in PUBLISHED_FILE_SUFFIXES:
        source_path = artifact_paths.get(artifact_key)
        if not source_path:
            continue
        file_name = f"{stem}{suffix}"
        try:
            data = Path(source_path).read_bytes()
            final_path, status = _place_file(folder / file_name, data)
        except Exception as exc:  # a failed copy must not keep the other files out
            failed.append((file_name, f"{type(exc).__name__}: {exc}"))
            continue
        paths.append(str(final_path))
        {"written": written, "unchanged": unchanged, "renamed": renamed}[status].append(str(final_path))
    return PublishOutcome(
        folder=folder if paths else None,
        paths=tuple(paths),
        written=tuple(written),
        unchanged=tuple(unchanged),
        renamed=tuple(renamed),
        failed=tuple(failed),
    )


def open_in_file_manager(folder: str | Path) -> str | None:
    """Open ``folder`` in Windows Explorer (``explorer.exe`` with the Windows path, from WSL too).

    Returns None when Explorer was started, otherwise the reason. Explorer's own exit code is
    not an error signal (it returns 1 on success), so it is not read.
    """
    try:
        subprocess.Popen(
            ["explorer.exe", windows_display_path(folder)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return f"{type(exc).__name__}: {exc}"
    return None
