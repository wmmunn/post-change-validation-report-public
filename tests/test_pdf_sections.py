import unittest
from dataclasses import dataclass

from src.post_change_validation_interface_status_rendering import parse_interface_detail_line
from src.post_change_validation_logs_rendering import parse_log_detail_line
from src.post_change_validation_mac_rendering import parse_mac_correlation_detail
from src.post_change_validation_neighbor_rendering import parse_neighbor_detail_line
from src.post_change_validation_pdf_rendering import build_poe_budget_pdf_card, poe_budget_bar_width
from src.post_change_validation_pdf_sections import (
    append_interface_status_pdf_sections,
    append_inventory_pdf_sections,
    append_logs_pdf_sections,
    append_mac_correlation_pdf_sections,
    append_neighbor_pdf_sections,
    append_poe_pdf_sections,
    append_port_map_pdf_sections,
    append_stp_root_pdf_sections,
    append_transceiver_pdf_sections,
)
from src.post_change_validation_inventory_rendering import parse_inventory_detail
from src.post_change_validation_poe_rendering import build_poe_budget_render_data, parse_poe_detail_line
from src.post_change_validation_port_map_rendering import parse_port_map_detail
from src.post_change_validation_stp_rendering import parse_stp_detail_line
from src.post_change_validation_transceivers import parse_transceiver_visual_rows, transceiver_level_class


@dataclass
class FakeFinding:
    category: str
    finding: str
    detail: str


