import unittest

from src.post_change_validation_interface_status_rendering import (
    build_interface_status_html,
    parse_interface_detail_line,
)


class InterfaceStatusRenderingTests(unittest.TestCase):
    def test_parse_mapped_interface_detail_extracts_ports_evidence_and_note(self):
        detail = (
            "Gi1/0/3 -> Te1/0/3 role=access: connected before and after | "
            "pre=Gi1/0/3 connected 10/100/1000 | post=Te1/0/3 connected 2.5G | note=observed endpoint"
        )

        row = parse_interface_detail_line(detail)

        self.assertEqual("Gi1/0/3", row["pre_port"])
        self.assertEqual("Te1/0/3", row["post_port"])
        self.assertEqual("access", row["role"])
        self.assertEqual("connected before and after", row["status"])
        self.assertEqual("Gi1/0/3 connected 10/100/1000", row["pre"])
        self.assertEqual("Te1/0/3 connected 2.5G", row["post"])
        self.assertEqual("observed endpoint", row["note"])

    def test_parse_unstructured_interface_detail_uses_status_fallback(self):
        row = parse_interface_detail_line("unexpected interface evidence")

        self.assertEqual("unexpected interface evidence", row["status"])
        self.assertEqual("", row["pre_port"])
        self.assertEqual("", row["post_port"])

    def test_parse_bare_post_port_detail_maps_to_post_port_column(self):
        row = parse_interface_detail_line("Fi2/0/1")

        self.assertEqual("Fi2/0/1", row["post_port"])
        self.assertEqual("", row["status"])
        self.assertEqual("", row["pre_port"])

    def test_parse_enriched_uncovered_detail_maps_role_status_and_post_evidence(self):
        detail = "uncovered -> Te1/0/6 role=access: connected | post=Te1/0/6 connected 1 a-full a-1000 10/100/1000BaseTX"

        row = parse_interface_detail_line(detail)

        self.assertEqual("uncovered", row["pre_port"])
        self.assertEqual("Te1/0/6", row["post_port"])
        self.assertEqual("access", row["role"])
        self.assertEqual("connected", row["status"])
        self.assertEqual("Te1/0/6 connected 1 a-full a-1000 10/100/1000BaseTX", row["post"])

    def test_build_interface_status_html_uncovered_post_port_in_post_port_column(self):
        detail = "Fi2/0/1\nTe1/0/6"

        rendered = build_interface_status_html("INFO", detail)

        self.assertIn("<tr class='iface-info'><td></td><td>Fi2/0/1</td><td></td><td></td>", rendered)
        self.assertIn("<tr class='iface-info'><td></td><td>Te1/0/6</td><td></td><td></td>", rendered)
        self.assertNotIn("<tr class='iface-info'><td>Fi2/0/1</td>", rendered)
        self.assertNotIn("<tr class='iface-info'><td>Te1/0/6</td>", rendered)

    def test_build_interface_status_html_enriched_uncovered_row_columns(self):
        detail = (
            "uncovered -> Te1/0/6 role=access: connected | "
            "post=Te1/0/6 connected 1 a-full a-1000 10/100/1000BaseTX"
        )

        rendered = build_interface_status_html("INFO", detail)

        self.assertIn(
            "<tr class='iface-info'><td>uncovered</td><td>Te1/0/6</td><td>access</td><td>connected</td>"
            "<td></td><td>Te1/0/6 connected 1 a-full a-1000 10/100/1000BaseTX</td><td></td></tr>",
            rendered,
        )

    def test_build_interface_status_html_escapes_values_and_uses_info_class(self):
        detail = "Gi1/0/3 -> Te1/0/3 role=access: newly connected | post=Te1/0/3 connected <endpoint>"

        rendered = build_interface_status_html("INFO", detail)

        self.assertIn("<table class='detail-table iface-table'>", rendered)
        self.assertIn("<tr class='iface-info'>", rendered)
        self.assertIn("connected &lt;endpoint&gt;", rendered)

    def test_build_interface_status_html_falls_back_to_escaped_preformatted_detail(self):
        rendered = build_interface_status_html("PASS", "")

        self.assertEqual("<pre></pre>", rendered)


if __name__ == "__main__":
    unittest.main()
