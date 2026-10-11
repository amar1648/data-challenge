import json
import tempfile
import unittest
from pathlib import Path

from challenge import de_gii
from challenge.lookup import find, lookup, ref_to_address
from challenge.model import read_act, unit_hash, write_act
from challenge.samples import DE_DIR


class RefParsing(unittest.TestCase):
    def test_spellings(self):
        cases = {
            "§ 3 Abs. 1": "art-3/par-1",
            "§3 Abs.1": "art-3/par-1",
            "§3Abs.1": "art-3/par-1",
            "§ 3 Absatz 1": "art-3/par-1",
            "§ 15a": "art-15a",
            "§ 5 Abs. 1 Buchst. a": "art-5/par-1/pt-a",
            "§ 12 Nr. 2": "art-12/pt-2",
            "Art. 3(1)(a)": "art-3/par-1/pt-a",
            "art-3/par-1": "art-3/par-1",
        }
        for ref, address in cases.items():
            with self.subTest(ref=ref):
                self.assertEqual(ref_to_address(ref), address)

    def test_rejects_unknown(self):
        with self.assertRaises(SystemExit):
            ref_to_address("Satz 1")


class Burlg(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.act, cls.units = de_gii.parse(DE_DIR / "burlg.xml", "de-burlg")
        cls.by_address = {unit.address: unit for unit in cls.units}

    def test_act(self):
        self.assertEqual(self.act.version, "2013-04-20")
        self.assertEqual(self.act.language, "de")

    def test_addresses_unique_and_ordered(self):
        self.assertEqual(len(self.by_address), len(self.units))
        self.assertEqual([u.order for u in self.units], list(range(len(self.units))))

    def test_paragraph(self):
        unit = self.by_address["art-3/par-1"]
        self.assertEqual(unit.label, "(1)")
        self.assertEqual(unit.text, "Der Urlaub beträgt jährlich mindestens 24 Werktage.")
        self.assertEqual(unit.source_anchor, "BJNR000020963BJNE000401308:P[1]")
        self.assertEqual(unit.content_hash, unit_hash(None, unit.text))

    def test_single_unnumbered_paragraph_is_par_1(self):
        unit = self.by_address["art-1/par-1"]
        self.assertEqual(unit.label, "")
        self.assertTrue(unit.text.startswith("Jeder Arbeitnehmer"))

    def test_points_are_separate_units(self):
        intro = self.by_address["art-5/par-1"]
        self.assertNotIn("Wartezeit aus dem", intro.text)
        self.assertEqual(self.by_address["art-5/par-1/pt-c"].parent, "art-5/par-1")
        # § 12 has one unnumbered Absatz; "§ 12 Nr. 2" still resolves.
        self.assertEqual(find(self.units, "art-12/pt-2").address, "art-12/par-1/pt-2")

    def test_heading_is_part_of_hash(self):
        unit = self.by_address["art-3"]
        self.assertNotEqual(unit.content_hash, unit_hash(None, ""))

    def test_refs_stay_inside_the_act(self):
        self.assertEqual(self.by_address["art-2/par-1"].refs, ["art-12"])
        self.assertEqual(self.by_address["art-7/par-3"].refs, ["art-5/par-1/pt-a"])
        # "§ 13 Abs. 1 des Dritten Überleitungsgesetzes" is another law.
        self.assertEqual(self.by_address["art-14/par-1"].refs, [])
        # "§§ 4 bis 6" is a range and deliberately not resolved.
        self.assertEqual(self.by_address["art-12/par-1"].refs, ["art-11"])

    def test_round_trip_and_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_act(Path(tmp), self.act, self.units)
            self.assertEqual(path.relative_to(tmp).as_posix(), "de-burlg/2013-04-20_de.json")
            self.assertEqual(read_act(path), (self.act, self.units))
            self.assertEqual(json.loads(path.read_text())["units"][0]["tags"], {})
            output = lookup(Path(tmp), "de-burlg", "§3 Abs.1", "de")
        self.assertIn("[art-3/par-1]", output)
        self.assertIn("Der Urlaub beträgt jährlich mindestens 24 Werktage.", output)


if __name__ == "__main__":
    unittest.main()
