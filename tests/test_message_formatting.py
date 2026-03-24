from typing import cast

import pytest

from message_formatting import (
    build_block_journal_entry,
    build_image_journal_entry,
    derive_live_status_title,
    derive_live_status_title_and_severity,
    get_preparation_state_unavailable_message,
    get_restartable_outcome_notice,
    humanize_reason,
    humanize_variant,
)


def _message(entry: dict[str, object]) -> str:
    return cast(str, entry["message"])


def _status(entry: dict[str, object]) -> str:
    return cast(str, entry["status"])


# ---------------------------------------------------------------------------
# humanize_variant
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "variant, expected",
    [
        ("original", "оригинал"),
        ("safe", "safe-вариант"),
        ("redrawn", "перерисовка"),
        ("unknown_variant", "unknown_variant"),
    ],
)
def test_humanize_variant(variant, expected):
    assert humanize_variant(variant) == expected


# ---------------------------------------------------------------------------
# humanize_reason
# ---------------------------------------------------------------------------

def test_humanize_reason_empty():
    assert humanize_reason("") == ""


@pytest.mark.parametrize(
    "reason, expected",
    [
        ("validator_exception", "ошибка валидации"),
        ("validator_exception:RuntimeError", "ошибка валидации: RuntimeError"),
        ("unsupported_source_image_format", "неподдерживаемый формат исходного изображения"),
        ("unsupported_source_image_format:image/x-emf", "неподдерживаемый формат исходного изображения: image/x-emf"),
        ("document_model_call_budget_exhausted", "достигнут лимит model calls для документа"),
        ("image_model_call_budget_exhausted", "достигнут лимит model calls для изображения"),
        ("image_processing_exception", "ошибка обработки изображения"),
        ("semantic_redraw_fell_back_to_safe_candidate", "перерисовка не прошла, оставлен safe-вариант"),
        ("semantic_candidate_attempts_exhausted", "попытки semantic redraw исчерпаны"),
        ("compare_all_variants_incomplete", "не все compare-all варианты подготовлены"),
        ("compare_all_variants_incomplete:safe, redrawn", "не все compare-all варианты подготовлены: safe-вариант, перерисовка"),
        ("compare_all_variants_ready:original, safe, redrawn", "подготовлены compare-all варианты: оригинал, safe-вариант, перерисовка"),
        ("compare_all_safe_variant_ready", "подготовлен safe-вариант для compare-all"),
        ("candidate_image_unreadable", "изображение-кандидат не читается"),
        ("no_change_mode", "режим «Без изменения»"),
    ],
)
def test_humanize_reason_known_prefixes(reason, expected):
    assert humanize_reason(reason) == expected


def test_humanize_reason_unknown_wraps_with_label():
    assert humanize_reason("some_new_reason_code") == "причина: some_new_reason_code"


# ---------------------------------------------------------------------------
# build_block_journal_entry
# ---------------------------------------------------------------------------

def test_build_block_journal_entry_structure():
    entry = build_block_journal_entry(
        status="OK",
        block_index=2,
        block_count=5,
        target_chars=100,
        context_chars=50,
        details="done",
    )
    assert entry["kind"] == "block"
    assert entry["status"] == "OK"
    assert entry["block_index"] == 2
    assert entry["block_count"] == 5
    assert entry["target_chars"] == 100
    assert entry["context_chars"] == 50
    assert entry["details"] == "done"
    message = _message(entry)
    assert "[OK] Блок 2/5" in message
    assert "цель: 100 симв." in message
    assert "контекст: 50 симв." in message
    assert "done" in message


# ---------------------------------------------------------------------------
# build_image_journal_entry — severity classes
# ---------------------------------------------------------------------------

