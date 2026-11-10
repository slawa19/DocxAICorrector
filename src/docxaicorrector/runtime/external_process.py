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

_DEFAULT_TIMEOUT_SECONDS = 120


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
                process.communicate()
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


def terminate_process_tree(process: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            process.kill()
            return
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        process.kill()
        return

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError:
            process.kill()