class PdfSectionTests(unittest.TestCase):
    def test_append_port_map_pdf_sections_builds_rows_and_backgrounds(self):
        finding = FakeFinding(
            "Port Map",
            "Port map loaded with 2 old-to-new mapping row(s).",
            "\n".join(
                [
                    "Auto-detected from post-change running-config",
                    "Profile: environment standard refresh mapping",
                    "Observed post-change neighbor override(s):",
                    "Gi1/0/49 -> Te1/1/1 (core-router, remote Twe1/0/1)",
                ]
            ),
        )
        calls = []

        def fake_detail_table(*args):
            calls.append(args)

        def fake_paragraph(text, style):
            return f"{style}:{text}"

        append_port_map_pdf_sections(
            [FakeFinding("Logs", "Ignore", "detail"), finding],
            is_port_map_finding=lambda item: item.category == "Port Map",
            parse_port_map_detail=parse_port_map_detail,
            detail_table=fake_detail_table,
            paragraph=fake_paragraph,
            tiny_style="tiny",
            inch=10.0,
            info_bg="info",
            pass_a="pass-a",
        )

        self.assertEqual(1, len(calls))
        title, finding_text, header, rows, widths, backgrounds, header_style = calls[0]
        self.assertEqual("Port Map Detail", title)
        self.assertEqual(finding.finding, finding_text)
        self.assertEqual(["Section", "Item", "Value / Target", "Note"], header)
        self.assertEqual([16.5, 15.5, 32.5, 30.0], widths)
        self.assertEqual(["info", "pass-a", "info"], backgrounds)
        self.assertEqual("tiny", header_style)
        self.assertEqual("tiny:Source", rows[0][0])
        self.assertEqual("tiny:Gi1/0/49", rows[2][1])
        self.assertEqual("tiny:Te1/1/1", rows[2][2])
        self.assertEqual("tiny:core-router, remote Twe1/0/1", rows[2][3])

    def test_append_logs_pdf_sections_builds_rows_and_review_backgrounds(self):
        finding = FakeFinding(
            "Logs",
            "Log review recommended: 2 message(s); correlate with approved change activity.",
            "\n".join(
                [
                    "Jun 20 12:03:04 %LINK-3-UPDOWN: Interface Te1/1/1 changed state",
                    "Jun 20 12:03:05 %SECURITY-4-ALERT: Sanitized event",
                ]
            ),
        )
        calls = []

        def fake_detail_table(*args):
            calls.append(args)

        def fake_paragraph(text, style):
            return f"{style}:{text}"

        append_logs_pdf_sections(
            [FakeFinding("Port Map", "Ignore", "detail"), finding],
            is_logs_finding=lambda item: item.category == "Logs",
            parse_log_detail_line=parse_log_detail_line,
            detail_table=fake_detail_table,
            paragraph=fake_paragraph,
            tiny_style="tiny",
            inch=10.0,
            info_bg="info",
            pass_a="pass-a",
            pass_b="pass-b",
        )

        self.assertEqual(1, len(calls))
        title, finding_text, header, rows, widths, backgrounds, header_style = calls[0]
        self.assertEqual("Logs Detail", title)
        self.assertEqual(finding.finding, finding_text)
        self.assertEqual(["Time/Prefix", "Message"], header)
        self.assertEqual([14.5, 81.0], widths)
        self.assertEqual(["info", "info"], backgrounds)
        self.assertEqual("tiny", header_style)
        self.assertEqual("tiny:Jun 20 12:03:04", rows[0][0])
        self.assertEqual("tiny:%LINK-3-UPDOWN: Interface Te1/1/1 changed state", rows[0][1])

    def test_append_logs_pdf_sections_alternates_non_review_backgrounds(self):
        finding = FakeFinding(
            "Logs",
            "No high-risk log keywords found.",
            "Jun 20 12:03:04 %LINEPROTO-5-UPDOWN: Line protocol up\nJun 20 12:03:05 %LINK-3-UPDOWN: Interface up",
        )
        calls = []

        append_logs_pdf_sections(
            [finding],
            is_logs_finding=lambda item: item.category == "Logs",
            parse_log_detail_line=parse_log_detail_line,
            detail_table=lambda *args: calls.append(args),
            paragraph=lambda text, style: f"{style}:{text}",
            tiny_style="tiny",
            inch=10.0,
            info_bg="info",
            pass_a="pass-a",
            pass_b="pass-b",
        )

        self.assertEqual(["pass-a", "pass-b"], calls[0][5])

    def test_append_poe_pdf_sections_builds_rows_and_skips_truncation_marker(self):
        finding = FakeFinding(
            "PoE",
            "PoE delivery restored on mapped endpoint.",
            "\n".join(
                [
                    "POE_BUDGET|pre|125.00|24.30|100.70|Available:125.0(w) Used:24.3(w) Remaining:100.7(w)",
                    "POE_BUDGET|post|400.00|54.30|345.70|Available:400.0(w) Used:54.3(w) Remaining:345.7(w)",
                    "POE_SPEED_UPGRADE|2|Gi1/0/1 -> Te1/0/1: 1000 -> 2.5G",
                    "Gi1/0/1 -> Te1/0/1: PoE still delivering | pre=Gi1/0/1 auto on 6.3 | post=Te1/0/1 auto on 6.1",
                    "... truncated ...",
                    "Gi1/0/2 -> Te1/0/2: PoE still delivering | pre=Gi1/0/2 auto on 4.3 | post=Te1/0/2 auto on 4.1",
                ]
            ),
        )
        finding.severity = "PASS"
        calls = []
        budget_calls = []

        append_poe_pdf_sections(
            [FakeFinding("Logs", "Ignore", "detail"), finding],
            is_poe_finding=lambda item: item.category == "PoE",
            parse_poe_detail_line=parse_poe_detail_line,
            poe_budget_card=lambda detail: budget_calls.append(detail) or "budget-card",
            detail_table=lambda *args, **kwargs: calls.append((args, kwargs)),
            paragraph=lambda text, style: f"{style}:{text}",
            tiny_style="tiny",
            inch=10.0,
            warn_bg="warn",
            pass_a="pass-a",
            pass_b="pass-b",
        )

        self.assertEqual(1, len(budget_calls))
        self.assertEqual(finding.detail, budget_calls[0])
        self.assertEqual(1, len(calls))
        args, kwargs = calls[0]
        title, finding_text, header, rows, widths, backgrounds, header_style = args
        self.assertEqual(["budget-card"], kwargs.get("before_table"))
        self.assertEqual("PoE Detail", title)
        self.assertEqual(finding.finding, finding_text)
        self.assertEqual(["Pre Port", "Post Port", "Status", "Pre Evidence", "Post Evidence"], header)
        self.assertEqual([8.0, 8.0, 12.5, 34.5, 34.5], widths)
        self.assertEqual(["pass-a", "pass-b"], backgrounds)
        self.assertEqual("tiny", header_style)
        self.assertEqual(2, len(rows))
        self.assertEqual("tiny:Gi1/0/1", rows[0][0])
        self.assertEqual("tiny:Te1/0/1", rows[0][1])
        self.assertEqual("tiny:PoE still delivering", rows[0][2])

    def test_append_poe_pdf_sections_uses_warn_background(self):
        finding = FakeFinding("PoE", "PoE delivery missing.", "Gi1/0/1 -> Te1/0/1: PoE missing | pre=on | post=off")
        finding.severity = "WARN"
        calls = []

        append_poe_pdf_sections(
            [finding],
            is_poe_finding=lambda item: item.category == "PoE",
            parse_poe_detail_line=parse_poe_detail_line,
            poe_budget_card=lambda detail: None,
            detail_table=lambda *args, **kwargs: calls.append((args, kwargs)),
            paragraph=lambda text, style: f"{style}:{text}",
            tiny_style="tiny",
            inch=10.0,
            warn_bg="warn",
            pass_a="pass-a",
            pass_b="pass-b",
        )

        self.assertEqual(["warn"], calls[0][0][5])

    def test_build_poe_budget_pdf_card_renders_summary_bar_and_context_note(self):
        detail = "\n".join(
            [
                "POE_BUDGET|pre|125.00|24.30|100.70|Available:125.0(w) Used:24.3(w) Remaining:100.7(w)",
                "POE_BUDGET|post|400.00|54.30|345.70|Available:400.0(w) Used:54.3(w) Remaining:345.7(w)",
                "POE_SPEED_UPGRADE|2|Gi1/0/1 -> Te1/0/1: 1000 -> 2.5G",
            ]
        )
        bar_calls = []

        class FakeTable:
            def __init__(self, rows, colWidths=None):
                self.rows = rows
                self.colWidths = colWidths

            def setStyle(self, _style):
                return None

        card = build_poe_budget_pdf_card(
            detail,
            paragraph_cls=lambda text, style: ("Paragraph", style, text),
            table_cls=FakeTable,
            table_style_cls=lambda styles: styles,
            colors=type("Colors", (), {"HexColor": lambda _self, value: value})(),
            tiny_style="tiny",
            normal_style="normal",
            note_style="note",
            build_poe_budget_render_data=build_poe_budget_render_data,
            poe_budget_bar=lambda pre_pct, post_pct, width: bar_calls.append((pre_pct, post_pct, width))
            or ("Drawing", pre_pct, post_pct),
            card_width=702,
        )

        self.assertAlmostEqual(6.075, bar_calls[0][0])
        self.assertAlmostEqual(13.575, bar_calls[0][1])
        self.assertAlmostEqual(poe_budget_bar_width(702), bar_calls[0][2])
        self.assertEqual(
            ("Paragraph", "normal", '<b>PoE Budget</b> <font color="#4f5b57" size="7">(gray = pre-change, black = post-change)</font>'),
            card.rows[0][0],
        )
        self.assertEqual(
            ("Paragraph", "tiny", "Post-change used 54.30 W / 400.00 W (13.6%); remaining 345.70 W; delta +30.00 W"),
            card.rows[1][0],
        )
        self.assertEqual("Drawing", card.rows[2][0][0])
        self.assertAlmostEqual(6.075, card.rows[2][0][1])
        self.assertAlmostEqual(13.575, card.rows[2][0][2])
        self.assertIn(
            "PoE draw increased after the change, and 2 powered mapped endpoint(s)",
            card.rows[3][0][2],
        )

    def test_append_neighbor_pdf_sections_builds_rows_and_backgrounds(self):
        finding = FakeFinding(
            "CDP Neighbors",
            "Expected neighbors retained.",
            "\n".join(
                [
                    "core-router: Gi1/0/49 -> Te1/1/1, remote Twe1/0/1",
                    "new-switch.example on Te1/1/8, remote Gi0/48",
                ]
            ),
        )
        finding.severity = "PASS"
        calls = []

        append_neighbor_pdf_sections(
            [FakeFinding("PoE", "Ignore", "detail"), finding],
            is_neighbor_finding=lambda item: item.category.endswith("Neighbors"),
            parse_neighbor_detail_line=parse_neighbor_detail_line,
            detail_table=lambda *args: calls.append(args),
            paragraph=lambda text, style: f"{style}:{text}",
            tiny_style="tiny",
            inch=10.0,
            warn_bg="warn",
            info_bg="info",
            pass_a="pass-a",
            pass_b="pass-b",
        )

        title, finding_text, header, rows, widths, backgrounds, header_style = calls[0]
        self.assertEqual("CDP Neighbors Detail", title)
        self.assertEqual(finding.finding, finding_text)
        self.assertEqual(["Status", "Neighbor", "Pre Local", "Post Local", "Remote", "Evidence"], header)
        self.assertEqual([10.5, 20.0, 8.5, 8.5, 12.0, 36.0], widths)
        self.assertEqual(["pass-a", "pass-b"], backgrounds)
        self.assertEqual("tiny", header_style)
        self.assertEqual("tiny:Matched mapped", rows[0][0])
        self.assertEqual("tiny:core-router", rows[0][1])
        self.assertEqual("tiny:Te1/1/1", rows[0][3])

    def test_append_neighbor_pdf_sections_uses_warn_and_info_backgrounds(self):
        warn_finding = FakeFinding("LLDP Neighbors", "Warn", "access-ap on Gi1/0/3, remote Gi0/1")
        warn_finding.severity = "WARN"
        info_finding = FakeFinding("LLDP Neighbors", "Info", "new-switch.example on Te1/1/8, remote Gi0/48")
        info_finding.severity = "INFO"
        calls = []

        append_neighbor_pdf_sections(
            [warn_finding, info_finding],
            is_neighbor_finding=lambda item: item.category.endswith("Neighbors"),
            parse_neighbor_detail_line=parse_neighbor_detail_line,
            detail_table=lambda *args: calls.append(args),
            paragraph=lambda text, style: f"{style}:{text}",
            tiny_style="tiny",
            inch=10.0,
            warn_bg="warn",
            info_bg="info",
            pass_a="pass-a",
            pass_b="pass-b",
        )

        self.assertEqual(["warn"], calls[0][5])
        self.assertEqual(["info"], calls[1][5])

    def test_append_interface_status_pdf_sections_builds_rows_and_backgrounds(self):
        finding = FakeFinding(
            "Interface Status",
            "Mapped access ports remained connected.",
            "\n".join(
                [
                    "Gi1/0/3 -> Te1/0/3 role=access: connected before and after | pre=Gi1/0/3 connected 10/100/1000 | post=Te1/0/3 connected 2.5G | note=observed endpoint",
                    "Gi1/0/4 -> Te1/0/4 role=access: connected before and after | pre=Gi1/0/4 connected 10/100/1000 | post=Te1/0/4 connected 2.5G",
                ]
            ),
        )
        finding.severity = "PASS"
        calls = []

        append_interface_status_pdf_sections(
            [FakeFinding("PoE", "Ignore", "detail"), finding],
            is_interface_status_finding=lambda item: item.category == "Interface Status",
            parse_interface_detail_line=parse_interface_detail_line,
            detail_table=lambda *args: calls.append(args),
            paragraph=lambda text, style: f"{style}:{text}",
            tiny_style="tiny",
            inch=10.0,
            warn_bg="warn",
            info_bg="info",
            pass_a="pass-a",
            pass_b="pass-b",
        )

        title, finding_text, header, rows, widths, backgrounds, header_style = calls[0]
        self.assertEqual("Interface Status Detail", title)
        self.assertEqual(finding.finding, finding_text)
        self.assertEqual(["Pre", "Post", "Role", "Status", "Pre Evidence", "Post Evidence", "Note"], header)
        self.assertEqual([7.0, 7.0, 8.0, 9.5, 26.0, 26.0, 11.0], widths)
        self.assertEqual(["pass-a", "pass-b"], backgrounds)
        self.assertEqual("tiny", header_style)
        self.assertEqual("tiny:Gi1/0/3", rows[0][0])
        self.assertEqual("tiny:Te1/0/3", rows[0][1])
        self.assertEqual("tiny:observed endpoint", rows[0][6])

    def test_append_interface_status_pdf_sections_uses_warn_and_info_backgrounds(self):
        warn_finding = FakeFinding("Interface Status", "Warn", "Gi1/0/3 -> Te1/0/3 role=access: missing | pre=connected | post=notconnect")
        warn_finding.severity = "WARN"
        info_finding = FakeFinding("Interface Status", "Info", "Gi1/0/3 -> Te1/0/3 role=access: newly connected | post=connected")
        info_finding.severity = "INFO"
        calls = []

        append_interface_status_pdf_sections(
            [warn_finding, info_finding],
            is_interface_status_finding=lambda item: item.category == "Interface Status",
            parse_interface_detail_line=parse_interface_detail_line,
            detail_table=lambda *args: calls.append(args),
            paragraph=lambda text, style: f"{style}:{text}",
            tiny_style="tiny",
            inch=10.0,
            warn_bg="warn",
            info_bg="info",
            pass_a="pass-a",
            pass_b="pass-b",
        )

        self.assertEqual(["warn"], calls[0][5])
        self.assertEqual(["info"], calls[1][5])

    def test_append_inventory_pdf_sections_builds_rows_and_backgrounds(self):
        finding = FakeFinding(
            "Inventory",
            "Inventory parsed: 2 PID/model value(s), 2 serial value(s).",
            "\n".join(
                [
                    "component|description|pid|vid|serial",
                    "Switch 1|48-port switch|C9300-48P|V02|SANITIZED1234",
                    "Power Supply 1|AC PSU|PWR-C1-715WAC|V01|SANITIZED5678",
                ]
            ),
        )
        calls = []

        append_inventory_pdf_sections(
            [FakeFinding("Logs", "Ignore", "detail"), finding],
            is_inventory_finding=lambda item: item.category == "Inventory",
            parse_inventory_detail=parse_inventory_detail,
            detail_table=lambda *args: calls.append(args),
            paragraph=lambda text, style: f"{style}:{text}",
            tiny_style="tiny",
            inch=10.0,
            pass_a="pass-a",
            pass_b="pass-b",
        )

        self.assertEqual(1, len(calls))
        title, finding_text, header, rows, widths, backgrounds, header_style = calls[0]
        self.assertEqual("Inventory Detail", title)
        self.assertEqual(finding.finding, finding_text)
        self.assertEqual(["Component", "Description", "PID / Model", "VID", "Serial"], header)
        self.assertEqual([22.0, 24.0, 17.5, 5.5, 15.5], widths)
        self.assertEqual(["pass-a", "pass-b"], backgrounds)
        self.assertEqual("tiny", header_style)
        self.assertEqual("tiny:Switch 1", rows[0][0])
        self.assertEqual("tiny:C9300-48P", rows[0][2])
        self.assertEqual("tiny:SANITIZED5678", rows[1][4])

    def test_append_transceiver_pdf_sections_builds_rows_bars_and_backgrounds(self):
        finding = FakeFinding(
            "Transceiver",
            "Transceiver readings retained.",
            """
Te1/1/1:
PRE-CHANGE:
Te1/1/1 -5.26 1.00 -3.00 -9.51 -13.51
POST-CHANGE:
Te1/1/1 -4.26 1.00 -3.00 -9.51 -13.51
Te1/1/2:
Te1/1/2 86.00 89.00 85.00 -5.00 -9.00
""",
        )
        calls = []
        bar_calls = []

        def fake_bar(*args):
            bar_calls.append(args)
            return f"bar:{args[0]:.2f}"

        append_transceiver_pdf_sections(
            [FakeFinding("Logs", "Ignore", "detail"), finding],
            is_transceiver_finding=lambda item: item.category == "Transceiver",
            parse_transceiver_visual_rows=parse_transceiver_visual_rows,
            transceiver_level_class=transceiver_level_class,
            transceiver_bar=fake_bar,
            detail_table=lambda *args: calls.append(args),
            paragraph=lambda text, style: f"{style}:{text}",
            tiny_style="tiny",
            inch=10.0,
            alarm_bg="alarm",
            warn_bg="warn",
            pass_a="pass-a",
        )

        self.assertEqual(1, len(calls))
        title, finding_text, header, rows, widths, backgrounds, header_style = calls[0]
        self.assertEqual("Transceiver Detail (gray = pre-change, black = post-change)", title)
        self.assertEqual(finding.finding, finding_text)
        self.assertEqual(["Interface", "Metric", "Pre", "Post", "Delta", "Low Alarm", "Low Warn", "High Warn", "High Alarm", "Range"], header)
        self.assertEqual([6.5, 8.5, 9.0, 9.0, 5.5, 7.8, 7.8, 7.8, 7.8, 20.0], [round(width, 1) for width in widths])
        self.assertEqual(["pass-a", "warn"], backgrounds)
        self.assertEqual("tiny", header_style)
        self.assertEqual("tiny:Te1/1/1", rows[0][0])
        self.assertEqual("tiny:dBm -5.26", rows[0][2])
        self.assertEqual("tiny:dBm -4.26", rows[0][3])
        self.assertEqual("tiny:+1.00", rows[0][4])
        self.assertEqual("bar:-4.26", rows[0][9])
        self.assertEqual((-4.26, -5.26, -13.51, -9.51, -3.0, 1.0), bar_calls[0])

    def test_append_stp_root_pdf_sections_builds_rows_and_severity_backgrounds(self):
        finding = FakeFinding(
            "STP Root",
            "STP root retained through mapped uplink.",
            "\n".join(
                [
                    "VLAN0001: root unchanged and root port mapped (Gi1/0/49 -> Te1/1/1); cost changed 4 -> 2000.",
                    "VLAN0004: root bridge unchanged but root port changed unexpectedly. pre port=Gi1/0/50, actual post=Te1/1/8",
                ]
            ),
        )
        finding.severity = "PASS"
        calls = []

        append_stp_root_pdf_sections(
            [FakeFinding("Logs", "Ignore", "detail"), finding],
            is_stp_root_finding=lambda item: item.category == "STP Root",
            parse_stp_detail_line=parse_stp_detail_line,
            detail_table=lambda *args: calls.append(args),
            paragraph=lambda text, style: f"{style}:{text}",
            normal_style="normal",
            tiny_style="tiny",
            inch=10.0,
            warn_bg="warn",
            info_bg="info",
            pass_a="pass-a",
            pass_b="pass-b",
        )

        self.assertEqual(1, len(calls))
        title, finding_text, header, rows, widths, backgrounds, header_style = calls[0]
        self.assertEqual("STP Root Detail", title)
        self.assertEqual(finding.finding, finding_text)
        self.assertEqual(["VLAN", "Status", "Pre Port", "Post Port", "Cost", "Context"], header)
        self.assertEqual([7.5, 13.5, 9.0, 9.0, 7.0, 52.5], widths)
        self.assertEqual(["pass-a", "pass-b"], backgrounds)
        self.assertEqual("tiny", header_style)
        self.assertEqual("tiny:VLAN0001", rows[0][0])
        self.assertEqual("tiny:Root retained", rows[0][1])
        self.assertEqual("normal:root bridge unchanged but root port changed unexpectedly. pre port=Gi1/0/50, actual post=Te1/1/8", rows[1][5])

    def test_append_stp_root_pdf_sections_uses_warn_and_info_backgrounds(self):
        warn_finding = FakeFinding("STP Root", "Warn finding", "VLAN0001: root bridge changed.")
        warn_finding.severity = "WARN"
        info_finding = FakeFinding("STP Root", "Info finding", "VLAN0001: local switch became root post-change.")
        info_finding.severity = "INFO"
        calls = []

        append_stp_root_pdf_sections(
            [warn_finding, info_finding],
            is_stp_root_finding=lambda item: item.category == "STP Root",
            parse_stp_detail_line=parse_stp_detail_line,
            detail_table=lambda *args: calls.append(args),
            paragraph=lambda text, style: f"{style}:{text}",
            normal_style="normal",
            tiny_style="tiny",
            inch=10.0,
            warn_bg="warn",
            info_bg="info",
            pass_a="pass-a",
            pass_b="pass-b",
        )

        self.assertEqual(["warn"], calls[0][5])
        self.assertEqual(["info"], calls[1][5])

    def test_append_mac_correlation_pdf_sections_builds_rows_and_backgrounds(self):
        finding = FakeFinding(
            "MAC Correlation",
            "MAC check found moved and missing entries.",
            "\n".join(
                [
                    "status|mac|vlan|pre_port|expected_post_port|actual_post_port|note",
                    "PASS|aaaa.bbbb.0001|10|Gi1/0/1|Gi2/0/1|Gi2/0/1|ok",
                    "MOVED|aaaa.bbbb.0002|10|Gi1/0/2|Gi2/0/2|Gi2/0/9|review",
                    "MISSING|aaaa.bbbb.0003|10|Gi1/0/3|Gi2/0/3|Not found|missing",
                    "UNKNOWN|aaaa.bbbb.0004|10|Gi1/0/4|Gi2/0/4|Gi2/0/4|unexpected",
                ]
            ),
        )
        calls = []

        append_mac_correlation_pdf_sections(
            [FakeFinding("STP Root", "Ignore", "detail"), finding],
            is_mac_correlation_finding=lambda item: item.category == "MAC Correlation",
            parse_mac_correlation_detail=parse_mac_correlation_detail,
            detail_table=lambda *args: calls.append(args),
            paragraph=lambda text, style: f"{style}:{text}",
            normal_style="normal",
            tiny_style="tiny",
            inch=10.0,
            moved_bg="moved",
            missing_bg="missing",
            pass_a="pass-a",
            pass_b="pass-b",
            fallback_bg="fallback",
        )

        self.assertEqual(1, len(calls))
        title, finding_text, header, rows, widths, backgrounds, header_style = calls[0]
        self.assertEqual("Access Port MAC Correlation", title)
        self.assertEqual(finding.finding, finding_text)
        self.assertEqual(["Status", "MAC", "VLAN", "Pre Port", "Expected Post", "Actual Post", "Note"], header)
        self.assertEqual([6.5, 11.0, 4.5, 8.5, 10.5, 10.5, 41.0], widths)
        self.assertEqual(["pass-a", "moved", "missing", "fallback"], backgrounds)
        self.assertEqual("tiny", header_style)
        self.assertEqual("tiny:PASS", rows[0][0])
        self.assertEqual("tiny:aaaa.bbbb.0002", rows[1][1])
        self.assertEqual("normal:missing", rows[2][6])


if __name__ == "__main__":
    unittest.main()