def test_image_journal_entry_ok_validated():
    entry = build_image_journal_entry(
        image_id="img-1",
        status="validated",
        decision="accept",
        confidence=0.92,
        final_variant="original",
    )
    assert entry["kind"] == "image"
    message = _message(entry)
    assert _status(entry) == "IMG OK"
    assert "обработка завершена" in message or "оставлен оригинал" in message
    assert "confidence: 0.92" in message


def test_image_journal_entry_ok_compared_with_decision_compared():
    entry = build_image_journal_entry(
        image_id="img-2",
        status="compared",
        decision="compared",
        confidence=0.0,
        final_variant="original",
    )
    assert _status(entry) == "IMG OK"
    assert "подготовлены варианты для сравнения" in _message(entry)


def test_image_journal_entry_ok_compared_humanizes_compare_all_ready_reason():
    entry = build_image_journal_entry(
        image_id="img-2b",
        status="compared",
        decision="compared",
        confidence=0.0,
        final_variant="original",
        final_reason="compare_all_variants_ready:original, safe, redrawn",
    )
    message = _message(entry)
    assert "подготовлены compare-all варианты: оригинал, safe-вариант, перерисовка" in message
    assert "причина: compare_all_variants_ready" not in message


def test_image_journal_entry_ok_compared_with_best_variant():
    entry = build_image_journal_entry(
        image_id="img-3",
        status="compared",
        decision="accept",
        confidence=0.85,
        final_variant="safe",
    )
    message = _message(entry)
    assert _status(entry) == "IMG OK"
    assert "выбран safe-вариант" in message
    assert "confidence: 0.85" in message


def test_image_journal_entry_warn_fallback():
    entry = build_image_journal_entry(
        image_id="img-4",
        status="failed",
        decision="fallback_original",
        confidence=0.0,
        suspicious_reasons=["unsupported_source_image_format:image/x-emf"],
        final_variant="original",
        final_reason="unsupported_source_image_format:image/x-emf",
    )
    message = _message(entry)
    assert _status(entry) == "IMG WARN"
    assert "оставлен оригинал" in message
    assert "неподдерживаемый формат" in message


def test_image_journal_entry_err():
    entry = build_image_journal_entry(
        image_id="img-5",
        status="error",
        decision="fallback_original",
        confidence=0.0,
        suspicious_reasons=["image_processing_exception:RuntimeError"],
        final_variant="original",
        final_reason="image_processing_exception:RuntimeError",
    )
    assert _status(entry) == "IMG ERR"
    assert "ошибка обработки" in _message(entry)


def test_image_journal_entry_no_change_mode():
    entry = build_image_journal_entry(
        image_id="img-6",
        status="skipped",
        decision="accept",
        confidence=0.0,
        final_variant="original",
        final_reason="no_change_mode",
    )
    message = _message(entry)
    assert _status(entry) == "IMG OK"
    assert "оставлен оригинал" in message
    assert "режим «Без изменения»" in message


def test_image_journal_entry_confidence_hidden_for_warn():
    entry = build_image_journal_entry(
        image_id="img-7",
        status="failed",
        decision="fallback_original",
        confidence=0.5,
        final_variant="original",
    )
    assert "confidence" not in _message(entry)


def test_image_journal_entry_confidence_hidden_when_zero():
    entry = build_image_journal_entry(
        image_id="img-8",
        status="validated",
        decision="accept",
        confidence=0.0,
        final_variant="original",
    )
    assert "confidence" not in _message(entry)


def test_image_journal_entry_metadata_fields():
    entry = build_image_journal_entry(
        image_id="img-9",
        status="validated",
        decision="accept",
        confidence=0.9,
        missing_labels=["label-a"],
        suspicious_reasons=["reason-a"],
        final_variant="original",
        final_reason="some_reason",
    )
    assert entry["image_id"] == "img-9"
    assert entry["image_status"] == "validated"
    assert entry["decision"] == "accept"
    assert entry["confidence"] == 0.9
    assert entry["missing_labels"] == ["label-a"]
    assert entry["suspicious_reasons"] == ["reason-a"]
    assert entry["final_variant"] == "original"
    assert entry["final_reason"] == "some_reason"


