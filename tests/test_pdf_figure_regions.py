"""Spec 082 slice B: the composite-figure region rule on plain boxes (no PDF).

Every test builds an invented page: an image the extractor cannot emit (the seed), emitted images, vector paths
and text lines, and checks one condition of ``plan_figure_regions``. Each condition has a test that fails when
the condition is removed (mutation list: spec 082 Changelog). Texts are invented.
"""

from __future__ import annotations

import pytest

from docxaicorrector.pdf_import import figure_regions as fr
from docxaicorrector.pdf_import.images import (
    SKIP_UNKNOWN_MIME,
    PdfDiscoveredImage,
    PdfImageExtraction,
    PdfImageObject,
)
from docxaicorrector.pdf_import.logical_import import PdfBodyTypography
from docxaicorrector.pdf_import.text_layer_quality import PdfTextSpan

PAGE = 1
CROP = (0.0, 0.0, 400.0, 600.0)
TYPO = PdfBodyTypography(body_font_size=11.0, body_left_x0=40.0, body_right_x1=360.0)  # column 320
BODY_SENTENCE = "An invented line of running text that goes on and on."  # 11 words


class Page:
    """An invented page: images (seed or emitted), paths and text lines, all top-origin boxes."""

    def __init__(self) -> None:
        self.images: list[tuple[tuple[float, float, float, float], bool, tuple[int, int] | None]] = []
        self.paths: list[tuple[float, float, float, float]] = []
        self.lines: list[PdfTextSpan] = []

    def seed(self, box, px=(40, 40)):
        self.images.append((box, False, px))
        return self

    def emitted(self, box, px=(40, 40)):
        self.images.append((box, True, px))
        return self

    def path(self, box):
        self.paths.append(box)
        return self

    def line(self, box, size, text, page=PAGE):
        self.lines.append(PdfTextSpan(page_number=page, text=text, x0=box[0], top=box[1], x1=box[2], bottom=box[3], font_size=size))
        return self

    def body_text(self, top=440.0, count=4):
        for i in range(count):
            self.line((40.0, top + i * 13, 360.0, top + i * 13 + 11), 11.0, BODY_SENTENCE)
        return self

    def extraction(self, page=PAGE) -> PdfImageExtraction:
        discovered = []
        emitted = []
        for index, (box, is_emitted, _px) in enumerate(self.images):
            discovered.append(
                PdfDiscoveredImage(
                    page_number=page, discovery_index=index, x0=box[0], top=box[1], x1=box[2], bottom=box[3],
                    colour_space_family="DeviceGray", skip_reason=None if is_emitted else SKIP_UNKNOWN_MIME, frame_box=box,
                )
            )
            if is_emitted:
                emitted.append(
                    PdfImageObject(
                        page_number=page, x0=box[0], top=box[1], x1=box[2], bottom=box[3], page_height=600.0,
                        image_bytes=b"jpeg", mime_type="image/jpeg", source_index=int(box[1]), discovery_index=index,
                        frame_box=box,
                    )
                )
        return PdfImageExtraction(images=tuple(emitted), discovered=tuple(discovered))

    def graphics(self, page=PAGE) -> dict[int, fr.PageGraphics]:
        items = [
            fr.PageGraphic(box=box, kind="image", discovery_index=index, source_px=px)
            for index, (box, _e, px) in enumerate(self.images)
        ] + [fr.PageGraphic(box=box, kind="path") for box in self.paths]
        return {page: fr.PageGraphics(page_number=page, graphics=tuple(items))}

    def plan(self, typography=TYPO, crop=CROP, graphics=None, extraction=None):
        return fr.plan_figure_regions(
            extraction or self.extraction(), self.lines, graphics or self.graphics(), typography, {PAGE: crop}
        )


def figure() -> Page:
    """A seed with a path and a small label inside, an emitted picture beside it, body text below."""

    page = Page().seed((100.0, 100.0, 200.0, 200.0)).emitted((205.0, 100.0, 255.0, 150.0))
    page.path((120.0, 120.0, 180.0, 180.0))
    page.line((110.0, 150.0, 150.0, 158.0), 8.0, "Label A")
    return page.body_text()


def only_region(plan) -> fr.FigureRegion:
    assert plan.declines == ()
    assert len(plan.regions) == 1
    return plan.regions[0]


def reasons(plan) -> list[str]:
    return [decline.reason for decline in plan.declines]


