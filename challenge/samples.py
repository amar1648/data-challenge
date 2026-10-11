"""Frozen sample paths and parsers. No network access."""

from pathlib import Path

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
