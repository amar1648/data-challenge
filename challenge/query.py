"""Answer the two content questions from the tags written at prepare time; no model, no parsing."""

from challenge.model import Act, Unit

QUESTIONS = {"applicability": "applicability", "obligations": "obligation"}
TYPE_ORDER = {"regulated": 0, "authority": 1}
TYPE_LABEL = {"regulated": "Normadressat", "authority": "Behörde/Organ"}
KIND_LABEL = {"duty": "Pflicht", "sanction": "Sanktion", "consequence": "Rechtsfolge"}


def query(units: list[Unit], question: str) -> list[dict]:
    """Hits for one question: address, label, text (with list items), reason, addressees."""
    role_name = QUESTIONS[question]
    by_address = {unit.address: unit for unit in units}
    sanctioned_by = _sanctioned_by(units)
    hits = []
    for unit in units:
        for role in unit.tags.get("roles", []):
            if role["role"] != role_name:
                continue
            article = _article(unit, by_address)
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
    while unit.parent:
        unit = by_address[unit.parent]
    return unit


def _citation(unit: Unit, by_address: dict[str, Unit]) -> str:
    chain = [unit]
    while chain[0].parent:
        chain.insert(0, by_address[chain[0].parent])
    return " ".join(u.label for u in chain if u.label)
