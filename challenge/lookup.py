"""Resolve a citation like "§ 3 Abs. 1" to an address and print that unit with its subtree."""

import re
from pathlib import Path

from challenge.model import Act, Unit, read_act

_ADDRESS = re.compile(r"[a-z]+-[0-9a-z]+(?:/[a-z]+-[0-9a-z]+)*")
# "15a" is a number, but in "§3Abs.1" the letters after the 3 start the next keyword.
_NUMBER = r"\d+(?:[a-z](?![a-z]))?|[a-z]{1,2}(?![a-z])"
_HEAD = re.compile(rf"(?:§|art(?:ikel|icle)?\.?)\s*({_NUMBER})", re.IGNORECASE)
_PART = re.compile(
    r"\s*(?:(abs(?:atz)?\.?|par(?:agraph)?\.?|buchst(?:abe)?\.?|nr\.?|nummer|lit\.?|point)"
    rf"\s*\(?({_NUMBER})\)?|\(({_NUMBER})\))\s*",
    re.IGNORECASE,
)
_PARAGRAPH_WORDS = ("abs", "par")


def ref_to_address(ref: str) -> str:
    """Accepts "§ 3 Abs. 1", "§3 Abs.1", "§ 5 Abs. 1 Buchst. a", "Art. 3(1)(a)" or an address."""
    value = ref.strip()
    if _ADDRESS.fullmatch(value):
        return value
    head = _HEAD.match(value)
    if not head:
        raise SystemExit(f"Stellenangabe nicht verstanden: {ref!r}")
    parts = [f"art-{head.group(1).lower()}"]
    position = head.end()
    while position < len(value):
        part = _PART.match(value, position)
        if not part or part.end() == position:
            raise SystemExit(f"Stellenangabe nicht verstanden ab {value[position:]!r}: {ref!r}")
        word, number, bracketed = part.groups()
        number = (number or bracketed).lower()
        # "(1)" directly after the article is the paragraph, every later level is a point.
        is_paragraph = word.lower().startswith(_PARAGRAPH_WORDS) if word else len(parts) == 1
        parts.append(f"par-{number}" if is_paragraph else f"pt-{number}")
        position = part.end()
    return "/".join(parts)


def latest_version(output_dir: Path, act_id: str, language: str) -> Path:
    candidates = sorted((output_dir / act_id).glob(f"*_{language}.json"))
    if not candidates:
        raise SystemExit(
            f"Keine aufbereitete Fassung für {act_id} ({language}) unter {output_dir}. "
            "Zuerst `python -m challenge prepare` ausführen."
        )
    return candidates[-1]  # file names start with the ISO date of the version


def find(units: list[Unit], address: str) -> Unit:
    by_address = {unit.address: unit for unit in units}
    if address in by_address:
        return by_address[address]
    # "§ 12 Nr. 2" omits the implicit Absatz of a single-Absatz article.
    article, _, rest = address.partition("/")
    implicit = by_address.get(f"{article}/par-1")
    if rest and not rest.startswith("par-") and implicit and not implicit.label:
        fallback = f"{article}/par-1/{rest}"
        if fallback in by_address:
            return by_address[fallback]
    raise SystemExit(f"Stelle {address} gibt es in diesem Akt nicht.")


def render(act: Act, units: list[Unit], unit: Unit) -> str:
    by_address = {u.address: u for u in units}
    chain = [unit]
    while chain[0].parent:
        chain.insert(0, by_address[chain[0].parent])
    citation = " ".join(u.label for u in chain if u.label)
    heading = next((u.heading for u in reversed(chain) if u.heading), None)

    lines = [
        f"{act.work_id} · Stand {act.version} · {act.language}",
        f"{citation}  [{unit.address}]",
    ]
    if heading:
        lines.append(heading)
    lines.append("")
    for item, depth in _subtree(units, unit):
        label = f"{item.label} " if item is not unit and item.label else ""
        if item.text:
            lines.append("  " * depth + label + item.text)
    lines.append("")
    lines.append(f"Quelle: {act.source} · {unit.source_anchor}")
    return "\n".join(lines)


def _subtree(units: list[Unit], root: Unit) -> list[tuple[Unit, int]]:
    result = [(root, 0)]
    depth = {root.address: 0}
    for unit in sorted(units, key=lambda u: u.order):
        if unit.parent in depth and unit.address not in depth:
            depth[unit.address] = depth[unit.parent] + 1
            result.append((unit, depth[unit.address]))
    return result


def lookup(output_dir: Path, act_id: str, ref: str, language: str) -> str:
    act, units = read_act(latest_version(output_dir, act_id, language))
    return render(act, units, find(units, ref_to_address(ref)))
