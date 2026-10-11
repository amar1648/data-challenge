"""Rule-based enrichment run at prepare time: roles and addressees go into Unit.tags.

tags["roles"] is a list of findings, each with the rule that fired and the
phrase that triggered it, so every answer of query can be explained:

    {"role": "applicability", "rule": "heading", "evidence": "Geltungsbereich"}
    {"role": "obligation", "kind": "duty", "rule": "modal", "evidence": "ist verpflichtet",
     "addressees": [{"name": "Arbeitgeber", "type": "regulated", "explicit": true}]}

Sanction provisions additionally get tags["sanctions"] = addresses of the
articles whose infringement they sanction.
"""

import re
from collections import Counter
from dataclasses import dataclass

from challenge.model import Unit


@dataclass(frozen=True)
class Actor:
    name: str
    type: str  # regulated | authority
    pattern: re.Pattern
    feminine_or_plural: bool  # "der <actor>" is then genitive/dative, not a subject
    holder: bool = False  # typically holds rights; its counterpart owes them


def _actor(name, type_, pattern, feminine_or_plural=False, holder=False) -> Actor:
    return Actor(name, type_, re.compile(rf"\b(?:{pattern})\b"), feminine_or_plural, holder)


GENERIC_PROVIDER = "Anbieter"
UNDETERMINED = "unbestimmt"  # obligation recognised, addressee not derivable
# Most specific first: a span matched by one actor is not matched again by a later one.
ACTORS = [
    _actor("Anbieter von Internetzugangsdiensten", "regulated",
           r"Anbieter(?:n|s)? (?:von|der) Internetzugangsdienste(?:n)?|Internetzugangsanbieter(?:n|s)?"),
    _actor("Anbieter öffentlicher elektronischer Kommunikation", "regulated",
           r"Anbieter(?:n|s)? öffentlicher elektronischer Kommunikation"),
    _actor("Anbieter regulierter intra-EU-Kommunikation", "regulated",
           r"Anbieter(?:n|s)? (?:einer )?regulierte[rn]? intra-EU-Kommunikation"),
    _actor(GENERIC_PROVIDER, "regulated", r"Anbieter(?:n|s)?"),
    _actor("Arbeitgeber", "regulated", r"Arbeitgeber(?:n|s)?"),
    _actor("Arbeitnehmer", "regulated", r"Arbeitnehmer(?:n|s)?", holder=True),
    _actor("Auftraggeber", "regulated", r"Auftraggeber(?:n|s)?"),
    _actor("Zwischenmeister", "regulated", r"Zwischenmeister(?:n|s)?"),
    _actor("Nationale Regulierungsbehörden", "authority",
           r"nationalen? Regulierungsbehörden?", feminine_or_plural=True),
    _actor("GEREK", "authority", r"GEREK"),
    _actor("Kommission", "authority", r"Kommission", feminine_or_plural=True),
    _actor("Mitgliedstaaten", "authority", r"Mitgliedstaat(?:en)?", feminine_or_plural=True),
]
ACTOR_BY_NAME = {actor.name: actor for actor in ACTORS}
# Rights holders that are not actors themselves; their counterpart owes the right.
HOLDERS = re.compile(r"\b(?:Verbraucher(?:n|s)?|Endnutzer(?:n|s)?|Arbeitnehmer(?:n|s)?)\b")
COUNTERPART = {"Arbeitnehmer": "Arbeitgeber"}  # Verbraucher/Endnutzer -> the article's provider

# Words before an actor that make it an object or attribute rather than the subject.
_NOT_SUBJECT = {
    "dem", "den", "des", "einem", "einer", "eines", "ihrem", "ihren", "ihres", "seinem", "seinen",
    "von", "vom", "mit", "gegen", "an", "am", "zu", "zur", "zum", "bei", "beim", "für", "nach",
    "auf", "über", "gemäß", "aus", "durch", "zwischen", "unter", "vor", "seitens",
}
# An actor after one of these is the subject of a subordinate or relative clause.
_SUBORDINATE = re.compile(
    r",\s*(?:wenn|dass|daß|soweit|sofern|falls|weil|ob|es sei denn|die|der|das|denen|dem|deren|dessen)\b"
)
_DETERMINERS = {"der", "die", "das", "ein", "eine", "jeder", "jede", "jedes", "diese", "dieser"}

