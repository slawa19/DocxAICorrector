"""Spec 082 acceptance (slices A and B): what the PDF bridge delivers, book by book, saved so it can be recounted.

Two subcommands.

``run`` converts each PDF with the text-layer bridge (`_convert_pdf_text_layer_to_docx`, parse in process)
from the source tree given by ``--src`` -- this tree, or a checkout of the base commit -- and saves, per
book, the FULL sequences a reader gets: every paragraph (text, style name) in order and every picture
(sha1, byte size, size in the DOCX in EMU) in order, with the run's provenance (label, commit, source
tree, whether the frame-replacement step exists there) and the time taken. When the step exists, each
replaced picture also gets a side-by-side PNG: bytes delivered before | bytes delivered now | the page
itself (the whole page rendered, cropped to the frame by PIL -- an independent crop path). When the slice-B step
exists, each composite-figure render gets a side-by-side PNG: the render delivered | the page (whole page rendered,
cropped by PIL). ``--prep`` also saves the audiobook preparation of each book (role, narration-exclusion reason and
text of every prepared paragraph; offline, no model).

``compare`` reads two saved runs and lists every difference: paragraphs by position, pictures by
position with every saved field (sha1, byte size, DOCX size), and -- when one run has more -- the added or
removed tail, item by item. Nothing is summarised away.

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
from itertools import zip_longest
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
    try:
        import docxaicorrector.pdf_import.figure_regions as figure_regions
    except ImportError:
        figure_regions = None
    regions: list = []
    if figure_regions is not None:
        real_regions = figure_regions.replace_composite_figures

        def recording_regions(path, extraction, images_a, spans, **kwargs):
            outcome = real_regions(path, extraction, images_a, spans, **kwargs)
            regions.extend(image for image in outcome.images if getattr(image, "region_members", None) is not None)
            return outcome

        figure_regions.replace_composite_figures = recording_regions  # type: ignore[assignment]
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
            "figure_region_step": figure_regions is not None,
            "module": runtime.__file__,
        },
        "books": books,
    }
    for pdf_path in args.pdfs:
        replaced.clear()
        regions.clear()
        started = time.perf_counter()
        docx_bytes, _backend = runtime._convert_pdf_text_layer_to_docx(filename=pdf_path.name, source_bytes=pdf_path.read_bytes())
        elapsed = time.perf_counter() - started
        view = _docx_view(docx_bytes)
        sides = []
        if replaced:
            sides_dir.mkdir(parents=True, exist_ok=True)
            stem = pdf_path.stem[:24].replace(" ", "_")
            sides = [_side_by_side(pdf_path, image, sides_dir, stem) for image in replaced]
        if regions:
            sides_dir.mkdir(parents=True, exist_ok=True)
            stem = pdf_path.stem[:24].replace(" ", "_")
            sides += [_region_side_by_side(pdf_path, image, sides_dir, stem) for image in regions]
        replaced_pages = [image.page_number for image in replaced]
        region_pages = [image.page_number for image in regions]
        region_members = [len(image.region_members or ()) for image in regions]
        replaced_count = len(replaced)
        prepared = _prepare(runtime, pdf_path) if args.prep else None  # converts again: snapshot the lists first
        prep = _prepared_rows(prepared) if prepared is not None else None
        structure = _prepared_structure(prepared) if prepared is not None else None
        books[pdf_path.name] = {
            "seconds": round(elapsed, 2),
            "paragraphs": view["paragraphs"],
            "pictures": view["pictures"],
            "replaced_pages": replaced_pages,
            "region_pages": region_pages,
            "region_members": region_members,
            "prepared": prep,
            "prepared_structure": structure,
            "side_by_side": sides,
        }
        print(f"{args.label}: {pdf_path.name[:40]}: {len(view['paragraphs'])} paragraphs, {len(view['pictures'])} pictures, "
              f"{replaced_count} replaced, {len(region_pages)} regions, {elapsed:.1f}s", flush=True)
    (args.out / f"{args.label}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def _region_side_by_side(pdf_path: Path, image, out_dir: Path, stem: str) -> str:
    """The region render delivered | the same box of the whole page rendered at the same density, cropped by PIL."""

    from PIL import Image

    from docxaicorrector.pdf_import.page_render import open_pdf_for_rendering, read_page_geometry

    after = Image.open(io.BytesIO(image.image_bytes)).convert("RGB")
    scale = after.size[0] / float(image.display_width_points)
    crop = read_page_geometry(pdf_path, {image.page_number})[image.page_number].layout_cropbox
    with open_pdf_for_rendering(pdf_path) as document:
        page = document[image.page_number - 1]  # type: ignore[index]
        whole = page.render(scale=scale, draw_annots=False, may_draw_forms=False).to_pil().convert("RGB")
        page.close()
    box = image.frame_box or (image.x0, image.top, image.x1, image.bottom)
    pixel_box = [(box[0] - crop[0]) * scale, (box[1] - crop[1]) * scale, (box[2] - crop[0]) * scale, (box[3] - crop[1]) * scale]
    page_view = whole.crop(tuple(int(round(v)) for v in pixel_box)).resize(after.size)
    gap = 8
    canvas = Image.new("RGB", (after.size[0] * 2 + gap, after.size[1]), (255, 0, 0))
    canvas.paste(after, (0, 0))
    canvas.paste(page_view, (after.size[0] + gap, 0))
    target = out_dir / f"{stem}_p{image.page_number}_region.png"
    canvas.save(target)
    whole.save(out_dir / f"{stem}_p{image.page_number}_page.png")
    return str(target)


def _prepare(runtime, pdf_path: Path):
    """The audiobook preparation of the book, offline (no model)."""

    from docxaicorrector.core.config import load_app_config
    from docxaicorrector.core.constants import DEFAULT_CHUNK_SIZE
    from docxaicorrector.processing.preparation import _prepare_document_for_processing

    def no_model(*args, **kwargs):
        raise AssertionError("no model in a measurement")

    config = load_app_config()
    config = dict(config) if isinstance(config, dict) else dict(config.to_dict())
    normalized = runtime.normalize_uploaded_document(filename=pdf_path.name, source_bytes=pdf_path.read_bytes())
    prepared = _prepare_document_for_processing(
        normalized.filename, normalized.content_bytes, DEFAULT_CHUNK_SIZE, source_format=normalized.source_format,
        conversion_backend=normalized.conversion_backend, app_config=config, processing_operation="audiobook",
        get_client_fn=no_model, client_factory=None,
    )
    return prepared


def _prepared_rows(prepared) -> list[list]:
    """[role, narration-exclusion reason, text] per prepared paragraph of every job."""

    rows: list[list] = []
    for job in prepared.jobs:
        ids = list(job["paragraph_ids"])
        texts = str(job["target_text"]).split("\n\n")
        if len(texts) != len(ids):
            # a job whose text does not split per paragraph is reported, never silently compared as None
            raise RuntimeError(f"prepared job text has {len(texts)} parts for {len(ids)} paragraphs")
        reasons = job.get("narration_exclusion_reasons") or [None] * len(ids)
        for k in range(len(ids)):
            rows.append([job["structural_roles"][k], reasons[k], texts[k]])
    return rows


def _prepared_structure(prepared) -> dict[str, list]:
    """Paragraph boundaries and relations of the prepared document: every paragraph (role, heading level, text) and
    every relation (kind, its members' texts, whether it is anchored to an asset)."""

    by_id = {getattr(p, "paragraph_id", None): str(getattr(p, "text", "")) for p in prepared.paragraphs}
    return {
        "paragraphs": [[str(getattr(p, "role", "")), getattr(p, "heading_level", None), str(getattr(p, "text", ""))] for p in prepared.paragraphs],
        "relations": [
            [r.relation_kind, [by_id.get(m, "?") for m in r.member_paragraph_ids], r.anchor_asset_id is not None]
            for r in prepared.relations
        ],
    }


def _picture_fields(before: dict | None, after: dict | None) -> list[str]:
    if before is None or after is None:
        return ["added" if before is None else "removed"]
    return [field for field in ("sha1", "bytes", "emu") if before.get(field) != after.get(field)]


def _compare(args) -> int:
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    books: dict[str, object] = {}
    result: dict[str, object] = {"before": before["provenance"], "after": after["provenance"], "books": books}
    for name in sorted(set(before["books"]) | set(after["books"])):
        if name not in before["books"] or name not in after["books"]:
            books[name] = {"only_in": "before" if name in before["books"] else "after"}
            print(f"{name[:40]}: only in the {books[name]['only_in']} run", flush=True)
            continue
        b = before["books"][name]
        a = after["books"][name]
        # Every position of the longer sequence is compared: an item present on one side only is a
        # difference with ``None`` on the other (an added or removed paragraph or picture), and a picture
        # differs when ANY of its sha1, byte size or DOCX size differs.
        paragraph_diffs = [
            {"index": i, "before": pb, "after": pa}
            for i, (pb, pa) in enumerate(zip_longest(b["paragraphs"], a["paragraphs"]))
            if pb != pa
        ]
        picture_diffs = [
            {"index": i, "before": pb, "after": pa, "fields": _picture_fields(pb, pa)}
            for i, (pb, pa) in enumerate(zip_longest(b["pictures"], a["pictures"]))
            if pb != pa
        ]
        entry = {
            "paragraphs": [len(b["paragraphs"]), len(a["paragraphs"])],
            "pictures": [len(b["pictures"]), len(a["pictures"])],
            "paragraph_differences": paragraph_diffs,
            "picture_differences": picture_diffs,
            "pictures_added": [d["index"] for d in picture_diffs if d["before"] is None],
            "pictures_removed": [d["index"] for d in picture_diffs if d["after"] is None],
            "replaced_pages_before": b["replaced_pages"],
            "replaced_pages_after": a["replaced_pages"],
            "region_pages_before": b.get("region_pages", []),
            "region_pages_after": a.get("region_pages", []),
            "seconds": [b["seconds"], a["seconds"]],
        }
        if b.get("prepared") is not None and a.get("prepared") is not None:
            # the audiobook preparation without the picture rows: text, role and narration reason, position by position
            pb = [row for row in b["prepared"] if row[0] != "image"]
            pa = [row for row in a["prepared"] if row[0] != "image"]
            entry["prepared_rows"] = [len(pb), len(pa)]
            entry["prepared_picture_rows"] = [len(b["prepared"]) - len(pb), len(a["prepared"]) - len(pa)]
            entry["prepared_differences"] = [
                {"index": i, "before": rb, "after": ra} for i, (rb, ra) in enumerate(zip_longest(pb, pa)) if rb != ra
            ]
        if b.get("prepared_structure") is not None and a.get("prepared_structure") is not None:
            sb, sa = b["prepared_structure"], a["prepared_structure"]
            pb2 = [row for row in sb["paragraphs"] if row[0] != "image"]
            pa2 = [row for row in sa["paragraphs"] if row[0] != "image"]
            entry["prepared_paragraphs"] = [len(pb2), len(pa2)]
            entry["prepared_paragraph_differences"] = [
                {"index": i, "before": rb, "after": ra} for i, (rb, ra) in enumerate(zip_longest(pb2, pa2)) if rb != ra
            ]
            entry["prepared_relations"] = [len(sb["relations"]), len(sa["relations"])]
            entry["prepared_relation_differences"] = [
                {"index": i, "before": rb, "after": ra}
                for i, (rb, ra) in enumerate(zip_longest(sb["relations"], sa["relations"]))
                if rb != ra
            ]
        books[name] = entry
        print(f"{name[:40]}: paragraphs {entry['paragraphs']} differences {len(paragraph_diffs)}; pictures {entry['pictures']} "
              f"differences {len(picture_diffs)} at {[d['index'] for d in picture_diffs]} "
              f"(fields {sorted({f for d in picture_diffs for f in d['fields']})}, added {entry['pictures_added']}, "
              f"removed {entry['pictures_removed']}); replaced pages {b['replaced_pages']} -> {a['replaced_pages']}; "
              f"seconds {entry['seconds']}", flush=True)
        if "prepared_rows" in entry:
            print(f"{name[:40]}: prepared rows without pictures {entry['prepared_rows']} differences "
                  f"{len(entry['prepared_differences'])}; picture rows {entry['prepared_picture_rows']}; "
                  f"region pages {entry['region_pages_before']} -> {entry['region_pages_after']}", flush=True)
        if "prepared_paragraphs" in entry:
            print(f"{name[:40]}: prepared paragraphs without pictures {entry['prepared_paragraphs']} differences "
                  f"{len(entry['prepared_paragraph_differences'])}; relations {entry['prepared_relations']} differences "
                  f"{len(entry['prepared_relation_differences'])}", flush=True)
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
    run.add_argument("--prep", action="store_true", help="also save the audiobook preparation of each book (slow)")
    compare = commands.add_parser("compare")
    compare.add_argument("before")
    compare.add_argument("after")
    compare.add_argument("--out")
    args = parser.parse_args(argv)
    return _run(args) if args.command == "run" else _compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
