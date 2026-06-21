import unittest

from src.post_change_validation_models import canonical_interface_name, norm_interface


class CanonicalInterfaceNameTests(unittest.TestCase):
    def test_expanded_five_gig_maps_to_fi_short_form(self):
        self.assertEqual("Fi2/0/1", canonical_interface_name("FiveGigabitEthernet2/0/1"))
        self.assertEqual("Fi2/0/1", canonical_interface_name("Fi2/0/1"))

    def test_case_insensitive_short_prefixes(self):
        self.assertEqual("Gi2/0/1", canonical_interface_name("gi2/0/1"))
        self.assertEqual("Gi2/0/1", canonical_interface_name("GigabitEthernet2/0/1"))

    def test_extra_abbreviations_not_handled_by_norm_interface(self):
        self.assertEqual("Fi2/0/1", canonical_interface_name("FiveGigE2/0/1"))
        self.assertEqual("Te2/0/1", canonical_interface_name("TenGigE2/0/1"))

    def test_norm_interface_behavior_is_unchanged(self):
        self.assertEqual(norm_interface("Gi1/0/1"), canonical_interface_name("Gi1/0/1"))
        self.assertEqual(norm_interface("GigabitEthernet1/0/1"), norm_interface("Gi1/0/1"))


if __name__ == "__main__":
    unittest.main()