# Obligation wording; checked per clause.
_MODAL = re.compile(
    r"\b(?:ist|sind) verpflichtet\b|\bverpflichtet\b|\bmu(?:ss|ß)\b|\bmüssen\b|\bsoll(?:en)?\b"
    r"|\bstell(?:t|en) (?:\w+ )?sicher\b|\bsicherstellen\b|\bsorg(?:t|en) dafür\b"
    r"|\b(?:darf|dürfen)\b[^;]{0,160}?\b(?:nicht|kein\w*|nur)\b"
)
_ZU_INFINITIVE = re.compile(
    r"\b(?:ist|sind|hat|haben)\b[^,;]*?"
    r"\b(?:zu \w+en|(?:ab|an|auf|aus|bei|ein|fest|her|mit|nach|vor|zurück|weiter|über)zu\w+en)\b"
)
_CLAIM = re.compile(r"\b(?:hat|haben)\b[^.;]*?\bAnspruch\b|\bAnspruch\b[^.;]*?\b(?:hat|haben)\b")
_CLAIM_AGAINST = re.compile(r"\bgegen (?:ihren|seinen|den) (\w+)")
_RECEIVE_FROM = re.compile(r"\berhalten von (?:ihrem|seinem|dem) (\w+)")
# Present indicative with an actor as subject ("Die Anbieter … richten … ein") is an
# obligation in EU drafting, unless the clause is permissive, passive or declarative.
_NOT_A_DUTY = re.compile(
    r"\b(?:kann|können|darf(?! nicht)|steht es \w+ frei|unberührt|hinder\w*|im Sinne|gilt|gelten"
    r"|Anspruch|Recht)\b"
)
# Passive voice is checked only up to the first comma, so that a trailing relative
# clause ("…, dem … beigefügt werden") does not hide the actor of the main clause.
_PASSIVE = re.compile(r"\b(?:wird|werden)\b")
# Verb-first conditional ("Erkrankt ein Arbeitnehmer …, so …"): its subject is not the addressee.
_CONDITIONAL = re.compile(
    r"^(?:[A-ZÄÖÜ]\w*t|Hat|Ist|Sind|Haben|Wird|Werden)\s+(?:sich|der|die|das|ein|eine|einer|es|auf|im)\b"
)
_SANCTION = re.compile(r"\bSanktion\w*|\bGeldbuße\w*|\bordnungswidrig\b|\bStrafe\w*")
_SANCTIONED_ARTICLES = re.compile(
    r"Verstöße gegen (?:die |den )?(?:Artikel|Art\.|§§?)\s*"
    r"(\d+[a-z]?(?:\s*(?:,|und|oder)\s*\d+[a-z]?)*)"
)
_CONSEQUENCE = re.compile(r"nicht vertragskonform\w*|\bunwirksam\b|\bnichtig\b|\bSchadensersatz\b")

_SCOPE_HEADING = re.compile(r"Anwendungsbereich|Geltungsbereich|Begriffsbestimmung|Gegenstand")
_PERSONS = r"(?:Arbeitnehmer|Personen|Beschäftigte\w*|Unternehmen|Anbieter\w*|Verbraucher|Endnutzer)"
_SCOPE_TEXT = re.compile(
    rf"\bJede[rs]? {_PERSONS}\b"
    rf"|\b{_PERSONS}\b[^.;]{{0,40}}\bim Sinne (?:dieses|des) (?:Gesetzes|Verordnung)\b"
    rf"|\bAls {_PERSONS} gelten\b|\bgelten auch Personen\b"
    r"|\bgelten die (?:vorstehenden|folgenden) (?:Bestimmungen|Vorschriften)\b"
    r"|\b(?:gilt|gelten) für\b|\bist anzuwenden auf\b|\bfindet Anwendung auf\b"
)

_ABBREVIATION = re.compile(r"(?:\b(?:Abs|Nr|Art|Buchst|bzw|vgl|ca|S|Bek|BGBl|I|ff|z\. B)|\d)\.$")


def tag_units(units: list[Unit]) -> None:
    """Add roles, addressees and sanction targets to tags; existing tags are kept."""
    by_address = {unit.address: unit for unit in units}
    article_of = {unit.address: _article(unit, by_address) for unit in units}
    article_actor = _dominant_actors(units, article_of)
    act_actor = _act_default_addressee(units)

    for unit in units:
        if unit.type not in ("paragraph", "sentence", "point") or not unit.text:
            continue
        article = by_address[article_of[unit.address]]
        roles: list[dict] = []
        scope_heading = _SCOPE_HEADING.search(article.heading or "")
        if scope_heading:
            roles.append({"role": "applicability", "rule": "heading", "evidence": scope_heading.group(0)})
        else:
            scope_text = _SCOPE_TEXT.search(unit.text)
            if scope_text:
                roles.append({"role": "applicability", "rule": "scope-wording", "evidence": scope_text.group(0)})
            provider = article_actor.get(article.address) or act_actor
            roles.extend(_obligations(unit, provider, act_actor))
        if roles:
            unit.tags["roles"] = _merge(roles)
        sanctioned = _sanctioned(unit, article)
        if sanctioned:
            unit.tags["sanctions"] = sanctioned


