import unittest

from src.post_change_validation_analysis_wrappers import analyze_trunks
from src.post_change_validation_models import Finding
from src.post_change_validation_trunks import compare_mapped_trunks
from src.post_change_validation_uplinks import parse_trunks


def legacy_analyze_trunks(
    pre_trunk_section: str,
    post_trunk_section: str,
    old_to_new: dict[str, str],
) -> list[Finding]:
    findings: list[Finding] = []
    pre_tr = parse_trunks(pre_trunk_section)
    post_tr = parse_trunks(post_trunk_section)
    trunk_comparison = compare_mapped_trunks(pre_tr, post_tr, old_to_new)
    if trunk_comparison.has_evidence:
        if trunk_comparison.missing:
            findings.append(Finding("WARN", "Trunks", f"{len(trunk_comparison.missing)} pre-change trunk port(s) missing after change.", "\n".join(trunk_comparison.missing)))
        else:
            detail = "\n".join(trunk_comparison.matched_mapped) if trunk_comparison.matched_mapped else ""
            findings.append(Finding("PASS", "Trunks", f"No pre-change trunk ports disappeared; {len(trunk_comparison.matched_mapped)} matched through the port map.", detail))
    return findings


class TrunksFindingExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_matches_legacy_for_warn_missing_mapped_trunk(self):
        pre_section = """
Port        Mode         Encapsulation  Status        Native vlan
Gi1/0/25    on           802.1q         trunking      1
"""
        post_section = """
Port        Mode         Encapsulation  Status        Native vlan
Gi1/0/3     on           802.1q         trunking      1
"""
        old_to_new = {"Gi1/0/25": "Te1/1/1"}

        legacy = legacy_analyze_trunks(pre_section, post_section, old_to_new)
        extracted = analyze_trunks(pre_section, post_section, old_to_new)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["WARN"], [finding.severity for finding in extracted])
        self.assertIn("Gi1/0/25 expected post Te1/1/1", extracted[0].detail)

    def test_extracted_matches_legacy_for_pass_mapped_trunk(self):
        pre_section = """
Port        Mode         Encapsulation  Status        Native vlan
Gi1/0/25    on           802.1q         trunking      1
"""
        post_section = """
Port        Mode         Encapsulation  Status        Native vlan
Te1/1/1     on           802.1q         trunking      1
"""
        old_to_new = {"Gi1/0/25": "Te1/1/1"}

        legacy = legacy_analyze_trunks(pre_section, post_section, old_to_new)
        extracted = analyze_trunks(pre_section, post_section, old_to_new)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["PASS"], [finding.severity for finding in extracted])
        self.assertIn("Gi1/0/25 -> Te1/1/1", extracted[0].detail)

    def test_extracted_matches_legacy_for_pass_same_port_no_mapped_detail(self):
        pre_section = """
Port        Mode         Encapsulation  Status        Native vlan
Po1         on           802.1q         trunking      1
"""
        post_section = """
Port        Mode         Encapsulation  Status        Native vlan
Po1         on           802.1q         trunking      1
"""

        legacy = legacy_analyze_trunks(pre_section, post_section, {})
        extracted = analyze_trunks(pre_section, post_section, {})

        self.assertEqual(legacy, extracted)
        self.assertEqual(["PASS"], [finding.severity for finding in extracted])
        self.assertEqual("", extracted[0].detail)

    def test_extracted_matches_legacy_for_no_trunk_evidence(self):
        legacy = legacy_analyze_trunks("", "", {})
        extracted = analyze_trunks("", "", {})

        self.assertEqual(legacy, extracted)
        self.assertEqual([], extracted)


if __name__ == "__main__":
    unittest.main()
