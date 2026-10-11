"""Parser for Formex 4 (Official Journal) zips from CELLAR, e.g. 32016R0679_de.fmx.zip.

Formex carries language-neutral identifiers: ARTICLE IDENTIFIER="004A" -> art-4a,
PARAG IDENTIFIER="006.001" -> par-1. Points have no identifier; their number (NO.P "a)"
in German, "(a)" in English) is normalised to pt-a, unnumbered items become pt-d1, pt-d2.
Divisions are addressed by their number only ("KAPITEL I" / "CHAPTER I" -> div-i), so
every language version yields the same addresses.

Not taken over (reported as issues): recitals, footnotes (NOTE), further files of the zip.
"""

import re
import zipfile
from collections import defaultdict
from pathlib import Path

from lxml import etree

from challenge.model import Act, Unit, normalize_space, unit_hash
from challenge.samples import relative

_CELEX = re.compile(r"^[03](\d{4})[A-Z](\d{4})")
_SKIP = {"NOTE", "LIST"}


def parse(path: Path) -> tuple[Act, list[Unit]]:
    act, units, _ = parse_with_issues(path)
    return act, units


def parse_with_issues(path: Path) -> tuple[Act, list[Unit], dict[str, list[str]]]:
    celex, _, rest = path.name.partition("_")
    language = rest.split(".")[0].lower()
    match = _CELEX.match(celex)
    if not match:
        raise SystemExit(f"Keine CELEX-Nummer im Dateinamen: {path.name}")
    with zipfile.ZipFile(path) as archive:
        names = sorted(n for n in archive.namelist() if n.endswith(".xml") and not n.endswith(".doc.xml"))
        root = _load(archive.read(names[0]))
    parser = _Parser()
    for name in names[1:]:
        parser.issues["Weitere Datei der Zip nicht verarbeitet"].append(name)
    if root.tag != "ACT":
        raise SystemExit(f"{path.name}: Wurzel <{root.tag}> wird noch nicht unterstützt (erwartet <ACT>).")
    year, number = match.groups()
    act = Act(work_id=f"eu-{year}-{int(number)}", version=_version(root), language=language, source=relative(path))
    recitals = sum(1 for _ in root.iter("CONSID"))
    if recitals:
        parser.issues["Erwägungsgründe nicht übernommen"].append(f"{recitals} Erwägungsgründe")
    for child in root.find("ENACTING.TERMS"):
        if isinstance(child.tag, str):
            parser.visit(child, None)
    notes = sum(1 for _ in root.find("ENACTING.TERMS").iter("NOTE"))
    if notes:
        parser.issues["Fußnoten (NOTE) nicht übernommen"].append(f"{notes} Fußnoten")
    return act, parser.units, dict(parser.issues)


def _load(data: bytes) -> etree._Element:
    return etree.fromstring(data, etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False))


def _version(root: etree._Element) -> str:
    """Date of adoption from the title, e.g. <DATE ISO="20160427">."""
    date = root.find("TITLE//DATE")
    if date is None or not date.get("ISO"):
        raise SystemExit("Kein Datum im Titel des Rechtsakts gefunden.")
    iso = date.get("ISO")
    return f"{iso[:4]}-{iso[4:6]}-{iso[6:8]}"


