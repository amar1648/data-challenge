import unittest
from pathlib import Path

from challenge import formex
from challenge.lookup import ref_to_address
from challenge.samples import SAMPLES

GDPR = {lang: SAMPLES / "eu" / "formex" / f"32016R0679_{lang}.fmx.zip" for lang in ("de", "en")}


class Gdpr(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parsed = {lang: formex.parse(path) for lang, path in GDPR.items()}

    def test_act(self):
        for lang, (act, _) in self.parsed.items():
            self.assertEqual((act.work_id, act.version, act.language), ("eu-2016-679", "2016-04-27", lang))

    def test_both_languages_have_exactly_the_same_addresses(self):
        de, en = self.parsed["de"][1], self.parsed["en"][1]
        self.assertEqual([u.address for u in de], [u.address for u in en])
        self.assertEqual([(u.type, u.parent) for u in de], [(u.type, u.parent) for u in en])
        self.assertEqual(len({u.address for u in de}), len(de))

    def test_same_place_in_both_languages(self):
        de = {u.address: u for u in self.parsed["de"][1]}
        en = {u.address: u for u in self.parsed["en"][1]}
        address = ref_to_address("Article 6(1)(f)")
        self.assertEqual(address, ref_to_address("Art. 6 Abs. 1 Buchst. f"))
        self.assertTrue(de[address].text.startswith("die Verarbeitung ist zur Wahrung der berechtigten Interessen"))
        self.assertTrue(en[address].text.startswith("processing is necessary for the purposes of the legitimate interests"))
        self.assertEqual((de["art-6/par-1"].label, en["art-6/par-1"].label), ("(1)", "1."))

    def test_divisions_are_language_neutral(self):
        de = {u.address: u for u in self.parsed["de"][1]}
        en = {u.address: u for u in self.parsed["en"][1]}
        self.assertEqual((de["div-iii/div-2"].label, en["div-iii/div-2"].label), ("Abschnitt 2", "Section 2"))

    def test_quotes_nested_lists_and_dashes(self):
        de = {u.address: u for u in self.parsed["de"][1]}
        self.assertEqual(de["art-4/par-1/pt-16"].text, "„Hauptniederlassung“")
        self.assertEqual(de["art-4/par-1/pt-16/pt-a"].parent, "art-4/par-1/pt-16")
        self.assertEqual(de["art-53/par-1/pt-d1"].text, "vom Parlament,")


if __name__ == "__main__":
    unittest.main()