def test_a_figure_with_a_seed_becomes_one_region_holding_its_emitted_picture() -> None:
    region = only_region(figure().plan())
    assert region.member_keys == ((PAGE, 1),)
    assert region.box == (100.0, 100.0, 255.0, 200.0)
    assert (region.seed_count, region.image_count, region.path_count) == (1, 2, 1)


def test_a_page_whose_images_are_all_emitted_is_not_planned() -> None:
    page = Page().emitted((100.0, 100.0, 200.0, 200.0)).emitted((205.0, 100.0, 255.0, 150.0)).body_text()
    plan = page.plan()
    assert plan.seed_pages == () and plan.regions == () and plan.declines == ()


def test_graphics_join_at_a_gap_of_one_median_line_height_and_not_beyond() -> None:
    # the body lines are 11 pt tall: the page's median line height is 11
    joined = Page().seed((100.0, 100.0, 200.0, 200.0)).emitted((211.0, 100.0, 260.0, 150.0)).body_text()
    assert only_region(joined.plan()).member_keys == ((PAGE, 1),)
    apart = Page().seed((100.0, 100.0, 200.0, 200.0)).emitted((211.5, 100.0, 260.0, 150.0)).body_text()
    assert only_region(apart.plan()).member_keys == ()


def test_the_tolerance_of_a_page_without_text_is_the_books_median_line_height() -> None:
    page = Page().seed((100.0, 100.0, 200.0, 200.0)).emitted((211.0, 100.0, 260.0, 150.0))
    for i in range(4):  # the text is on page 2; page 1 has none
        page.line((40.0, 440.0 + i * 13, 360.0, 451.0 + i * 13), 11.0, BODY_SENTENCE, page=2)
    assert only_region(page.plan()).member_keys == ((PAGE, 1),)


def test_a_small_label_crossing_the_edge_of_the_graphics_grows_the_region() -> None:
    page = figure().line((90.0, 160.0, 130.0, 168.0), 8.0, "Edge label")
    region = only_region(page.plan())
    assert region.box[0] == 90.0 and region.grown_line_count == 1


def test_growth_by_lines_does_not_cascade_through_a_block_of_small_text() -> None:
    # the first line crosses the graphics' edge; the second touches only the first line
    page = figure().line((60.0, 160.0, 130.0, 168.0), 8.0, "Edge label").line((20.0, 166.0, 95.0, 174.0), 8.0, "Next line")
    region = only_region(page.plan())
    assert region.box[0] == 60.0 and region.grown_line_count == 1


def test_a_body_size_line_crossing_the_edge_declines_instead_of_growing() -> None:
    page = figure().line((60.0, 160.0, 130.0, 171.0), 11.0, "Edge words")
    assert reasons(page.plan()) == [fr.DECLINE_RUNNING_TEXT]


@pytest.mark.parametrize("text", ["Words", "136"])
def test_a_body_size_line_with_a_letter_or_a_digit_inside_declines(text) -> None:
    page = figure().line((130.0, 170.0, 160.0, 181.0), 11.0, text)
    assert reasons(page.plan()) == [fr.DECLINE_RUNNING_TEXT]


def test_a_large_line_of_symbols_only_inside_does_not_decline() -> None:
    page = figure().line((130.0, 165.0, 145.0, 189.0), 24.0, "$")
    only_region(page.plan())


def test_a_body_size_line_touching_the_region_with_zero_area_does_not_decline() -> None:
    page = figure().line((255.0, 120.0, 300.0, 131.0), 11.0, "Beside")  # x0 == the region's x1: no area
    only_region(page.plan())


def test_a_full_line_of_small_text_inside_declines() -> None:
    page = Page().seed((40.0, 100.0, 380.0, 300.0)).body_text()
    page.line((45.0, 150.0, 290.0, 158.0), 8.0, "Small words")  # 245 >= 0.72 x 320
    assert reasons(page.plan()) == [fr.DECLINE_FULL_LINE]


def test_an_unknown_body_typography_declines_every_seed_page() -> None:
    unknown = PdfBodyTypography(body_font_size=11.0, body_left_x0=None, body_right_x1=None)
    assert reasons(figure().plan(typography=unknown)) == [fr.DECLINE_TYPOGRAPHY_UNKNOWN]
    no_size = PdfBodyTypography(body_font_size=None, body_left_x0=40.0, body_right_x1=360.0)
    assert reasons(figure().plan(typography=no_size)) == [fr.DECLINE_TYPOGRAPHY_UNKNOWN]


