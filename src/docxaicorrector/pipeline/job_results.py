import logging
from collections.abc import Mapping
from typing import Any


def persist_terminal_job_result(
    *,
    context: Any,
    dependencies: Any,
    index: int,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    prepared_source_key = str(getattr(context, "prepared_source_key", "") or "").strip()
    structure_fingerprint = str(getattr(context, "structure_fingerprint", "") or "").strip()
    jobs = list(getattr(context, "jobs", ()) or ())
    if not prepared_source_key or not structure_fingerprint or index <= 0 or index > len(jobs):
        return

    job = jobs[index - 1]
    if not isinstance(job, Mapping):
        return

    job_id = str(job.get("job_id") or "").strip()
    if not job_id:
        return

    record: dict[str, object] = {
        "schema_version": 1,
        "prepared_source_key": prepared_source_key,
        "structure_fingerprint": structure_fingerprint,
        "job_id": job_id,
        "segment_id": str(job.get("segment_id") or "").strip(),
        "status": status,
        "block_index": index,
    }
    if error_code:
        record["error_code"] = error_code
    if error_message:
        record["error_message"] = error_message

    try:
        dependencies.write_job_result_registry(records=[record])
    except OSError as exc:
        dependencies.log_event(
            logging.WARNING,
            "job_result_registry_save_failed",
            "Не удалось сохранить persisted job result registry.",
            filename=getattr(context, "uploaded_filename", ""),
            job_id=job_id,
            block_index=index,
            status=status,
            error_message=str(exc),
        )