import unittest

from src.post_change_validation_transceiver_rendering import (
    TransceiverHtmlRow,
    build_transceiver_row_html,
    build_transceiver_html,
    transceiver_delta_text,
    transceiver_range_bar,
    transceiver_row_class,
    transceiver_scale_bounds,
    transceiver_scale_pct,
    transceiver_value_text,
)


class TransceiverRenderingTests(unittest.TestCase):
    def test_html_fallback_escapes_unparsed_detail(self):
        rendered = build_transceiver_html("unparsed <optic> evidence")

        self.assertEqual("<pre>unparsed &lt;optic&gt; evidence</pre>", rendered)

    def test_pre_post_delta_text_and_markers_render(self):
        detail = """
Te1/1/1:
PRE-CHANGE:
Te1/1/1 -5.26 1.00 -3.00 -9.51 -13.51
POST-CHANGE:
Te1/1/1 -4.26 1.00 -3.00 -9.51 -13.51
"""

        rendered = build_transceiver_html(detail)

        self.assertIn("<td>dBm -5.26</td>", rendered)
        self.assertIn("<td>dBm -4.26</td>", rendered)
        self.assertIn("<td>+1.00</td>", rendered)
        self.assertIn("xcvr-pre-marker", rendered)
        self.assertIn("xcvr-post-marker", rendered)

    def test_row_severity_class_follows_threshold_level(self):
        detail = """
Te1/1/1:
Te1/1/1 86.00 89.00 85.00 -5.00 -9.00
"""

        rendered = build_transceiver_html(detail)

        self.assertIn("<tr class='xcvr-warn'>", rendered)

    def test_range_marker_output_uses_clamped_percentages(self):
        scale_min, scale_max = transceiver_scale_bounds(-10.0, 10.0)

        self.assertEqual((-13.0, 13.0), (scale_min, scale_max))
        self.assertEqual(50.0, transceiver_scale_pct(0.0, scale_min, scale_max))
        self.assertEqual(0.0, transceiver_scale_pct(-20.0, scale_min, scale_max))
        self.assertEqual(100.0, transceiver_scale_pct(20.0, scale_min, scale_max))

    def test_value_and_delta_text_helpers_format_missing_and_numeric_values(self):
        self.assertEqual("n/a", transceiver_value_text("dBm", None))
        self.assertEqual("dBm -5.26", transceiver_value_text("dBm", -5.26))
        self.assertEqual("n/a", transceiver_delta_text(-4.26, None))
        self.assertEqual("+1.00", transceiver_delta_text(-4.26, -5.26))

    def test_row_html_escapes_text_and_uses_threshold_class(self):
        row = TransceiverHtmlRow(
            interface="Te1/1/1",
            metric="Rx <Power>",
            unit="dBm",
            value=-4.26,
            low_alarm=-13.51,
            low_warn=-9.51,
            high_warn=-3.00,
            high_alarm=1.00,
            pre_value=-5.26,
        )

        rendered = build_transceiver_row_html(row)

        self.assertEqual("ok", transceiver_row_class(row))
        self.assertIn("Rx &lt;Power&gt;", rendered)
        self.assertIn("<td>dBm -5.26</td>", rendered)
        self.assertIn("<td>+1.00</td>", rendered)

    def test_range_bar_omits_pre_marker_when_no_pre_value_exists(self):
        rendered = transceiver_range_bar(-5.0, None, -13.0, -9.0, -3.0, 1.0)

        self.assertNotIn("xcvr-pre-marker", rendered)
        self.assertIn("xcvr-post-marker", rendered)


if __name__ == "__main__":
    unittest.main()
