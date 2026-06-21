import unittest

from src.post_change_validation_port_map_rendering import build_port_map_html, parse_port_map_detail


class PortMapRenderingTests(unittest.TestCase):
    def test_parse_port_map_detail_extracts_source_summary_and_mapping_sections(self):
        detail = "\n".join(
            [
                "Auto-detected from post-change running-config",
                "Profile: environment standard refresh mapping",
                "Detected stack members: 1, 2",
                "",
                "Observed post-change neighbor override(s):",
                "Gi1/0/49 -> Te1/1/1 (core-router, remote Twe1/0/1)",
            ]
        )

        rows = parse_port_map_detail(detail)

        self.assertEqual({"section": "Source", "item": "Source", "value": "Auto-detected from post-change running-config", "note": ""}, rows[0])
        self.assertEqual({"section": "Summary", "item": "Profile", "value": "environment standard refresh mapping", "note": ""}, rows[1])
        self.assertEqual("Observed post-change neighbor override(s)", rows[3]["section"])
        self.assertEqual("Gi1/0/49", rows[3]["item"])
        self.assertEqual("Te1/1/1", rows[3]["value"])
        self.assertEqual("core-router, remote Twe1/0/1", rows[3]["note"])

    def test_build_port_map_html_escapes_values_and_alternates_rows(self):
        detail = "\n".join(
            [
                "Manual CSV override: C:/sanitized/<map>.csv",
                "Manual port map CSV selected.",
            ]
        )

        rendered = build_port_map_html(detail)

        self.assertIn("<table class='detail-table port-map-table'>", rendered)
        self.assertIn("<tr class='port-map-a'>", rendered)
        self.assertIn("<tr class='port-map-b'>", rendered)
        self.assertIn("C:/sanitized/&lt;map&gt;.csv", rendered)

    def test_build_port_map_html_falls_back_to_escaped_preformatted_detail(self):
        rendered = build_port_map_html("")

        self.assertEqual("<pre></pre>", rendered)


if __name__ == "__main__":
    unittest.main()
