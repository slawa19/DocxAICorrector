import text_transform_assessment


def test_assess_text_transform_excerpt_returns_unknown_for_empty_text():
    assessment = text_transform_assessment.assess_text_transform_excerpt(
        "",
        target_language="ru",
    )

    assert assessment == {
        "dominant_language": None,
        "dominant_script": "unknown",
        "target_language_script_match": None,
        "mixed_script_detected": False,
    }


def test_assess_text_transform_excerpt_detects_cyrillic_target_match():
    assessment = text_transform_assessment.assess_text_transform_excerpt(
        "Привет, мир. Это уже русский текст.",
        target_language="ru",
    )

    assert assessment == {
        "dominant_language": "ru",
        "dominant_script": "cyrillic",
        "target_language_script_match": True,
        "mixed_script_detected": False,
    }


def test_assess_text_transform_excerpt_detects_mixed_scripts():
    assessment = text_transform_assessment.assess_text_transform_excerpt(
        "Привет world こんにちは",
        target_language="ru",
    )

    assert assessment["mixed_script_detected"] is True
    assert assessment["dominant_script"] in {"cyrillic", "latin", "cjk"}


def test_assess_text_transform_excerpt_detects_mixed_scripts_below_old_threshold():
    cyrillic_text = "Привет" * 30
    latin_insert = "loremipsum" * 6

    assessment = text_transform_assessment.assess_text_transform_excerpt(
        cyrillic_text + latin_insert,
        target_language="ru",
    )

    assert assessment["mixed_script_detected"] is True


def test_build_text_transform_warnings_warns_on_matching_source_and_target():
    warnings = text_transform_assessment.build_text_transform_warnings(
        operation="translate",
        source_language="en",
        target_language="en",
        assessment={
            "dominant_language": None,
            "dominant_script": "latin",
            "target_language_script_match": True,
            "mixed_script_detected": False,
        },
    )

    assert any("Исходный и целевой язык совпадают" in warning for warning in warnings)


def test_build_text_transform_warnings_warns_when_text_already_matches_target_language():
    warnings = text_transform_assessment.build_text_transform_warnings(
        operation="translate",
        source_language="en",
        target_language="ru",
        assessment={
            "dominant_language": "ru",
            "dominant_script": "cyrillic",
            "target_language_script_match": True,
            "mixed_script_detected": False,
        },
    )

    assert any("Текст уже выглядит как текст на целевом языке" in warning for warning in warnings)


def test_build_text_transform_warnings_warns_on_obvious_source_script_mismatch():
    warnings = text_transform_assessment.build_text_transform_warnings(
        operation="translate",
        source_language="en",
        target_language="ru",
        assessment={
            "dominant_language": "ru",
            "dominant_script": "cyrillic",
            "target_language_script_match": True,
            "mixed_script_detected": False,
        },
    )

    assert any("язык оригинала" in warning for warning in warnings)


def test_build_text_transform_warnings_warns_on_target_script_mismatch():
    warnings = text_transform_assessment.build_text_transform_warnings(
        operation="translate",
        source_language="auto",
        target_language="ru",
        assessment={
            "dominant_language": None,
            "dominant_script": "latin",
            "target_language_script_match": False,
            "mixed_script_detected": False,
        },
    )

    assert any("Скрипт текста не похож" in warning for warning in warnings)


def test_build_text_transform_warnings_warns_on_mixed_scripts():
    warnings = text_transform_assessment.build_text_transform_warnings(
        operation="translate",
        source_language="auto",
        target_language="ru",
        assessment={
            "dominant_language": None,
            "dominant_script": "cyrillic",
            "target_language_script_match": True,
            "mixed_script_detected": True,
        },
    )

    assert any("смешение скриптов" in warning for warning in warnings)


def test_build_text_transform_warnings_skips_translate_specific_warning_in_edit_mode():
    warnings = text_transform_assessment.build_text_transform_warnings(
        operation="edit",
        source_language="en",
        target_language="ru",
        assessment={
            "dominant_language": "ru",
            "dominant_script": "cyrillic",
            "target_language_script_match": True,
            "mixed_script_detected": False,
        },
    )

    assert not any("Текст уже выглядит как текст на целевом языке" in warning for warning in warnings)