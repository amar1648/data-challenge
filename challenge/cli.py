"""Command-line stub: prepare, lookup, query and diff on harmonized structure."""

import argparse
import json
import sys
from pathlib import Path

from challenge import de_gii, eurlex_html
from challenge.diff import diff, german_summary
from challenge.lookup import lookup
from challenge.model import Act, Unit, write_act
from challenge.samples import (
    EU_CONSOLIDATED,
    EU_ORIGINAL,
    ROOT,
    describe_xml,
    german_acts,
    iter_samples,
    resolve_act,
)

OUTPUT = ROOT / "output"
# Acts whose parser is implemented and checked; the rest is reported as skipped.
SUPPORTED = {"de-burlg"}
EU_HTML = (EU_ORIGINAL, EU_CONSOLIDATED)


def main() -> None:
    parser = argparse.ArgumentParser(
    prog="python -m challenge",
    description="Gesetzestexte harmonisieren und abfragen: Stelle nachschlagen, Fragen beantworten, Stände vergleichen.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("prepare", help="Harmonisierte Struktur nach output/ schreiben")

    lookup_parser = sub.add_parser("lookup", help="Eine Stelle aus einem Akt holen")
    lookup_parser.add_argument("--act", required=True)
    lookup_parser.add_argument("--ref", required=True)
    lookup_parser.add_argument("--lang", default="de", help="Sprachfassung, Standard: de")

    query = sub.add_parser("query", help="Stellen zu einer Frage holen")
    query.add_argument("--act", required=True)
    query.add_argument(
        "--question",
        required=True,
        choices=("applicability", "obligations"),
    )

    diff = sub.add_parser("diff", help="Zwei Stände gegenüberstellen")
    diff.add_argument("--from", dest="source", required=True)
    diff.add_argument("--to", dest="target", required=True)

    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "lookup":
        lookup_cmd(args.act, args.ref, args.lang)
    elif args.command == "query":
        query_cmd(args.act, args.question)
    elif args.command == "diff":
        diff_cmd(args.source, args.target)


def prepare() -> None:
    for act_id, path in german_acts().items():
        if act_id not in SUPPORTED:
            print(f"übersprungen  {path.relative_to(ROOT)} (Parser noch nicht freigegeben)")
            continue
        _write(*de_gii.parse(path, act_id))
    for path in EU_HTML:
        _write(*eurlex_html.parse(path))
    other = [path for path in iter_samples() if path.parent.name != "de" and path not in EU_HTML]
    if other:
        print(f"übersprungen  {len(other)} Formex-Dateien unter samples/eu/formex/ (Parser noch offen)")


def _write(act: Act, units: list[Unit]) -> None:
    target = write_act(OUTPUT, act, units)
    print(f"geschrieben   {target.relative_to(ROOT)} ({len(units)} Einheiten)")


def lookup_cmd(act_id: str, ref: str, language: str) -> None:
    print(lookup(OUTPUT, act_id, ref, language))


def query_cmd(act_id: str, question: str) -> None:
    path = resolve_act(act_id)
    _pending(
        "query soll Treffer mit Adresse und Textstück liefern, nicht den ganzen Akt.\n"
        f"Frage: {question}.\n"
        "Ob dafür ein Modell nötig ist, und welches, entscheidest du. "
        "Dieser Stub ruft keines auf.",
        [describe_xml(path)],
    )


def diff_cmd(source: str, target: str) -> None:
    result = diff(*_parse_source(source), *_parse_source(target))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(german_summary(result), file=sys.stderr)


def _parse_source(value: str) -> tuple[Act, list[Unit]]:
    """Parse a raw source file; the format follows from the file extension."""
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    if path.suffix == ".html":
        return eurlex_html.parse(path)
    if path.suffix == ".xml":
        return de_gii.parse(path, f"de-{path.stem}")
    raise SystemExit(f"Unbekanntes Format: {path.name} (erwartet .html oder .xml)")


def _pending(task: str, loaded: list[str]) -> None:
    print("Nicht implementiert.")
    print()
    print(task)
    print()
    print("Gelesen:")
    for line in loaded:
        print(f"- {line}")
