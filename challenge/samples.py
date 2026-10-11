"""Frozen sample paths and parsers. No network access."""

import zipfile
from pathlib import Path

from bs4 import BeautifulSoup
from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
DE_DIR = SAMPLES / "de"
EU_ORIGINAL = SAMPLES / "eu" / "32015R2120_de.html"
EU_CONSOLIDATED = SAMPLES / "eu" / "02015R2120-20240515_de.html"


def relative(path: Path) -> str:
    """Path as recorded in Act.source: relative to the repo root when inside it."""
    resolved = path.resolve()
    return str(resolved.relative_to(ROOT)) if resolved.is_relative_to(ROOT) else str(resolved)


def german_acts() -> dict[str, Path]:
    return {f"de-{path.stem}": path for path in sorted(DE_DIR.glob("*.xml"))}


def resolve_act(act_id: str) -> Path:
    acts = german_acts()
    try:
        return acts[act_id]
    except KeyError as exc:
        known = ", ".join(acts)
        raise SystemExit(f"Unbekannter Akt {act_id!r}. Bekannt: {known}.") from exc


def iter_samples() -> list[Path]:
    return sorted(
        path
        for path in SAMPLES.rglob("*")
        if path.is_file() and path.suffix != ".md" and path.name != ".DS_Store"
    )


def parse_xml(path: Path) -> etree._ElementTree:
    if not path.is_file():
        raise SystemExit(f"Datei fehlt: {path}")
    parser = etree.XMLParser(load_dtd=False, no_network=True, resolve_entities=False)
    return etree.parse(str(path), parser)


def parse_html(path: Path) -> BeautifulSoup:
    """Parse one HTML sample. The original open-internet stand starts with an XML declaration."""
    if not path.is_file():
        raise SystemExit(f"Datei fehlt: {path}")
    return BeautifulSoup(path.read_text(encoding="utf-8"), features="xml")


def describe_xml(path: Path) -> str:
    root = parse_xml(path).getroot()
    tag = etree.QName(root).localname
    rel = path.relative_to(ROOT)
    return f"{rel} (XML, Wurzel {tag}, {path.stat().st_size} Bytes)"


def describe_html(path: Path) -> str:
    parse_html(path)
    rel = path.relative_to(ROOT)
    return f"{rel} (HTML, {path.stat().st_size} Bytes)"


def describe_zip(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    xml_count = sum(1 for name in names if name.lower().endswith(".xml"))
    rel = path.relative_to(ROOT)
    return (
        f"{rel} (Formex-Zip, {xml_count} XML-Dateien, "
        f"{len(names)} Einträge, {path.stat().st_size} Bytes)"
    )


def describe_sample(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".xml":
        return describe_xml(path)
    if suffix == ".html":
        return describe_html(path)
    if suffix == ".zip":
        return describe_zip(path)
    rel = path.relative_to(ROOT)
    return f"{rel} ({path.stat().st_size} Bytes)"
