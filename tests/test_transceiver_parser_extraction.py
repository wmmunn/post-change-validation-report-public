import unittest

from src.post_change_validation_models import PortMapRow
from src.post_change_validation_transceivers import (
    TransceiverEntry,
    compact_transceiver_row,
    compare_transceiver_delivery,
    parse_transceiver_detail,
    parse_transceiver_visual_rows,
    transceiver_level_class,
)


class TransceiverParserExtractionTests(unittest.TestCase):
    def test_compact_threshold_rows_infer_metrics_and_units(self):
        detail = """Te1/1/1 25.20 89.00 85.00 -5.00 -9.00
Te1/1/1 3.31 3.60 3.50 3.10 3.00
Te1/1/1 5.20 13.00 12.40 2.00 1.00
Te1/1/1 -5.26 1.00 -3.00 -9.51 -13.51
Te1/1/1 -5.11 4.00 0.00 -17.00 -21.04
"""

        rows = parse_transceiver_visual_rows(f"Te1/1/1:\n{detail}")

        self.assertEqual(["Temperature", "Voltage", "Current", "Tx Power", "Rx Power"], [row["metric"] for row in rows])
        self.assertEqual(["Celsius", "Volts", "mA", "dBm", "dBm"], [row["unit"] for row in rows])
        self.assertEqual("ok", transceiver_level_class(25.20, -9.00, -5.00, 85.00, 89.00))

    def test_detail_parser_groups_interface_rows_and_evaluates_thresholds(self):
        section = """
Te1/1/1 86.00 89.00 85.00 -5.00 -9.00
Te1/1/1 3.31 3.60 3.50 3.10 3.00
"""

        entries = parse_transceiver_detail(section)

        self.assertEqual(["Te1/1/1"], sorted(entries))
        self.assertTrue(entries["Te1/1/1"].has_warning)
        self.assertFalse(entries["Te1/1/1"].has_alarm)

    def test_detail_parser_uses_symbol_fallback_for_unparsed_alarm_text(self):
        section = """
Te1/1/1
Optical Receive Power ++
"""

        entries = parse_transceiver_detail(section)

        self.assertTrue(entries["Te1/1/1"].has_alarm)
        self.assertFalse(entries["Te1/1/1"].has_warning)

    def test_named_threshold_and_value_rows_parse_metric(self):
        detail = """
Te1/1/1:
Optical Tx Power Threshold 1.00 0.00 -17.00 -21.04 dBm
Optical Tx Power Value -5.11 dBm
"""

        rows = parse_transceiver_visual_rows(detail)

        self.assertEqual(1, len(rows))
        self.assertEqual("Te1/1/1", rows[0]["interface"])
        self.assertEqual("Tx Power", rows[0]["metric"])
        self.assertEqual("dBm", rows[0]["unit"])
        self.assertEqual(-5.11, rows[0]["value"])
        self.assertEqual(-21.04, rows[0]["low_alarm"])

    def test_pre_post_change_blocks_attach_pre_value_to_post_row(self):
        detail = """
Te1/1/1:
PRE-CHANGE:
Te1/1/1 -5.26 1.00 -3.00 -9.51 -13.51
POST-CHANGE:
Te1/1/1 -4.26 1.00 -3.00 -9.51 -13.51
"""

        rows = parse_transceiver_visual_rows(detail)

        self.assertEqual(1, len(rows))
        self.assertEqual("Tx Power", rows[0]["metric"])
        self.assertEqual(-5.26, rows[0]["pre_value"])
        self.assertEqual(-4.26, rows[0]["value"])

    def test_compact_row_handles_lane_column(self):
        row = compact_transceiver_row("Te1/1/1 1 -5.11 4.00 0.00 -17.00 -21.04", "Rx Power")

        self.assertIsNotNone(row)
        self.assertEqual("Te1/1/1", row["interface"])
        self.assertEqual("Rx Power", row["metric"])
        self.assertEqual(-5.11, row["value"])

    def test_compare_transceiver_delivery_pairs_mapped_pre_and_post_entries(self):
        pre = {
            "Gi1/0/49": TransceiverEntry("Gi1/0/49", ["Gi1/0/49 pre optical row"]),
        }
        post = {
            "Te1/1/1": TransceiverEntry("Te1/1/1", ["Te1/1/1 post optical row"]),
        }
        pm = {
            "Gi1/0/49": PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", "uplink A"),
        }

        comparison = compare_transceiver_delivery(pre, post, pm, {"Te1/1/1"})

        self.assertEqual(1, comparison.parsed_post_rows)
        self.assertEqual(1, comparison.matched_target_rows)
        self.assertEqual([], comparison.warn_blocks)
        self.assertEqual(
            ["Te1/1/1:\nPRE-CHANGE:\nGi1/0/49 pre optical row\nPOST-CHANGE:\nTe1/1/1 post optical row"],
            comparison.info_blocks,
        )

    def test_compare_transceiver_delivery_reports_warning_blocks(self):
        post = {
            "Te1/1/1": TransceiverEntry("Te1/1/1", ["Te1/1/1 warning row"], has_warning=True),
        }

        comparison = compare_transceiver_delivery({}, post, {}, {"Te1/1/1"})

        self.assertEqual(1, len(comparison.warn_blocks))
        self.assertIn("POST-CHANGE:\nTe1/1/1 warning row", comparison.warn_blocks[0])
        self.assertEqual([], comparison.info_blocks)

    def test_compare_transceiver_delivery_reports_unmatched_targets(self):
        post = {
            "Gi1/0/1": TransceiverEntry("Gi1/0/1", ["Gi1/0/1 access optic row"]),
        }

        comparison = compare_transceiver_delivery({}, post, {}, set())

        self.assertEqual(1, comparison.parsed_post_rows)
        self.assertEqual(0, comparison.matched_target_rows)
        self.assertIn("Gi1/0/1 access optic row", comparison.unmatched_detail)

    def test_compare_transceiver_delivery_includes_all_standalone_industrial_entries(self):
        post = {
            "Gi1/1": TransceiverEntry("Gi1/1", ["Gi1/1 industrial optic row"]),
        }

        comparison = compare_transceiver_delivery({}, post, {}, set(), standalone_industrial=True)

        self.assertEqual(1, comparison.matched_target_rows)
        self.assertIn("Gi1/1 industrial optic row", comparison.info_blocks[0])

    def test_compare_transceiver_delivery_includes_module_uplink_without_explicit_target(self):
        post = {
            "Te1/1/1": TransceiverEntry("Te1/1/1", ["Te1/1/1 module optic row"]),
        }

        comparison = compare_transceiver_delivery({}, post, {}, set())

        self.assertEqual(1, comparison.matched_target_rows)
        self.assertIn("Te1/1/1 module optic row", comparison.info_blocks[0])

    def test_compare_transceiver_delivery_falls_back_to_sorted_pre_entries_once(self):
        pre = {
            "Gi1/0/49": TransceiverEntry("Gi1/0/49", ["Gi1/0/49 first pre optic row"]),
            "Gi2/0/52": TransceiverEntry("Gi2/0/52", ["Gi2/0/52 second pre optic row"]),
        }
        post = {
            "Te1/1/1": TransceiverEntry("Te1/1/1", ["Te1/1/1 first post optic row"]),
            "Te2/1/8": TransceiverEntry("Te2/1/8", ["Te2/1/8 second post optic row"]),
        }

        comparison = compare_transceiver_delivery(pre, post, {}, {"Te1/1/1", "Te2/1/8"})

        self.assertIn("PRE-CHANGE:\nGi1/0/49 first pre optic row", comparison.info_blocks[0])
        self.assertIn("PRE-CHANGE:\nGi2/0/52 second pre optic row", comparison.info_blocks[1])


if __name__ == "__main__":
    unittest.main()
