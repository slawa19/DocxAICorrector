import streamlit as st


def render_compare_all_apply_panel(
    *,
    has_completed_result: bool,
    latest_image_mode: str | None,
    uploaded_filename: str,
    render_section_gap,
    render_image_compare_selector,
    apply_selected_compare_variants,
    present_error,
) -> None:
    if not has_completed_result or latest_image_mode != "compare_all":
        return

    render_section_gap("lg")
    render_image_compare_selector()
    if st.button(
        "Собрать итоговый DOCX с выбранными изображениями",
        type="primary",
        use_container_width=True,
        key="apply_compare_variants_button",
    ):
        try:
            apply_selected_compare_variants()
            st.success("Итоговый DOCX пересобран с выбранными вариантами изображений.")
        except Exception as exc:
            user_message = present_error(
                "compare_variant_apply_failed",
                exc,
                "Ошибка применения выбранных вариантов изображений",
                filename=uploaded_filename,
            )
            st.error(user_message)
    st.caption(
        "До пересборки итоговый DOCX сохраняет исходные изображения. После нажатия кнопки будут вставлены выбранные варианты."
    )