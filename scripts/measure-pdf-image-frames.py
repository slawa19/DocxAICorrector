"""Spec 082 slice A acceptance: the PDF bridge with and without page-frame replacements, book by book.

For every PDF given, the text-layer bridge (`_convert_pdf_text_layer_to_docx`) runs twice in one process:
once as shipped, once with the replacement plan forced empty (what the bridge did before spec 082). The
two intermediate DOCX files are compared on what a reader gets:

* paragraphs -- text and style name, in order;
* pictures   -- sha1 of every picture's bytes, in document order, and its size in the DOCX (EMU).

Paragraphs must be identical; pictures may differ only where an image was replaced. For every replaced
picture a side-by-side PNG is written to ``--out``: the bytes delivered before | the bytes delivered now |
the page itself (the whole page rendered, then cropped to the frame), for a person to look at.

Offline: no model, no network. Run from the repository root in WSL:
    . .venv/bin/activate && python -I scripts/measure-pdf-image-frames.py tests/sources/book/*.pdf --out <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"


def _bootstrap() -> None:
    for root in (str(SRC_ROOT), str(PROJECT_ROOT)):
        if root not in sys.path:
            sys.path.insert(0, root)


def _docx_view(docx_bytes: bytes) -> dict[str, list]:
    from docx import Document

    document = Document(io.BytesIO(docx_bytes))
    blip_tag = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
    embed = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
    extent_tag = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"
    paragraphs = []
    pictures = []
    for paragraph in document.paragraphs:
        if paragraph.text:
            paragraphs.append([paragraph.text, paragraph.style.name if paragraph.style is not None else ""])
        for blip in paragraph._element.iter(blip_tag):
            blob = document.part.related_parts[blip.get(embed)].blob
            extent = next(paragraph._element.iter(extent_tag), None)
            size = [int(extent.get("cx")), int(extent.get("cy"))] if extent is not None else None
            pictures.append({"sha1": hashlib.sha1(blob).hexdigest(), "bytes": len(blob), "emu": size, "blob": blob})
    return {"paragraphs": paragraphs, "pictures": pictures}


def _convert(pdf_path: Path, *, replacements: bool) -> tuple[dict, float, list]:
    import docxaicorrector.pdf_import.image_frames as image_frames
    import docxaicorrector.processing.processing_runtime as runtime

    replaced: list = []
    real_plan = image_frames.plan_frame_replacements
    real_apply = image_frames.apply_frame_replacements

    def empty_plan(extraction, spans):
        return image_frames.FramePlan(candidates=(), declines=())

    def recording_apply(path, extraction, plan):
        outcome = real_apply(path, extraction, plan)
        replaced.extend(image for image in outcome.images if image.original_image_bytes is not None)
        return outcome

    image_frames.plan_frame_replacements = real_plan if replacements else empty_plan
    image_frames.apply_frame_replacements = recording_apply
    try:
        started = time.perf_counter()
        docx_bytes, _backend = runtime._convert_pdf_text_layer_to_docx(filename=pdf_path.name, source_bytes=pdf_path.read_bytes())
        elapsed = time.perf_counter() - started
    finally:
        image_frames.plan_frame_replacements = real_plan
        image_frames.apply_frame_replacements = real_apply
    return _docx_view(docx_bytes), elapsed, replaced


def _side_by_side(pdf_path: Path, image, out_dir: Path, stem: str) -> Path:
    from PIL import Image

    from docxaicorrector.pdf_import.page_render import open_pdf_for_rendering, page_layout_cropbox

    after = Image.open(io.BytesIO(image.image_bytes)).convert("RGB")
    before = Image.open(io.BytesIO(image.original_image_bytes)).convert("RGB").resize(after.size)
    scale = after.size[0] / float(image.display_width_points)
    with open_pdf_for_rendering(pdf_path) as document:
        page = document[image.page_number - 1]  # type: ignore[index]
        crop = page_layout_cropbox(page)
        whole = page.render(scale=scale, draw_annots=False, may_draw_forms=False).to_pil().convert("RGB")
        page.close()
    box = ((image.x0 - crop[0]) * scale, (image.top - crop[1]) * scale, (image.x1 - crop[0]) * scale, (image.bottom - crop[1]) * scale)
    page_view = whole.crop(tuple(int(round(v)) for v in box)).resize(after.size)
    gap = 8
    canvas = Image.new("RGB", (after.size[0] * 3 + gap * 2, after.size[1]), (255, 0, 0))
    for index, panel in enumerate((before, after, page_view)):
        canvas.paste(panel, (index * (after.size[0] + gap), 0))
    target = out_dir / f"{stem}_p{image.page_number}_i{image.discovery_index}.png"
    canvas.save(target)
    return target


def main(argv: list[str] | None = None) -> int:
    _bootstrap()
    import docxaicorrector.processing.processing_runtime as runtime

    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="directory for side-by-side PNGs and report.json")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    # In-process parse so the "before" run's empty plan reaches the worker (a spawned child would not see it).
    runtime._PDF_PARSE_IN_PROCESS = True
    report = {}
    for pdf_path in args.pdfs:
        before, before_secs, _ = _convert(pdf_path, replacements=False)
        after, after_secs, replaced = _convert(pdf_path, replacements=True)
        changed = [
            index
            for index, (b, a) in enumerate(zip(before["pictures"], after["pictures"]))
            if b["sha1"] != a["sha1"]
        ]
        stem = pdf_path.stem[:24].replace(" ", "_")
        sides = [str(_side_by_side(pdf_path, image, args.out, stem)) for image in replaced]
        entry = {
            "paragraphs_before": len(before["paragraphs"]),
            "paragraphs_after": len(after["paragraphs"]),
            "paragraphs_identical": before["paragraphs"] == after["paragraphs"],
            "pictures_before": len(before["pictures"]),
            "pictures_after": len(after["pictures"]),
            "pictures_changed_at": changed,
            "pictures_changed": [
                {"index": index, "before": before["pictures"][index]["sha1"], "after": after["pictures"][index]["sha1"],
                 "emu_before": before["pictures"][index]["emu"], "emu_after": after["pictures"][index]["emu"]}
                for index in changed
            ],
            "replaced_pages": [image.page_number for image in replaced],
            "seconds_before": round(before_secs, 2),
            "seconds_after": round(after_secs, 2),
            "side_by_side": sides,
        }
        report[pdf_path.name] = entry
        print(
            f"{pdf_path.name[:40]}: paragraphs {entry['paragraphs_before']}->{entry['paragraphs_after']} "
            f"identical={entry['paragraphs_identical']}; pictures {entry['pictures_before']}->{entry['pictures_after']}, "
            f"changed {len(changed)} at pages {entry['replaced_pages']}; seconds {before_secs:.1f}->{after_secs:.1f}",
            flush=True,
        )
    (args.out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