def test_running_text_outside_set_in_another_size_than_the_body_declines() -> None:
    # the document's body is 12 pt; this page's prose is 8 pt and narrow -- the profile does not describe it
    page = Page().seed((100.0, 100.0, 200.0, 200.0)).line((110.0, 150.0, 150.0, 158.0), 8.0, "Label A")
    for i in range(4):
        page.line((40.0, 300.0 + i * 10, 140.0, 308.0 + i * 10), 8.0, "small prose of the page in eight words")
    typography = PdfBodyTypography(body_font_size=12.0, body_left_x0=40.0, body_right_x1=440.0)
    assert reasons(page.plan(typography=typography)) == [fr.DECLINE_TYPOGRAPHY_DISAGREES]
    # one line of running text at body size on the page and the profile describes it
    page.line((40.0, 400.0, 400.0, 412.0), 12.0, BODY_SENTENCE)
    only_region(page.plan(typography=typography))


def test_a_text_block_framed_with_an_icon_declines() -> None:
    page = Page().seed((100.0, 100.0, 120.0, 120.0)).path((95.0, 95.0, 300.0, 200.0)).body_text()
    for i in range(3):
        page.line((125.0, 105.0 + i * 10, 290.0, 113.0 + i * 10), 8.0, "framed small prose with seven or more words")
    assert reasons(page.plan()) == [fr.DECLINE_TEXT_BLOCK]


def test_a_path_framing_most_of_the_page_text_does_not_join_the_figure() -> None:
    page = figure()
    page.path((30.0, 50.0, 380.0, 560.0))  # holds every line of the page
    region = only_region(page.plan())
    assert region.box == (100.0, 100.0, 255.0, 200.0)


def test_an_image_holding_most_of_the_page_text_declines_the_page() -> None:
    page = figure().emitted((30.0, 50.0, 380.0, 560.0))
    assert reasons(page.plan()) == [fr.DECLINE_IMAGE_ENCLOSES_TEXT]
    scan = Page().seed((0.0, 0.0, 400.0, 600.0)).body_text()
    assert reasons(scan.plan()) == [fr.DECLINE_IMAGE_ENCLOSES_TEXT]


def test_two_seeds_whose_regions_touch_become_one_and_distant_ones_stay_two() -> None:
    touching = Page().seed((100.0, 100.0, 150.0, 150.0)).seed((150.0, 100.0, 200.0, 150.0)).body_text()
    assert len(touching.plan().regions) == 1
    apart = Page().seed((50.0, 100.0, 100.0, 150.0)).seed((250.0, 100.0, 300.0, 150.0)).body_text()
    plan = apart.plan()
    assert plan.declines == () and len(plan.regions) == 2


def test_an_emitted_picture_touching_the_region_edge_is_taken_whole() -> None:
    page = Page().seed((100.0, 100.0, 200.0, 200.0)).emitted((150.0, 190.0, 260.0, 260.0)).body_text()
    region = only_region(page.plan())
    assert region.member_keys == ((PAGE, 1),) and region.box == (100.0, 100.0, 260.0, 260.0)


def test_a_region_reaching_past_the_cropbox_is_clipped() -> None:
    page = Page().seed((-20.0, 100.0, 100.0, 200.0)).body_text()
    assert only_region(page.plan()).box == (0.0, 100.0, 100.0, 200.0)


@pytest.mark.parametrize(
    "member",
    [(-5.0, 100.0, 60.0, 150.0), (350.0, 100.0, 405.0, 150.0), (100.0, -5.0, 150.0, 60.0), (100.0, 560.0, 150.0, 605.0)],
    ids=["left", "right", "top", "bottom"],
)
def test_an_emitted_member_partly_outside_the_cropbox_declines_the_page(member) -> None:
    page = Page().emitted(member).body_text(top=300.0)
    page.seed(member)  # the seed sits on the member (the same box), so the member is in the region
    assert reasons(page.plan()) == [fr.DECLINE_MEMBER_OUTSIDE]


def test_a_region_entirely_outside_the_cropbox_declines() -> None:
    page = Page().seed((410.0, 100.0, 450.0, 150.0)).body_text()
    assert reasons(page.plan()) == [fr.DECLINE_OUTSIDE_CROP_BOX]


def test_a_pass_that_disagrees_with_the_inventory_declines_the_page() -> None:
    page = figure()
    graphics = page.graphics()
    moved = list(graphics[PAGE].graphics)
    moved[1] = fr.PageGraphic(box=(205.0, 100.0, 255.0, 150.5), kind="image", discovery_index=1, source_px=(40, 40))
    assert reasons(page.plan(graphics={PAGE: fr.PageGraphics(PAGE, tuple(moved))})) == [fr.DECLINE_INVENTORY_MISMATCH]
    fewer = tuple(g for g in graphics[PAGE].graphics if g.discovery_index != 1)
    assert reasons(page.plan(graphics={PAGE: fr.PageGraphics(PAGE, fewer)})) == [fr.DECLINE_INVENTORY_MISMATCH]


