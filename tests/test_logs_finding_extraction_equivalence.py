import re
import unittest

from src.post_change_validation_analysis_wrappers import analyze_logs
from src.post_change_validation_models import Finding


HIGH_RISK_LOG_PAT = re.compile(r"DUPADDR|ERR-?DISABLE|PM-4-ERR_DISABLE|LOOP|UDLD|SPANTREE.*(?:BLOCK|LOOP|INCONSIST|ROOTGUARD|BPDU)|AUTHMGR.*FAIL|MAB.*FAIL|DOT1X.*FAIL|SECURITY", re.I)


def legacy_analyze_logs(post_logging_section: str) -> list[Finding]:
    high = [ln.strip() for ln in post_logging_section.splitlines() if HIGH_RISK_LOG_PAT.search(ln)]
    if high:
        return [Finding("INFO", "Logs", f"Log review recommended: {len(high)} message(s); correlate with approved change activity.", "\n".join(high[:80]))]
    return [Finding("PASS", "Logs", "No high-risk log keywords found.", "")]


class LogsFindingExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_analyze_logs_matches_legacy_for_pass_no_keywords(self):
        post_logs = """
Jun 20 12:03:04 %LINEPROTO-5-UPDOWN: Line protocol on Interface Gi1/0/1, changed state to up
Jun 20 12:03:05 %LINK-3-UPDOWN: Interface GigabitEthernet1/0/1, changed state to up
"""

        legacy = legacy_analyze_logs(post_logs)
        extracted = analyze_logs(post_logs)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["PASS"], [finding.severity for finding in extracted])
        self.assertEqual("No high-risk log keywords found.", extracted[0].finding)

    def test_extracted_analyze_logs_matches_legacy_for_info_high_risk_match(self):
        post_logs = """
Jun 20 12:03:04 %LINEPROTO-5-UPDOWN: Line protocol on Interface Gi1/0/1, changed state to up
Jun 20 12:03:05 %PM-4-ERR_DISABLE: err-disable caused by loop on Gi1/0/3
Jun 20 12:03:06 %AUTHMGR-5-FAIL: Authorization failed for client aabb.ccdd.eeff on Gi1/0/4
"""

        legacy = legacy_analyze_logs(post_logs)
        extracted = analyze_logs(post_logs)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["INFO"], [finding.severity for finding in extracted])
        self.assertIn("Log review recommended: 2 message(s)", extracted[0].finding)
        self.assertIn("%PM-4-ERR_DISABLE", extracted[0].detail)
        self.assertIn("%AUTHMGR-5-FAIL", extracted[0].detail)

    def test_extracted_analyze_logs_matches_legacy_for_info_truncation_at_80_lines(self):
        post_logs = "\n".join(
            f"Jun 20 12:03:{idx % 60:02d} %PM-4-ERR_DISABLE: err-disable caused by loop on Gi1/0/{idx % 48 + 1}"
            for idx in range(81)
        )

        legacy = legacy_analyze_logs(post_logs)
        extracted = analyze_logs(post_logs)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["INFO"], [finding.severity for finding in extracted])
        self.assertIn("Log review recommended: 81 message(s)", extracted[0].finding)
        self.assertEqual(80, len(extracted[0].detail.splitlines()))


if __name__ == "__main__":
    unittest.main()
