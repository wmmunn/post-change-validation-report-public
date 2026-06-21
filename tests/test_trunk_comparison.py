import unittest

from src.post_change_validation_trunks import compare_mapped_trunks


class TrunkComparisonTests(unittest.TestCase):
    def test_mapped_trunk_pass_records_mapped_detail(self):
        result = compare_mapped_trunks(
            {"Gi1/0/25"},
            {"Te1/1/1"},
            {"Gi1/0/25": "Te1/1/1"},
        )

        self.assertTrue(result.has_evidence)
        self.assertEqual(["Gi1/0/25 -> Te1/1/1"], result.matched_mapped)
        self.assertEqual([], result.missing)

    def test_same_port_trunk_pass_has_no_mapped_detail(self):
        result = compare_mapped_trunks(
            {"Po1"},
            {"Po1"},
            {},
        )

        self.assertTrue(result.has_evidence)
        self.assertEqual([], result.matched_mapped)
        self.assertEqual([], result.missing)

    def test_missing_mapped_trunk_reports_expected_post_port(self):
        result = compare_mapped_trunks(
            {"Gi2/0/52"},
            {"Te1/1/1"},
            {"Gi2/0/52": "Te2/1/8"},
        )

        self.assertTrue(result.has_evidence)
        self.assertEqual([], result.matched_mapped)
        self.assertEqual(["Gi2/0/52 expected post Te2/1/8"], result.missing)

    def test_no_trunk_evidence_is_quiet(self):
        result = compare_mapped_trunks(set(), set(), {})

        self.assertFalse(result.has_evidence)
        self.assertEqual([], result.matched_mapped)
        self.assertEqual([], result.missing)


if __name__ == "__main__":
    unittest.main()
