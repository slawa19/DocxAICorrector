from translation_domains import build_terminology_plan, build_translation_domain_instructions, load_domain_instructions


def test_load_domain_instructions_returns_theology_glossary_text():
    instructions = load_domain_instructions(translation_domain="theology")

    assert "ДОМЕН ПЕРЕВОДА: богословие / эсхатология." in instructions
    assert "Great Tribulation -> Великая скорбь" in instructions


def test_build_terminology_plan_selects_only_detected_theology_terms():
    plan = build_terminology_plan(
        source_text="The Great Tribulation, the rapture, and the Antichrist are discussed in Revelation.",
        translation_domain="theology",
    )

    assert "Great Tribulation -> Великая скорбь" in plan
    assert "rapture -> восхищение Церкви / восхищение верующих" in plan
    assert "Antichrist -> Антихрист" in plan
    assert "Revelation -> Откровение / книга Откровения" in plan
    assert "mark of the beast" not in plan


def test_build_translation_domain_instructions_combines_glossary_and_plan():
    instructions = build_translation_domain_instructions(
        translation_domain="theology",
        source_text="The mark of the beast appears during the Great Tribulation.",
    )

    assert "ГЛОССАРИЙ И ПРЕДПОЧТИТЕЛЬНЫЕ ЭКВИВАЛЕНТЫ" in instructions
    assert "ТЕРМИНОЛОГИЧЕСКИЙ ПЛАН ДЛЯ ТЕКУЩЕГО ДОКУМЕНТА" in instructions
    assert "mark of the beast -> начертание зверя" in instructions
    assert "Great Tribulation -> Великая скорбь" in instructions
