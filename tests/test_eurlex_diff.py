import re
import unittest

from challenge import eurlex_html
from challenge.diff import ADDED, MODIFIED, REMOVED, UNCHANGED, diff, text_diff
from challenge.samples import EU_CONSOLIDATED, EU_ORIGINAL


def _punctuation_only(change: dict) -> bool:
    words = change["text_diff"]["inserted"] + change["text_diff"]["deleted"]
    stripped = {re.sub(r"[.,;:]+$", "", word) for word in words}
    return len(stripped) == 1 and len(words) == 2


class Parser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_act, cls.old = eurlex_html.parse(EU_ORIGINAL)
        cls.new_act, cls.new, cls.deletions = eurlex_html.parse_with_deletions(EU_CONSOLIDATED)
        cls.old_by = {u.address: u for u in cls.old}
        cls.new_by = {u.address: u for u in cls.new}

    def test_acts(self):
        self.assertEqual((self.old_act.work_id, self.old_act.version), ("eu-2015-2120", "2015-11-25"))
        self.assertEqual((self.new_act.work_id, self.new_act.version), ("eu-2015-2120", "2024-05-15"))

    def test_quoted_text_in_article_8_is_not_a_paragraph_of_article_1(self):
        self.assertNotIn("art-1/par-3", self.old_by)
        self.assertIn("Richtlinie 2002/22/EG", self.old_by["art-8/par-1"].text)
        self.assertIn("„(3) Im Rahmen nationaler Maßnahmen", self.old_by["art-8/par-1"].text)

    def test_both_markups_give_the_same_structure(self):
        for address in ("art-3/par-3/pt-c", "art-4/par-1/pt-e", "art-10/par-2/pt-d"):
            self.assertEqual(self.old_by[address].content_hash, self.new_by[address].content_hash)

    def test_footnote_references_are_dropped(self):
        # The OJ numbers this footnote (12), the consolidated text (5).
        self.assertEqual(self.old_by["art-10/par-4"].text, self.new_by["art-10/par-4"].text)
        self.assertIn("der Kommission, die die technische", self.new_by["art-10/par-4"].text)

    def test_heading_outside_the_heading_class(self):
        self.assertEqual(self.new_by["art-5b"].heading, "Ausschussverfahren")

    def test_list_inside_a_paragraph(self):
        self.assertEqual(self.new_by["art-5a/par-10/pt-f"].parent, "art-5a/par-10")

    def test_inline_marker(self):
        unit = self.new_by["art-10/par-5"]
        self.assertEqual(unit.text, "Die Geltungsdauer von Artikel 5a endet am 30. Juni 2032.")
        self.assertEqual(
            unit.tags["amended_by"],
            [
                {"act": "32018R1971", "marker": "M2", "action": "INSERTED"},
                {"act": "32024R1309", "marker": "M3", "action": "REPLACED"},
            ],
        )


class Diff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        old_act, old = eurlex_html.parse(EU_ORIGINAL)
        new_act, cls.new, cls.deletions = eurlex_html.parse_with_deletions(EU_CONSOLIDATED)
        cls.result = diff(old_act, old, new_act, cls.new)
        cls.by = {entry["address"]: entry for entry in cls.result["changes"]}

    def test_expected_changes(self):
        for address in ("art-1/par-3", "art-5a", "art-5b", "art-5a/par-10/pt-a", "art-10/par-5"):
            self.assertEqual(self.by[address]["change"], ADDED, address)
        for address in ("art-8", "art-8/par-1"):
            self.assertEqual(self.by[address]["change"], REMOVED, address)
        self.assertEqual(self.by["art-6/par-1"]["change"], MODIFIED)
        self.assertEqual(self.by["art-1/par-1"]["change"], UNCHANGED)

    def test_removed_units_keep_their_position(self):
        order = [entry["address"] for entry in self.result["changes"]]
        self.assertEqual(order[order.index("art-6/par-1") + 1 : order.index("art-9")], ["art-8", "art-8/par-1"])

    def test_text_diff(self):
        inserted = self.by["art-6/par-1"]["text_diff"]["inserted"]
        self.assertEqual(len(inserted), 1)
        self.assertTrue(inserted[0].startswith("Die Mitgliedstaaten erlassen für Verstöße gegen Artikel 5a"))
        self.assertEqual(self.by["art-6/par-1"]["text_diff"]["deleted"], [])

    def test_summary_counts_all_entries(self):
        self.assertEqual(sum(self.result["summary"].values()), len(self.result["changes"]))


class MarkerCrossCheck(unittest.TestCase):
    """The consolidated text marks amendments with ▼/►◄ markers; the hash diff must agree."""

    @classmethod
    def setUpClass(cls):
        old_act, old = eurlex_html.parse(EU_ORIGINAL)
        new_act, cls.new, cls.deletions = eurlex_html.parse_with_deletions(EU_CONSOLIDATED)
        cls.changes = diff(old_act, old, new_act, cls.new)["changes"]
        cls.marked = {
            unit.address
            for unit in cls.new
            if any(tag["action"] in ("INSERTED", "REPLACED") for tag in unit.tags.get("amended_by", []))
        }

    def test_every_added_or_modified_unit_is_marked(self):
        for entry in self.changes:
            if entry["change"] == ADDED:
                self.assertIn(entry["address"], self.marked)
            elif entry["change"] == MODIFIED and entry["address"] not in self.marked:
                # Consolidators do not mark punctuation, e.g. "bietet." -> "bietet;"
                # when new points are appended after Art. 2 point 2.
                self.assertTrue(_punctuation_only(entry), entry["address"])

    def test_every_marked_unit_is_added_or_modified(self):
        status = {entry["address"]: entry["change"] for entry in self.changes}
        for address in self.marked:
            self.assertIn(status[address], (ADDED, MODIFIED), address)

    def test_removed_units_sit_at_a_deleted_marker(self):
        deleted_after = {after for after, marker in self.deletions}
        order = [entry["address"] for entry in self.changes]
        removed = [i for i, entry in enumerate(self.changes) if entry["change"] == REMOVED]
        self.assertTrue(removed)
        for index in removed:
            before = next(order[i] for i in range(index - 1, -1, -1) if self.changes[i]["change"] != REMOVED)
            self.assertIn(before, deleted_after, order[index])


class TextDiff(unittest.TestCase):
    def test_words(self):
        self.assertEqual(
            text_diff("endet am 30. Juni 2025.", "endet am 30. Juni 2032."),
            {"inserted": ["2032."], "deleted": ["2025."]},
        )


if __name__ == "__main__":
    unittest.main()
