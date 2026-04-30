import hashlib

import lxml.etree as etree


def build_source_xml_fingerprint(paragraph) -> str | None:
    try:
        xml_text = etree.tostring(paragraph._element, encoding="utf-8")
    except Exception:
        return None
    return hashlib.sha1(xml_text).hexdigest()[:12]


def extract_run_element_images(
    run_element,
    part,
    *,
    relationship_namespace: str,
) -> list[tuple[bytes, str | None, int | None, int | None, dict[str, object]]]:
    images: list[tuple[bytes, str | None, int | None, int | None, dict[str, object]]] = []
    for drawing in run_element.xpath(".//w:drawing"):
        blips = drawing.xpath(".//a:blip")
        width_emu, height_emu = resolve_drawing_extent_emu(drawing)
        for blip in blips:
            embed_id = blip.get(f"{{{relationship_namespace}}}embed")
            if not embed_id:
                continue
            image_part = part.related_parts.get(embed_id)
            if image_part is None:
                continue
            images.append(
                (
                    image_part.blob,
                    getattr(image_part, "content_type", None),
                    width_emu,
                    height_emu,
                    build_drawing_forensics(drawing, embed_id=embed_id),
                )
            )
    return images


def resolve_drawing_extent_emu(drawing) -> tuple[int | None, int | None]:
    extents = drawing.xpath(".//wp:extent")
    if not extents:
        return None, None

    extent = extents[0]
    try:
        width_emu = int(extent.get("cx"))
        height_emu = int(extent.get("cy"))
    except (TypeError, ValueError):
        return None, None

    if width_emu <= 0 or height_emu <= 0:
        return None, None
    return width_emu, height_emu


def build_drawing_forensics(drawing, *, embed_id: str) -> dict[str, object]:
    doc_properties = resolve_drawing_doc_properties(drawing)
    return {
        "relationship_id": embed_id,
        "drawing_container": resolve_drawing_container_kind(drawing),
        "drawing_container_xml": resolve_drawing_container_xml(drawing),
        "source_rect": resolve_drawing_source_rect(drawing),
        "doc_properties": doc_properties,
    }


def resolve_drawing_container_kind(drawing) -> str | None:
    if drawing.xpath("./wp:inline"):
        return "inline"
    if drawing.xpath("./wp:anchor"):
        return "anchor"
    return None


def resolve_drawing_container_xml(drawing) -> str | None:
    containers = drawing.xpath("./wp:inline | ./wp:anchor")
    if not containers:
        return None
    return etree.tostring(containers[0], encoding="unicode")


def resolve_drawing_source_rect(drawing) -> dict[str, int] | None:
    source_rects = drawing.xpath(".//a:srcRect")
    if not source_rects:
        return None
    source_rect = source_rects[0]
    resolved: dict[str, int] = {}
    for key in ("l", "t", "r", "b"):
        raw_value = source_rect.get(key)
        if raw_value is None:
            continue
        try:
            resolved[key] = int(raw_value)
        except (TypeError, ValueError):
            continue
    return resolved or None


def resolve_drawing_doc_properties(drawing) -> dict[str, object] | None:
    properties = drawing.xpath(".//wp:docPr")
    if not properties:
        return None
    doc_pr = properties[0]
    payload = {
        "id": doc_pr.get("id"),
        "name": doc_pr.get("name"),
        "descr": doc_pr.get("descr"),
        "title": doc_pr.get("title"),
    }
    return {key: value for key, value in payload.items() if value not in {None, ""}}


def resolve_paragraph_num_pr(
    paragraph,
    *,
    find_child_element,
):
    paragraph_properties = find_child_element(paragraph._element, "pPr")
    num_pr = find_child_element(paragraph_properties, "numPr")
    if num_pr is not None:
        return num_pr

    style = getattr(paragraph, "style", None)
    while style is not None:
        style_properties = find_child_element(getattr(style, "_element", None), "pPr")
        num_pr = find_child_element(style_properties, "numPr")
        if num_pr is not None:
            return num_pr
        style = getattr(style, "base_style", None)
    return None


def extract_num_pr_level(
    num_pr,
    *,
    find_child_element,
    get_xml_attribute,
) -> int:
    ilvl = find_child_element(num_pr, "ilvl")
    level_value = get_xml_attribute(ilvl, "val") if ilvl is not None else None
    if level_value is None:
        return 0
    try:
        return max(0, int(level_value))
    except (TypeError, ValueError):
        return 0


def resolve_num_pr_details(
    paragraph,
    num_pr,
    *,
    xml_local_name,
    find_child_element,
    get_xml_attribute,
) -> dict[str, str | None]:
    num_id_element = find_child_element(num_pr, "numId")
    ilvl_element = find_child_element(num_pr, "ilvl")
    num_id = get_xml_attribute(num_id_element, "val") if num_id_element is not None else None
    ilvl = get_xml_attribute(ilvl_element, "val") if ilvl_element is not None else "0"
    if num_id is None:
        return {
            "num_id": None,
            "abstract_num_id": None,
            "num_format": None,
            "num_xml": None,
            "abstract_num_xml": None,
        }

    numbering_part = getattr(paragraph.part, "numbering_part", None)
    numbering_root = getattr(numbering_part, "element", None)
    if numbering_root is None:
        return {
            "num_id": num_id,
            "abstract_num_id": None,
            "num_format": None,
            "num_xml": None,
            "abstract_num_xml": None,
        }

    abstract_num_id = None
    num_xml = None
    for child in numbering_root:
        if xml_local_name(child.tag) != "num":
            continue
        if get_xml_attribute(child, "numId") != num_id:
            continue
        abstract_num = find_child_element(child, "abstractNumId")
        abstract_num_id = get_xml_attribute(abstract_num, "val") if abstract_num is not None else None
        num_xml = etree.tostring(child, encoding="unicode")
        break

    if abstract_num_id is None:
        return {
            "num_id": num_id,
            "abstract_num_id": None,
            "num_format": None,
            "num_xml": num_xml,
            "abstract_num_xml": None,
        }

    for child in numbering_root:
        if xml_local_name(child.tag) != "abstractNum":
            continue
        if get_xml_attribute(child, "abstractNumId") != abstract_num_id:
            continue
        abstract_num_xml = etree.tostring(child, encoding="unicode")
        for level in child:
            if xml_local_name(level.tag) != "lvl":
                continue
            if get_xml_attribute(level, "ilvl") != ilvl:
                continue
            num_format = find_child_element(level, "numFmt")
            lvl_text = find_child_element(level, "lvlText")
            return {
                "num_id": num_id,
                "abstract_num_id": abstract_num_id,
                "num_format": get_xml_attribute(num_format, "val") if num_format is not None else None,
                "lvl_text": get_xml_attribute(lvl_text, "val") if lvl_text is not None else None,
                "num_xml": num_xml,
                "abstract_num_xml": abstract_num_xml,
            }
        return {
            "num_id": num_id,
            "abstract_num_id": abstract_num_id,
            "num_format": None,
            "num_xml": num_xml,
            "abstract_num_xml": abstract_num_xml,
        }
    return {
        "num_id": num_id,
        "abstract_num_id": abstract_num_id,
        "num_format": None,
        "num_xml": num_xml,
        "abstract_num_xml": None,
    }
