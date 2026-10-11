"""Parser for EUR-Lex HTML, both the Official Journal rendering (oj-* classes)
and the consolidated rendering (norm / no-parag / grid-list classes).

Addresses come from the article number and the normalised paragraph and point
numbers, never from HTML ids: the OJ variant reuses ids such as "001.003" for
quoted text of other acts (Art. 8 of 2015/2120).

The consolidated variant marks amendments with block markers
(<p class="modref"><a title="32018R1971: INSERTED">▼M2</a></p>, valid until the
next marker) and inline pairs (►M3 … ◄). Units whose own content lies under a
non-base marker get tags["amended_by"]. DELETED markers have no unit to attach
to; parse_with_deletions() returns them with the address they follow.
"""

import re
import warnings
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning

from challenge.model import Act, Unit, normalize_space, unit_hash
from challenge.samples import relative

_ARTICLE_ID = re.compile(r"^art_\w+$")
_ARTICLE_NO = re.compile(r"^Artikel\s*(\d+[a-z]*)$")
_PARAGRAPH_NO = re.compile(r"^\((\d+[a-z]*)\)\s*")
_CELEX = re.compile(r"^[03](\d{4})[A-Z](\d{4})")
_MARKER_TITLE = re.compile(r"^(\w+)(?::\s*(\w+))?$")
_INLINE_GLYPHS = re.compile(r"►\s*M\d+|◄")
_MONTHS = {
    name: number
    for number, name in enumerate(
        "Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split(),
        start=1,
    )
}


@dataclass(frozen=True)
class Marker:
    act: str  # CELEX of the amending act, or of the act itself for the base text
    marker: str  # "B", "M1", "M2", ...
    action: str | None  # INSERTED | REPLACED | DELETED; None for the base text

    @property
    def is_base(self) -> bool:
        return self.action is None

    def as_tag(self) -> dict:
        return {"act": self.act, "marker": self.marker, "action": self.action}


def parse(path: Path) -> tuple[Act, list[Unit]]:
    act, units, _ = parse_with_deletions(path)
    return act, units


def parse_with_deletions(path: Path) -> tuple[Act, list[Unit], list[tuple[str | None, Marker]]]:
    soup = _load(path)
    walker = _Walker()
    walker.walk(soup.body)
    return _act(path, soup), walker.units, walker.deletions


def _load(path: Path) -> BeautifulSoup:
    if not path.is_file():
        raise SystemExit(f"Datei fehlt: {path}")
    # The OJ file starts with an XML declaration but is not well-formed XML.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        return BeautifulSoup(path.read_text(encoding="utf-8"), features="lxml")


def _act(path: Path, soup: BeautifulSoup) -> Act:
    celex, _, language = path.name.removesuffix(".html").rpartition("_")
    match = _CELEX.match(celex)
    if not match:
        raise SystemExit(f"Keine CELEX-Nummer im Dateinamen: {path.name}")
    year, number = match.groups()
    return Act(
        work_id=f"eu-{year}-{int(number)}",
        version=_version(celex, soup),
        language=language.lower(),
        source=relative(path),
    )


def _version(celex: str, soup: BeautifulSoup) -> str:
    """Consolidated: date suffix of the CELEX. Official Journal: date of adoption from the title."""
    consolidated = re.search(r"-(\d{4})(\d{2})(\d{2})$", celex)
    if consolidated:
        return "-".join(consolidated.groups())
    for title in soup.select("p.oj-doc-ti"):
        match = re.match(r"vom (\d{1,2})\. (\w+) (\d{4})", normalize_space(title.get_text()))
        if match and match.group(2) in _MONTHS:
            day, month, year = match.groups()
            return f"{year}-{_MONTHS[month]:02d}-{int(day):02d}"
    raise SystemExit("Kein Datum im Titel der Amtsblatt-Fassung gefunden.")


