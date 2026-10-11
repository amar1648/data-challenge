"""Answer the two content questions from the tags written at prepare time; no model call, no parsing.

Five readings of the same tags:
- "hybrid" (default): role from the rules. The model replaces only addressees that come from
  the act-wide default or are "unbestimmt", and only if it names one. Addressees the rule
  derives (named in the clause, counterpart of a rights holder, actor of the article) stay.
- "hybrid-wide": like hybrid, but the model replaces every inferred addressee (explicit=false).
- "rules": tags["roles"] from the rule-based tagger only.
- "combined": rules as pre-filter. For a candidate (rule hit, or unit of an article whose
  heading names scope or definitions) the model answer in tags["model"] decides role and
  addressees; kind and sanction references stay with the rules. Without a model answer the
  rules apply.
- "model": the model answer decides for every unit that has one; rules only as fallback.
"""

import re

from challenge.model import Act, Unit
from challenge.tagging import _SCOPE_HEADING, UNDETERMINED

MODES = ("hybrid", "hybrid-wide", "rules", "combined", "model")
QUESTIONS = {"applicability": "applicability", "obligations": "obligation"}
TYPE_ORDER = {"regulated": 0, "authority": 1, "unknown": 2}
TYPE_LABEL = {"regulated": "Normadressat", "authority": "Behörde/Organ", "unknown": "Adressat unbestimmt"}
KIND_LABEL = {"duty": "Pflicht", "sanction": "Sanktion", "consequence": "Rechtsfolge"}


def query(units: list[Unit], question: str, mode: str = "hybrid") -> list[dict]:
    """Hits for one question: address, label, text (with list items), reason, addressees."""
    role_name = QUESTIONS[question]
    by_address = {unit.address: unit for unit in units}
    sanctioned_by = _sanctioned_by(units)
    hits = []
    for unit in units:
        article = _article(unit, by_address)
        for role in _findings(unit, article, role_name, mode):
            members = _subtree(unit, units) if role_name == "obligation" and _continues(unit) else [unit]
            hits.append({
                "address": unit.address,
                "label": _citation(unit, by_address),
                "heading": article.heading,
                "text": _text(unit, members),
                "covered": [u.address for u in members],
                "kind": role.get("kind"),
                "rule": role["rule"],
                "evidence": role["evidence"],
                "addressees": role.get("addressees", []),
                "sanctioned_by": sanctioned_by.get(article.address, []) if role.get("kind") == "duty" else [],
                "sanctions": unit.tags.get("sanctions", []),
            })
    return hits


def is_candidate(unit: Unit, article: Unit) -> bool:
    """Units the rules pre-select for the model."""
    return bool(unit.tags.get("roles")) or bool(_SCOPE_HEADING.search(article.heading or ""))


def _findings(unit: Unit, article: Unit, role_name: str, mode: str) -> list[dict]:
    rules = [role for role in unit.tags.get("roles", []) if role["role"] == role_name]
    model = unit.tags.get("model")
    if mode in ("hybrid", "hybrid-wide"):
        return [_with_model_addressees(role, model, wide=mode == "hybrid-wide") for role in rules]
    if mode == "rules" or model is None or (mode == "combined" and not is_candidate(unit, article)):
        return rules
    if model["role"] != role_name:
        return []
    finding = {"role": role_name, "rule": ["model"], "evidence": [f"{model['model']} {model['prompt_version']}"]}
    if role_name == "obligation":
        rule_kinds = [role.get("kind") for role in rules]
        kind = rule_kinds[0] if rule_kinds else (model["kind"] if model["kind"] != "none" else "duty")
        addressees = [
            {"name": a["name"], "type": a["type"], "explicit": bool(model["addressee_explicit"])}
            for a in model["addressees"]
        ] or [{"name": UNDETERMINED, "type": "unknown", "explicit": False}]
        finding.update(kind=kind, addressees=addressees)
    return [finding]


# Rule addressees the model may replace in the default reading.
REPLACEABLE = {"act-default", "undetermined"}


def _with_model_addressees(role: dict, model: dict | None, wide: bool = False) -> dict:
    """Replace default or undetermined rule addressees (wide: every inferred one) by the model's."""
    if role["role"] != "obligation" or model is None or model["role"] != "obligation" or not model["addressees"]:
        return role
    if any(a["explicit"] for a in role["addressees"]):
        return role
    if not wide and not all(a.get("via") in REPLACEABLE for a in role["addressees"]):
        return role
    addressees = [
        {"name": _without_article(a["name"]), "type": a["type"], "explicit": False, "source": "model"}
        for a in model["addressees"]
    ]
    return {**role, "addressees": addressees, "rule": [*role["rule"], "model-addressee"]}


