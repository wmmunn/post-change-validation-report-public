import unittest

from src.post_change_validation_analysis_wrappers import analyze_command_sections_findings
from src.post_change_validation_models import Finding


def legacy_analyze_command_sections_findings(pre: dict[str, str], post: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    findings.append(Finding("INFO", "Command Sections", f"Pre-change sections found: {len(pre)}", ", ".join(sorted(pre.keys()))))
    findings.append(Finding("INFO", "Command Sections", f"Post-change sections found: {len(post)}", ", ".join(sorted(post.keys()))))
    if not pre or not post:
        findings.append(Finding("FAIL", "Command Sections", "One or both logs had zero command sections parsed.", "Check whether command prompts or script formatting changed. v8 supports prompt-prefixed lines such as switch#show int status."))
    return findings


class CommandSectionsFindingExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_matches_legacy_for_info_both_sections_present(self):
        pre = {"show version": "pre version", "show interfaces status": "pre if status"}
        post = {"show version": "post version", "show logging": "post logs"}

        legacy = legacy_analyze_command_sections_findings(pre, post)
        extracted = analyze_command_sections_findings(pre, post)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["INFO", "INFO"], [finding.severity for finding in extracted])
        self.assertIn("Pre-change sections found: 2", extracted[0].finding)
        self.assertIn("Post-change sections found: 2", extracted[1].finding)

    def test_extracted_matches_legacy_for_fail_empty_pre(self):
        pre: dict[str, str] = {}
        post = {"show version": "post version"}

        legacy = legacy_analyze_command_sections_findings(pre, post)
        extracted = analyze_command_sections_findings(pre, post)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["INFO", "INFO", "FAIL"], [finding.severity for finding in extracted])
        self.assertEqual("One or both logs had zero command sections parsed.", extracted[2].finding)

    def test_extracted_matches_legacy_for_fail_empty_post(self):
        pre = {"show version": "pre version"}
        post: dict[str, str] = {}

        legacy = legacy_analyze_command_sections_findings(pre, post)
        extracted = analyze_command_sections_findings(pre, post)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["INFO", "INFO", "FAIL"], [finding.severity for finding in extracted])


if __name__ == "__main__":
    unittest.main()
