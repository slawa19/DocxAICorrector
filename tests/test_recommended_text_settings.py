import recommended_text_settings


def test_derive_recommended_text_settings_prefers_edit_when_text_matches_target_language():
    recommendation = recommended_text_settings.derive_recommended_text_settings(
        file_token="report.docx:3:abc",
        assessment={
            "dominant_language": "ru",
            "dominant_script": "cyrillic",
            "target_language_script_match": True,
            "mixed_script_detected": False,
        },
        current_settings={
            "processing_operation": "translate",
            "source_language": "en",
            "target_language": "ru",
        },
    )

    assert recommendation == {
        "file_token": "report.docx:3:abc",
        "processing_operation": "edit",
        "source_language": "en",
        "target_language": "ru",
        "reason_summary": "text already looks like target-language content",
    }


def test_derive_recommended_text_settings_prefers_auto_when_source_is_ambiguous():
    recommendation = recommended_text_settings.derive_recommended_text_settings(
        file_token="report.docx:3:abc",
        assessment={
            "dominant_language": None,
            "dominant_script": "latin",
            "target_language_script_match": False,
            "mixed_script_detected": False,
        },
        current_settings={
            "processing_operation": "edit",
            "source_language": "en",
            "target_language": "ru",
        },
    )

    assert recommendation["processing_operation"] == "translate"
    assert recommendation["source_language"] == "auto"
    assert recommendation["target_language"] == "ru"


def test_mark_manual_overrides_from_recommendation_is_field_aware():
    manual_override = recommended_text_settings.build_empty_manual_text_settings_override("report.docx:3:abc")

    updated = recommended_text_settings.mark_manual_overrides_from_recommendation(
        manual_override,
        current_settings={
            "processing_operation": "translate",
            "source_language": "auto",
            "target_language": "ru",
        },
        recommended_settings={
            "file_token": "report.docx:3:abc",
            "processing_operation": "edit",
            "source_language": "auto",
            "target_language": "ru",
            "reason_summary": None,
        },
        source_visible=True,
    )

    assert updated == {
        "file_token": "report.docx:3:abc",
        "processing_operation": True,
        "source_language": False,
        "target_language": False,
    }


def test_mark_manual_overrides_from_baseline_tracks_hidden_source_language_value():
    manual_override = recommended_text_settings.build_empty_manual_text_settings_override("report.docx:3:abc")

    updated = recommended_text_settings.mark_manual_overrides_from_baseline(
        manual_override,
        current_settings={
            "processing_operation": "edit",
            "source_language": "auto",
            "target_language": "ru",
        },
        baseline_settings={
            "processing_operation": "edit",
            "source_language": "en",
            "target_language": "ru",
        },
        source_visible=False,
    )

    assert updated["source_language"] is True


def test_derive_recommended_text_settings_uses_dominant_language_for_translate_source():
    recommendation = recommended_text_settings.derive_recommended_text_settings(
        file_token="report.docx:3:abc",
        assessment={
            "dominant_language": "en",
            "dominant_script": "latin",
            "target_language_script_match": False,
            "mixed_script_detected": False,
        },
        current_settings={
            "processing_operation": "edit",
            "source_language": "auto",
            "target_language": "ru",
        },
    )

    assert recommendation["processing_operation"] == "translate"
    assert recommendation["source_language"] == "en"


def test_derive_recommended_text_settings_does_not_switch_to_edit_on_script_match_alone():
    recommendation = recommended_text_settings.derive_recommended_text_settings(
        file_token="report.docx:3:abc",
        assessment={
            "dominant_language": None,
            "dominant_script": "latin",
            "target_language_script_match": True,
            "mixed_script_detected": False,
        },
        current_settings={
            "processing_operation": "translate",
            "source_language": "en",
            "target_language": "de",
        },
    )

    assert recommendation["processing_operation"] == "translate"
    assert recommendation["source_language"] == "auto"
    assert recommendation["reason_summary"] == "source language is ambiguous; auto is safer"


def test_mark_manual_overrides_from_snapshot_detects_real_user_change():
    manual_override = recommended_text_settings.build_empty_manual_text_settings_override("report.docx:3:abc")

    updated = recommended_text_settings.mark_manual_overrides_from_snapshot(
        manual_override,
        current_settings={
            "processing_operation": "edit",
            "source_language": "auto",
            "target_language": "ru",
        },
        applied_snapshot={
            "file_token": "report.docx:3:abc",
            "processing_operation": "translate",
            "source_language": "auto",
            "target_language": "ru",
        },
    )

    assert updated["processing_operation"] is True
    assert updated["source_language"] is False
    assert updated["target_language"] is False


def test_normalize_recommendation_snapshot_requires_matching_file_token():
    assert recommended_text_settings.normalize_recommendation_snapshot(
        {
            "file_token": "other.docx:3:def",
            "processing_operation": "translate",
            "source_language": "auto",
            "target_language": "ru",
        },
        file_token="report.docx:3:abc",
    ) is None
