"""Command-line stub: prepare, lookup, query and diff on harmonized structure."""

import argparse
import copy
import json
import sys
from pathlib import Path

from challenge import de_gii, enrich, eurlex_html, formex
from challenge.diff import diff, german_summary
from challenge.lookup import latest_version, lookup
from challenge.query import MODES, query, render
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
# Formex zips with a parser; the other samples in samples/eu/formex/ are reported as skipped.
FORMEX = tuple(ROOT / "samples" / "eu" / "formex" / f"32016R0679_{lang}.fmx.zip" for lang in ("de", "en"))
EU_HTML = (EU_ORIGINAL, EU_CONSOLIDATED)


def main() -> None:
    parser = argparse.ArgumentParser(
    prog="python -m challenge",
    description="Gesetzestexte harmonisieren und abfragen: Stelle nachschlagen, Fragen beantworten, Stände vergleichen.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare", help="Harmonisierte Struktur nach output/ schreiben")
    prepare_parser.add_argument(
        "--enrich", action="store_true",
        help="Modell-Anreicherung aus enrichment/cache.json; fehlende Einträge über Ollama (OLLAMA_URL, LLM_MODEL)",
    )

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
    query.add_argument(
        "--mode", choices=MODES, default="hybrid",
        help="hybrid: Rolle aus Regeln, erschlossene Adressaten aus dem Modell (Standard); rules: nur Regeln; "
        "combined: Regeln als Vorfilter + Modell; model: Modell auf allen Einheiten",
    )

    diff = sub.add_parser("diff", help="Zwei Stände gegenüberstellen")
    diff.add_argument("--from", dest="source", required=True)
    diff.add_argument("--to", dest="target", required=True)

    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.enrich)
    elif args.command == "lookup":
        lookup_cmd(args.act, args.ref, args.lang)
    elif args.command == "query":
        query_cmd(args.act, args.question, args.lang, args.json, args.mode)
    elif args.command == "diff":
        diff_cmd(args.source, args.target)


def prepare(with_model: bool = False) -> None:
    cache = enrich.Cache() if with_model else None
    tagged: dict[tuple[str, str], list[Unit]] = {}  # German versions, source of the tag transfer
    for act_id, path in german_acts().items():
        act, units, issues = de_gii.parse_with_issues(path, act_id)
        _write(act, units, cache, tagged)
        _report(issues)
    for path in EU_HTML:
        _write(*eurlex_html.parse(path), cache, tagged)
    for path in FORMEX:  # German before English
        act, units, issues = formex.parse_with_issues(path)
        _write(act, units, cache, tagged)
        _report(issues)
    other = [path for path in iter_samples() if path.parent.name != "de" and path not in EU_HTML + FORMEX]
    if other:
        print(f"übersprungen  {len(other)} Formex-Dateien unter samples/eu/formex/ (Parser noch nicht freigegeben)")


def _report(issues: dict[str, list[str]]) -> None:
    for category, examples in issues.items():
        shown = ", ".join(dict.fromkeys(examples))
        if len(shown) > 90:
            shown = shown[:90].rsplit(",", 1)[0] + ", …"
        print(f"              {category}: {len(examples)} ({shown})")


def _write(act: Act, units: list[Unit], cache: enrich.Cache | None, tagged: dict) -> None:
    if act.language == "de":  # the tagging rules are German wording
        tag_units(units)
        tagged[(act.work_id, act.version)] = units
    else:
        _transfer_tags(act, units, tagged.get((act.work_id, act.version)))
    if cache is not None and enrich.ENRICHED.get(act.work_id) == act.version:
        counts = enrich.enrich(act, units, cache)
        print(f"              Modell: {counts['units']} Einheiten, {counts['cached']} aus dem Cache, "
              f"{counts['called']} neu abgefragt")
    target = write_act(OUTPUT, act, units)
    print(f"geschrieben   {target.relative_to(ROOT)} ({len(units)} Einheiten)")


def _transfer_tags(act: Act, units: list[Unit], german: list[Unit] | None) -> None:
    """Roles of a language version come from the German one, matched by address.

    Only when both versions have exactly the same addresses; the same address is the same
    provision, so the same obligation, in every language.
    """
    if german is None:
        print(f"              Keine deutsche Fassung, keine Tags für {act.language}")
        return
    if [u.address for u in german] != [u.address for u in units]:
        print(f"              Adressen weichen von der deutschen Fassung ab, keine Tags übertragen")
        return
    for source, target in zip(german, units):
        for name in ("roles", "sanctions"):
            if name in source.tags:
                target.tags[name] = copy.deepcopy(source.tags[name])
        if "roles" in source.tags:
            target.tags["transferred_from"] = "de"
    count = sum(1 for u in units if "transferred_from" in u.tags)
    print(f"              Tags von der deutschen Fassung übertragen: {count} Einheiten")


def lookup_cmd(act_id: str, ref: str, language: str) -> None:
    print(lookup(OUTPUT, act_id, ref, language))


def query_cmd(act_id: str, question: str, language: str, as_json: bool, mode: str) -> None:
    act, units = read_act(latest_version(OUTPUT, act_id, language))
    hits = query(units, question, mode)
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
