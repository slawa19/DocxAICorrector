import streamlit as st

from models import ImageMode


def render_compare_all_apply_panel(
    *,
    latest_image_mode: str | None,
    image_assets,
    render_section_gap,
) -> None:
    if latest_image_mode != ImageMode.COMPARE_ALL.value:
        return

    if not image_assets:
        return

    if not any(getattr(asset, "comparison_variants", None) for asset in image_assets):
        return

    render_section_gap("lg")
    st.info(
        "В итоговый DOCX уже вставлены все сгенерированные варианты изображений: safe, креативный и структурный. Лишние варианты можно удалить прямо в Word."
    )
    st.caption(
        "Предпросмотр в UI нужен только для проверки качества вариантов. Дополнительная пересборка документа не требуется."
    )