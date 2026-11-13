"""Spec 082 slice A acceptance: what the PDF bridge delivers, book by book, saved so it can be recounted.

Two subcommands.

``run`` converts each PDF with the text-layer bridge (`_convert_pdf_text_layer_to_docx`, parse in process)
from the source tree given by ``--src`` -- this tree, or a checkout of the base commit -- and saves, per
book, the FULL sequences a reader gets: every paragraph (text, style name) in order and every picture
(sha1, byte size, size in the DOCX in EMU) in order, with the run's provenance (label, commit, source
tree, whether the frame-replacement step exists there) and the time taken. When the step exists, each
replaced picture also gets a side-by-side PNG: bytes delivered before | bytes delivered now | the page
itself (the whole page rendered, cropped to the frame by PIL -- an independent crop path).

``compare`` reads two saved runs and lists every difference: paragraphs by position, pictures by
position with both sha1. Nothing is summarised away.

Offline: no model, no network. Run from the repository root in WSL, for example:
    . .venv/bin/activate && python -I scripts/measure-pdf-image-frames.py run --src <base>/src \
        --label base --commit <sha> --out <dir> tests/sources/book/*.pdf
    . .venv/bin/activate && python -I scripts/measure-pdf-image-frames.py run --src src \
        --label branch --commit <sha> --out <dir> tests/sources/book/*.pdf
    . .venv/bin/activate && python -I scripts/measure-pdf-image-frames.py compare <dir>/base.json <dir>/branch.json
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
            pictures.append({"sha1": hashlib.sha1(blob).hexdigest(), "bytes": len(blob), "emu": size})
    return {"paragraphs": paragraphs, "pictures": pictures}


def _side_by_side(pdf_path: Path, image, out_dir: Path, stem: str) -> str:
    from PIL import Image

    from docxaicorrector.pdf_import.page_render import open_pdf_for_rendering, read_page_geometry

    after = Image.open(io.BytesIO(image.image_bytes)).convert("RGB")
    before = Image.open(io.BytesIO(image.original_image_bytes)).convert("RGB").resize(after.size)
    scale = after.size[0] / float(image.display_width_points)
    crop = read_page_geometry(pdf_path, {image.page_number})[image.page_number].layout_cropbox
    with open_pdf_for_rendering(pdf_path) as document:
        page = document[image.page_number - 1]  # type: ignore[index]
        whole = page.render(scale=scale, draw_annots=False, may_draw_forms=False).to_pil().convert("RGB")
        page.close()
    box = ((image.x0 - crop[0]) * scale, (image.top - crop[1]) * scale, (image.x1 - crop[0]) * scale, (image.bottom - crop[1]) * scale)
    page_view = whole.crop((int(round(box[0])), int(round(box[1])), int(round(box[2])), int(round(box[3])))).resize(after.size)
    gap = 8
    canvas = Image.new("RGB", (after.size[0] * 3 + gap * 2, after.size[1]), (255, 0, 0))
    for index, panel in enumerate((before, after, page_view)):
        canvas.paste(panel, (index * (after.size[0] + gap), 0))
    target = out_dir / f"{stem}_p{image.page_number}_i{image.discovery_index}.png"
    canvas.save(target)
    return str(target)


def _run(args) -> int:
    src = Path(args.src).resolve()
    sys.path.insert(0, str(src))
    import docxaicorrector.processing.processing_runtime as runtime

    try:
        import docxaicorrector.pdf_import.image_frames as image_frames
    except ImportError:
        image_frames = None
    runtime._PDF_PARSE_IN_PROCESS = True  # in-process parse, one interpreter, same modules
    replaced: list = []
    if image_frames is not None:
        real_apply = image_frames.apply_frame_replacements

        def recording_apply(path, extraction, plan):
            outcome = real_apply(path, extraction, plan)
            replaced.extend(image for image in outcome.images if image.original_image_bytes is not None)
            return outcome

        image_frames.apply_frame_replacements = recording_apply  # type: ignore[assignment]
    args.out.mkdir(parents=True, exist_ok=True)
    sides_dir = args.out / f"{args.label}_side_by_side"
    books: dict[str, object] = {}
    report: dict[str, object] = {
        "provenance": {
            "label": args.label,
            "commit": args.commit,
            "src": str(src),
            "frame_replacement_step": image_frames is not None,
            "module": runtime.__file__,
        },
        "books": books,
    }
    for pdf_path in args.pdfs:
        replaced.clear()
        started = time.perf_counter()
        docx_bytes, _backend = runtime._convert_pdf_text_layer_to_docx(filename=pdf_path.name, source_bytes=pdf_path.read_bytes())
        elapsed = time.perf_counter() - started
        view = _docx_view(docx_bytes)
        sides = []
        if replaced:
            sides_dir.mkdir(parents=True, exist_ok=True)
            stem = pdf_path.stem[:24].replace(" ", "_")
            sides = [_side_by_side(pdf_path, image, sides_dir, stem) for image in replaced]
        books[pdf_path.name] = {
            "seconds": round(elapsed, 2),
            "paragraphs": view["paragraphs"],
            "pictures": view["pictures"],
            "replaced_pages": [image.page_number for image in replaced],
            "side_by_side": sides,
        }
        print(f"{args.label}: {pdf_path.name[:40]}: {len(view['paragraphs'])} paragraphs, {len(view['pictures'])} pictures, "
              f"{len(replaced)} replaced, {elapsed:.1f}s", flush=True)
    (args.out / f"{args.label}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def _compare(args) -> int:
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    books: dict[str, object] = {}
    result: dict[str, object] = {"before": before["provenance"], "after": after["provenance"], "books": books}
    for name, b in before["books"].items():
        a = after["books"][name]
        paragraph_diffs = [
            {"index": i, "before": pb, "after": pa}
            for i, (pb, pa) in enumerate(zip(b["paragraphs"], a["paragraphs"]))
            if pb != pa
        ]
        picture_diffs = [
            {"index": i, "before": pb, "after": pa}
            for i, (pb, pa) in enumerate(zip(b["pictures"], a["pictures"]))
            if pb["sha1"] != pa["sha1"]
        ]
        entry = {
            "paragraphs": [len(b["paragraphs"]), len(a["paragraphs"])],
            "pictures": [len(b["pictures"]), len(a["pictures"])],
            "paragraph_differences": paragraph_diffs,
            "picture_differences": picture_diffs,
            "replaced_pages_after": a["replaced_pages"],
            "seconds": [b["seconds"], a["seconds"]],
        }
        books[name] = entry
        print(f"{name[:40]}: paragraphs {entry['paragraphs']} differences {len(paragraph_diffs)}; pictures {entry['pictures']} "
              f"differences {len(picture_diffs)} at {[d['index'] for d in picture_diffs]}; replaced pages {a['replaced_pages']}; "
              f"seconds {entry['seconds']}", flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("pdfs", nargs="+", type=Path)
    run.add_argument("--src", default=str(PROJECT_ROOT / "src"), help="the docxaicorrector source tree to measure")
    run.add_argument("--label", required=True)
    run.add_argument("--commit", required=True, help="commit the source tree is checked out at (provenance)")
    run.add_argument("--out", type=Path, required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("before")
    compare.add_argument("after")
    compare.add_argument("--out")
    args = parser.parse_args(argv)
    return _run(args) if args.command == "run" else _compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
