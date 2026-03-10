from collections.abc import MutableMapping


def apply_selected_compare_variants(
    session_state: MutableMapping[str, object],
    *,
    convert_markdown_to_docx_bytes,
    reinsert_inline_images,
) -> bytes:
    image_assets = list(session_state.get("image_assets", []))
    markdown_text = str(session_state.get("latest_markdown", ""))
    if not image_assets or not markdown_text:
        raise RuntimeError("Нет готовых данных для пересборки DOCX с выбранными вариантами изображений.")

    for asset in image_assets:
        image_id = getattr(asset, "image_id", None)
        if not image_id:
            continue
        selected_variant = str(session_state.get(f"compare_choice_{image_id}", "original"))
        asset.selected_compare_variant = selected_variant
        if selected_variant == "original":
            asset.final_variant = "original"
        elif selected_variant == "safe":
            asset.final_variant = "safe"
        else:
            asset.final_variant = "redrawn"
        asset.final_decision = "accept"
        asset.final_reason = f"compare_variant_selected:{selected_variant}"

    rebuilt_docx_bytes = convert_markdown_to_docx_bytes(markdown_text)
    rebuilt_docx_bytes = reinsert_inline_images(rebuilt_docx_bytes, image_assets)

    session_state["image_assets"] = image_assets
    session_state["latest_docx_bytes"] = rebuilt_docx_bytes
    return rebuilt_docx_bytes