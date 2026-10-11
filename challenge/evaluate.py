"""Recall and precision of query against the gold sets in tests/gold/.

Run after prepare (with --enrich for the model readings):
    python -m challenge.evaluate                 comparison table of all readings
    python -m challenge.evaluate --mode rules    details of one reading

A hit counts for a gold entry only if it is that unit or one of its descendants;
hits on borderline entries are left out of both measures. Precision is given per unit and
per character (text of the units a hit returns), the latter does not depend on how finely
a paragraph is split.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from challenge.model import Unit, read_act
from challenge.query import MODES, query
from challenge.samples import ROOT

GOLD_DIR = ROOT / "tests" / "gold"
OUTPUT = ROOT / "output"
TYPES = ("regulated", "authority")


def covers(hit: str, gold: str) -> bool:
    return hit == gold or hit.startswith(gold + "/")


def evaluate(gold: dict, units: list[Unit], mode: str = "rules") -> dict:
    """With gold["scope"] (article addresses), only hits and text inside the scope are counted."""
    scope = gold.get("scope")

    def in_scope(address: str) -> bool:
        return scope is None or any(covers(address, s) for s in scope)

    # query runs on the whole act (parents, sanction references); only scoring is limited.
    total_chars = sum(len(unit.text) for unit in units if in_scope(unit.address))
    text_of = {unit.address: unit.text for unit in units}
    report = {}
    for question in ("applicability", "obligations"):
        entries = gold[question]
        borderline = [b["address"] for b in gold["borderline"] if b["question"] == question]
        hits = {a: h for a, h in _by_address(query(units, question, mode)).items() if in_scope(a)}
        scored = {a: h for a, h in hits.items() if not any(covers(a, b) for b in borderline)}

        def matching(address: str) -> list[dict]:
            return [e for e in entries if covers(address, e["address"])]

        found = [e for e in entries if any(covers(a, e["address"]) for a in hits)]
        true_hits = [a for a in scored if matching(a)]
        covered = {member for hit in hits.values() for member in hit["covered"] if in_scope(member)}
        scored_text = {m for hit in scored.values() for m in hit["covered"] if in_scope(m)}
        true_text = {m for a in true_hits for m in scored[a]["covered"] if in_scope(m)}
        result = {
            "recall": _ratio(len(found), len(entries)),
            "precision": _ratio(len(true_hits), len(scored)),
            "precision_chars": _ratio(sum(len(text_of[m]) for m in true_text), sum(len(text_of[m]) for m in scored_text)),
            "hits": len(hits),
            "scored_hits": len(scored),
            "gold": len(entries),
            "text_share": _ratio(sum(len(text_of[a]) for a in covered), total_chars),
            "missed": [e["address"] for e in entries if e not in found],
            "false_positives": [a for a in scored if not matching(a)],
            "borderline_hits": [a for a in hits if a not in scored],
        }
        if question == "obligations":
            result["by_type"] = {t: _by_type(t, entries, scored, matching) for t in TYPES}
            result["addressee_correct"] = _ratio(
                sum(1 for a in true_hits if _names(scored[a]) & {_name(x["name"]) for e in matching(a) for x in e["addressees"]}),
                len(true_hits),
            )
        report[question] = result
    return report


def _by_type(type_: str, entries: list[dict], scored: dict, matching) -> dict:
    gold_entries = [e for e in entries if any(a["type"] == type_ for a in e["addressees"])]
    found = [e for e in gold_entries if any(covers(a, e["address"]) for a in scored)]
    predicted = [a for a, hit in scored.items() if any(x["type"] == type_ for x in hit["addressees"])]
    correct = [a for a in predicted if any(any(x["type"] == type_ for x in e["addressees"]) for e in matching(a))]
    return {
        "recall": _ratio(len(found), len(gold_entries)),
        "precision": _ratio(len(correct), len(predicted)),
        "gold": len(gold_entries),
        "predicted": len(predicted),
    }


def _by_address(hits: list[dict]) -> dict[str, dict]:
    """A unit can carry several findings (duty and sanction); score it once."""
    merged: dict[str, dict] = {}
    for hit in hits:
        target = merged.setdefault(hit["address"], {**hit, "addressees": []})
        for addressee in hit["addressees"]:
            if addressee not in target["addressees"]:
                target["addressees"].append(addressee)
    return merged


def _names(hit: dict) -> set[str]:
    return {_name(a["name"]) for a in hit["addressees"]}


def _name(name: str) -> str:
    """Addressee names compared without case and inflection: "Regulierungsbehörde(n)", "Mitgliedstaat(en)"."""
    words = re.findall(r"[a-zäöüß-]+", name.casefold())
    return " ".join(re.sub(r"(?:en|n|e|s)$", "", word) for word in words)


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def _percent(value: float | None) -> str:
    return "–" if value is None else f"{value:.0%}"


def render(act_id: str, version: str, report: dict) -> str:
    lines = [f"{act_id} · Stand {version}"]
    for question, label in (("applicability", "Geltungsbereich"), ("obligations", "Pflichten")):
        r = report[question]
        lines.append(
            f"  {label:<16} Recall {_percent(r['recall']):>5}  Precision {_percent(r['precision']):>5} "
            f"(Zeichen {_percent(r['precision_chars'])})  "
            f"Treffer {r['hits']} (gewertet {r['scored_hits']}), Gold {r['gold']}, "
            f"Textanteil {_percent(r['text_share'])}"
        )
        for type_, t in r.get("by_type", {}).items():
            lines.append(
                f"    {type_:<14} Recall {_percent(t['recall']):>5}  Precision {_percent(t['precision']):>5}  "
                f"Gold {t['gold']}, vorhergesagt {t['predicted']}"
            )
        if "addressee_correct" in r:
            lines.append(f"    Adressat getroffen bei {_percent(r['addressee_correct'])} der richtigen Treffer")
        lines.append(f"    verfehlt: {', '.join(r['missed']) or '–'}")
        lines.append(f"    falsch positiv: {', '.join(r['false_positives']) or '–'}")
        if r["borderline_hits"]:
            lines.append(f"    Grenzfälle (nicht gewertet): {', '.join(r['borderline_hits'])}")
    return "\n".join(lines)


MODE_LABEL = {"rules": "Regeln", "combined": "Regeln+Modell", "model": "Modell alle"}


def compare(golds: list[tuple[dict, list[Unit]]]) -> str:
    """One row per act, question and reading."""
    header = (f"{'Akt':<14}{'Frage':<10}{'Lesart':<15}{'Recall':>7}{'P Einh.':>9}{'P Zeich.':>9}"
              f"{'Textant.':>9}{'Adressat':>9}{'Treffer':>8}")
    lines = [header, "-" * len(header)]
    for gold, units in golds:
        for question, label in (("applicability", "Geltung"), ("obligations", "Pflichten")):
            for mode in MODES:
                r = evaluate(gold, units, mode)[question]
                lines.append(
                    f"{gold['act']:<14}{label:<10}{MODE_LABEL[mode]:<15}{_percent(r['recall']):>7}"
                    f"{_percent(r['precision']):>9}{_percent(r['precision_chars']):>9}{_percent(r['text_share']):>9}"
                    f"{_percent(r.get('addressee_correct')):>9}{r['scored_hits']:>8}"
                )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m challenge.evaluate")
    parser.add_argument("--mode", choices=MODES, help="Details einer Lesart statt der Vergleichstabelle")
    args = parser.parse_args()
    golds = []
    for path in sorted(GOLD_DIR.glob("*.json")):
        gold = json.loads(path.read_text(encoding="utf-8"))
        prepared = OUTPUT / gold["act"] / f"{gold['version']}_{gold['language']}.json"
        if not prepared.is_file():
            sys.exit(f"{prepared.relative_to(ROOT)} fehlt. Zuerst `python -m challenge prepare` ausführen.")
        golds.append((gold, read_act(prepared)[1]))
    if args.mode is None:
        print(compare(golds))
        return
    for gold, units in golds:
        print(render(gold["act"], gold["version"], evaluate(gold, units, args.mode)))
        print()


if __name__ == "__main__":
    main()
