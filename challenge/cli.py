"""Command-line stub: prepare, lookup, query and diff on harmonized structure."""

import argparse
import json
import sys
from pathlib import Path

from challenge import de_gii, eurlex_html
from challenge.diff import diff, german_summary
from challenge.lookup import latest_version, lookup
from challenge.query import query, render
from challenge.tagging import tag_units
from challenge.model import Act, Unit, read_act, write_act
from challenge.samples import (
    EU_CONSOLIDATED,
    EU_ORIGINAL,
    ROOT,
    german_acts,
    iter_samples,
)

OUTPUT = ROOT / "output"
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
    query.add_argument("--lang", default="de", help="Sprachfassung, Standard: de")
    query.add_argument("--json", action="store_true", help="Treffer als JSON ausgeben")

    diff = sub.add_parser("diff", help="Zwei Stände gegenüberstellen")
    diff.add_argument("--from", dest="source", required=True)
    diff.add_argument("--to", dest="target", required=True)

    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "lookup":
        lookup_cmd(args.act, args.ref, args.lang)
    elif args.command == "query":
        query_cmd(args.act, args.question, args.lang, args.json)
    elif args.command == "diff":
        diff_cmd(args.source, args.target)


def prepare() -> None:
    for act_id, path in german_acts().items():
        act, units, issues = de_gii.parse_with_issues(path, act_id)
        _write(act, units)
        for category, examples in issues.items():
            shown = ", ".join(dict.fromkeys(examples))
            if len(shown) > 90:
                shown = shown[:90].rsplit(",", 1)[0] + ", …"
            print(f"              {category}: {len(examples)} ({shown})")
    for path in EU_HTML:
        _write(*eurlex_html.parse(path))
    other = [path for path in iter_samples() if path.parent.name != "de" and path not in EU_HTML]
    if other:
        print(f"übersprungen  {len(other)} Formex-Dateien unter samples/eu/formex/ (Parser noch offen)")


def _write(act: Act, units: list[Unit]) -> None:
    tag_units(units)
    target = write_act(OUTPUT, act, units)
    print(f"geschrieben   {target.relative_to(ROOT)} ({len(units)} Einheiten)")


def lookup_cmd(act_id: str, ref: str, language: str) -> None:
    print(lookup(OUTPUT, act_id, ref, language))


def query_cmd(act_id: str, question: str, language: str, as_json: bool) -> None:
    act, units = read_act(latest_version(OUTPUT, act_id, language))
    hits = query(units, question)
    if as_json:
        print(json.dumps({"act": act.__dict__, "question": question, "hits": hits}, ensure_ascii=False, indent=2))
    else:
        print(render(act, question, hits))


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
