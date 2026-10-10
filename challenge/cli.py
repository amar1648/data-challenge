"""Command-line stub. Loading the samples is implemented; the task is not."""

import argparse
from pathlib import Path

from challenge.samples import (
    EU_CONSOLIDATED,
    EU_ORIGINAL,
    ROOT,
    describe_html,
    describe_sample,
    describe_xml,
    iter_samples,
    resolve_act,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m challenge",
        description=(
            "Einstieg für die Data Challenge. Die Befehle laden die Beispiele "
            "und melden, dass die Aufbereitung noch offen ist."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("prepare", help="Harmonisierte Struktur nach output/ schreiben")

    lookup = sub.add_parser("lookup", help="Eine Stelle aus einem Akt holen")
    lookup.add_argument("--act", required=True)
    lookup.add_argument("--ref", required=True)

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
        lookup_cmd(args.act, args.ref)
    elif args.command == "query":
        query_cmd(args.act, args.question)
    elif args.command == "diff":
        diff_cmd(args.source, args.target)


def prepare() -> None:
    _pending(
        "prepare soll die eigene Struktur nach output/ schreiben.",
        [describe_sample(path) for path in iter_samples()],
    )


def lookup_cmd(act_id: str, ref: str) -> None:
    path = resolve_act(act_id)
    _pending(
        f"lookup soll die Stelle {ref!r} aus {act_id} liefern.",
        [describe_xml(path)],
    )


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
    _pending(
        "diff soll eine strukturierte Gegenüberstellung der beiden Stände ausgeben.",
        [describe_html(_html_path(source)), describe_html(_html_path(target))],
    )


def _html_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def _pending(task: str, loaded: list[str]) -> None:
    print("Nicht implementiert.")
    print()
    print(task)
    print()
    print("Gelesen:")
    for line in loaded:
        print(f"- {line}")
