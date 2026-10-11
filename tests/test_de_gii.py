import unittest

from challenge import de_gii
from challenge.lookup import find, ref_to_address
from challenge.samples import german_acts
from challenge.tagging import tag_units


class AllGermanActs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parsed = {
            act_id: de_gii.parse_with_issues(path, act_id) for act_id, path in german_acts().items()
        }

    def unit(self, act_id: str, address: str):
        return next(u for u in self.parsed[act_id][1] if u.address == address)

    def test_every_act_parses_with_unique_addresses(self):
        self.assertEqual(len(self.parsed), 10)
        for act_id, (_, units, issues) in self.parsed.items():
            with self.subTest(act=act_id):
                self.assertGreater(len(units), 0)
                self.assertEqual(len({u.address for u in units}), len(units))
                self.assertNotIn("Doppelte Adresse, mit ~N unterschieden", issues)
                known = {u.address for u in units}
                self.assertTrue(all(u.parent is None or u.parent in known for u in units))

    def test_version_prefers_stand_over_neufassung(self):
        self.assertEqual(self.parsed["de-bgb"][0].version, "2026-07-23")
        self.assertEqual(self.parsed["de-lksg"][0].version, "2021-07-16")
        self.assertIn("Kein Stand im Kopf, Version = Ausfertigungsdatum", self.parsed["de-lksg"][2])

    def test_divisions_are_parents_but_not_part_of_the_address(self):
        article = self.unit("de-lksg", "art-1")
        self.assertEqual(article.parent, "div-abschnitt-1")
        self.assertEqual(self.unit("de-lksg", "div-abschnitt-1").heading, "Allgemeine Bestimmungen")
        # BImSchG reuses the code 020030 for two siblings.
        self.assertTrue(self.unit("de-bimschg", "div-zweiter-teil/div-vierter-abschnitt"))

    def test_lists_per_sentence(self):
        # LkSG § 1 Abs. 1: "Satz 1 Nummer 1" and "Satz 2 Nummer 1".
        self.assertTrue(self.unit("de-lksg", "art-1/par-1/sen-1/pt-1").text.startswith("ihre Hauptverwaltung"))
        self.assertTrue(self.unit("de-lksg", "art-1/par-1/sen-2/pt-1").text.startswith("eine Zweigniederlassung"))
        self.assertEqual(ref_to_address("§ 1 Abs. 1 Satz 2 Nr. 1"), "art-1/par-1/sen-2/pt-1")
        # BImSchG § 52 Abs. 1 refers to its second list as "Satz 5".
        self.assertTrue(self.unit("de-bimschg", "art-52/par-1/sen-5/pt-1"))

    def test_each_sentence_carries_its_own_lead_in(self):
        sentence_1 = self.unit("de-lksg", "art-1/par-1/sen-1")
        sentence_2 = self.unit("de-lksg", "art-1/par-1/sen-2")
        self.assertEqual(sentence_1.text, "Dieses Gesetz ist anzuwenden auf Unternehmen ungeachtet ihrer Rechtsform, die")
        self.assertTrue(sentence_2.text.startswith("Abweichend von Satz 1 Nummer 1"))
        self.assertEqual(self.unit("de-lksg", "art-1/par-1/sen-2/pt-1").parent, "art-1/par-1/sen-2")
        # Sentences without a list stay with the Absatz.
        self.assertTrue(self.unit("de-lksg", "art-1/par-1").text.startswith("Ab dem 1. Januar 2024"))
        # A sentence interrupted by its list keeps both halves (BDSG § 4 Abs. 1 Satz 1).
        self.assertIn("soweit sie\nerforderlich ist", self.unit("de-bdsg_2018", "art-4/par-1/sen-1").text)

    def test_text_after_a_list_is_not_glued_to_the_lead_in(self):
        text = self.unit("de-lksg", "art-7/par-3").text
        self.assertIn("nur geboten, wenn\nDie bloße Tatsache", text)
        self.assertIn("dass der Zahler\nhat.", self.unit("de-bgb", "art-675w/par-1").text)

    def test_unlabelled_block_stays_in_place(self):
        text = self.unit("de-gg", "art-56/par-1").text
        self.assertLess(text.index("Ich schwöre"), text.index("Der Eid kann auch"))

    def test_one_list_split_into_two_blocks_keeps_plain_numbers(self):
        # BDSG § 33 Abs. 1: "1." in one <DL>, "2." in the next.
        self.assertTrue(self.unit("de-bdsg_2018", "art-33/par-1/pt-1"))
        self.assertTrue(self.unit("de-bdsg_2018", "art-33/par-1/pt-2"))

    def test_footnote_only_paragraph_is_skipped(self):
        self.assertTrue(self.unit("de-bgb", "art-14/par-1").text.startswith("Unternehmer ist"))

    def test_dash_lists_and_unlabelled_blocks(self):
        self.assertEqual(self.unit("de-bimschg", "art-1/par-2/pt-d1").label, "–")
        self.assertIn("Ich schwöre", self.unit("de-gg", "art-56/par-1").text)

    def test_special_parts(self):
        self.assertEqual(self.unit("de-gg", "preamble").label, "Präambel")
        self.assertEqual(self.unit("de-gg", "formula").label, "Eingangsformel")
        self.assertEqual(self.unit("de-enefg", "anx-1").type, "annex")
        self.assertIn("§§ 3 bis 6", self.parsed["de-bgb"][2]["Weggefallene Sammelbezeichnung übersprungen"])

    def test_division_heading_does_not_trigger_the_scope_rule(self):
        # GwG § 3a "Risikobasierter Ansatz" sits directly in Abschnitt 1 "Begriffsbestimmungen,
        # Verpflichtete und risikobasierter Ansatz"; that heading must not make it a scope provision.
        units = self.parsed["de-gwg_2017"][1]
        tag_units(units)
        self.assertEqual(self.unit("de-gwg_2017", "art-3a").parent, "div-abschnitt-1")
        roles = [r["role"] for r in self.unit("de-gwg_2017", "art-3a/par-1").tags.get("roles", [])]
        self.assertNotIn("applicability", roles)

    def test_lookup_skips_the_implicit_paragraph(self):
        units = self.parsed["de-burlg"][1]
        self.assertEqual(find(units, "art-12/pt-2").address, "art-12/par-1/pt-2")


if __name__ == "__main__":
    unittest.main()