def test_a_lone_seed_is_a_region_with_no_members() -> None:
    page = Page().seed((100.0, 100.0, 200.0, 200.0)).body_text()
    region = only_region(page.plan())
    assert region.member_keys == () and region.seed_count == 1


def test_one_declined_region_declines_every_region_of_its_page() -> None:
    page = Page().seed((50.0, 100.0, 100.0, 150.0)).seed((250.0, 100.0, 300.0, 150.0)).body_text()
    page.line((260.0, 120.0, 290.0, 131.0), 11.0, "Words")  # body text in the second region only
    plan = page.plan()
    assert plan.regions == ()
    assert sorted(reasons(plan)) == [fr.DECLINE_PAGE_ATOMIC, fr.DECLINE_RUNNING_TEXT]


def test_the_seed_density_is_the_area_weighted_median_of_the_seeds() -> None:
    page = Page().seed((100.0, 100.0, 200.0, 200.0), px=(100, 100)).seed((200.0, 100.0, 210.0, 110.0), px=(100, 100)).body_text()
    region = only_region(page.plan())
    assert region.seed_density == pytest.approx(1.0)  # the large seed: 100 px over 100 pt


def test_the_body_typography_is_the_importers_own_preparation(monkeypatch) -> None:
    from docxaicorrector.pdf_import import logical_import

    spans = []
    for page in (1, 2, 3):
        for i in range(5):
            spans.append(PdfTextSpan(page_number=page, text=BODY_SENTENCE, x0=40.0, top=100.0 + 13 * i, x1=360.0, bottom=111.0 + 13 * i, font_size=11.0))
        spans.append(PdfTextSpan(page_number=page, text="Label of a figure", x0=60.0, top=300.0, x1=120.0, bottom=308.0, font_size=8.0))
    typography = logical_import.pdf_body_typography(spans)
    assert (typography.body_font_size, typography.body_left_x0, typography.body_right_x1) == (11.0, 40.0, 360.0)

    calls: list[int] = []
    real = logical_import._prepare_spans_for_import

    def spy(items):
        calls.append(len(items))
        return real(items)

    monkeypatch.setattr(logical_import, "_prepare_spans_for_import", spy)
    logical_import.build_paragraph_units_from_text_spans(spans)
    logical_import.pdf_body_typography(spans)
    assert calls == [len(spans), len(spans)]  # the importer and the step run the one preparation


def test_growth_by_lines_does_not_cascade_even_when_the_region_grows_again() -> None:
    # the edge label pulls in a path that touches it (another pass of growth follows); the next line touches only the
    # label, never the graphics, and stays outside
    page = Page().seed((100.0, 100.0, 140.0, 140.0)).body_text()
    page.line((60.0, 120.0, 110.0, 128.0), 8.0, "Edge label")
    page.path((62.0, 115.0, 70.0, 120.0))
    page.line((20.0, 126.0, 61.0, 134.0), 8.0, "Next line")
    region = only_region(page.plan())
    assert region.box[0] == 60.0 and region.grown_line_count == 1 and region.path_count == 1


def test_two_seeds_joined_only_by_a_label_between_them_become_one_region() -> None:
    page = Page().seed((100.0, 100.0, 150.0, 150.0)).seed((170.0, 100.0, 220.0, 150.0)).body_text()
    page.line((140.0, 120.0, 180.0, 128.0), 8.0, "Shared")
    region = only_region(page.plan())
    assert region.box == (100.0, 100.0, 220.0, 150.0) and region.seed_count == 2


def test_a_drawing_reached_only_through_a_grown_label_is_absorbed() -> None:
    page = Page().seed((100.0, 100.0, 140.0, 140.0)).emitted((182.0, 110.0, 220.0, 150.0)).body_text()
    page.line((130.0, 120.0, 182.0, 128.0), 8.0, "Pointer label")
    region = only_region(page.plan())
    assert region.member_keys == ((PAGE, 1),) and region.box == (100.0, 100.0, 220.0, 150.0)


def test_the_seed_density_is_weighted_by_area_not_the_smallest() -> None:
    page = Page().seed((100.0, 100.0, 200.0, 200.0), px=(200, 200)).seed((200.0, 100.0, 210.0, 110.0), px=(10, 10)).body_text()
    assert only_region(page.plan()).seed_density == pytest.approx(2.0)
