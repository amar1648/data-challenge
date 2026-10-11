"""Recall and precision of query against the gold sets in tests/gold/.

Run after prepare:  python -m challenge.evaluate
A hit counts for a gold entry only if it is that unit or one of its descendants;
hits on borderline entries are left out of both measures.
"""

import json
import sys
from pathlib import Path

from challenge.model import Unit, read_act
from challenge.query import query
from challenge.samples import ROOT

GOLD_DIR = ROOT / "tests" / "gold"
OUTPUT = ROOT / "output"
TYPES = ("regulated", "authority")


def covers(hit: str, gold: str) -> bool:
    return hit == gold or hit.startswith(gold + "/")


def evaluate(gold: dict, units: list[Unit]) -> dict:
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
        hits = {a: h for a, h in _by_address(query(units, question)).items() if in_scope(a)}
        scored = {a: h for a, h in hits.items() if not any(covers(a, b) for b in borderline)}

        def matching(address: str) -> list[dict]:
            return [e for e in entries if covers(address, e["address"])]

        found = [e for e in entries if any(covers(a, e["address"]) for a in hits)]
        true_hits = [a for a in scored if matching(a)]
        covered = {member for hit in hits.values() for member in hit["covered"] if in_scope(member)}
        result = {
            "recall": _ratio(len(found), len(entries)),
            "precision": _ratio(len(true_hits), len(scored)),
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
                sum(1 for a in true_hits if _names(scored[a]) & {x["name"] for e in matching(a) for x in e["addressees"]}),
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
    return {a["name"] for a in hit["addressees"]}


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def _percent(value: float | None) -> str:
    return "–" if value is None else f"{value:.0%}"


def render(act_id: str, version: str, report: dict) -> str:
    lines = [f"{act_id} · Stand {version}"]
    for question, label in (("applicability", "Geltungsbereich"), ("obligations", "Pflichten")):
        r = report[question]
        lines.append(
            f"  {label:<16} Recall {_percent(r['recall']):>5}  Precision {_percent(r['precision']):>5}  "
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


def main() -> None:
    for path in sorted(GOLD_DIR.glob("*.json")):
        gold = json.loads(path.read_text(encoding="utf-8"))
        prepared = OUTPUT / gold["act"] / f"{gold['version']}_{gold['language']}.json"
        if not prepared.is_file():
            sys.exit(f"{prepared.relative_to(ROOT)} fehlt. Zuerst `python -m challenge prepare` ausführen.")
        _, units = read_act(prepared)
        print(render(gold["act"], gold["version"], evaluate(gold, units)))
        print()


if __name__ == "__main__":
    main()
