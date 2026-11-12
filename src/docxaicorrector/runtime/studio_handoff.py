"""Spec 075 FR-004: hand the narration book file to the audiobook studio in one click.

The studio (a separate repository) takes the raw ``.narration.json`` at ``POST /api/books`` and answers
``{"book_id": ...}``; a bad file is a 400 with ``{"detail": "<human text>"}``. This module does the
request with the standard library (``httpx`` is only a transitive dependency here), starts the
studio when it is not running, and retries once.

It returns an outcome with a machine ``error_code`` and the facts for the message; the result
screen turns them into localized text and logs the event, so nothing here talks to the user.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_STUDIO_URL = "http://127.0.0.1:8601"
DEFAULT_STUDIO_DIR = "../AudiobookStudio"
STUDIO_DIR_SETTING = "DOCX_AI_STUDIO_DIR"
STUDIO_URL_SETTING = "DOCX_AI_STUDIO_URL"
POST_TIMEOUT_SECONDS = 60.0
# studio.sh waits up to 30 s for the server and prints its own reason when it gives up.
START_TIMEOUT_SECONDS = 90.0
_OUTPUT_TAIL_CHARS = 1500
_DETAIL_FALLBACK_CHARS = 300


class StudioConnectionError(Exception):
    """The request never got an HTTP answer. ``refused`` is True when nothing listens on the port."""

    def __init__(self, reason: str, *, refused: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.refused = refused


@dataclass(frozen=True)
class HttpReply:
    status: int
    body: bytes


@dataclass(frozen=True)
class StartResult:
    returncode: int
    output: str


@dataclass(frozen=True)
class StudioHandoffOutcome:
    """``ok`` -> ``book_id`` and ``link``. Otherwise ``error_code`` is one of
    ``studio_dir_missing``, ``start_failed``, ``unreachable``, ``rejected``, ``bad_response``;
    ``error_detail`` is the fact to show (a path, the script output, the studio's ``detail``, a reason)."""

    ok: bool
    book_id: str | None = None
    link: str | None = None
    error_code: str | None = None
    error_detail: str = ""
    http_status: int | None = None
    started_studio: bool = False


HttpPost = Callable[[str, bytes, float], HttpReply]
StartStudio = Callable[[Path], StartResult]


def post_json_bytes(url: str, body: bytes, timeout: float) -> HttpReply:
    """``POST`` the raw bytes; an HTTP error status is an answer, not an exception."""
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - http(s) studio URL from settings
            return HttpReply(status=int(response.status), body=response.read())
    except urllib.error.HTTPError as exc:
        try:
            return HttpReply(status=int(exc.code), body=exc.read())
        finally:
            exc.close()
    except urllib.error.URLError as exc:
        raise StudioConnectionError(
            str(exc.reason), refused=isinstance(exc.reason, ConnectionRefusedError)
        ) from exc
    except (OSError, ValueError) as exc:  # timeout, reset, a malformed URL
        raise StudioConnectionError(f"{type(exc).__name__}: {exc}", refused=False) from exc


def run_studio_start_script(studio_dir: Path) -> StartResult:
    """``bash <studio dir>/scripts/studio.sh start``; its output (stdout + stderr) is the reason on failure."""
    script = studio_dir / "scripts" / "studio.sh"
    try:
        completed = subprocess.run(
            ["bash", str(script), "start"],
            cwd=str(studio_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=START_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return StartResult(returncode=-1, output=f"studio.sh start did not finish in {START_TIMEOUT_SECONDS:.0f} s")
    except OSError as exc:
        return StartResult(returncode=-1, output=f"{type(exc).__name__}: {exc}")
    output = completed.stdout.decode("utf-8", errors="replace").strip()
    return StartResult(returncode=completed.returncode, output=output)


def build_browser_link(studio_url: str, book_id: str) -> str:
    """The studio page for a book. The browser side always uses ``localhost`` (what ``start-studio.cmd`` opens),
    whatever host the server-side URL names."""
    parts = urlsplit(studio_url)
    port = parts.port
    host = "localhost" if port is None else f"localhost:{port}"
    return f"{parts.scheme or 'http'}://{host}/#book={book_id}"


def _studio_detail(body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("detail"), str) and payload["detail"].strip():
        return payload["detail"].strip()
    return body.decode("utf-8", errors="replace").strip()[:_DETAIL_FALLBACK_CHARS]


def _tail(text: str) -> str:
    return text if len(text) <= _OUTPUT_TAIL_CHARS else "…" + text[-_OUTPUT_TAIL_CHARS:]


def _outcome_from_reply(reply: HttpReply, *, studio_url: str, started_studio: bool) -> StudioHandoffOutcome:
    if 200 <= reply.status < 300:
        try:
            payload = json.loads(reply.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            payload = None
        book_id = payload.get("book_id") if isinstance(payload, dict) else None
        if isinstance(book_id, str) and book_id.strip():
            return StudioHandoffOutcome(
                ok=True,
                book_id=book_id.strip(),
                link=build_browser_link(studio_url, book_id.strip()),
                http_status=reply.status,
                started_studio=started_studio,
            )
        return StudioHandoffOutcome(
            ok=False,
            error_code="bad_response",
            error_detail=reply.body.decode("utf-8", errors="replace").strip()[:_DETAIL_FALLBACK_CHARS],
            http_status=reply.status,
            started_studio=started_studio,
        )
    return StudioHandoffOutcome(
        ok=False,
        error_code="rejected",
        error_detail=_studio_detail(reply.body),
        http_status=reply.status,
        started_studio=started_studio,
    )


def send_book_to_studio(
    book_bytes: bytes,
    *,
    studio_url: str,
    studio_dir: Path,
    post: HttpPost = post_json_bytes,
    start_studio: StartStudio = run_studio_start_script,
) -> StudioHandoffOutcome:
    """Post the book file; when the studio is down start it and try once more. Never raises."""
    endpoint = studio_url.rstrip("/") + "/api/books"
    started_studio = False
    try:
        reply = post(endpoint, book_bytes, POST_TIMEOUT_SECONDS)
    except StudioConnectionError as first:
        if not first.refused:
            return StudioHandoffOutcome(ok=False, error_code="unreachable", error_detail=first.reason)
        script = studio_dir / "scripts" / "studio.sh"
        if not script.is_file():
            return StudioHandoffOutcome(ok=False, error_code="studio_dir_missing", error_detail=str(studio_dir))
        started = start_studio(studio_dir)
        started_studio = True
        if started.returncode != 0:
            return StudioHandoffOutcome(
                ok=False,
                error_code="start_failed",
                error_detail=_tail(started.output) or f"exit code {started.returncode}",
                started_studio=True,
            )
        try:
            reply = post(endpoint, book_bytes, POST_TIMEOUT_SECONDS)
        except StudioConnectionError as second:
            return StudioHandoffOutcome(
                ok=False, error_code="unreachable", error_detail=second.reason, started_studio=True
            )
    return _outcome_from_reply(reply, studio_url=studio_url, started_studio=started_studio)
