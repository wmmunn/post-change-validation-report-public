import unittest

from src.post_change_validation_mac_rendering import build_mac_correlation_html, parse_mac_correlation_detail


class MacRenderingTests(unittest.TestCase):
    def test_parse_mac_correlation_detail_uses_pipe_header_and_pads_missing_fields(self):
        detail = "\n".join(
            [
                "status|mac|vlan|pre_port|expected_post_port|actual_post_port|note",
                "PASS|aaaa.bbbb.0001|10|Gi1/0/1|Gi2/0/1|Gi2/0/1",
            ]
        )

        rows = parse_mac_correlation_detail(detail)

        self.assertEqual("PASS", rows[0]["status"])
        self.assertEqual("aaaa.bbbb.0001", rows[0]["mac"])
        self.assertEqual("", rows[0]["note"])

    def test_build_mac_correlation_html_escapes_finding_and_row_values(self):
        detail = "\n".join(
            [
                "status|mac|vlan|pre_port|expected_post_port|actual_post_port|note",
                "MOVED|aaaa.bbbb.0002|10|Gi1/0/2|Gi2/0/2|Gi2/0/9|review <placement>",
            ]
        )

        rendered = build_mac_correlation_html("MAC check <review>", detail)

        self.assertIn("<div class='mac-section'>", rendered)
        self.assertIn("MAC check &lt;review&gt;", rendered)
        self.assertIn("<tr class='mac-moved'>", rendered)
        self.assertIn("review &lt;placement&gt;", rendered)

    def test_build_mac_correlation_html_uses_expected_status_classes(self):
        detail = "\n".join(
            [
                "status|mac|vlan|pre_port|expected_post_port|actual_post_port|note",
                "PASS|aaaa.bbbb.0001|10|Gi1/0/1|Gi2/0/1|Gi2/0/1|ok",
                "PASS|aaaa.bbbb.0002|10|Gi1/0/2|Gi2/0/2|Gi2/0/2|ok",
                "MISSING|aaaa.bbbb.0003|10|Gi1/0/3|Gi2/0/3|Not found|missing",
            ]
        )

        rendered = build_mac_correlation_html("MAC summary", detail)

        self.assertIn("<tr class='mac-pass-a'>", rendered)
        self.assertIn("<tr class='mac-pass-b'>", rendered)
        self.assertIn("<tr class='mac-missing'>", rendered)

    def test_build_mac_correlation_html_preserves_empty_section_behavior(self):
        rendered = build_mac_correlation_html("MAC summary", "status|mac|vlan|pre_port|expected_post_port|actual_post_port|note")

        self.assertIn("<table class='mac-table'>", rendered)
        self.assertNotIn("<pre>", rendered)


if __name__ == "__main__":
    unittest.main()
