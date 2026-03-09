from io import BytesIO

from PIL import Image, ImageDraw

import image_analysis


def _make_diagram_like_jpeg() -> bytes:
    image = Image.new("RGB", (480, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 50, 180, 120), outline="black", width=4)
    draw.rectangle((280, 50, 420, 120), outline="black", width=4)
    draw.rectangle((160, 200, 300, 270), outline="black", width=4)
    draw.line((180, 85, 280, 85), fill="black", width=4)
    draw.line((350, 120, 230, 200), fill="black", width=4)
    draw.line((110, 120, 230, 200), fill="black", width=4)
    draw.rectangle((70, 72, 150, 84), fill="black")
    draw.rectangle((310, 72, 390, 84), fill="black")
    draw.rectangle((190, 222, 270, 234), fill="black")
    output = BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def _make_photo_like_jpeg() -> bytes:
    image = Image.new("RGB", (480, 320))
    draw = ImageDraw.Draw(image)
    for x in range(480):
        for y in range(320):
            draw.point((x, y), fill=((x * 3) % 256, (y * 5) % 256, ((x + y) * 2) % 256))
    output = BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def test_analyze_image_allows_semantic_redraw_for_diagram_like_jpeg():
    result = image_analysis.analyze_image(_make_diagram_like_jpeg(), model="gpt-4.1", mime_type="image/jpeg")

    assert result.image_type == "diagram"
    assert result.semantic_redraw_allowed is True
    assert result.prompt_key == "diagram_semantic_redraw"
    assert result.render_strategy == "deterministic_reconstruction"


def test_analyze_image_keeps_photo_like_jpeg_in_safe_mode():
    result = image_analysis.analyze_image(_make_photo_like_jpeg(), model="gpt-4.1", mime_type="image/jpeg")

    assert result.image_type == "photo"
    assert result.semantic_redraw_allowed is False
    assert result.prompt_key == "photo_safe_fallback"
    assert result.render_strategy == "safe_mode"