class _Walker:
    """Single pass in document order; block markers are state that persists across articles."""

    def __init__(self) -> None:
        self.units: list[Unit] = []
        self.deletions: list[tuple[str | None, Marker]] = []
        self.marker: Marker | None = None
        self.article: Unit | None = None
        self.article_id = ""
        self.paragraph: Unit | None = None
        self.paragraph_count = 0

    def walk(self, element: Tag) -> None:
        for child in element.children:
            if isinstance(child, Tag):
                self._visit(child)

    def _visit(self, element: Tag) -> None:
        classes = element.get("class") or []
        if "modref" in classes:
            self._set_marker(element)
        elif element.name == "div" and _ARTICLE_ID.match(element.get("id", "")):
            self._article(element)
        elif self.article is None:
            self.walk(element)  # outside articles only markers matter
        elif "eli-title" in classes or "oj-ti-art" in classes or "title-article-norm" in classes:
            pass  # read in _article
        elif element.name == "div" and element.find("span", class_="no-parag", recursive=False):
            number = element.find("span", class_="no-parag", recursive=False)
            self._start_paragraph(normalize_space(number.get_text()), "")
            for child in element.children:
                if isinstance(child, Tag) and child is not number:
                    self._flow(child, self.paragraph, self.paragraph)
        else:
            self._flow(element, None, None)

    def _set_marker(self, element: Tag) -> None:
        link = element.find("a")
        match = _MARKER_TITLE.match(link.get("title", "")) if link else None
        if not match:
            return
        self.marker = Marker(
            act=match.group(1), marker=link.get_text(strip=True).lstrip("▼"), action=match.group(2)
        )
        if self.marker.action == "DELETED":
            self.deletions.append((self.units[-1].address if self.units else None, self.marker))

    def _article(self, element: Tag) -> None:
        title = element.find("p", class_=["oj-ti-art", "title-article-norm"])
        match = _ARTICLE_NO.match(normalize_space(title.get_text())) if title else None
        if not match:
            raise SystemExit(f"Artikelnummer nicht erkannt in #{element.get('id')}")
        heading_box = element.find("div", class_="eli-title")
        heading = normalize_space(heading_box.get_text()) if heading_box else None
        self.article_id = element["id"]
        self.article = self._add(
            f"art-{match.group(1)}", normalize_space(title.get_text()), "article", heading, None,
            f"#{self.article_id}",
        )
        self.paragraph = None
        self.paragraph_count = 0
        self.walk(element)
        self.article = None

    def _flow(self, element: Tag, target: Unit | None, point_parent: Unit | None) -> None:
        """Running content. target receives text (None: current or new paragraph);
        point_parent receives list items (None: the paragraph)."""
        classes = element.get("class") or []
        if "modref" in classes:
            self._set_marker(element)
        elif element.name == "table":
            for row in element.find_all("tr"):
                cells = row.find_all("td", recursive=False)
                if len(cells) == 2:
                    self._point(cells[0], cells[1], point_parent)
        elif "grid-container" in classes:
            label = element.find("div", class_="grid-list-column-1")
            content = element.find("div", class_="grid-list-column-2")
            self._point(label, content, point_parent)
        elif element.name in ("p", "div") and not element.find(["p", "div", "table"]):
            self._text(element, target)
        elif element.name in ("div", "tbody"):
            for child in element.children:
                if isinstance(child, Tag):
                    self._flow(child, target, point_parent)

    def _text(self, element: Tag, target: Unit | None) -> None:
        inline = [
            link for link in element.find_all("a", title=True) if "►" in link.get_text()
        ]
        text = _clean_text(element)
        if not text:
            return
        if target is None:
            numbered = _PARAGRAPH_NO.match(text)
            if numbered:
                self._start_paragraph(numbered.group(0).strip(), text[numbered.end():])
                target = self.paragraph
            else:
                target = self.paragraph or self._start_paragraph("", "")
                self._append(target, text)
        else:
            self._append(target, text)
        for link in inline:
            match = _MARKER_TITLE.match(link["title"])
            marker = link.get_text(strip=True).lstrip("►").strip()
            _tag_amendment(target, Marker(match.group(1), marker, match.group(2)))

    def _start_paragraph(self, label: str, text: str) -> Unit:
        number = _PARAGRAPH_NO.match(label + " ")
        self.paragraph_count += 1
        key = number.group(1) if number else "1"
        self.paragraph = self._add(
            f"{self.article.address}/par-{key}", label, "paragraph", None, self.article.address,
            f"#{self.article_id}/par[{self.paragraph_count}]",
        )
        if text:
            self._append(self.paragraph, text)
        return self.paragraph

    def _point(self, label_box: Tag, content: Tag, parent: Unit | None) -> None:
        parent = parent or self.paragraph or self._start_paragraph("", "")
        label = normalize_space(label_box.get_text())
        key = re.sub(r"[^0-9a-z]", "", label.lower())
        if not key:
            raise SystemExit(f"Listenpunkt ohne Nummer unter {parent.address}: {label!r}")
        siblings = sum(1 for unit in self.units if unit.parent == parent.address and unit.type == "point")
        point = self._add(
            f"{parent.address}/pt-{key}", label, "point", None, parent.address,
            f"{parent.source_anchor}/pt[{siblings + 1}]",
        )
        for child in content.children:
            if isinstance(child, Tag):
                self._flow(child, point, point)
            elif isinstance(child, NavigableString) and child.strip():
                self._append(point, normalize_space(child))

    def _add(self, address, label, type_, heading, parent, anchor) -> Unit:
        if any(unit.address == address for unit in self.units):
            raise SystemExit(f"Adresse doppelt vergeben: {address} ({anchor})")
        unit = Unit(
            address=address, label=label, type=type_, heading=heading, text="", parent=parent,
            order=len(self.units), content_hash=unit_hash(heading, ""), source_anchor=anchor,
        )
        self.units.append(unit)
        if type_ == "article":
            self._tag_current_marker(unit)
        return unit

    def _append(self, unit: Unit, text: str) -> None:
        unit.text = f"{unit.text}\n{text}" if unit.text else text
        unit.content_hash = unit_hash(unit.heading, unit.text)
        self._tag_current_marker(unit)

    def _tag_current_marker(self, unit: Unit) -> None:
        if self.marker and not self.marker.is_base:
            _tag_amendment(unit, self.marker)


def _tag_amendment(unit: Unit, marker: Marker) -> None:
    tags = unit.tags.setdefault("amended_by", [])
    if marker.as_tag() not in tags:
        tags.append(marker.as_tag())


def _clean_text(element: Tag) -> str:
    """Visible text without footnote references and amendment glyphs."""
    parts = []
    for node in element.descendants:
        if isinstance(node, NavigableString) and not any(
            parent.name == "a" and parent.get("href", "").startswith("#")
            for parent in node.parents
            if parent is not element
        ):
            parts.append(str(node))
    text = _INLINE_GLYPHS.sub(" ", "".join(parts))
    text = re.sub(r"\(\s*\)", "", text)  # parentheses left over from footnote references
    text = normalize_space(text)
    return re.sub(r"\s+([.,;:])", r"\1", text)
