import unittest

from src.post_change_validation_logs_rendering import build_logs_html, parse_log_detail_line


class LogsRenderingTests(unittest.TestCase):
    def test_parse_log_detail_line_extracts_month_day_prefix_and_message(self):
        row = parse_log_detail_line("Jun 20 12:03:04 %LINK-3-UPDOWN: Interface Te1/1/1 changed state")

        self.assertEqual("Jun 20 12:03:04", row["prefix"])
        self.assertEqual("%LINK-3-UPDOWN: Interface Te1/1/1 changed state", row["message"])

    def test_parse_log_detail_line_extracts_two_token_prefix(self):
        row = parse_log_detail_line("%SYS-5-CONFIG_I Configured from console")

        self.assertEqual("%SYS-5-CONFIG_I Configured", row["prefix"])
        self.assertEqual("from console", row["message"])

    def test_build_logs_html_escapes_values_and_uses_warning_class(self):
        detail = "Jun 20 12:03:04 %LINK-3-UPDOWN: Interface <Te1/1/1> changed state"

        rendered = build_logs_html("Log review recommended: 1 message(s)", detail)

        self.assertIn("<table class='detail-table logs-table'>", rendered)
        self.assertIn("<tr class='log-warn'>", rendered)
        self.assertIn("&lt;Te1/1/1&gt;", rendered)

    def test_build_logs_html_alternates_pass_rows(self):
        detail = "\n".join(
            [
                "Jun 20 12:03:04 %LINEPROTO-5-UPDOWN: Line protocol up",
                "Jun 20 12:03:05 %LINK-3-UPDOWN: Interface up",
            ]
        )

        rendered = build_logs_html("No high-risk log keywords found.", detail)

        self.assertIn("<tr class='log-pass-a'>", rendered)
        self.assertIn("<tr class='log-pass-b'>", rendered)

    def test_build_logs_html_falls_back_to_escaped_preformatted_detail(self):
        rendered = build_logs_html("No high-risk log keywords found.", "")

        self.assertEqual("<pre></pre>", rendered)


if __name__ == "__main__":
    unittest.main()