class _Parser:
    def __init__(self) -> None:
        self.units: list[Unit] = []
        self.known: set[str] = set()
        self.issues: dict[str, list[str]] = defaultdict(list)

    def visit(self, element: etree._Element, parent: Unit | None) -> None:
        if element.tag == "DIVISION":
            self.division(element, parent)
        elif element.tag == "ARTICLE":
            self.article(element, parent)
        else:
            self.issues[f"Element <{element.tag}> im verfügenden Teil übersprungen"].append(element.tag)

    def division(self, element: etree._Element, parent: Unit | None) -> None:
        label = _text(element.find("TITLE/TI"))
        number = label.split()[-1] if label else str(len(self.units))
        segment = f"div-{_slug(number)}"
        address = f"{parent.address}/{segment}" if parent else segment
        heading = _text(element.find("TITLE/STI")) or None
        unit = self.add(address, label, "division", heading, "", parent.address if parent else None, "DIVISION")
        for child in element:
            if isinstance(child.tag, str) and child.tag != "TITLE":
                self.visit(child, unit)

    def article(self, element: etree._Element, parent: Unit | None) -> None:
        identifier = element.get("IDENTIFIER", "")
        number = identifier.lstrip("0").lower() or identifier
        article = self.add(
            f"art-{number}", _text(element.find("TI.ART")), "article", _text(element.find("STI.ART")) or None,
            "", parent.address if parent else None, f"ARTICLE[@IDENTIFIER='{identifier}']",
        )
        implicit: Unit | None = None
        for child in element:
            if child.tag == "PARAG":
                paragraph_id = child.get("IDENTIFIER", "")
                key = paragraph_id.rpartition(".")[2].lstrip("0").lower()
                paragraph = self.add(
                    f"{article.address}/par-{key}", _text(child.find("NO.PARAG")), "paragraph", None, "",
                    article.address, f"PARAG[@IDENTIFIER='{paragraph_id}']",
                )
                for alinea in child.findall("ALINEA"):
                    self.alinea(alinea, paragraph)
            elif child.tag == "ALINEA":
                # Article without numbered paragraphs: like a single unnumbered Absatz.
                if implicit is None:
                    implicit = self.add(
                        f"{article.address}/par-1", "", "paragraph", None, "", article.address,
                        f"ARTICLE[@IDENTIFIER='{identifier}']/ALINEA",
                    )
                self.alinea(child, implicit)

    def alinea(self, alinea: etree._Element, paragraph: Unit) -> None:
        self.append(paragraph, _text(alinea))
        for child in alinea:
            if child.tag == "LIST":
                self.items(child, paragraph)

    def items(self, element: etree._Element, parent: Unit) -> None:
        dashes = 0
        for index, item in enumerate(element.findall("ITEM"), start=1):
            label = _text(item.find("NP/NO.P"))
            key = re.sub(r"[^0-9a-z]", "", label.lower())
            if not key:
                dashes += 1
                key, label = f"d{dashes}", label or "–"
                if dashes == 1:
                    self.issues["Liste ohne Nummern, Punkte als d1, d2 … adressiert"].append(parent.address)
            point = self.add(
                f"{parent.address}/pt-{key}", label, "point", None, "", parent.address,
                f"{parent.source_anchor}/ITEM[{index}]",
            )
            body = item.find("NP")
            blocks = [body.find("TXT"), *body.findall("P")] if body is not None else item.findall("P")
            for block in blocks:
                if block is None:
                    continue
                self.append(point, _text(block))
                for nested in block.iter("LIST"):
                    if nested.getparent() is block or nested.getparent().getparent() is block:
                        self.items(nested, point)

    def add(self, address, label, type_, heading, text, parent, anchor) -> Unit:
        if address in self.known:
            self.issues["Doppelte Adresse, mit ~N unterschieden"].append(address)
            suffix = 2
            while f"{address}~{suffix}" in self.known:
                suffix += 1
            address = f"{address}~{suffix}"
        unit = Unit(
            address=address, label=label, type=type_, heading=heading, text=text, parent=parent,
            order=len(self.units), content_hash=unit_hash(heading, text), source_anchor=anchor,
        )
        self.units.append(unit)
        self.known.add(address)
        return unit

    @staticmethod
    def append(unit: Unit, text: str) -> None:
        if text:
            unit.text = f"{unit.text}\n{text}" if unit.text else text
            unit.content_hash = unit_hash(unit.heading, unit.text)


def _text(element: etree._Element | None) -> str:
    """Running text without lists and footnotes; quotation marks restored from their codes."""
    if element is None:
        return ""
    parts = [element.text or ""]
    for child in element:
        if not isinstance(child.tag, str):  # processing instruction (<?PAGE?>) or comment
            pass
        elif child.tag in ("QUOT.START", "QUOT.END"):
            parts.append(chr(int(child.get("CODE", "22"), 16)))
        elif child.tag in _SKIP:
            pass
        else:
            parts.append(_text(child))
        parts.append(child.tail or "")
    return normalize_space("".join(parts))


def _slug(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "-", value.lower()).strip("-")
