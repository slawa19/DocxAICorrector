"""Spec 072 acceptance finding 1: a timeout ends the WHOLE process group and always returns.

Real processes, no mock of ``terminate_process_tree``: the leader exits on SIGTERM while a
child of the same session ignores SIGTERM and keeps the stdout pipe open. Before the fix the
group never got SIGKILL (only the leader's own wait timing out triggered it) and the
unbounded ``communicate()`` hung forever.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

import pytest

from docxaicorrector.runtime import external_process

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX process groups only")


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return True
    return state != "Z"


def _wait_dead(pid: int, seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _is_alive(pid):
            return True
        time.sleep(0.05)
    return not _is_alive(pid)


def _run_in_thread(call, join_seconds: float):
    outcome: dict[str, object] = {}

    def target():
        try:
            outcome["result"] = call()
        except BaseException as exc:  # noqa: BLE001 - captured for the assertion
            outcome["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(join_seconds)
    return thread, outcome


def _read_pid(pid_file: Path) -> int | None:
    try:
        return int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return None


@pytest.mark.skipif(not Path("/bin/bash").exists(), reason="needs bash")
def test_timeout_kills_group_even_when_leader_exits_on_sigterm_and_child_holds_stdout(tmp_path, monkeypatch):
    monkeypatch.setattr(external_process, "_TERMINATE_GRACE_SECONDS", 0.5)
    pid_file = tmp_path / "child.pid"
    script = (
        'trap "exit 0" TERM; '
        f'(trap "" TERM; echo $BASHPID > "{pid_file}"; exec sleep 600) & '
        "wait"
    )
    child_pid: int | None = None
    try:
        started = time.monotonic()
        thread, outcome = _run_in_thread(
            lambda: external_process.run_completed_process(
                ["/bin/bash", "-c", script],
                error_message="convert failed.",
                cleanup_process_group=True,
                timeout_seconds=1,
            ),
            join_seconds=15,
        )
        child_pid = _read_pid(pid_file)
        elapsed = time.monotonic() - started

        assert not thread.is_alive(), "run_completed_process hung after the timeout"
        assert isinstance(outcome.get("error"), RuntimeError)
        assert "Превышено время ожидания" in str(outcome["error"])
        assert elapsed < 12
        assert child_pid is not None, "the child never started"
        assert _wait_dead(child_pid), "a process of the group survived the timeout"
    finally:
        if child_pid is not None and _is_alive(child_pid):
            os.kill(child_pid, signal.SIGKILL)


@pytest.mark.skipif(not Path("/bin/bash").exists(), reason="needs bash")
def test_terminate_process_tree_kills_group_after_leader_already_exited(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setattr(external_process, "_TERMINATE_GRACE_SECONDS", 0.5)
    pid_file = tmp_path / "child.pid"
    script = (
        'trap "exit 0" TERM; '
        f'(trap "" TERM; echo $BASHPID > "{pid_file}"; exec sleep 600) & '
        "wait"
    )
    process = subprocess.Popen(
        ["/bin/bash", "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    child_pid: int | None = None
    try:
        deadline = time.monotonic() + 5
        while child_pid is None and time.monotonic() < deadline:
            child_pid = _read_pid(pid_file)
            time.sleep(0.05)
        assert child_pid is not None

        external_process.terminate_process_tree(process)

        assert process.poll() is not None
        assert _wait_dead(child_pid), "SIGKILL never reached the surviving child of the group"
        with pytest.raises(ProcessLookupError):
            os.killpg(process.pid, 0)
    finally:
        if child_pid is not None and _is_alive(child_pid):
            os.kill(child_pid, signal.SIGKILL)
        if process.poll() is None:
            process.kill()


def test_timeout_returns_when_output_collection_stays_blocked(monkeypatch):
    """Even if the pipes never close (a process outside the group holds them), the call returns."""
    monkeypatch.setattr(external_process, "_TERMINATE_GRACE_SECONDS", 0.2)
    monkeypatch.setattr(external_process, "_COLLECT_TIMEOUT_SECONDS", 0.5)
    # The leader is killed by the helper; a detached grandchild (own session) keeps the pipe open.
    script = (
        "import subprocess,sys,time\n"
        "subprocess.Popen([sys.executable,'-c','import time; time.sleep(15)'], start_new_session=True)\n"
        "time.sleep(600)\n"
    )
    started = time.monotonic()
    thread, outcome = _run_in_thread(
        lambda: external_process.run_completed_process(
            [sys.executable, "-c", script],
            error_message="convert failed.",
            cleanup_process_group=True,
            timeout_seconds=1,
        ),
        join_seconds=25,
    )
    assert not thread.is_alive(), "output collection was not bounded"
    assert isinstance(outcome.get("error"), RuntimeError)
    assert "Превышено время ожидания" in str(outcome["error"])
    assert time.monotonic() - started < 10
