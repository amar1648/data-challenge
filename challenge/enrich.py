"""Model enrichment: a local model (Ollama) classifies candidate units.

The rules stay as they are; they select the candidates and remain the fallback.
Answers are cached in enrichment/cache.json under a hash of the complete input (act title,
heading, lead-in of the parent, unit) + model + prompt version, so query and evaluation run
without Ollama and any change of the input invalidates the entry.

Environment: OLLAMA_URL (default http://host.docker.internal:11434), LLM_MODEL (default qwen3:4b).
Only the standard library is used for HTTP.
"""

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from lxml import etree

from challenge.model import Act, Unit, normalize_space
from challenge.samples import ROOT

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "qwen3:4b")
PROMPT_VERSION = "v1"
CACHE_PATH = ROOT / "enrichment" / "cache.json"
TIMEOUT = 300  # seconds per call; the first call also loads the model

SCHEMA = {
    "type": "object",
    "properties": {
        "role": {"type": "string", "enum": ["applicability", "obligation", "none"]},
        "addressees": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["regulated", "authority"]},
                },
                "required": ["name", "type"],
            },
        },
        "addressee_explicit": {"type": "boolean"},
        "kind": {"type": "string", "enum": ["duty", "sanction", "consequence", "none"]},
    },
    "required": ["role", "addressees", "addressee_explicit", "kind"],
}

SYSTEM = """Du klassifizierst eine einzelne Einheit eines Gesetzestextes (Absatz, Satz oder Nummer).

role:
- "applicability": Die Einheit bestimmt, für wen das Gesetz gilt (persönlicher Anwendungsbereich), oder definiert einen Adressaten des Gesetzes. Nicht: Definitionen von Sachen, Rechten oder Risiken; zeitliche Geltung; Inkrafttreten.
- "obligation": Die Einheit selbst begründet eine Pflicht, ein Gebot oder ein Verbot für jemanden. Ein Anspruch einer Person ist eine Pflicht des Gegenübers. Auch Sanktionsvorschriften und angeordnete Rechtsfolgen zählen.
- "none": alles andere, z. B. Erlaubnisse, Ermächtigungen, Maßstäbe, reine Begriffsinhalte, Ausnahmen ohne eigene Pflicht.

addressees (nur bei "obligation"): wer die Pflicht trägt, als Nominalform im Singular oder wie im Gesetz üblich (z. B. "Unternehmen", "Arbeitgeber", "Kommission"). type "regulated" für Normadressaten aus Wirtschaft und Gesellschaft, "authority" für Behörden, Organe, Mitgliedstaaten. Bei "applicability" oder "none": leere Liste.
addressee_explicit: true nur, wenn der Pflichtträger im Pflichtsatz grammatisch genannt ist (auch als Pronomen). Bei Passiv oder erschlossenem Träger false.
kind: "duty", "sanction" (Sanktion/Bußgeld), "consequence" (angeordnete Rechtsfolge) bei "obligation", sonst "none".

Beurteile nur die gegebene Einheit; der Einleitungstext des Elternteils dient nur als Kontext."""