def _without_article(name: str) -> str:
    """The model sometimes answers "Das Unternehmen"; addressees are listed without article."""
    return re.sub(r"^(?:der|die|das)\s+", "", name.strip(), flags=re.IGNORECASE)


def group_by_addressee(hits: list[dict]) -> list[tuple[dict, list[dict]]]:
    """Groups ordered regulated first, then authorities; a hit can be in several groups."""
    groups: dict[str, tuple[dict, list[dict]]] = {}
    for hit in hits:
        for addressee in hit["addressees"] or [{"name": "Adressat nicht erkannt", "type": "regulated"}]:
            groups.setdefault(addressee["name"], (addressee, []))[1].append(hit)
    return sorted(groups.values(), key=lambda g: (TYPE_ORDER.get(g[0]["type"], 9), -len(g[1]), g[0]["name"]))


def render(act: Act, question: str, hits: list[dict]) -> str:
    title = "Geltungsbereich" if question == "applicability" else "Pflichten"
    lines = [f"{act.work_id} · Stand {act.version} · {act.language} · Frage: {title}", f"{len(hits)} Treffer", ""]
    if question == "applicability":
        for hit in hits:
            lines.extend(_render_hit(hit, with_addressee=False))
        return "\n".join(lines)
    for addressee, group in group_by_addressee(hits):
        if addressee["type"] == "unknown":
            lines.append(f"## {TYPE_LABEL['unknown']}, {len(group)} Treffer")
        else:
            lines.append(f"## {addressee['name']} ({TYPE_LABEL.get(addressee['type'], addressee['type'])}), {len(group)} Treffer")
        lines.append("")
        for hit in group:
            lines.extend(_render_hit(hit, with_addressee=True, addressee=addressee["name"]))
    return "\n".join(lines)


def _render_hit(hit: dict, with_addressee: bool, addressee: str | None = None) -> list[str]:
    reason = f"Regel: {', '.join(hit['rule'])} – „{' / '.join(hit['evidence'])}“"
    if with_addressee:
        named = next((a for a in hit["addressees"] if a["name"] == addressee), None)
        how = "genannt" if named and named["explicit"] else "erschlossen"
        if named and named.get("source") == "model":
            how = "vom Modell erschlossen"
        if named and named["type"] == "unknown":
            how = "unbestimmt"
        reason = f"{KIND_LABEL.get(hit['kind'], hit['kind'])}, Adressat {how}; {reason}"
    lines = [f"- {hit['label']}  [{hit['address']}]  {hit['heading'] or ''}".rstrip(), f"  {reason}"]
    if hit["sanctions"]:
        lines.append(f"  Sanktioniert Verstöße gegen: {', '.join(hit['sanctions'])}")
    if hit["sanctioned_by"]:
        lines.append(f"  Verstoß sanktioniert in: {', '.join(hit['sanctioned_by'])}")
    lines.extend(f"    {line}" for line in hit["text"].splitlines())
    lines.append("")
    return lines


def _sanctioned_by(units: list[Unit]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for unit in units:
        for article in unit.tags.get("sanctions", []):
            result.setdefault(article, []).append(unit.address)
    return result


def _subtree(root: Unit, units: list[Unit]) -> list[Unit]:
    members = {root.address}
    result = [root]
    for unit in units:
        if unit.parent in members:
            members.add(unit.address)
            result.append(unit)
    return result


def _continues(unit: Unit) -> bool:
    """A sentence ending in ':' or without final punctuation continues in the list items below."""
    return any(not line.rstrip().endswith((".", "!", "?")) for line in unit.text.splitlines())


def _text(unit: Unit, members: list[Unit]) -> str:
    """Own text, followed by the list items it continues in."""
    lines = []
    for member in members:
        prefix = f"{member.label} " if member is not unit and member.label else ""
        lines.append(prefix + member.text)
    return "\n".join(line for line in lines if line.strip())


def _article(unit: Unit, by_address: dict[str, Unit]) -> Unit:
    while unit.parent and by_address[unit.parent].type != "division":
        unit = by_address[unit.parent]
    return unit


def _citation(unit: Unit, by_address: dict[str, Unit]) -> str:
    chain = [unit]
    while chain[0].parent and by_address[chain[0].parent].type != "division":
        chain.insert(0, by_address[chain[0].parent])
    return " ".join(u.label for u in chain if u.label)
