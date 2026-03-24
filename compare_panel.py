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

    if not any(getattr(asset, "validation_status", None) == "compared" and getattr(asset, "comparison_variants", None) for asset in image_assets):
        return

    return