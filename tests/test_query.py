import json
import unittest

from challenge import de_gii, eurlex_html
from challenge.evaluate import GOLD_DIR, evaluate
from challenge.model import Unit, unit_hash
from challenge.query import group_by_addressee, query
from challenge.samples import DE_DIR, EU_CONSOLIDATED
from challenge.tagging import tag_units


def _prepared(act_id: str) -> list[Unit]:
    if act_id == "de-burlg":
        _, units = de_gii.parse(DE_DIR / "burlg.xml", act_id)
    else:
        _, units = eurlex_html.parse(EU_CONSOLIDATED)
    tag_units(units)
    return units


def _unit(address: str, text: str, heading: str | None = None) -> list[Unit]:
    article = Unit("art-1", "§ 1", "article", heading, "", None, 0, unit_hash(heading, ""), "x")
    unit = Unit(address, "", "paragraph", None, text, "art-1", 1, unit_hash(None, text), "x")
    return [article, unit]


def _addressees(units: list[Unit], address: str) -> list[tuple[str, bool]]:
    unit = next(u for u in units if u.address == address)
    return [
        (a["name"], a["explicit"])
        for role in unit.tags.get("roles", [])
        if role["role"] == "obligation"
        for a in role["addressees"]
    ]


class Rules(unittest.TestCase):
    def test_subject_of_a_subordinate_clause_is_not_the_addressee(self):
        units = _unit("art-1/par-1", "Der Urlaub ist zu gewähren, wenn der Arbeitnehmer dies verlangt.")
        tag_units(units)
        self.assertEqual(_addressees(units, "art-1/par-1"), [("Arbeitgeber", False)])

    def test_verb_first_conditional_keeps_the_rule_with_undetermined_addressee(self):
        units = _unit(
            "art-1/par-1",
            "Erkrankt ein Arbeitnehmer während des Urlaubs, so werden die Tage nicht angerechnet.",
        )
        tag_units(units)
        # The subject of the condition is not the addressee; the rule is reported anyway.
        self.assertEqual(_addressees(units, "art-1/par-1"), [("unbestimmt", False)])

    def test_claim_against_names_the_counterpart(self):
        units = _unit("art-1/par-1", "Zwischenmeister haben gegen ihren Auftraggeber Anspruch auf die Beträge.")
        tag_units(units)
        self.assertEqual(_addressees(units, "art-1/par-1"), [("Auftraggeber", True)])

    def test_dative_actor_is_not_the_subject(self):
        units = _unit("art-1/par-1", "Der Arbeitgeber ist verpflichtet, dem Arbeitnehmer eine Bescheinigung auszuhändigen.")
        tag_units(units)
        self.assertEqual(_addressees(units, "art-1/par-1"), [("Arbeitgeber", True)])

    def test_permission_is_not_a_duty(self):
        units = _unit("art-1/par-1", "Die Mitgliedstaaten können nationale Maßnahmen aufrechterhalten.")
        tag_units(units)
        self.assertNotIn("roles", units[1].tags)

    def test_readings_of_the_model_answer(self):
        units = _unit("art-1/par-1", "Der Arbeitgeber ist verpflichtet, Urlaub zu gewähren.")
        tag_units(units)
        units[1].tags["model"] = {
            "role": "none", "addressees": [], "addressee_explicit": False, "kind": "none",
            "model": "test", "prompt_version": "v0",
        }
        self.assertEqual(len(query(units, "obligations", "rules")), 1)
        self.assertEqual(query(units, "obligations", "combined"), [])  # candidate: the model decides
        units[1].tags["model"].update(role="obligation", kind="none")
        hit = query(units, "obligations", "combined")[0]
        self.assertEqual(hit["addressees"], [{"name": "unbestimmt", "type": "unknown", "explicit": False}])
        self.assertEqual(hit["kind"], "duty")  # kind stays with the rules

    def test_combined_ignores_model_answers_outside_the_candidates(self):
        units = _unit("art-1/par-1", "Der Urlaub beträgt jährlich mindestens 24 Werktage.")
        tag_units(units)
        units[1].tags["model"] = {
            "role": "obligation", "addressees": [{"name": "Arbeitgeber", "type": "regulated"}],
            "addressee_explicit": False, "kind": "duty", "model": "test", "prompt_version": "v0",
        }
        self.assertEqual(query(units, "obligations", "combined"), [])
        self.assertEqual(query(units, "obligations", "model")[0]["addressees"][0]["name"], "Arbeitgeber")

    def test_hybrid_replaces_only_inferred_addressees(self):
        model = {
            "role": "obligation", "addressees": [{"name": "Das Unternehmen", "type": "regulated"}],
            "addressee_explicit": True, "kind": "duty", "model": "test", "prompt_version": "v0",
        }
        inferred = _unit("art-1/par-1", "Der Urlaub ist zu gewähren.")
        named = _unit("art-1/par-1", "Der Arbeitgeber ist verpflichtet, Urlaub zu gewähren.")
        for units in (inferred, named):
            tag_units(units)
            units[1].tags["model"] = dict(model)
        hit = query(inferred, "obligations")[0]  # hybrid is the default reading
        self.assertEqual(hit["addressees"], [
            {"name": "Unternehmen", "type": "regulated", "explicit": False, "source": "model"},
        ])
        self.assertEqual(query(named, "obligations")[0]["addressees"][0]["name"], "Arbeitgeber")
        # A model obligation without addressee is not taken over.
        inferred[1].tags["model"]["addressees"] = []
        self.assertEqual(query(inferred, "obligations")[0]["addressees"][0]["name"], "unbestimmt")

    def test_query_only_reads_tags(self):
        units = _unit("art-1/par-1", "Der Arbeitgeber ist verpflichtet, Urlaub zu gewähren.")
        self.assertEqual(query(units, "obligations"), [])