def prompt(title: str, unit: Unit, units_by_address: dict[str, Unit]) -> list[dict]:
    article = _article(unit, units_by_address)
    parent = units_by_address.get(unit.parent)
    lead_in = parent.text if parent is not None and parent.type in ("paragraph", "sentence", "point") else ""
    user = "\n".join([
        f"Gesetz: {title}",
        f"Vorschrift: {article.label} {article.heading or ''}".rstrip(),
        f"Einleitungstext des Elternteils: {lead_in or '–'}",
        f"Einheit: {_citation(unit, units_by_address)}",
        f"Text: {unit.text}",
    ])
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def call(messages: list[dict]) -> tuple[dict, dict]:
    """One chat call with structured output; returns (answer, stats)."""
    body = {
        "model": MODEL,
        "messages": messages,
        "format": SCHEMA,
        "think": False,
        "stream": False,
        "options": {"temperature": 0, "seed": 0},
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            reply = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit(f"Ollama unter {OLLAMA_URL} nicht erreichbar: {exc}") from exc
    answer = json.loads(reply["message"]["content"])
    stats = {
        "seconds": round(time.monotonic() - started, 2),
        "prompt_tokens": reply.get("prompt_eval_count"),
        "output_tokens": reply.get("eval_count"),
        "load_seconds": round(reply.get("load_duration", 0) / 1e9, 2),
    }
    return answer, stats


class Cache:
    def __init__(self, path: Path = CACHE_PATH) -> None:
        self.path = path
        self.entries: dict[str, dict] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    @staticmethod
    def key(messages: list[dict]) -> str:
        digest = hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return f"{digest}|{MODEL}|{PROMPT_VERSION}"

    def get(self, messages: list[dict]) -> dict | None:
        return self.entries.get(self.key(messages))

    def put(self, messages: list[dict], unit: Unit, act: Act, answer: dict, stats: dict) -> None:
        self.entries[self.key(messages)] = {
            "act": f"{act.work_id}/{act.version}_{act.language}", "address": unit.address,
            "answer": answer, "stats": stats,
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = dict(sorted(self.entries.items()))
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(ordered, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(self.path)


def text_units(units: list[Unit]) -> list[Unit]:
    return [unit for unit in units if unit.text and unit.type != "division"]


def enrich(act: Act, units: list[Unit], cache: Cache, offline: bool = False, log=None) -> dict:
    """Write tags["model"] for every text unit; calls Ollama only for cache misses."""
    by_address = {unit.address: unit for unit in units}
    title = act_title(act)
    counts = {"units": 0, "cached": 0, "called": 0, "missing": 0, "seconds": 0.0,
              "prompt_tokens": 0, "output_tokens": 0}
    for unit in text_units(units):
        counts["units"] += 1
        messages = prompt(title, unit, by_address)
        entry = cache.get(messages)
        if entry is None and offline:
            counts["missing"] += 1
            continue
        if entry is None:
            answer, stats = call(messages)
            cache.put(messages, unit, act, answer, stats)
            cache.save()  # after every call, so an interrupted run loses nothing
            entry = cache.get(messages)
            counts["called"] += 1
            for name in ("seconds", "prompt_tokens", "output_tokens"):
                counts[name] += stats[name] or 0
            if log:
                log(f"{act.work_id} {unit.address} {stats['seconds']}s in={stats['prompt_tokens']} "
                    f"out={stats['output_tokens']} -> {json.dumps(answer, ensure_ascii=False)}")
        else:
            counts["cached"] += 1
        unit.tags["model"] = {**entry["answer"], "model": MODEL, "prompt_version": PROMPT_VERSION}
    counts["seconds"] = round(counts["seconds"], 1)
    return counts


# Acts and versions that are enriched (eu-2015-2120: the newest version only).
ENRICHED = {"de-burlg": "2013-04-20", "eu-2015-2120": "2024-05-15", "de-lksg": "2021-07-16"}


def main() -> None:
    """Fill the cache for the enriched acts: python -m challenge.enrich"""
    import sys

    from challenge.model import read_act

    def log(line: str) -> None:
        print(f"{time.strftime('%H:%M:%S')} {line}", flush=True)

    cache = Cache()
    started = time.monotonic()
    totals = {"units": 0, "cached": 0, "called": 0, "seconds": 0.0, "prompt_tokens": 0, "output_tokens": 0}
    log(f"Modell {MODEL}, Prompt {PROMPT_VERSION}, {OLLAMA_URL}")
    for act_id, version in ENRICHED.items():
        act, units = read_act(ROOT / "output" / act_id / f"{version}_de.json")
        counts = enrich(act, units, cache, log=log)
        log(f"{act_id} {act.version}: {counts}")
        for name in totals:
            totals[name] += counts[name]
    totals["wall_seconds"] = round(time.monotonic() - started, 1)
    log(f"GESAMT {totals}")
    sys.exit(0)


def act_title(act: Act) -> str:
    """Title from the source file; the Act model does not carry one."""
    path = ROOT / act.source
    if path.suffix == ".xml":
        head = etree.parse(str(path), etree.XMLParser(load_dtd=False, no_network=True)).getroot().find("norm")
        long_title = normalize_space("".join(head.find("metadaten/langue").itertext()))
        short = head.findtext("metadaten/jurabk") or ""
        return f"{long_title} ({short})" if short else long_title
    text = path.read_text(encoding="utf-8")
    parts = re.findall(r'<p class="(?:oj-doc-ti|title-doc-first)"[^>]*>(.*?)</p>', text, flags=re.S)
    title = " ".join(re.sub(r"<[^>]+>", " ", part) for part in parts[:3])
    return normalize_space(re.sub(r"[►▼]\s*[BM]\d*|◄", " ", title))


def _article(unit: Unit, by_address: dict[str, Unit]) -> Unit:
    while unit.parent and by_address[unit.parent].type != "division":
        unit = by_address[unit.parent]
    return unit


def _citation(unit: Unit, by_address: dict[str, Unit]) -> str:
    chain = [unit]
    while chain[0].parent and by_address[chain[0].parent].type != "division":
        chain.insert(0, by_address[chain[0].parent])
    return " ".join(u.label for u in chain if u.label)


if __name__ == "__main__":
    main()
