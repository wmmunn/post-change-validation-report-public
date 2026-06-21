import unittest

from src.post_change_validation_stp_rendering import build_stp_root_html, parse_stp_detail_line


class StpRenderingTests(unittest.TestCase):
    def test_parse_retained_root_detail_extracts_ports_cost_and_context(self):
        detail = (
            "VLAN0001: root unchanged and root port mapped (Gi1/0/49 -> Te1/1/1); "
            "cost changed 4 -> 2000. STP path-cost method: pre=short, post=long. "
            "Post root port evidence: Te1/1/1 speed=a-10G type=SFP-10G."
        )

        row = parse_stp_detail_line(detail)

        self.assertEqual("VLAN0001", row["vlan"])
        self.assertEqual("Root retained", row["status"])
        self.assertEqual("Gi1/0/49", row["pre_port"])
        self.assertEqual("Te1/1/1", row["post_port"])
        self.assertEqual("4 -> 2000", row["cost"])
        self.assertEqual("pre=short, post=long; Te1/1/1 speed=a-10G type=SFP-10G", row["context"])

    def test_parse_root_change_detail_extracts_costs_and_vlan1_context(self):
        detail = (
            "VLAN0001: local switch became root post-change, but classified as informational based on VLAN 1 context. "
            "pre root=32769 0011.2233.4455, cost=4, port=Gi1/0/49; "
            "post root=32769 00aa.bbcc.ddee, cost=0, port=local root. VLAN 1 SVI is shutdown."
        )

        row = parse_stp_detail_line(detail)

        self.assertEqual("Local root post-change", row["status"])
        self.assertEqual("4 -> 0", row["cost"])
        self.assertEqual("VLAN 1 SVI shutdown context", row["context"])

    def test_parse_root_port_change_detail_extracts_expected_and_actual_ports(self):
        detail = (
            "VLAN0001: root bridge unchanged but root port changed unexpectedly. "
            "pre port=Gi1/0/49 expected post=Te1/1/1, actual post=Te1/1/8"
        )

        row = parse_stp_detail_line(detail)

        self.assertEqual("Root port changed", row["status"])
        self.assertEqual("Gi1/0/49 expected post=Te1/1/1", row["pre_port"])
        self.assertEqual("Te1/1/8", row["post_port"])

    def test_build_stp_root_html_escapes_context_and_uses_severity_class(self):
        detail = "VLAN0004: root bridge changed. pre root=<old>, cost=4; post root=<new>, cost=0."

        rendered = build_stp_root_html("WARN", detail)

        self.assertIn("<tr class='stp-warn'>", rendered)
        self.assertIn("&lt;old&gt;", rendered)
        self.assertIn("&lt;new&gt;", rendered)


if __name__ == "__main__":
    unittest.main()
