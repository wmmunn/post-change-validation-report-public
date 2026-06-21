import unittest

from src.post_change_validation_inventory_rendering import build_inventory_html, parse_inventory_detail


class InventoryRenderingTests(unittest.TestCase):
    def test_parse_inventory_detail_uses_pipe_header_and_pads_missing_fields(self):
        detail = "\n".join(
            [
                "component|description|pid|vid|serial",
                "Switch 1|48-port switch|C9300-48P|V02|SANITIZED1234",
                "Power Supply 1|AC PSU|PWR-C1-715WAC|V01",
            ]
        )

        rows = parse_inventory_detail(detail)

        self.assertEqual("Switch 1", rows[0]["component"])
        self.assertEqual("C9300-48P", rows[0]["pid"])
        self.assertEqual("SANITIZED1234", rows[0]["serial"])
        self.assertEqual("", rows[1]["serial"])

    def test_build_inventory_html_escapes_values_and_alternates_rows(self):
        detail = "\n".join(
            [
                "component|description|pid|vid|serial",
                "Switch <1>|48-port switch|C9300-48P|V02|SANITIZED1234",
                "Power Supply 1|AC PSU|PWR-C1-715WAC|V01|SANITIZED5678",
            ]
        )

        rendered = build_inventory_html(detail)

        self.assertIn("<table class='detail-table inventory-table'>", rendered)
        self.assertIn("<tr class='inventory-pass-a'>", rendered)
        self.assertIn("<tr class='inventory-pass-b'>", rendered)
        self.assertIn("Switch &lt;1&gt;", rendered)
        self.assertIn("SANITIZED5678", rendered)

    def test_build_inventory_html_falls_back_to_escaped_preformatted_detail(self):
        rendered = build_inventory_html("unparsed <inventory> evidence")

        self.assertEqual("<pre>unparsed &lt;inventory&gt; evidence</pre>", rendered)


if __name__ == "__main__":
    unittest.main()