class EuQuery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.units = _prepared("eu-2015-2120")
        cls.hits = query(cls.units, "obligations")

    def test_sanction_targets(self):
        unit = next(u for u in self.units if u.address == "art-6/par-1")
        self.assertEqual(unit.tags["sanctions"], ["art-3", "art-4", "art-5", "art-5a"])

    def test_duties_point_to_their_sanction(self):
        hit = next(h for h in self.hits if h["address"] == "art-4/par-2")
        self.assertEqual(hit["sanctioned_by"], ["art-6/par-1"])

    def test_regulated_groups_come_first(self):
        types = [addressee["type"] for addressee, _ in group_by_addressee(self.hits)]
        self.assertEqual(types, sorted(types, key=["regulated", "authority"].index))

    def test_open_obligation_includes_its_points(self):
        hit = next(h for h in self.hits if h["address"] == "art-3/par-3")
        self.assertIn("art-3/par-3/pt-c", hit["covered"])
        closed = next(h for h in self.hits if h["address"] == "art-4/par-2")
        self.assertEqual(closed["covered"], ["art-4/par-2"])


class GoldRegression(unittest.TestCase):
    """Floors at the level reached when the rules were written; a drop fails the test."""

    FLOORS = {
        "de-burlg": {"applicability": (1.0, 1.0), "obligations": (0.89, 1.0)},
        "eu-2015-2120": {"applicability": (1.0, 1.0), "obligations": (0.95, 1.0)},
    }

    def test_recall_and_precision(self):
        for act_id, floors in self.FLOORS.items():
            gold = json.loads((GOLD_DIR / f"{act_id}.json").read_text(encoding="utf-8"))
            report = evaluate(gold, _prepared(act_id))
            for question, (recall, precision) in floors.items():
                with self.subTest(act=act_id, question=question):
                    self.assertGreaterEqual(report[question]["recall"], recall)
                    self.assertGreaterEqual(report[question]["precision"], precision)
                    self.assertLess(report[question]["text_share"], 0.7)

    def test_ancestor_hits_do_not_count(self):
        gold = {
            "applicability": [{"address": "art-2/par-1"}],
            "obligations": [],
            "borderline": [],
        }
        units = _prepared("de-burlg")
        for unit in units:
            unit.tags.pop("roles", None)
        # Only the whole article is returned: it contains the gold unit but must not score.
        article = next(u for u in units if u.address == "art-2")
        article.tags["roles"] = [{"role": "applicability", "rule": ["test"], "evidence": ["x"]}]
        report = evaluate(gold, units)
        self.assertEqual(report["applicability"]["recall"], 0.0)
        self.assertEqual(report["applicability"]["precision"], 0.0)


if __name__ == "__main__":
    unittest.main()
