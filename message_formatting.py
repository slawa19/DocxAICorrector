from collections.abc import Mapping


_VARIANT_LABELS: dict[str, str] = {
    "original": "оригинал",
    "safe": "safe-вариант",
    "redrawn": "перерисовка",
}

_REASON_PREFIXES: list[tuple[str, str]] = [
    ("compare_all_variants_incomplete", "не все compare-all варианты подготовлены"),
    ("compare_all_variants_ready", "подготовлены compare-all варианты"),
    ("candidate_image_unreadable", "изображение-кандидат не читается"),
    ("validator_exception", "ошибка валидации"),
    ("unsupported_source_image_format", "неподдерживаемый формат исходного изображения"),
    ("document_model_call_budget_exhausted", "достигнут лимит model calls для документа"),
    ("image_model_call_budget_exhausted", "достигнут лимит model calls для изображения"),
    ("image_processing_exception", "ошибка обработки изображения"),
    ("semantic_redraw_fell_back_to_safe_candidate", "перерисовка не прошла, оставлен safe-вариант"),
    ("semantic_candidate_attempts_exhausted", "попытки semantic redraw исчерпаны"),
    ("compare_all_safe_variant_ready", "подготовлен safe-вариант для compare-all"),
    ("no_change_mode", "режим «Без изменения»"),
]


def humanize_variant(variant: str) -> str:
    return _VARIANT_LABELS.get(variant, variant)


def humanize_reason(reason: str) -> str:
    if not reason:
        return ""
    for prefix, label in _REASON_PREFIXES:
        if reason == prefix or reason.startswith(prefix + ":"):
            suffix = reason[len(prefix) + 1 :] if reason.startswith(prefix + ":") else ""
            if suffix:
                parts = [humanize_variant(part.strip()) for part in suffix.split(",") if part.strip()]
                if parts:
                    return f"{label}: {', '.join(parts)}"
            return label
    # Unknown reason codes pass through; they are technical strings not yet
    # covered by _REASON_PREFIXES.  Wrap them so the user sees a softer label.
    return f"причина: {reason}"


def build_block_journal_entry(
    *,
    status: str,
    block_index: int,
    block_count: int,
    target_chars: int,
    context_chars: int,
    details: str,
) -> dict[str, object]:
    return {
        "kind": "block",
        "status": status,
        "block_index": block_index,
        "block_count": block_count,
        "target_chars": target_chars,
        "context_chars": context_chars,
        "details": details,
        "message": (
            f"[{status}] Блок {block_index}/{block_count} | "
            f"цель: {target_chars} симв. | контекст: {context_chars} симв. | {details}"
        ),
    }


def build_image_journal_entry(
    *,
    image_id: str,
    status: str,
    decision: str,
    confidence: float,
    missing_labels: list[str] | None = None,
    suspicious_reasons: list[str] | None = None,
    final_variant: str | None = None,
    final_reason: str | None = None,
) -> dict[str, object]:
    reason = final_reason or (suspicious_reasons[0] if suspicious_reasons else "")
    if not reason and missing_labels:
        reason = f"не найдены объекты: {', '.join(missing_labels)}"

    variant = final_variant or (decision.removeprefix("fallback_") if decision.startswith("fallback_") else "")
    variant_label = humanize_variant(variant) if variant else ""

    if status == "error":
        severity = "IMG ERR"
        outcome = "ошибка обработки"
    elif decision.startswith("fallback_") or status == "failed":
        severity = "IMG WARN"
        outcome = f"оставлен {variant_label}" if variant_label else "применён fallback"
    elif status == "compared":
        severity = "IMG OK"
        if decision == "compared":
            outcome = "подготовлены варианты для сравнения"
        else:
            outcome = f"выбран {variant_label}" if variant_label else "выбран лучший вариант"
    else:
        severity = "IMG OK"
        outcome = f"оставлен {variant_label}" if variant_label else "обработка завершена"

    parts = [f"[{severity}] Изображение {image_id}", outcome]
    if reason:
        parts.append(humanize_reason(reason))
    if confidence > 0 and severity == "IMG OK":
        parts.append(f"confidence: {confidence:.2f}")

    return {
        "kind": "image",
        "status": severity,
        "image_id": image_id,
        "image_status": status,
        "decision": decision,
        "confidence": confidence,
        "missing_labels": list(missing_labels or []),
        "suspicious_reasons": list(suspicious_reasons or []),
        "final_variant": final_variant,
        "final_reason": final_reason,
        "message": " | ".join(parts),
    }


def get_restartable_outcome_notice(outcome: str | None, uploaded_filename: str) -> tuple[str, str] | None:
    if outcome == "stopped":
        return (
            "warning",
            f"Обработка файла «{uploaded_filename}» была остановлена. Можно изменить настройки и запустить заново без повторной загрузки.",
        )
    if outcome == "failed":
        return (
            "error",
            f"Обработка файла «{uploaded_filename}» завершилась ошибкой. Можно изменить настройки и запустить заново без повторной загрузки.",
        )
    return None


def get_preparation_state_unavailable_message() -> str:
    return (
        "Сохраненное состояние подготовки файла потеряно или недоступно. Если документ не появился "
        "в режиме готовности, загрузите файл повторно, чтобы заново запустить подготовку."
    )


def derive_live_status_title_and_severity(status: Mapping[str, object]) -> tuple[str, str]:
    """Return (title, severity) where severity is 'info' | 'warning' | 'error'."""
    phase = str(status.get("phase") or "processing")
    stage = str(status.get("stage") or "")
    is_running = bool(status.get("is_running"))
    terminal_kind = status.get("terminal_kind")

    if phase == "preparing":
        if is_running:
            return "Идет анализ файла", "info"
        if terminal_kind == "error":
            return "Ошибка подготовки файла", "error"
        if terminal_kind == "completed":
            return "Документ подготовлен", "info"
        if stage.startswith("Ошибка"):
            return "Ошибка подготовки файла", "error"
        if stage == "Документ подготовлен":
            return "Документ подготовлен", "info"
        return "Статус подготовки", "info"

    if is_running:
        return "Идет обработка", "info"
    if terminal_kind == "stopped":
        return "Обработка остановлена", "warning"
    if terminal_kind == "error":
        return "Ошибка обработки", "error"
    if terminal_kind == "completed":
        return "Обработка завершена", "info"
    if stage.startswith("Остановлено"):
        return "Обработка остановлена", "warning"
    if "Ошибка" in stage:
        return "Ошибка обработки", "error"
    if stage == "Обработка завершена":
        return "Обработка завершена", "info"
    return "Состояние", "info"


def derive_live_status_title(status: Mapping[str, object]) -> str:
    """Backward-compatible wrapper returning only the title string."""
    title, _severity = derive_live_status_title_and_severity(status)
    return title
