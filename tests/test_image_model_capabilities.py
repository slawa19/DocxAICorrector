"""Spec 062 FR-003 / FR-004: the positive capability table builds every Images API request."""

import logging
import tomllib
from types import SimpleNamespace

import pytest

from docxaicorrector.core import config
from docxaicorrector.image import generation as image_generation
from docxaicorrector.image import model_capabilities as capabilities
from docxaicorrector.image.output_policy import DEFAULT_EDIT_CANDIDATE_SIZES, DEFAULT_GENERATE_CANDIDATE_SIZES


@pytest.fixture(autouse=True)
def _reset_unknown_model_warnings():
    capabilities._WARNED_UNKNOWN_IMAGE_MODELS.clear()
    yield
    capabilities._WARNED_UNKNOWN_IMAGE_MODELS.clear()


def _capture_log_events(monkeypatch, module) -> list[tuple[int, str, dict]]:
    events: list[tuple[int, str, dict]] = []
    monkeypatch.setattr(module, "log_event", lambda level, event_id, message, **context: events.append((level, event_id, context)))
    return events


@pytest.mark.parametrize("model", ["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"])
def test_generate_request_for_the_2_5_family_omits_response_format_and_keeps_transparency(model):
    payload = capabilities.build_images_request(
        operation="generate",
        model=model,
        prompt="p",
        size="1536x1024",
        quality="high",
        background="transparent",
    )

    assert payload == {
        "model": model,
        "prompt": "p",
        "size": "1536x1024",
        "output_format": "png",
        "quality": "high",
        "background": "transparent",
    }


def test_edit_request_sends_input_fidelity_only_where_the_table_says_so():
    common = {"operation": "edit", "prompt": "p", "size": "1024x1024", "quality": "high", "input_fidelity": "high", "image": [b"x"]}

    accepted = capabilities.build_images_request(model="gpt-image-1.5", **common)
    omitted_2 = capabilities.build_images_request(model="gpt-image-2", **common)
    omitted_25 = capabilities.build_images_request(model="gpt-image-2.5-flare", **common)

    assert accepted["input_fidelity"] == "high"
    assert "input_fidelity" not in omitted_2
    assert "input_fidelity" not in omitted_25
    assert all("response_format" not in payload for payload in (accepted, omitted_2, omitted_25))
    assert accepted["image"] == [b"x"]


def test_quality_and_background_the_model_does_not_accept_are_left_out():
    gpt_image_2 = capabilities.build_images_request(
        operation="generate", model="gpt-image-2", prompt="p", size="1024x1024", quality="max", background="transparent"
    )
    flare = capabilities.build_images_request(
        operation="generate", model="gpt-image-2.5-flare", prompt="p", size="1024x1024", quality="max", background="transparent"
    )
    flare_2_6 = capabilities.build_images_request(
        operation="generate", model="gpt-image-2.6-flare", prompt="p", size="1024x1024", quality="high", background="transparent"
    )

    # gpt-image-2: transparency is "in preview", xhigh/max are 2.5-only.
    assert "quality" not in gpt_image_2 and "background" not in gpt_image_2
    assert flare["quality"] == "max" and flare["background"] == "transparent"
    # 2.6: background support is not documented, so it is not sent.
    assert flare_2_6["quality"] == "high" and "background" not in flare_2_6


def test_dated_snapshot_resolves_to_its_family():
    assert capabilities.resolve_image_model_capabilities("gpt-image-2.5-flare-2026-09-08") is capabilities.IMAGE_MODEL_CAPABILITIES["gpt-image-2.5-flare"]
    assert capabilities.resolve_image_model_capabilities("openai:gpt-image-2.5-sunburst") is capabilities.IMAGE_MODEL_CAPABILITIES["gpt-image-2.5-sunburst"]
    assert capabilities.resolve_image_model_capabilities("gpt-image-9") is None


def test_unknown_model_gets_the_minimal_request_and_one_warning_per_model(monkeypatch):
    events = _capture_log_events(monkeypatch, capabilities)
    kwargs = {"operation": "generate", "prompt": "p", "size": "1024x1024", "quality": "high", "background": "transparent"}

    first = capabilities.build_images_request(model="gpt-image-9", **kwargs)
    capabilities.build_images_request(model="gpt-image-9", **kwargs)

    assert set(first) == {"model", "prompt", "size", "quality", "output_format"}
    warnings = [event for event in events if event[1] == "image_model_capabilities_unknown"]
    assert len(warnings) == 1
    assert warnings[0][0] == logging.WARNING
    assert warnings[0][2]["model"] == "gpt-image-9"


