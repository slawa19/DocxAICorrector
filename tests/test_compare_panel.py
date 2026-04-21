import compare_panel
from models import ImageAsset


def test_render_compare_all_apply_panel_is_noop_for_completed_compare_assets(monkeypatch):
    calls = []

    monkeypatch.setattr(compare_panel.st, "info", lambda message: calls.append(("info", message)))
    monkeypatch.setattr(compare_panel.st, "caption", lambda message: calls.append(("caption", message)))

    compare_panel.render_compare_all_apply_panel(
        latest_image_mode="compare_all",
        image_assets=[ImageAsset(image_id="img_001", placeholder="[[DOCX_IMAGE_img_001]]", original_bytes=b"x", mime_type="image/png", position_index=0, comparison_variants={"safe": {"bytes": b"safe"}}, validation_status="compared", final_decision="compared")],
        render_section_gap=lambda gap: calls.append(("gap", gap)),
    )

    assert calls == []


def test_render_compare_all_apply_panel_does_not_render_apply_controls(monkeypatch):
    calls = []

    monkeypatch.setattr(compare_panel.st, "info", lambda message: calls.append(("info", message)))
    monkeypatch.setattr(compare_panel.st, "caption", lambda message: calls.append(("caption", message)))

    compare_panel.render_compare_all_apply_panel(
        latest_image_mode="compare_all",
        image_assets=[ImageAsset(image_id="img_001", placeholder="[[DOCX_IMAGE_img_001]]", original_bytes=b"x", mime_type="image/png", position_index=0, comparison_variants={"safe": {"bytes": b"safe"}}, validation_status="compared", final_decision="compared")],
        render_section_gap=lambda gap: calls.append(("gap", gap)),
    )

    assert not any(kind == "apply" for kind, _ in calls)
    assert not any(kind == "selector" for kind, _ in calls)


def test_render_compare_all_apply_panel_hides_incomplete_compare_assets(monkeypatch):
    calls = []

    monkeypatch.setattr(compare_panel.st, "info", lambda message: calls.append(("info", message)))
    monkeypatch.setattr(compare_panel.st, "caption", lambda message: calls.append(("caption", message)))

    compare_panel.render_compare_all_apply_panel(
        latest_image_mode="compare_all",
        image_assets=[ImageAsset(image_id="img_001", placeholder="[[DOCX_IMAGE_img_001]]", original_bytes=b"x", mime_type="image/png", position_index=0, comparison_variants={"safe": {"bytes": b"safe"}}, validation_status="failed", final_decision="fallback_safe")],
        render_section_gap=lambda gap: calls.append(("gap", gap)),
    )

    assert calls == []