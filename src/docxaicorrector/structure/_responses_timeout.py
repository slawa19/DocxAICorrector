from __future__ import annotations

import logging
from queue import Queue
from threading import Thread
from typing import Any, Callable, cast

from docxaicorrector.image.shared import call_responses_create_with_retry


def call_responses_with_hard_timeout(
    *,
    client: object,
    request_payload: dict[str, object],
    timeout: float,
    thread_name: str,
    logger: logging.Logger,
    request_kind: str,
    timeout_error_factory: Callable[[float], Exception],
) -> Any:
    result_queue: Queue[tuple[str, object]] = Queue(maxsize=1)

    def _run_request() -> None:
        try:
            response = call_responses_create_with_retry(
                client,
                request_payload,
                max_retries=1,
                retryable_error_predicate=lambda exc: False,
            )
        except Exception as exc:
            result_queue.put(("error", exc))
            return
        result_queue.put(("ok", response))

    worker = Thread(target=_run_request, name=thread_name, daemon=True)
    worker.start()
    worker.join(timeout=max(0.001, timeout))
    if worker.is_alive():
        logger.warning("%s hard timeout exceeded; request_abandoned=True timeout_seconds=%.3f", request_kind, timeout)
        raise timeout_error_factory(timeout)

    status, payload = result_queue.get_nowait()
    if status == "error":
        raise cast(Exception, payload)
    return payload