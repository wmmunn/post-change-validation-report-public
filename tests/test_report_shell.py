import unittest
from dataclasses import dataclass

from post_change_validation_report_shell import (
    build_html_report,
    build_review_required_html,
    display_input_path,
    display_severity,
    neighbor_highlight,
    report_highlights,
    report_input_values,
    severity_counts,
)


@dataclass
class FakeFinding:
    severity: str
    category: str
    finding: str
    detail: str = ""


class ReportShellTests(unittest.TestCase):
    def test_log_review_uses_review_display_and_neutral_callout(self):
        finding = FakeFinding(
            "WARN",
            "Logs",
            "Log review recommended: 1 message(s); correlate with approved change activity.",
            "Jun 20 12:03:04 %LINK-3-UPDOWN: Interface Te1/1/1 changed state",
        )

        rendered = build_review_required_html([finding])

        self.assertEqual("REVIEW", display_severity(finding))
        self.assertIn("review-required neutral", rendered)
        self.assertIn("REVIEW - Logs", rendered)

    def test_neighbor_highlight_reports_supported_missing_as_pass_with_evidence(self):
        findings = [
            FakeFinding("PASS", "CDP Neighbors", "2 CDP neighbor record(s) matched after change.", ""),
            FakeFinding(
                "INFO",
                "LLDP Neighbors",
                "1 LLDP neighbor advertisement(s) missing, but endpoint evidence is present.",
                "",
            ),
        ]

        highlight = neighbor_highlight(findings)

        self.assertEqual(("Neighbors", "PASS", "PASS + EVIDENCE"), highlight[:3])
        self.assertIn("2 matched", highlight[3])
        self.assertIn("1 advertisement cleared by MAC/PoE evidence", highlight[3])

    def test_display_input_path_strips_absolute_paths_to_basename(self):
        self.assertEqual("pre.log", display_input_path(r"D:\logs\site\pre.log"))
        self.assertEqual("sample_data/post.log", display_input_path("sample_data/post.log"))

    def test_display_input_path_preserves_d_report_absolute_paths(self):
        self.assertEqual(
            "D:\\report\\synthetic_stack_refresh_pre.log",
            display_input_path("D:/report/synthetic_stack_refresh_pre.log"),
        )
        self.assertEqual(
            "D:\\report\\synthetic_stack_refresh_post.log",
            display_input_path("D:/report/synthetic_stack_refresh_post.log"),
        )

    def test_report_input_values_use_display_safe_paths(self):
        rows = dict(
            report_input_values(
                r"C:\Users\operator\captures\synthetic_stack_refresh_pre.log",
                "sample_data/synthetic_stack_refresh_post.log",
                "",
            )
        )
        self.assertEqual("synthetic_stack_refresh_pre.log", rows["Pre-change file"])
        self.assertEqual("sample_data/synthetic_stack_refresh_post.log", rows["Post-change file"])
        self.assertEqual("None", rows["Port map file"])

    def test_html_report_uses_structured_detail_and_inputs(self):
        findings = [
            FakeFinding("PASS", "PoE", "PoE delivery restored.", "Gi1/0/1 -> Te1/0/1: PoE still delivering | pre=on | post=on"),
            FakeFinding("INFO", "Inventory", "Inventory parsed.", "component|description|pid|vid|serial\nSwitch 1|48-port|C9300-48P|V01|SANITIZED1234"),
        ]

        rendered = build_html_report(findings, "pre.log", "post.log", "")

        self.assertEqual({"FAIL": 0, "WARN": 0, "PASS": 1, "INFO": 1}, severity_counts(findings))
        self.assertIn("<h1>Post-Change Validation Report</h1>", rendered)
        self.assertIn("<table class='detail-table poe-table'>", rendered)
        self.assertIn("<table class='detail-table inventory-table'>", rendered)
        self.assertIn("<td>Port map file</td><td>None</td>", rendered)
        self.assertEqual("MAC Addresses", report_highlights(findings)[0][0])


if __name__ == "__main__":
    unittest.main()