# ---------------------------------------------------------------------------
# derive_live_status_title / derive_live_status_title_and_severity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "status, expected_title, expected_severity",
    [
        # Preparing phase
        ({"phase": "preparing", "is_running": True, "stage": ""}, "Идет анализ файла", "info"),
        ({"phase": "preparing", "is_running": False, "stage": "Нейтральный текст", "terminal_kind": "completed"}, "Документ подготовлен", "info"),
        ({"phase": "preparing", "is_running": False, "stage": "Нейтральный текст", "terminal_kind": "error"}, "Ошибка подготовки файла", "error"),
        ({"phase": "preparing", "is_running": False, "stage": "Ошибка подготовки"}, "Ошибка подготовки файла", "error"),
        ({"phase": "preparing", "is_running": False, "stage": "Документ подготовлен"}, "Документ подготовлен", "info"),
        ({"phase": "preparing", "is_running": False, "stage": "Какой-то другой"}, "Статус подготовки", "info"),
        # Processing phase
        ({"phase": "processing", "is_running": True, "stage": ""}, "Идет обработка", "info"),
        ({"phase": "processing", "is_running": False, "stage": "Остановлено пользователем"}, "Обработка остановлена", "warning"),
        ({"phase": "processing", "is_running": False, "stage": "Ошибка обработки"}, "Ошибка обработки", "error"),
        ({"phase": "processing", "is_running": False, "stage": "Обработка завершена"}, "Обработка завершена", "info"),
        ({"phase": "processing", "is_running": False, "stage": "Ожидание запуска"}, "Состояние", "info"),
        ({"phase": "processing", "is_running": False, "stage": "Нейтральный текст", "terminal_kind": "stopped"}, "Обработка остановлена", "warning"),
        ({"phase": "processing", "is_running": False, "stage": "Нейтральный текст", "terminal_kind": "error"}, "Ошибка обработки", "error"),
        ({"phase": "processing", "is_running": False, "stage": "Нейтральный текст", "terminal_kind": "completed"}, "Обработка завершена", "info"),
    ],
)
def test_derive_live_status_title_and_severity(status, expected_title, expected_severity):
    title, severity = derive_live_status_title_and_severity(status)
    assert title == expected_title
    assert severity == expected_severity


def test_derive_live_status_title_backward_compatible():
    status = {"phase": "preparing", "is_running": True, "stage": ""}
    assert derive_live_status_title(status) == "Идет анализ файла"


# ---------------------------------------------------------------------------
# get_restartable_outcome_notice
# ---------------------------------------------------------------------------

def test_restartable_outcome_notice_stopped():
    result = get_restartable_outcome_notice("stopped", "report.docx")
    assert result is not None
    level, message = result
    assert level == "warning"
    assert "остановлена" in message
    assert "report.docx" in message


def test_restartable_outcome_notice_failed():
    result = get_restartable_outcome_notice("failed", "report.docx")
    assert result is not None
    level, message = result
    assert level == "error"
    assert "ошибкой" in message
    assert "report.docx" in message


@pytest.mark.parametrize("outcome", ["idle", "succeeded", "running", None])
def test_restartable_outcome_notice_non_restartable(outcome):
    assert get_restartable_outcome_notice(outcome, "report.docx") is None


# ---------------------------------------------------------------------------
# get_preparation_state_unavailable_message
# ---------------------------------------------------------------------------

def test_preparation_state_unavailable_message_not_empty():
    msg = get_preparation_state_unavailable_message()
    assert isinstance(msg, str)
    assert len(msg) > 10


def test_preparation_state_unavailable_message_explains_lost_state_semantics():
    msg = get_preparation_state_unavailable_message().lower()
    assert "подготов" in msg
    assert ("потер" in msg) or ("недоступ" in msg)
    assert "загруз" in msg
