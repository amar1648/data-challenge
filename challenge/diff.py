"""Compare two versions of one act: pair units by address, compare by content_hash."""

import difflib
import re
from dataclasses import asdict

from challenge.model import Act, Unit

UNCHANGED, MODIFIED, ADDED, REMOVED = "unchanged", "modified", "added", "removed"
GERMAN = {UNCHANGED: "unverändert", MODIFIED: "geändert", ADDED: "neu", REMOVED: "entfallen"}


def diff(old_act: Act, old: list[Unit], new_act: Act, new: list[Unit]) -> dict:
    if old_act.work_id != new_act.work_id:
        raise SystemExit(
            f"Verschiedene Akte: {old_act.work_id} und {new_act.work_id} lassen sich nicht vergleichen."
        )
    old_by_address = {unit.address: unit for unit in old}
    new_by_address = {unit.address: unit for unit in new}

    entries = []
    for unit in new:
        before = old_by_address.get(unit.address)
        if before is None:
            change = ADDED
        elif before.content_hash == unit.content_hash:
            change = UNCHANGED
        else:
            change = MODIFIED
        entries.append(((unit.order, 0, 0), _entry(unit.address, change, before, unit)))
    for index, unit in enumerate(old):
        if unit.address not in new_by_address:
            # Removed units stay where they were: after their last surviving predecessor.
            anchor = next(
                (new_by_address[o.address].order for o in reversed(old[:index]) if o.address in new_by_address),
                -1,
            )
            entries.append(((anchor, 1, unit.order), _entry(unit.address, REMOVED, unit, None)))
    changes = [entry for _, entry in sorted(entries, key=lambda pair: pair[0])]

    summary = {kind: 0 for kind in (UNCHANGED, MODIFIED, ADDED, REMOVED)}
    for entry in changes:
        summary[entry["change"]] += 1
    return {"from": asdict(old_act), "to": asdict(new_act), "summary": summary, "changes": changes}


def german_summary(result: dict) -> str:
    counts = ", ".join(f"{count} {GERMAN[kind]}" for kind, count in result["summary"].items())
    return f"Vergleich {result['from']['version']} → {result['to']['version']}: {counts}"


def text_diff(old: str, new: str) -> dict:
    """Word-level inserted and deleted passages."""
    old_words, new_words = re.findall(r"\S+", old), re.findall(r"\S+", new)
    inserted, deleted = [], []
    matcher = difflib.SequenceMatcher(a=old_words, b=new_words, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            deleted.append(" ".join(old_words[i1:i2]))
        if tag in ("insert", "replace"):
            inserted.append(" ".join(new_words[j1:j2]))
    return {"inserted": inserted, "deleted": deleted}


def _entry(address: str, change: str, old: Unit | None, new: Unit | None) -> dict:
    entry = {"address": address, "change": change, "old": _side(old), "new": _side(new)}
    if change == MODIFIED:
        entry["text_diff"] = text_diff(old.text, new.text)
        if old.heading != new.heading:  # the hash covers the heading, so it can be the only change
            entry["heading_diff"] = {"old": old.heading, "new": new.heading}
    return entry


def _side(unit: Unit | None) -> dict | None:
    if unit is None:
        return None
    return {
        "label": unit.label,
        "heading": unit.heading,
        "text": unit.text,
        "content_hash": unit.content_hash,
        "source_anchor": unit.source_anchor,
        "amended_by": unit.tags.get("amended_by", []),
    }
