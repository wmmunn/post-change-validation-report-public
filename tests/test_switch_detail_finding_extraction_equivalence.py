import unittest

import re

from src.post_change_validation_analysis_wrappers import analyze_switch_detail_findings
from src.post_change_validation_models import Finding


def legacy_analyze_switch_detail_findings(switch_detail_section: str) -> list[Finding]:
    findings: list[Finding] = []
    sw = switch_detail_section
    if sw:
        if re.search(r"active|ready|standby", sw, re.I):
            findings.append(Finding("PASS", "Switch Detail", "Post-change switch detail section is present and contains active/ready/standby wording.", ""))
        else:
            findings.append(Finding("INFO", "Switch Detail", "Post-change switch detail section is present.", ""))
    return findings


class SwitchDetailFindingExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_matches_legacy_for_pass_active_wording(self):
        section = "Switch/Stack Mac Address : 0011.2233.4455\nSwitch#   Role    Mac Address     Priority Version  State\n*1       Active   0011.2233.4455     15     V01     Ready"

        legacy = legacy_analyze_switch_detail_findings(section)
        extracted = analyze_switch_detail_findings(section)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["PASS"], [finding.severity for finding in extracted])

    def test_extracted_matches_legacy_for_info_without_keywords(self):
        section = "Switch/Stack Mac Address : 0011.2233.4455\nMember count: 1"

        legacy = legacy_analyze_switch_detail_findings(section)
        extracted = analyze_switch_detail_findings(section)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["INFO"], [finding.severity for finding in extracted])
        self.assertEqual("Post-change switch detail section is present.", extracted[0].finding)

    def test_extracted_matches_legacy_for_empty_section(self):
        legacy = legacy_analyze_switch_detail_findings("")
        extracted = analyze_switch_detail_findings("")

        self.assertEqual(legacy, extracted)
        self.assertEqual([], extracted)


if __name__ == "__main__":
    unittest.main()