def _obligations(unit: Unit, provider: str, act_actor: str) -> list[dict]:
    findings = []
    for clause in _clauses(unit.text):
        subjects = _subjects(clause, provider)
        finding = None
        if _SANCTION.search(clause) and _SANCTIONED_ARTICLES.search(unit.text):
            finding = ("sanction", "sanction", _SANCTION.search(clause).group(0))
        elif _CONSEQUENCE.search(clause):
            finding = ("consequence", "consequence", _CONSEQUENCE.search(clause).group(0))
        elif _CLAIM.search(clause):
            against = _CLAIM_AGAINST.search(clause)
            if against:
                subjects = _subjects(against.group(1), provider, subject_only=False)
            else:
                subjects = _counterparts(clause, provider, act_actor)
                for subject in subjects:
                    subject["explicit"] = False
            finding = ("duty", "claim-counterpart", _CLAIM.search(clause).group(0))
        elif _RECEIVE_FROM.search(clause):
            match = _RECEIVE_FROM.search(clause)
            tail = clause[match.start():]
            subjects = _subjects(tail, provider, subject_only=False)
            finding = ("duty", "receive-from", match.group(0))
        elif _MODAL.search(clause):
            finding = ("duty", "modal", _MODAL.search(clause).group(0))
        elif _ZU_INFINITIVE.search(clause):
            finding = ("duty", "zu-infinitive", _ZU_INFINITIVE.search(clause).group(0))
        elif _actor_present(clause, provider):
            subjects = _actor_present(clause, provider)
            finding = ("duty", "actor-present", subjects[0]["name"])
        elif _conditional_passive(clause):
            # "Erkrankt ein Arbeitnehmer …, so werden … nicht angerechnet": a rule without a
            # named or inferable addressee is reported rather than dropped.
            subjects = [_addressee(UNDETERMINED, explicit=False)]
            finding = ("duty", "conditional-passive", _conditional_passive(clause))
        if not finding:
            continue
        if not subjects:
            subjects = _counterparts(clause, provider, act_actor)
            for subject in subjects:
                subject["explicit"] = False
        kind, rule, evidence = finding
        if len(evidence) > 40:  # long modal spans: keep the frame, e.g. "dürfen … nicht"
            words = evidence.split()
            evidence = f"{words[0]} … {words[-1]}"
        findings.append({
            "role": "obligation", "kind": kind, "rule": rule, "evidence": evidence, "addressees": subjects,
        })
    return findings


def _conditional_passive(clause: str) -> str | None:
    """Evidence if a verb-first condition is followed by a passive main clause."""
    if not _CONDITIONAL.match(clause):
        return None
    main = re.sub(r"^\s*so\s+", "", clause.partition(",")[2])
    passive = _PASSIVE.search(main)
    if not passive or _NOT_A_DUTY.search(main):
        return None
    return f"{passive.group(0)} … {main.split()[-1].rstrip('.')}"


def _actor_present(clause: str, provider: str) -> list[dict]:
    """Subjects of a main clause in present indicative that states what an actor does."""
    if not clause[:1].isupper() or _NOT_A_DUTY.search(clause):
        return []
    if _CONDITIONAL.match(clause):
        _, _, clause = clause.partition(",")
        clause = re.sub(r"^\s*so\s+", "", clause)
    if _PASSIVE.search(clause.split(",")[0]):
        return []
    return _subjects(clause, provider)


def _subjects(clause: str, provider: str, subject_only: bool = True) -> list[dict]:
    """Actors named in the clause, in order; with subject_only, only those in subject position."""
    found, taken = [], []
    for actor in ACTORS:
        for match in actor.pattern.finditer(clause):
            if any(start < match.end() and match.start() < end for start, end in taken):
                continue
            taken.append((match.start(), match.end()))
            if subject_only and (
                _SUBORDINATE.search(clause[: match.start()]) or not _is_subject(clause[: match.start()], actor)
            ):
                continue
            specific = provider in ACTOR_BY_NAME and provider != GENERIC_PROVIDER
            name = provider if actor.name == GENERIC_PROVIDER and specific else actor.name
            found.append((match.start(), name))
    names = []
    for _, name in sorted(found):
        if name not in names:
            names.append(name)
    return [_addressee(name, explicit=True) for name in names]


