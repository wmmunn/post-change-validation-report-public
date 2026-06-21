import unittest

import post_change_validation_reviewer as reviewer
from src.post_change_validation_models import PortMapRow
from src.post_change_validation_poe import compare_poe_delivery
from src.post_change_validation_poe_rendering import (
    build_poe_budget_html,
    build_poe_html,
    parse_poe_detail_line,
)


class PoeAnalysisRenderingTests(unittest.TestCase):
    def test_budget_html_renders_used_remaining_delta_and_context_note(self):
        detail = "\n".join(
            [
                "POE_BUDGET|pre|125.00|24.30|100.70|Available:125.0(w) Used:24.3(w) Remaining:100.7(w)",
                "POE_BUDGET|post|400.00|54.30|345.70|Available:400.0(w) Used:54.3(w) Remaining:345.7(w)",
                "POE_SPEED_UPGRADE|2|Gi1/0/1 -> Te1/0/1: 1000 -> 2.5G; Gi1/0/2 -> Te1/0/2: 1000 -> 5G",
            ]
        )

        html = build_poe_budget_html(detail)

        self.assertIn("Post-change used 54.30 W / 400.00 W (13.6%); remaining 345.70 W; delta +30.00 W", html)
        self.assertIn("poe-budget-pre", html)
        self.assertIn("left: 6.1%", html)
        self.assertIn("poe-budget-post", html)
        self.assertIn("left: 13.6%", html)
        self.assertIn("PoE draw increased after the change, and 2 powered mapped endpoint(s)", html)

    def test_poe_html_renders_detail_rows_and_escapes_evidence(self):
        detail = "Gi1/0/1 -> Te1/0/1: PoE still delivering | pre=Gi1/0/1 auto on 6.3 <phone> | post=Te1/0/1 auto on 6.1 <phone>"

        row = parse_poe_detail_line(detail)
        rendered = build_poe_html("PASS", detail)

        self.assertEqual("Gi1/0/1", row["pre_port"])
        self.assertEqual("Te1/0/1", row["post_port"])
        self.assertEqual("PoE still delivering", row["status"])
        self.assertIn("&lt;phone&gt;", rendered)
        self.assertIn("poe-pass-a", rendered)

    def test_analyze_poe_treats_observed_neighbor_power_as_restored(self):
        pre_poe = """
Interface Admin Oper Power Device Class Max
Gi1/9 auto on 6.3 IP Phone 3 30.0
"""
        post_poe = """
Interface Admin Oper Power Device Class Max
Gi2/9 auto off 0.0 n/a n/a 30.0
Gi1/8 auto delivering 6.1 IP Phone 3 30.0
"""
        pre_sections = {
            "show lldp neighbors": "phone-1.example Gi1/9 120 B Gi0/1",
        }
        post_sections = {
            "show lldp neighbors": "phone-1.example Gi1/8 120 B Gi0/1",
        }
        port_map = {
            "Gi1/9": PortMapRow("Gi1/9", "Gi2/9", "standalone_industrial", "profile inference"),
        }

        findings = reviewer.analyze_poe(pre_poe, post_poe, port_map, pre_sections=pre_sections, post_sections=post_sections)

        self.assertEqual(["PASS"], [finding.severity for finding in findings])
        self.assertIn("still show PoE", findings[0].finding)
        self.assertIn("Gi1/9 -> Gi1/8: PoE still delivering on observed neighbor port", findings[0].detail)
        self.assertIn("inferred map expected Gi2/9", findings[0].detail)

    def test_compare_poe_delivery_reports_observed_neighbor_power(self):
        pre_poe = "Gi1/9 auto on 6.3 IP Phone 3 30.0"
        post_poe = "\n".join(
            [
                "Gi2/9 auto off 0.0 n/a n/a 30.0",
                "Gi1/8 auto delivering 6.1 IP Phone 3 30.0",
            ]
        )
        port_map = {
            "Gi1/9": PortMapRow("Gi1/9", "Gi2/9", "standalone_industrial", "profile inference"),
        }

        comparison = compare_poe_delivery(pre_poe, post_poe, port_map, observed_ports={"Gi1/9": "Gi1/8"})

        self.assertEqual([], comparison.missing)
        self.assertEqual(1, comparison.parsed_pre_rows)
        self.assertEqual(2, comparison.parsed_post_rows)
        self.assertEqual(
            [
                "Gi1/9 -> Gi1/8: PoE still delivering on observed neighbor port; "
                "inferred map expected Gi2/9 | pre=Gi1/9 auto on 6.3 IP Phone 3 30.0 | "
                "post=Gi1/8 auto delivering 6.1 IP Phone 3 30.0"
            ],
            comparison.restored,
        )


if __name__ == "__main__":
    unittest.main()
