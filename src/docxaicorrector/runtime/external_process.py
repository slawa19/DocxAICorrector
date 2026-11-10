"""Shared external-process helpers (spec 072, research R8).

Moved verbatim from ``processing/processing_runtime.py`` (``_run_completed_process`` /
``_terminate_process_tree``) so that lower layers (``generation``, ``pipeline``) can run
LibreOffice without importing ``processing``. ``processing_runtime`` is switched to these
names by a later work package.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time

_DEFAULT_TIMEOUT_SECONDS = 120
_TERMINATE_GRACE_SECONDS = 5
_COLLECT_TIMEOUT_SECONDS = 5


def find_soffice_binary() -> str | None:
    """Return the LibreOffice executable (``soffice``, else ``libreoffice``) or ``None``."""
    return shutil.which("soffice") or shutil.which("libreoffice")


def run_completed_process(
    command: list[str],
    *,
    error_message: str,
    text: bool = True,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    cleanup_process_group: bool = False,
):
    if cleanup_process_group:
        process = None
        try:
            popen_kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": text,
            }
            if text:
                popen_kwargs["encoding"] = "utf-8"
                popen_kwargs["errors"] = "replace"
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True
            process = subprocess.Popen(command, **popen_kwargs)
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            if process is not None:
                terminate_process_tree(process)
                _collect_output_bounded(process)
            raise RuntimeError(
                f"{error_message} Превышено время ожидания {timeout_seconds} сек."
            ) from exc
        except OSError as exc:
            raise RuntimeError(error_message) from exc

        if process is None:
            raise RuntimeError(error_message)
        if process.returncode != 0:
            stderr_text = (stderr or "").strip() if text else ""
            stdout_text = (stdout or "").strip() if text else ""
            detail = stderr_text or stdout_text or f"exit_code={process.returncode}"
            raise RuntimeError(f"{error_message} {detail}")
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=text,
            timeout=timeout_seconds,
            encoding="utf-8" if text else None,
            errors="replace" if text else None,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"{error_message} Превышено время ожидания {timeout_seconds} сек."
        ) from exc
    except OSError as exc:
        raise RuntimeError(error_message) from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip() if text else ""
        detail = stderr or stdout or f"exit_code={result.returncode}"
        raise RuntimeError(f"{error_message} {detail}")
    return result


def _collect_output_bounded(process: subprocess.Popen) -> None:
    """Drain what is left on the pipes after a timeout, never blocking for good.

    A process outside the killed group (or one that escaped it) may still hold the pipe
    write ends; then ``communicate()`` would wait forever. Give up after a bound, close
    the pipes and return so the caller can raise its timeout error."""
    try:
        process.communicate(timeout=_COLLECT_TIMEOUT_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    except (OSError, ValueError):
        pass
    for stream in (process.stdout, process.stderr):
        try:
            if stream is not None:
                stream.close()
        except (OSError, ValueError):
            pass
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=_COLLECT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        pass


def _group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def terminate_process_tree(process: subprocess.Popen) -> None:
    """End the whole process group of ``process``: SIGTERM, a short grace, then SIGKILL.

    The group always gets SIGKILL when it is still populated after the grace, whether or
    not the leader itself already exited (a child that outlives the leader would
    otherwise keep the pipes open and survive)."""
    if os.name == "nt":
        try:
            process.kill()
        except OSError:
            pass
        return
    pgid = process.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        process.kill()
        return

    deadline = time.monotonic() + _TERMINATE_GRACE_SECONDS
    try:
        process.wait(timeout=_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    while _group_exists(pgid) and time.monotonic() < deadline:
        time.sleep(0.05)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        process.kill()
        return
    try:
        process.wait(timeout=_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass
