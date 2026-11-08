import hashlib

import lxml.etree as etree


def build_source_xml_fingerprint(paragraph) -> str | None:
    try:
        xml_text = etree.tostring(paragraph._element, encoding="utf-8")
    except Exception:
        return None
    return hashlib.sha1(xml_text).hexdigest()[:12]


# Spec 067 FR-002: the one paragraph property that carries "this paragraph is a table cell"
# across the PDF->DOCX bridge. `w:cnfStyle` is OOXML's table conditional-formatting marker
# of a paragraph; twelve zero bits name a body cell (no first-row, banded or corner format).
# The writer and the reader live side by side so the contract has one home.
_TABLE_CELL_CNF_STYLE_VALUE = "000000000000"


def set_paragraph_pdf_table_cell_signal(paragraph) -> None:
    """Mark a python-docx paragraph as a table cell (``w:pPr/w:cnfStyle``)."""

    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    paragraph_properties = paragraph._element.get_or_add_pPr()
    if paragraph_properties.find(qn("w:cnfStyle")) is not None:
        return
    cnf_style = OxmlElement("w:cnfStyle")
    cnf_style.set(qn("w:val"), _TABLE_CELL_CNF_STYLE_VALUE)
    paragraph_properties.insert_element_before(cnf_style, "w:rPr", "w:sectPr", "w:pPrChange")


def paragraph_has_pdf_table_cell_signal(paragraph) -> bool:
    """Does the paragraph's OWN ``w:pPr`` carry the ``w:cnfStyle`` the bridge writes, with the
    bridge's exact value?

    The property alone is not provenance: Word writes ``w:cnfStyle`` for conditional table
    formatting, and a native DOCX may carry one with any value (Codex acceptance review of
    spec 067, P1). Callers therefore honour it only in a document the bridge marked
    (``document_is_pdf_bridge_output``); this predicate is the per-paragraph half."""

    element = getattr(paragraph, "_element", None)
    if element is None:
        return False
    for child in element:
        if _local_tag_name(child) != "pPr":
            continue
        return any(
            _local_tag_name(grandchild) == "cnfStyle" and _xml_attribute(grandchild, "val") == _TABLE_CELL_CNF_STYLE_VALUE
            for grandchild in child
        )
    return False


# Spec 067 FR-002 (Codex P1): the document-level provenance of the cell signal. The PDF bridge
# names its intermediate DOCX with a document variable (`w:settings/w:docVars/w:docVar`) --
# OOXML's place for an application's own named values, invisible in the text and in the
# document properties a user edits. Nothing else in the repository stamped the intermediate
# DOCX; the bridge's backend name (`conversion_backend = "pdf-text-layer"`) lives in the
# normalized-document contract and never reaches `extraction.py`, which reads DOCX bytes only.
_PDF_BRIDGE_DOC_VAR_NAME = "DocxAICorrectorPdfTextLayerBridge"
_PDF_BRIDGE_DOC_VAR_VALUE = "1"


def mark_document_as_pdf_bridge_output(document) -> None:
    """Stamp a python-docx document as the PDF text-layer bridge's intermediate DOCX."""

    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    settings = document.settings.element
    doc_vars = settings.find(qn("w:docVars"))
    if doc_vars is None:
        doc_vars = OxmlElement("w:docVars")
        settings.insert_element_before(doc_vars, *_SETTINGS_SUCCESSORS_OF_DOC_VARS)
    for doc_var in doc_vars.findall(qn("w:docVar")):
        if doc_var.get(qn("w:name")) == _PDF_BRIDGE_DOC_VAR_NAME:
            doc_var.set(qn("w:val"), _PDF_BRIDGE_DOC_VAR_VALUE)
            return
    doc_var = OxmlElement("w:docVar")
    doc_var.set(qn("w:name"), _PDF_BRIDGE_DOC_VAR_NAME)
    doc_var.set(qn("w:val"), _PDF_BRIDGE_DOC_VAR_VALUE)
    doc_vars.append(doc_var)


def document_is_pdf_bridge_output(document) -> bool:
    """Did the PDF text-layer bridge write this document (``mark_document_as_pdf_bridge_output``)?"""

    try:
        settings = document.settings.element
    except Exception:
        return False
    for child in settings:
        if _local_tag_name(child) != "docVars":
            continue
        return any(
            _local_tag_name(doc_var) == "docVar"
            and _xml_attribute(doc_var, "name") == _PDF_BRIDGE_DOC_VAR_NAME
            and _xml_attribute(doc_var, "val") == _PDF_BRIDGE_DOC_VAR_VALUE
            for doc_var in child
        )
    return False


# `w:settings` children after `w:docVars` in the schema order (CT_Settings).
_SETTINGS_SUCCESSORS_OF_DOC_VARS = (
    "w:rsids",
    "m:mathPr",
    "w:attachedSchema",
    "w:themeFontLang",
    "w:clrSchemeMapping",
    "w:doNotIncludeSubdocsInStats",
    "w:doNotAutoCompressPictures",
    "w:forceUpgrade",
    "w:captions",
    "w:readModeInkLockDown",
    "w:smartTagType",
    "sl:schemaLibrary",
    "w:shapeDefaults",
    "w:doNotEmbedSmartTags",
    "w:decimalSymbol",
    "w:listSeparator",
)


def _xml_attribute(element, local_name: str) -> str | None:
    for key, value in element.attrib.items():
        if str(key).rsplit("}", 1)[-1] == local_name:
            return str(value)
    return None


def _local_tag_name(element) -> str:
    tag = getattr(element, "tag", None)
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


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
