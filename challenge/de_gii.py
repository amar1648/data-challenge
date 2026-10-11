"""Parser for German federal law XML from Gesetze im Internet (gii-norm.dtd).

Each § is one <norm> with its number in <enbez>. Absätze are <P> elements whose
number "(1)" exists only as a text prefix; a § with a single unnumbered <P>
gets par-1. Lists are <DL><DT>a)</DT><DD><LA>…</LA></DD></DL> inside a <P>.
"""

import re
from pathlib import Path

from lxml import etree

from challenge.model import Act, Unit, normalize_space, unit_hash
from challenge.samples import parse_xml, relative

# Elements whose content is not part of the running text of a unit.
_SKIP = {"DL", "FnR", "Footnote", "FnArea", "Footnotes"}
_PARAGRAPH_NO = re.compile(r"^\((\d+[a-z]*)\)\s*")
_ARTICLE_NO = re.compile(r"^(?:§|Art\.?|Artikel)\s*(\d+[a-z]*)$")
_DATE = re.compile(r"v\.\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")
# "§§ 4 bis 6" (ranges and enumerations) is deliberately not matched.
_REF = re.compile(
    r"(?<!§)§\s*(\d+[a-z]*)"
    r"(?:\s+(?:Abs\.|Absatz)\s*(\d+[a-z]*))?"
    r"(?:\s+(?:Buchst\.|Buchstabe|Nr\.|Nummer)\s*(\d+|[a-z]{1,2})\b)?"
)
# Citation belongs to another law: "des Dritten Überleitungsgesetzes", "SGB 3".
_EXTERNAL = re.compile(
    r"\b(?:des|der)\s+(?:[\w-]+\s+){0,3}[\w-]*(?:gesetz|ordnung|buch|vertrag|richtlinie)\w*"
    r"|\b[A-Z][A-Za-z]*[A-Z]\b"
)
_CLAUSE_END = re.compile(r"[;()]|\.\s+[A-ZÄÖÜ]")


def parse(path: Path, work_id: str) -> tuple[Act, list[Unit]]:
    root = parse_xml(path).getroot()
    norms = root.findall("norm")
    act = Act(
        work_id=work_id,
        version=_version(norms[0]),
        language="de",
        source=relative(path),
    )
    units: list[Unit] = []
    for norm in norms:
        enbez = _text(norm.find("metadaten/enbez"))
        if enbez:
            _parse_norm(norm, enbez, units)
    _resolve_refs(units)
    return act, units


def _version(head: etree._Element) -> str:
    """Legal state: date of the last amending act, else the date of enactment."""
    for comment in head.iterfind("metadaten/standangabe/standkommentar"):
        match = _DATE.search(_text(comment))
        if match:
            day, month, year = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
    enacted = _text(head.find("metadaten/ausfertigung-datum"))
    if not enacted:
        raise SystemExit("Kein Stand und kein Ausfertigungsdatum in der Quelle.")
    return enacted


def _parse_norm(norm: etree._Element, enbez: str, units: list[Unit]) -> None:
    doknr = norm.get("doknr")
    heading = _text(norm.find("metadaten/titel")) or None
    paragraphs = norm.findall("textdaten/text/Content/P")

    match = _ARTICLE_NO.match(enbez)
    if not match:
        # Eingangsformel and similar: one unit holding the whole text.
        text = "\n".join(_own_text(p) for p in paragraphs)
        address = "preamble" if enbez == "Eingangsformel" else _slug(enbez)
        _add(units, address, enbez, "preamble", heading, text, None, doknr)
        return

    article = f"art-{match.group(1)}"
    _add(units, article, enbez, "article", heading, "", None, doknr)

    current: Unit | None = None
    for index, p in enumerate(paragraphs, start=1):
        text = _own_text(p)
        numbered = _PARAGRAPH_NO.match(text)
        anchor = f"{doknr}:P[{index}]"
        if numbered:
            number, label = numbered.group(1), numbered.group(0).strip()
            text = text[numbered.end():]
        elif current is None:
            number, label = "1", ""  # single unnumbered Absatz
        else:
            # Unnumbered <P> after a numbered one continues that Absatz.
            current.text = f"{current.text}\n{text}".strip()
            current.content_hash = unit_hash(current.heading, current.text)
            current.source_anchor += f"+P[{index}]"
            _parse_lists(p, current.address, anchor, units)
            continue
        current = _add(units, f"{article}/par-{number}", label, "paragraph", None, text, article, anchor)
        _parse_lists(p, current.address, anchor, units)


def _parse_lists(container: etree._Element, parent: str, anchor: str, units: list[Unit]) -> None:
    lists = [child for child in container if child.tag == "DL"]
    if container.tag == "DD":
        lists = [dl for la in container.findall("LA") for dl in la.findall("DL")] + lists
    for dl_index, dl in enumerate(lists, start=1):
        for dd_index, (dt, dd) in enumerate(zip(dl.findall("DT"), dl.findall("DD")), start=1):
            label = _text(dt)
            key = re.sub(r"[^0-9A-Za-z]", "", label).lower()
            if not key:
                raise SystemExit(f"Listenpunkt ohne Nummer unter {parent}: {label!r}")
            item_anchor = f"{anchor}/DL[{dl_index}]/DD[{dd_index}]"
            text = "\n".join(_own_text(la) for la in dd.findall("LA")) or _own_text(dd)
            unit = _add(units, f"{parent}/pt-{key}", label, "point", None, text, parent, item_anchor)
            _parse_lists(dd, unit.address, item_anchor, units)


def _add(
    units: list[Unit],
    address: str,
    label: str,
    type_: str,
    heading: str | None,
    text: str,
    parent: str | None,
    anchor: str,
) -> Unit:
    if any(unit.address == address for unit in units):
        raise SystemExit(f"Adresse doppelt vergeben: {address} ({anchor})")
    unit = Unit(
        address=address,
        label=label,
        type=type_,
        heading=heading,
        text=text,
        parent=parent,
        order=len(units),
        content_hash=unit_hash(heading, text),
        source_anchor=anchor,
    )
    units.append(unit)
    return unit


def _resolve_refs(units: list[Unit]) -> None:
    """Explicit "§ N" / "§ N Abs. M" citations of this act; citations of other laws are dropped."""
    known = {unit.address for unit in units}
    for unit in units:
        refs: list[str] = []
        for match in _REF.finditer(unit.text):
            clause = _CLAUSE_END.split(unit.text[match.end():], maxsplit=1)[0]
            if _EXTERNAL.search(clause):
                continue
            article, paragraph, point = match.groups()
            candidates = [f"art-{article}"]
            if paragraph:
                candidates.append(f"{candidates[-1]}/par-{paragraph}")
            if point:
                candidates.append(f"{candidates[-1]}/pt-{point}")
            # Most specific level that exists in this act.
            address = next((c for c in reversed(candidates) if c in known), None)
            if address and address not in refs:
                refs.append(address)
        unit.refs = refs


def _own_text(element: etree._Element) -> str:
    """Text of an element without nested lists and footnotes; text after a list is kept."""
    parts = [element.text or ""]
    for child in element:
        if child.tag in _SKIP:
            pass
        elif child.tag == "BR":
            parts.append(" ")
        else:
            parts.append(_own_text(child))
        parts.append(child.tail or "")
    return normalize_space("".join(parts))


def _text(element: etree._Element | None) -> str:
    return normalize_space("".join(element.itertext())) if element is not None else ""


def _slug(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "-", value.lower()).strip("-")
