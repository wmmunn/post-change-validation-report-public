import unittest

import re

from src.post_change_validation_analysis_wrappers import analyze_dot1x_findings
from src.post_change_validation_models import Finding


def legacy_analyze_dot1x_findings(dot1x_section: str) -> list[Finding]:
    findings: list[Finding] = []
    dot = dot1x_section
    if dot:
        if re.search(r"auth|unauth|mab|dot1x|authorized", dot, re.I):
            findings.append(Finding("INFO", "Dot1x", "Dot1x summary section found.", ""))
        else:
            findings.append(Finding("INFO", "Dot1x", "Dot1x summary section found, but no common auth state keywords detected.", ""))
    return findings


class Dot1xFindingExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_matches_legacy_for_info_with_auth_keywords(self):
        section = "Interface  Auth Method  Status\nGi1/0/3    dot1x        authorized"

        legacy = legacy_analyze_dot1x_findings(section)
        extracted = analyze_dot1x_findings(section)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["INFO"], [finding.severity for finding in extracted])
        self.assertEqual("Dot1x summary section found.", extracted[0].finding)

    def test_extracted_matches_legacy_for_info_without_auth_keywords(self):
        section = "Port-based network access control is enabled on the switch."

        legacy = legacy_analyze_dot1x_findings(section)
        extracted = analyze_dot1x_findings(section)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["INFO"], [finding.severity for finding in extracted])
        self.assertEqual(
            "Dot1x summary section found, but no common auth state keywords detected.",
            extracted[0].finding,
        )

    def test_extracted_matches_legacy_for_empty_section(self):
        legacy = legacy_analyze_dot1x_findings("")
        extracted = analyze_dot1x_findings("")

        self.assertEqual(legacy, extracted)
        self.assertEqual([], extracted)


if __name__ == "__main__":
    unittest.main()
