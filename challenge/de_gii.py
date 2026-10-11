"""Parser for German federal law XML from Gesetze im Internet (gii-norm.dtd).

Each § is one <norm> with its number in <enbez>. Absätze are <P> elements whose
number "(1)" exists only as a text prefix; a § with a single unnumbered <P>
gets par-1. Lists are <DL><DT>a)</DT><DD><LA>…</LA></DD></DL> inside a <P>.

Outline units (<gliederungseinheit>) become "division" units. They are the
structural parent of the §§ below them but not part of their address: "§ 3"
is cited without its Abschnitt and stays addressable if the outline changes.

When an Absatz holds several lists, each list belongs to a sentence and is
cited as "Satz 2 Nummer 1"; its points get a sen-N segment (art-1/par-1/sen-2/pt-1).

Everything the parser skips or flattens is collected as an issue, so prepare
can report it per act.
"""

import re
from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

from challenge.model import Act, Unit, normalize_space, unit_hash
from challenge.samples import parse_xml, relative

# Elements whose content is not part of the running text of a unit.
_SKIP = {"DL", "FnR", "Footnote", "FnArea", "Footnotes", "noindex", "TOC"}
_PARAGRAPH_NO = re.compile(r"^\((\d+[a-z]*)\)\s*")
_ARTICLE_NO = re.compile(r"^(?:§|Art\.?|Artikel)\s*(\d+[a-z]*)$")
_ANNEX = re.compile(r"^(?:Anlage|Anhang)\b\s*(.*)$")
_SPECIAL = {"Eingangsformel": "formula", "Präambel": "preamble", "Schlussformel": "closing"}
_DATE = re.compile(r"v\.\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
_NOT_A_SENTENCE_END = re.compile(
    r"(?:\b(?:Abs|Nr|Art|Buchst|bzw|vgl|ca|S|Bek|BGBl|ff|Satz|Anh|Anl|z\. B|u\. a|d\. h)|\d)\.$"
)
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
    act, units, _ = parse_with_issues(path, work_id)
    return act, units


def parse_with_issues(path: Path, work_id: str) -> tuple[Act, list[Unit], dict[str, list[str]]]:
    """Act, units and issues: category -> examples of what was skipped or flattened."""
    root = parse_xml(path).getroot()
    norms = root.findall("norm")
    parser = _Parser()
    act = Act(work_id=work_id, version=parser.version(norms[0]), language="de", source=relative(path))
    for norm in norms[1:]:
        parser.norm(norm)
    _resolve_refs(parser.units)
    return act, parser.units, dict(parser.issues)


class _Parser:
    def __init__(self) -> None:
        self.units: list[Unit] = []
        self.issues: dict[str, list[str]] = defaultdict(list)
        self.known: set[str] = set()
        self.divisions: list[tuple[str, Unit]] = []  # (gliederungskennzahl, unit), outermost first

    def version(self, head: etree._Element) -> str:
        """Legal state: the "Stand" annotation, else the re-promulgation, else enactment."""
        dates = {}
        for annotation in head.iter("standangabe"):
            kind = _text(annotation.find("standtyp"))
            comment = _text(annotation.find("standkommentar"))
            match = _DATE.search(comment)
            if kind == "Hinweis":
                self.issues["Änderung textlich nachgewiesen, dokumentarisch noch offen"].append(comment[:80])
            if match and kind in ("Stand", "Neuf") and kind not in dates:
                day, month, year = match.groups()
                dates[kind] = f"{year}-{int(month):02d}-{int(day):02d}"
        version = dates.get("Stand") or dates.get("Neuf")
        if not version:
            version = _text(head.find("metadaten/ausfertigung-datum"))
            self.issues["Kein Stand im Kopf, Version = Ausfertigungsdatum"].append(version)
        if not version:
            raise SystemExit("Kein Stand und kein Ausfertigungsdatum in der Quelle.")
        return version

    def norm(self, norm: etree._Element) -> None:
        doknr = norm.get("doknr")
        outline = norm.find("metadaten/gliederungseinheit")
        enbez = _text(norm.find("metadaten/enbez"))
        heading = _text(norm.find("metadaten/titel")) or None
        content = norm.find("textdaten/text/Content")
        name = enbez or _text(norm.find("metadaten/gliederungseinheit/gliederungsbez")) or doknr
        footnotes = sum(1 for _ in norm.iter("Footnote"))
        if footnotes:
            self.issues["Fußnoten nicht übernommen"].extend([name] * footnotes)
        notes = norm.find("textdaten/fussnoten")
        if notes is not None and _text(notes):
            self.issues["Fußnotenblock der Norm (Text- und Änderungsnachweise) nicht übernommen"].append(name)
        if outline is not None:
            self.division(outline, doknr)
        elif not enbez:
            self.issues["Norm ohne Bezeichnung übersprungen"].append(doknr)
        elif enbez == "Inhaltsübersicht":
            self.issues["Inhaltsübersicht übersprungen (doppelt zur Gliederung)"].append(enbez)
        elif enbez.startswith("(XXXX)"):
            self.issues["Weggefallene Sammelbezeichnung übersprungen"].append(enbez.removeprefix("(XXXX)").strip())
        elif _ARTICLE_NO.match(enbez):
            self.article(_ARTICLE_NO.match(enbez).group(1), enbez, heading, content, doknr)
        elif enbez in _SPECIAL:
            text = _block_text(content) if content is not None else ""
            self.add(_SPECIAL[enbez], enbez, "preamble", heading, text, None, doknr)
        elif _ANNEX.match(enbez):
            suffix = _slug(_ANNEX.match(enbez).group(1))
            text = _block_text(content) if content is not None else ""
            self.add(f"anx-{suffix}" if suffix else "anx", enbez, "annex", heading, text, self.parent(), doknr)
            self.issues["Anlage als ein Textblock übernommen (ohne Untergliederung)"].append(enbez)
        else:
            self.issues["Unbekannte Bezeichnung als Textblock übernommen"].append(enbez)
            text = _block_text(content) if content is not None else ""
            self.add(_slug(enbez), enbez, "preamble", heading, text, self.parent(), doknr)

    def division(self, outline: etree._Element, doknr: str) -> None:
        code = _text(outline.find("gliederungskennzahl"))
        label = _text(outline.find("gliederungsbez"))
        # Codes nest by prefix (010 > 010010); equal codes occur (BImSchG) and are siblings.
        while self.divisions and not (code.startswith(self.divisions[-1][0]) and code != self.divisions[-1][0]):
            self.divisions.pop()
        parent = self.divisions[-1][1] if self.divisions else None
        segment = f"div-{_slug(label) or code}"
        address = f"{parent.address}/{segment}" if parent else segment
        heading = _text(outline.find("gliederungstitel")) or None
        unit = self.add(address, label, "division", heading, "", parent.address if parent else None, doknr)
        self.divisions.append((code, unit))

    def parent(self) -> str | None:
        return self.divisions[-1][1].address if self.divisions else None

    def article(self, number: str, enbez: str, heading, content, doknr: str) -> None:
        article = self.add(f"art-{number}", enbez, "article", heading, "", self.parent(), doknr)
        if content is None or not any(_own_text(p) for p in content.findall("P")):
            if heading and "weggefallen" in heading:
                self.issues["Weggefallene Vorschrift ohne Text"].append(enbez)
            elif content is not None and content.find(".//table") is None:
                self.issues["Vorschrift ohne Text"].append(enbez)
        if content is None:
            return
        current: Unit | None = None
        for index, child in enumerate(content, start=1):
            anchor = f"{doknr}:{child.tag}[{index}]"
            if child.tag == "P":
                if child.find(".//table") is not None:
                    self.issues["Tabelle im Absatz als Text übernommen"].append(enbez)
                text = _own_text(child)
                if not text and child.find(".//DL") is None:
                    if child.find(".//FnR") is not None:
                        self.issues["Absatz nur mit Fußnotenverweis übersprungen"].append(enbez)
                    continue
                numbered = _PARAGRAPH_NO.match(text)
                if numbered:
                    current = self.add(
                        f"{article.address}/par-{numbered.group(1)}", numbered.group(0).strip(), "paragraph",
                        None, "", article.address, anchor,
                    )
                elif current is None:
                    current = self.add(f"{article.address}/par-1", "", "paragraph", None, "", article.address, anchor)
                else:
                    # Unnumbered <P> after a numbered one continues that Absatz.
                    current.source_anchor += f"+{child.tag}[{index}]"
                self.fill(child, current, anchor, strip_number=bool(numbered))
            elif child.tag in ("table", "Title"):
                text = _block_text(child)
                if current is None:
                    current = self.add(f"{article.address}/par-1", "", "paragraph", None, text, article.address, anchor)
                else:
                    self.append(current, text, f"+{child.tag}[{index}]")
                kind = "Tabelle" if child.tag == "table" else "Zwischenüberschrift"
                self.issues[f"{kind} im Normtext als Text übernommen"].append(enbez)
            elif child.tag not in ("BR", "TOC"):
                self.issues[f"Unbekanntes Element <{child.tag}> übersprungen"].append(enbez)

    def fill(self, container: etree._Element, unit: Unit, anchor: str, strip_number: bool = False) -> None:
        """Text and lists of a <P> or <DD>. Text before, between and after lists stays separate."""
        flow = _flow(container)
        if any(kind == "block" for kind, _ in flow):
            self.issues["Listenpunkt ohne Bezeichnung als Text übernommen"].append(unit.address)
        lists = [item for kind, item in flow if kind == "dl"]
        # Several <DL> with distinct numbers are one list split up (BDSG § 33 Abs. 1: "1." | "2.");
        # only when numbers repeat does each list belong to its own sentence.
        keys = [_key(_text(dt)) for dl in lists for dt in dl.findall("DT") if _key(_text(dt))]
        if len(keys) == len(set(keys)):
            for index, segment in enumerate(_segments(flow)):
                self.append(unit, _PARAGRAPH_NO.sub("", segment, count=1) if strip_number and index == 0 else segment, "")
            for dl_index, dl in enumerate(lists, start=1):
                self.items(dl, unit, unit.address, f"{anchor}/DL[{dl_index}]")
            return

        # Each list-carrying sentence becomes its own unit with its own lead-in (LkSG § 1 Abs. 1:
        # "Satz 1 Nummer 1", "Satz 2 Nummer 1"); sentences without a list stay with the Absatz.
        chunks, sentence_of = _sentence_layout(flow)
        if strip_number and chunks:
            chunks[0] = (chunks[0][0], _PARAGRAPH_NO.sub("", chunks[0][1], count=1))
        with_lists = sorted(set(sentence_of.values()))
        self.append(unit, " ".join(text for number, text in chunks if number not in with_lists), "")
        sentences: dict[int, Unit] = {}
        per_sentence = Counter(sentence_of.values())
        for dl_index, dl in enumerate(lists, start=1):
            number = sentence_of[dl]
            if number not in sentences:  # created just before its list, so document order holds
                sentences[number] = self.add(
                    f"{unit.address}/sen-{number}", f"Satz {number}", "sentence", None,
                    "\n".join(text for n, text in chunks if n == number), unit.address, f"{anchor}/S[{number}]",
                )
            target = sentences[number]
            prefix = target.address
            if per_sentence[number] > 1:
                prefix += f"/lst-{dl_index}"
                self.issues["Mehrere Listen in einem Satz, nach Listenposition adressiert"].append(unit.address)
            self.items(dl, target, prefix, f"{anchor}/DL[{dl_index}]")

    def items(self, dl: etree._Element, parent: Unit, prefix: str, anchor: str) -> None:
        dashes = 0
        for dd_index, (dt, dd) in enumerate(zip(dl.findall("DT"), dl.findall("DD")), start=1):
            label = _text(dt)
            key = _key(label)
            item_anchor = f"{anchor}/DD[{dd_index}]"
            if not label:
                # Unlabelled item inside a labelled list: keep its text with the parent.
                self.append(parent, _own_text(dd), "")
                self.issues["Listenpunkt ohne Bezeichnung als Text übernommen"].append(parent.address)
                continue
            if not key:
                dashes += 1
                key = f"d{dashes}"
                if dashes == 1:
                    self.issues["Spiegelstrichliste, Punkte als d1, d2 … adressiert"].append(parent.address)
            point = self.add(f"{prefix}/pt-{key}", label, "point", None, "", parent.address, item_anchor)
            self.fill(dd, point, item_anchor)

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

    def append(self, unit: Unit, text: str, anchor_suffix: str) -> None:
        if not text:
            return
        unit.text = f"{unit.text}\n{text}".strip()
        unit.content_hash = unit_hash(unit.heading, unit.text)
        unit.source_anchor += anchor_suffix


def _key(label: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", label).lower()


def _flow(container: etree._Element) -> list[tuple[str, object]]:
    """Content of a <P> or <DD> in order: ("text", str), ("break", None), ("block", str), ("dl", element).

    A <DL> without any item label is an indented block (the oath in Art. 56 GG) and stays in the
    text flow where it stands.
    """
    flow: list[tuple[str, object]] = []

    def walk(element: etree._Element) -> None:
        flow.append(("text", element.text or ""))
        for child in element:
            if child.tag == "DL":
                if any(_text(dt) for dt in child.findall("DT")):
                    flow.append(("dl", child))
                else:
                    flow.append(("block", " ".join(_own_text(dd) for dd in child.findall("DD"))))
            elif child.tag == "table":
                flow.append(("text", f" {_table_text(child)} "))
            elif child.tag == "BR":
                flow.append(("text", " "))
            elif child.tag == "LA":
                walk(child)
                flow.append(("break", None))
            elif child.tag not in _SKIP:
                walk(child)
            flow.append(("text", child.tail or ""))

    walk(container)
    return flow


def _segments(flow: list[tuple[str, object]]) -> list[str]:
    """Text between the lists; blocks and <LA> boundaries become line breaks."""
    segments: list[list[str]] = [[""]]
    for kind, item in flow:
        if kind == "dl":
            segments.append([""])
        elif kind == "text":
            segments[-1][-1] += item
        elif kind == "break":
            segments[-1].append("")
        elif kind == "block":
            segments[-1].extend([item, ""])
    return ["\n".join(line for line in map(normalize_space, segment) if line) for segment in segments]


def _sentence_layout(flow: list[tuple[str, object]]) -> tuple[list[tuple[int, str]], dict]:
    """Text chunks with their sentence number, and the sentence each list starts in."""
    chunks: list[tuple[int, str]] = []
    sentence_of: dict = {}
    seen = ""
    new_chunk = True

    def add(number: int, text: str) -> None:
        nonlocal new_chunk
        if chunks and chunks[-1][0] == number and not new_chunk:
            chunks[-1] = (number, chunks[-1][1] + text)
        else:
            chunks.append((number, text))
        new_chunk = False

    for kind, item in flow:
        if kind == "dl":
            sentence_of[item] = 1 + _count_sentences(seen)
            seen += " " + " ".join(item.itertext()) + " "
            new_chunk = True
            continue
        text = item if kind == "text" else f" {item or ''} "
        start = 0
        for match in _SENTENCE_END.finditer(text):
            if _NOT_A_SENTENCE_END.search(normalize_space(seen + text[: match.end()])):
                continue
            add(1 + _count_sentences(seen + text[:start]), text[start : match.end()])
            start = match.end()
        add(1 + _count_sentences(seen + text[:start]), text[start:])
        seen += text
    return [(number, normalize_space(text)) for number, text in chunks if normalize_space(text)], sentence_of


def _count_sentences(text: str) -> int:
    text = normalize_space(text)
    return sum(
        1 for match in _SENTENCE_END.finditer(text) if not _NOT_A_SENTENCE_END.search(text[: match.end()])
    )


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
    """Text of an element without nested lists, footnotes and editorial notes; tables inline."""
    parts = [element.text or ""]
    for child in element:
        if child.tag == "table":
            parts.append(f" {_table_text(child)} ")
        elif child.tag in _SKIP:
            pass
        elif child.tag == "BR":
            parts.append(" ")
        else:
            parts.append(_own_text(child))
        parts.append(child.tail or "")
    return normalize_space("".join(parts))


def _block_text(element: etree._Element) -> str:
    """Whole text of an annex or preamble, lists included, one line per block."""
    if element.tag == "table":
        return _table_text(element)
    lines = []
    for child in element:
        if child.tag == "DL":
            for dt, dd in zip(child.findall("DT"), child.findall("DD")):
                lines.append(normalize_space(f"{_text(dt)} {_block_text(dd) or _own_text(dd)}"))
        elif child.tag == "table":
            lines.append(_table_text(child))
        elif child.tag in ("P", "LA", "Title", "DD"):
            nested = child.find(".//DL") is not None or child.find(".//table") is not None
            lines.append(_block_text(child) if nested else _own_text(child))
        elif child.tag not in _SKIP and child.tag != "BR":
            lines.append(_own_text(child))
    if not lines:
        return _own_text(element)
    head = normalize_space(element.text or "")
    return "\n".join(line for line in [head, *lines] if line)


def _table_text(table: etree._Element) -> str:
    """Rows as "cell | cell", rows separated by " / "."""
    rows = []
    for row in table.iter("row"):
        cells = [_own_text(entry) for entry in row.findall("entry")]
        if any(cells):
            rows.append(" | ".join(cells))
    return " / ".join(rows)


def _text(element: etree._Element | None) -> str:
    return normalize_space("".join(element.itertext())) if element is not None else ""


_TRANSLITERATION = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _slug(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "-", value.lower().translate(_TRANSLITERATION)).strip("-")