def test_size_the_model_rejects_moves_to_the_nearest_size_it_accepts():
    # gpt-image-1.5 takes only the three standard sizes; 2.5 takes arbitrary WxH by its rules.
    standard = capabilities.build_images_request(
        operation="generate", model="gpt-image-1.5", prompt="p", size="1792x1024", quality="high"
    )
    arbitrary = capabilities.build_images_request(
        operation="generate", model="gpt-image-2.5-flare", prompt="p", size="1536x864", quality="high"
    )
    too_small = capabilities.build_images_request(
        operation="edit", model="gpt-image-2.5-flare", prompt="p", size="512x512", quality="high", image=[b"x"]
    )

    assert standard["size"] == "1536x1024"
    assert arbitrary["size"] == "1536x864"
    assert too_small["size"] == "1024x1024"


def test_accepts_size_follows_the_documented_2x_limits():
    flare = capabilities.IMAGE_MODEL_CAPABILITIES["gpt-image-2.5-flare"]

    assert capabilities.accepts_size(flare, "1536x864")
    assert not capabilities.accepts_size(flare, "1530x864")  # not divisible by 16
    assert not capabilities.accepts_size(flare, "512x512")  # under 655 360 pixels
    assert not capabilities.accepts_size(flare, "3200x800")  # aspect over 3:1
    assert not capabilities.accepts_size(flare, "4096x2048")  # edge over 3840


def _shipped_image_output_grids() -> list[tuple[str, tuple[str, ...]]]:
    shipped = tomllib.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))["image_output"]
    return [
        ("config.toml generate_candidate_sizes", tuple(shipped["generate_candidate_sizes"])),
        ("config.toml edit_candidate_sizes", tuple(shipped["edit_candidate_sizes"])),
        ("output_policy DEFAULT_GENERATE_CANDIDATE_SIZES", DEFAULT_GENERATE_CANDIDATE_SIZES),
        ("output_policy DEFAULT_EDIT_CANDIDATE_SIZES", DEFAULT_EDIT_CANDIDATE_SIZES),
    ]


@pytest.mark.parametrize("family", sorted(capabilities.IMAGE_MODEL_CAPABILITIES))
def test_every_shipped_size_grid_is_accepted_by_every_model_in_the_table(family):
    # Spec 062 FR-003: no dall-e-era size (512x512, 256x256, 1792x1024) in any grid, and
    # every grid size meets every model's minimum area.
    model_capabilities = capabilities.IMAGE_MODEL_CAPABILITIES[family]
    for grid_name, sizes in _shipped_image_output_grids():
        for size in sizes:
            width, height = (int(part) for part in size.split("x"))
            assert width * height >= model_capabilities.min_pixels, (grid_name, size, family)
            assert capabilities.accepts_size(model_capabilities, size), (grid_name, size, family)


def test_filter_sizes_for_model_drops_what_the_model_rejects():
    assert capabilities.filter_sizes_for_model("gpt-image-2.5-flare", ("1536x1024", "512x512")) == ("1536x1024",)
    assert capabilities.filter_sizes_for_model("gpt-image-1.5", ("256x256",)) == capabilities.STANDARD_GPT_IMAGE_SIZES
    assert capabilities.filter_sizes_for_model("gpt-image-9", ("1024x1024", "512x512")) == ("1024x1024",)


def test_error_text_adaptation_is_a_logged_warning_not_a_silent_debug(monkeypatch):
    # FR-004: the error-text path stays only as a last resort, and when it fires it says so.
    events = _capture_log_events(monkeypatch, image_generation)
    calls: list[dict] = []

    class FakeImages:
        def edit(self, **kwargs):
            calls.append(kwargs)
            if "input_fidelity" in kwargs:
                raise RuntimeError("Error code: 400 - Unsupported parameter: 'input_fidelity' is not supported with this model.")
            return SimpleNamespace(data=[])

    client = SimpleNamespace(images=FakeImages())
    image_generation._call_images_edit(
        client,
        {"model": "gpt-image-2.5-flare", "image": [b"x"], "prompt": "p", "input_fidelity": "high"},
    )

    assert "input_fidelity" in calls[0] and "input_fidelity" not in calls[1]
    adaptation = [event for event in events if event[1] == "semantic_image_edit_retry_without_optional_param"]
    assert len(adaptation) == 1
    assert adaptation[0][0] == logging.WARNING
    assert adaptation[0][2]["model"] == "gpt-image-2.5-flare"
    assert adaptation[0][2]["removed_param"] == "input_fidelity"


def test_last_resort_parser_recognises_the_measured_2_5_rejection_wording():
    # Verbatim 400 from the 2026-11-07 FR-006 probe; before spec 062 this wording was not
    # recognised and the edit failed instead of retrying without the parameter.
    from docxaicorrector.image.shared import extract_unsupported_parameter_name

    message = (
        "Error code: 400 - {'error': {'message': \"The model 'gpt-image-2.5-flare' does not support the "
        "'input_fidelity' parameter.\", 'type': 'image_generation_user_error', 'param': 'input_fidelity', "
        "'code': 'invalid_input_fidelity_model'}}"
    )

    assert extract_unsupported_parameter_name(message) == "input_fidelity"
