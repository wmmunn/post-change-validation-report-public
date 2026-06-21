import unittest
from dataclasses import dataclass

from src.post_change_validation_gui_detail_formatting import format_detail_pane, format_detail_summary


@dataclass
class FakeFinding:
    severity: str
    category: str
    finding: str
    detail: str = ""


class GuiDetailFormattingTests(unittest.TestCase):
    def test_mac_warn_summary_shows_first_issue_row(self):
        detail = "\n".join(
            [
                "status|mac|vlan|pre_port|expected_post_port|actual_post_port|note",
                "PASS|aaaa.bbbb.0001|10|Gi1/0/1|Gi2/0/1|Gi2/0/1|ok",
                "MISSING|aaaa.bbbb.0003|10|Gi1/0/3|Gi2/0/3|Not found|endpoint offline",
            ]
        )
        finding = FakeFinding(
            "WARN",
            "Access Port MAC Correlation",
            "1 access-port MAC issue(s) require review.",
            detail,
        )

        summary = format_detail_summary(finding)

        self.assertIn("MISSING", summary)
        self.assertIn("aaaa.bbbb.0003", summary)
        self.assertIn("Gi1/0/3", summary)
        self.assertNotIn("status|mac|vlan", summary)

    def test_mac_pass_summary_shows_row_counts(self):
        detail = "\n".join(
            [
                "status|mac|vlan|pre_port|expected_post_port|actual_post_port|note",
                "PASS|aaaa.bbbb.0001|10|Gi1/0/1|Gi2/0/1|Gi2/0/1|ok",
                "PASS|aaaa.bbbb.0002|10|Gi1/0/2|Gi2/0/2|Gi2/0/2|ok",
            ]
        )
        finding = FakeFinding(
            "PASS",
            "Access Port MAC Correlation",
            "2 access-port MAC(s) correlated successfully.",
            detail,
        )

        self.assertEqual("2 rows: 2 PASS", format_detail_summary(finding))

    def test_mac_detail_pane_uses_labeled_fields(self):
        detail = "\n".join(
            [
                "status|mac|vlan|pre_port|expected_post_port|actual_post_port|note",
                "MOVED|aaaa.bbbb.0002|10|Gi1/0/2|Gi2/0/2|Gi2/0/9|review placement",
            ]
        )
        finding = FakeFinding("WARN", "Access Port MAC Correlation", "MAC moved.", detail)

        pane = format_detail_pane(finding)

        self.assertIn("Status: MOVED", pane)
        self.assertIn("MAC Address: aaaa.bbbb.0002", pane)
        self.assertIn("Expected Post Port: Gi2/0/2", pane)
        self.assertIn("Actual Post Port: Gi2/0/9", pane)
        self.assertNotIn("|", pane)

    def test_interface_warn_summary_shows_port_status(self):
        detail = "Gi1/0/18 -> Te1/0/18 role=access: was connected, now notconnect | pre=connected | post=notconnect"
        finding = FakeFinding(
            "WARN",
            "Interface Status",
            "1 mapped port issue(s) require review.",
            detail,
        )

        summary = format_detail_summary(finding)

        self.assertEqual("Gi1/0/18->Te1/0/18: was connected, now notconnect", summary)

    def test_interface_pass_summary_shows_port_count(self):
        detail = "\n".join(
            [
                "Gi1/0/1 -> Te1/0/1 role=access: connected before and after",
                "Gi1/0/2 -> Te1/0/2 role=access: connected before and after",
            ]
        )
        finding = FakeFinding(
            "PASS",
            "Interface Status",
            "2 mapped connected port(s) remained connected after change.",
            detail,
        )

        self.assertEqual("2 ports remained connected", format_detail_summary(finding))

    def test_interface_detail_pane_uses_labeled_fields(self):
        detail = (
            "Gi1/0/3 -> Te1/0/3 role=access: connected before and after | "
            "pre=Gi1/0/3 connected 10/100/1000 | post=Te1/0/3 connected 2.5G | note=observed endpoint"
        )
        finding = FakeFinding("PASS", "Interface Status", "Port remained connected.", detail)

        pane = format_detail_pane(finding)

        self.assertIn("Pre Port: Gi1/0/3", pane)
        self.assertIn("Post Port: Te1/0/3", pane)
        self.assertIn("Role: access", pane)
        self.assertIn("Pre Evidence: Gi1/0/3 connected 10/100/1000", pane)
        self.assertIn("Note: observed endpoint", pane)

    def test_neighbor_pass_summary_shows_match_count_and_example(self):
        detail = "\n".join(
            [
                "gw-a.example: Gi1/0/25, remote Te1/1/1",
                "core-router: Gi1/0/49 -> Te1/1/1, remote Twe1/0/1",
            ]
        )
        finding = FakeFinding(
            "PASS",
            "LLDP Neighbors",
            "2 LLDP neighbor record(s) matched after change.",
            detail,
        )

        summary = format_detail_summary(finding)

        self.assertIn("2 matched:", summary)
        self.assertIn("gw-a.example", summary)
        self.assertIn("Gi1/0/25", summary)

    def test_neighbor_warn_detail_pane_uses_labeled_fields(self):
        detail = (
            "access-ap.example on Gi1/0/3, remote Gi0/1 | expected post local Te1/0/3, "
            "remote Gi0/1 | supporting evidence: MAC present on Te1/0/3"
        )
        finding = FakeFinding(
            "WARN",
            "LLDP Neighbors",
            "1 LLDP neighbor record(s) missing after change.",
            detail,
        )

        summary = format_detail_summary(finding)
        pane = format_detail_pane(finding)

        self.assertIn("missing access-ap.example", summary)
        self.assertIn("Status: Missing advertisement", pane)
        self.assertIn("Pre Local: Gi1/0/3", pane)
        self.assertIn("Post Local: Te1/0/3", pane)
        self.assertIn("Evidence: MAC present on Te1/0/3", pane)

    def test_unstructured_finding_falls_back_to_truncated_plain_detail(self):
        finding = FakeFinding(
            "INFO",
            "Command Sections",
            "Pre-change sections found: 12",
            "show int status, show cdp neighbors detail, show lldp neighbors detail",
        )

        summary = format_detail_summary(finding)
        pane = format_detail_pane(finding)

        self.assertEqual(
            "show int status, show cdp neighbors detail, show lldp neighbors detail",
            summary,
        )
        self.assertEqual(finding.detail, pane)


if __name__ == "__main__":
    unittest.main()
