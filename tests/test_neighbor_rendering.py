import unittest

from src.post_change_validation_neighbor_rendering import build_neighbor_html, parse_neighbor_detail_line


class NeighborRenderingTests(unittest.TestCase):
    def test_parse_missing_neighbor_detail_extracts_expected_port_and_evidence(self):
        detail = (
            "access-ap.example on Gi1/0/3, remote Gi0/1 | expected post local Te1/0/3, "
            "remote Gi0/1 | supporting evidence: MAC present on Te1/0/3"
        )

        row = parse_neighbor_detail_line(detail)

        self.assertEqual("Missing advertisement", row["status"])
        self.assertEqual("access-ap.example", row["neighbor"])
        self.assertEqual("Gi1/0/3", row["local"])
        self.assertEqual("Te1/0/3", row["post_local"])
        self.assertEqual("Gi0/1", row["remote"])
        self.assertEqual("MAC present on Te1/0/3", row["evidence"])

    def test_parse_mapped_and_new_neighbor_details(self):
        mapped = parse_neighbor_detail_line("core-router: Gi1/0/49 -> Te1/1/1, remote Twe1/0/1")
        new = parse_neighbor_detail_line("new-switch.example on Te1/1/8, remote Gi0/48")

        self.assertEqual("Matched mapped", mapped["status"])
        self.assertEqual("Gi1/0/49", mapped["local"])
        self.assertEqual("Te1/1/1", mapped["post_local"])
        self.assertEqual("New", new["status"])
        self.assertEqual("Te1/1/8", new["post_local"])

    def test_build_neighbor_html_escapes_values_and_uses_warning_class(self):
        detail = "core<router>: Gi1/0/49 -> Te1/1/1, remote Twe1/0/1 | raw=neighbor <raw>"

        rendered = build_neighbor_html("WARN", detail)

        self.assertIn("<table class='detail-table neighbor-table'>", rendered)
        self.assertIn("<tr class='neighbor-warn'>", rendered)
        self.assertIn("core&lt;router&gt;", rendered)
        self.assertIn("neighbor &lt;raw&gt;", rendered)

    def test_build_neighbor_html_falls_back_to_escaped_preformatted_detail(self):
        rendered = build_neighbor_html("PASS", "")

        self.assertEqual("<pre></pre>", rendered)


if __name__ == "__main__":
    unittest.main()