def _is_subject(before: str, actor: Actor) -> bool:
    words = re.findall(r"[\wäöüß]+", before.lower())[-3:]
    for word in reversed(words):
        if word in _NOT_SUBJECT:
            return False
        if word == "der" and actor.feminine_or_plural:
            return False
        if word in _DETERMINERS:
            return True
        if not word.endswith(("e", "en", "er", "es")):  # stop at the first non-adjective
            return True
    return True


def _counterparts(clause: str, provider: str, act_actor: str) -> list[dict]:
    """Implicit addressee: the counterpart of a rights holder named in the clause, else the default."""
    holder = HOLDERS.search(clause)
    if holder:
        name = holder.group(0)
        for actor_name, counterpart in COUNTERPART.items():
            if name.startswith(actor_name):
                return [_addressee(counterpart, explicit=False)]
        return [_addressee(provider, explicit=False)]
    return [_addressee(provider or act_actor, explicit=False)]


def _addressee(name: str, explicit: bool) -> dict:
    if name == UNDETERMINED:
        return {"name": name, "type": "unknown", "explicit": False}
    actor = ACTOR_BY_NAME.get(name)
    return {"name": name, "type": actor.type if actor else "regulated", "explicit": explicit}


def _dominant_actors(units: list[Unit], article_of: dict[str, str]) -> dict[str, str]:
    """Per article: the most frequently named specific regulated actor (for generic "Anbieter")."""
    counts: dict[str, Counter] = {}
    for unit in units:
        for actor in ACTORS:
            if actor.type != "regulated" or actor.name == GENERIC_PROVIDER:
                continue
            hits = len(actor.pattern.findall(unit.text))
            if hits:
                name = COUNTERPART.get(actor.name, actor.name) if actor.holder else actor.name
                counts.setdefault(article_of[unit.address], Counter())[name] += hits
    return {article: counter.most_common(1)[0][0] for article, counter in counts.items()}


def _act_default_addressee(units: list[Unit]) -> str:
    """Counterpart of the most frequent rights holder in the whole act."""
    counter = Counter()
    for unit in units:
        for match in HOLDERS.finditer(unit.text):
            name = re.sub(r"(?:n|s)$", "", match.group(0))
            counter[COUNTERPART.get(name, GENERIC_PROVIDER)] += 1
    return counter.most_common(1)[0][0] if counter else UNDETERMINED


def _sanctioned(unit: Unit, article: Unit) -> list[str]:
    if not (_SANCTION.search(article.heading or "") or _SANCTION.search(unit.text)):
        return []
    targets = []
    for match in _SANCTIONED_ARTICLES.finditer(unit.text):
        for number in re.findall(r"\d+[a-z]?", match.group(1)):
            if f"art-{number}" not in targets:
                targets.append(f"art-{number}")
    return targets


def _merge(roles: list[dict]) -> list[dict]:
    """One finding per role and kind; addressees and evidence of the clauses are combined."""
    merged: dict[tuple, dict] = {}
    for role in roles:
        key = (role["role"], role.get("kind"))
        if key not in merged:
            merged[key] = {**role, "evidence": [role["evidence"]], "rule": [role["rule"]]}
            continue
        target = merged[key]
        for name in ("evidence", "rule"):
            if role[name] not in target[name]:
                target[name].append(role[name])
        for addressee in role.get("addressees", []):
            if all(addressee["name"] != a["name"] for a in target["addressees"]):
                target["addressees"].append(addressee)
            elif addressee["explicit"]:
                next(a for a in target["addressees"] if a["name"] == addressee["name"])["explicit"] = True
    for role in merged.values():
        # Named addressees beat inferred ones from other clauses of the same unit.
        if any(a["explicit"] for a in role.get("addressees", [])):
            role["addressees"] = [a for a in role["addressees"] if a["explicit"]]
    return list(merged.values())


def _clauses(text: str) -> list[str]:
    """Sentences, split further at ';' and coordinating ', und|oder|sondern'."""
    sentences, start = [], 0
    for match in re.finditer(r"[.;:](?=\s+[A-ZÄÖÜ„])|\n", text):
        if match.group(0) != "\n" and _ABBREVIATION.search(text[start : match.end()]):
            continue
        sentences.append(text[start : match.end()])
        start = match.end()
    sentences.append(text[start:])
    clauses = []
    for sentence in sentences:
        clauses.extend(re.split(r";\s*|,\s*(?=(?:und|oder|sondern)\s)", sentence))
    return [clause.strip() for clause in clauses if clause.strip()]


def _article(unit: Unit, by_address: dict[str, Unit]) -> str:
    """The article (or annex, preamble) a unit belongs to; divisions above it are not part of it."""
    while unit.parent and by_address[unit.parent].type != "division":
        unit = by_address[unit.parent]
    return unit.address
