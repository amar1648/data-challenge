"""Harmonised model shared by all sources: one Act, a flat list of Units.

Addresses are language-neutral paths derived from the source's outline,
always in the form art-N/par-N/pt-x. A German "§ 3 Abs. 1" and an EU
"Artikel 3 Absatz 1" / "Article 3(1)" both become art-3/par-1. The source's
own spelling lives only in Unit.label.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCHEMA = 1


@dataclass
class Act:
    work_id: str  # stable across versions and languages, e.g. "de-burlg" or "32015R2120"
    version: str  # legal state as ISO date, e.g. "2013-04-20"
    language: str  # ISO 639-1, e.g. "de"
    source: str  # source file, relative to the repo root


@dataclass
class Unit:
    address: str  # e.g. "art-3/par-1"; unique within one Act
    label: str  # source spelling of this level, e.g. "§ 3", "Abs. 1", "a)"
    type: str  # preamble | division | article | paragraph | point
    heading: str | None
    text: str  # own text only; children are separate Units
    parent: str | None  # address of the structural parent
    order: int  # position in document order
    content_hash: str  # over heading + text, see unit_hash()
    source_anchor: str  # way back into the raw file, e.g. "<doknr>:P[1]/DL[1]/DD[2]"
    refs: list[str] = field(default_factory=list)  # addresses in the same Act
    tags: dict = field(default_factory=dict)  # later enrichment (roles, addressees)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def unit_hash(heading: str | None, text: str) -> str:
    payload = normalize_space(heading or "") + "\n" + normalize_space(text)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def output_path(output_dir: Path, act: Act) -> Path:
    return output_dir / act.work_id / f"{act.version}_{act.language}.json"


def write_act(output_dir: Path, act: Act, units: list[Unit]) -> Path:
    path = output_path(output_dir, act)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": SCHEMA,
        "act": asdict(act),
        "units": [asdict(unit) for unit in units],
    }
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_act(path: Path) -> tuple[Act, list[Unit]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != SCHEMA:
        raise SystemExit(f"{path}: unbekannte Schema-Version {document.get('schema')!r}.")
    return Act(**document["act"]), [Unit(**unit) for unit in document["units"]]
