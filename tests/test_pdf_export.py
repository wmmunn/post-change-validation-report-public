import tempfile
import unittest
from pathlib import Path
from typing import List, Optional
from unittest import mock

try:
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.graphics.shapes import Drawing, Rect, Line
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
except Exception:  # pragma: no cover - environment-dependent optional dependency
    colors = None
    getSampleStyleSheet = None
    inch = None
    Drawing = None
    Paragraph = None
    Spacer = None
    Table = None
    TableStyle = None

from src.post_change_validation_interface_status_rendering import parse_interface_detail_line
from src.post_change_validation_inventory_rendering import parse_inventory_detail
from src.post_change_validation_logs_rendering import parse_log_detail_line
from src.post_change_validation_mac_rendering import parse_mac_correlation_detail
from src.post_change_validation_models import Finding
from src.post_change_validation_neighbor_rendering import parse_neighbor_detail_line
from src.post_change_validation_pdf import (
    build_pdf_story,
    export_pdf,
    export_pdf_from_html_browser,
    find_browser_pdf_renderer,
)
from src.post_change_validation_pdf_rendering import (
    append_detail_table,
    build_poe_budget_pdf_card,
    pdf_paragraph,
    poe_budget_bar_width,
)
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
from src.post_change_validation_poe_rendering import build_poe_budget_render_data, parse_poe_detail_line
from src.post_change_validation_port_map_rendering import parse_port_map_detail
from post_change_validation_report_shell import (
    append_pdf_report_shell,
    is_interface_status_finding,
    is_inventory_finding,
    is_logs_finding,
    is_mac_correlation_finding,
    is_neighbor_finding,
    is_poe_finding,
    is_port_map_finding,
    is_stp_root_finding,
    is_transceiver_finding,
)
from src.post_change_validation_stp_rendering import parse_stp_detail_line
from src.post_change_validation_transceiver_rendering import (
    transceiver_scale_bounds,
    transceiver_scale_pct,
)
from src.post_change_validation_transceivers import (
    parse_transceiver_visual_rows,
    transceiver_level_class,
)


def sanitized_pdf_findings() -> List[Finding]:
    return [
        Finding(
            "INFO",
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
        ),
        Finding(
            "PASS",
            "PoE",
            "PoE delivery restored on mapped endpoint.",
            "Gi1/0/1 -> Te1/0/1: PoE still delivering | pre=Gi1/0/1 auto on 6.3 | post=Te1/0/1 auto on 6.1",
        ),
        Finding(
            "PASS",
            "CDP Neighbors",
            "Expected neighbors retained.",
            "core-router: Gi1/0/49 -> Te1/1/1, remote Twe1/0/1",
        ),
        Finding(
            "PASS",
            "Interface Status",
            "Mapped access ports remained connected.",
            "Gi1/0/3 -> Te1/0/3 role=access: connected before and after | pre=Gi1/0/3 connected 10/100/1000 | post=Te1/0/3 connected 2.5G",
        ),
        Finding(
            "WARN",
            "Logs",
            "Log review recommended: 1 message(s); correlate with approved change activity.",
            "Jun 20 12:03:04 %LINK-3-UPDOWN: Interface Te1/1/1 changed state",
        ),
        Finding(
            "INFO",
            "Inventory",
            "Inventory parsed: 1 PID/model value(s), 1 serial value(s).",
            "component|description|pid|vid|serial\nSwitch 1|48-port switch|C9300-48P|V02|SANITIZED1234",
        ),
        Finding(
            "PASS",
            "Transceiver",
            "Transceiver readings retained.",
            "Te1/1/1:\nPRE-CHANGE:\nTe1/1/1 -5.26 1.00 -3.00 -9.51 -13.51\nPOST-CHANGE:\nTe1/1/1 -4.26 1.00 -3.00 -9.51 -13.51",
        ),
        Finding(
            "PASS",
            "STP Root",
            "STP root retained through mapped uplink.",
            "VLAN0001: root unchanged and root port mapped (Gi1/0/49 -> Te1/1/1); cost changed 4 -> 2000.",
        ),
        Finding(
            "WARN",
            "MAC Correlation",
            "MAC check found moved and missing entries.",
            "status|mac|vlan|pre_port|expected_post_port|actual_post_port|note\nMOVED|aaaa.bbbb.0002|10|Gi1/0/2|Gi2/0/2|Gi2/0/9|review",
        ),
    ]


def _cell_fingerprint(cell: object) -> object:
    if hasattr(cell, "getPlainText"):
        return ("Paragraph", cell.getPlainText())
    if type(cell).__name__ == "Drawing":
        return ("Drawing", round(cell.width, 2), round(cell.height, 2))
    if isinstance(cell, str):
        return ("str", cell)
    return (type(cell).__name__, str(cell))


def story_fingerprint(story: list) -> list:
    fingerprint = []
    for item in story:
        name = type(item).__name__
        if name == "Paragraph":
            fingerprint.append(("Paragraph", item.getPlainText()))
        elif name == "Spacer":
            fingerprint.append(("Spacer", round(item.height, 4)))
        elif name == "Table":
            fingerprint.append(
                (
                    "Table",
                    [[_cell_fingerprint(cell) for cell in row] for row in item._cellvalues],
                )
            )
        elif name == "Drawing":
            fingerprint.append(("Drawing", round(item.width, 2), round(item.height, 2)))
        else:
            fingerprint.append((name,))
    return fingerprint


def legacy_build_pdf_story(
    findings: List[Finding],
    pre_file: str,
    post_file: str,
    port_map_file: str,
) -> list:
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    small = ParagraphStyle("small", parent=normal, fontName="Courier", fontSize=7, leading=8)
    tiny = ParagraphStyle("tiny", parent=normal, fontSize=6.5, leading=7.5)
    note = ParagraphStyle("poe_note", parent=tiny, textColor=colors.HexColor("#34454d"))
    pass_a = colors.HexColor("#eef8ef")
    pass_b = colors.HexColor("#dff3df")
    info_bg = colors.HexColor("#f5f7f8")
    warn_bg = colors.HexColor("#fff2a8")
    alarm_bg = colors.HexColor("#ffd6d2")
    header_bg = colors.HexColor("#d8e1de")

    def p(text: object, style=normal) -> Paragraph:
        return pdf_paragraph(Paragraph, text, style)

    story: list = []

    def detail_table(
        title_text: str,
        finding_text: str,
        header: List[str],
        rows: List[List[object]],
        widths: List[float],
        row_backgrounds: Optional[List[object]] = None,
        header_style=normal,
        before_table: Optional[List[object]] = None,
    ) -> None:
        append_detail_table(
            story,
            title_text,
            finding_text,
            header,
            rows,
            widths,
            styles=styles,
            colors=colors,
            table_cls=Table,
            table_style_cls=TableStyle,
            paragraph_cls=Paragraph,
            spacer_cls=Spacer,
            header_bg=header_bg,
            normal_style=normal,
            row_backgrounds=row_backgrounds,
            header_style=header_style,
            before_table=before_table,
        )

    poe_detail_width = 9.75 * inch

    def pdf_transceiver_bar(
        value: float,
        pre_value: Optional[float],
        low_alarm: float,
        low_warn: float,
        high_warn: float,
        high_alarm: float,
    ) -> Drawing:
        width = 138
        height = 12
        d = Drawing(width, height)
        scale_min, scale_max = transceiver_scale_bounds(low_alarm, high_alarm)
        low_alarm_pct = transceiver_scale_pct(low_alarm, scale_min, scale_max) / 100.0
        low_warn_pct = transceiver_scale_pct(low_warn, scale_min, scale_max) / 100.0
        high_warn_pct = transceiver_scale_pct(high_warn, scale_min, scale_max) / 100.0
        high_alarm_pct = transceiver_scale_pct(high_alarm, scale_min, scale_max) / 100.0
        zones = [
            (0.0, low_alarm_pct, colors.HexColor("#f4b4ad")),
            (low_alarm_pct, low_warn_pct, colors.HexColor("#ffe19a")),
            (low_warn_pct, high_warn_pct, colors.HexColor("#bfe8c4")),
            (high_warn_pct, high_alarm_pct, colors.HexColor("#ffe19a")),
            (high_alarm_pct, 1.0, colors.HexColor("#f4b4ad")),
        ]
        for start, end, fill in zones:
            if end > start:
                d.add(Rect(start * width, 1, (end - start) * width, height - 2, fillColor=fill, strokeColor=None))
        d.add(Rect(0, 1, width, height - 2, fillColor=None, strokeColor=colors.grey, strokeWidth=0.5))
        if pre_value is not None:
            pre_x = transceiver_scale_pct(float(pre_value), scale_min, scale_max) / 100.0 * width
            d.add(Line(pre_x, 0, pre_x, height, strokeColor=colors.grey, strokeWidth=1.2))
        post_x = transceiver_scale_pct(value, scale_min, scale_max) / 100.0 * width
        d.add(Line(post_x, 0, post_x, height, strokeColor=colors.black, strokeWidth=1.5))
        return d

    def pdf_poe_budget_bar(pre_pct: Optional[float], post_pct: float, width: float) -> Drawing:
        from src.post_change_validation_pdf import _pdf_poe_budget_bar

        return _pdf_poe_budget_bar(Drawing, Rect, Line, colors, pre_pct, post_pct, width=width)

    def poe_budget_card(detail: str):
        return build_poe_budget_pdf_card(
            detail,
            paragraph_cls=Paragraph,
            table_cls=Table,
            table_style_cls=TableStyle,
            colors=colors,
            tiny_style=tiny,
            normal_style=normal,
            note_style=note,
            build_poe_budget_render_data=build_poe_budget_render_data,
            poe_budget_bar=pdf_poe_budget_bar,
            card_width=poe_detail_width,
        )

    def append_structured_detail_sections() -> None:
        append_port_map_pdf_sections(
            findings,
            is_port_map_finding=is_port_map_finding,
            parse_port_map_detail=parse_port_map_detail,
            detail_table=detail_table,
            paragraph=p,
            tiny_style=tiny,
            inch=inch,
            info_bg=info_bg,
            pass_a=pass_a,
        )

        append_poe_pdf_sections(
            findings,
            is_poe_finding=is_poe_finding,
            parse_poe_detail_line=parse_poe_detail_line,
            poe_budget_card=poe_budget_card,
            detail_table=detail_table,
            paragraph=p,
            tiny_style=tiny,
            inch=inch,
            warn_bg=warn_bg,
            pass_a=pass_a,
            pass_b=pass_b,
        )

        append_neighbor_pdf_sections(
            findings,
            is_neighbor_finding=is_neighbor_finding,
            parse_neighbor_detail_line=parse_neighbor_detail_line,
            detail_table=detail_table,
            paragraph=p,
            tiny_style=tiny,
            inch=inch,
            warn_bg=warn_bg,
            info_bg=info_bg,
            pass_a=pass_a,
            pass_b=pass_b,
        )

        append_interface_status_pdf_sections(
            findings,
            is_interface_status_finding=is_interface_status_finding,
            parse_interface_detail_line=parse_interface_detail_line,
            detail_table=detail_table,
            paragraph=p,
            tiny_style=tiny,
            inch=inch,
            warn_bg=warn_bg,
            info_bg=info_bg,
            pass_a=pass_a,
            pass_b=pass_b,
        )

        append_logs_pdf_sections(
            findings,
            is_logs_finding=is_logs_finding,
            parse_log_detail_line=parse_log_detail_line,
            detail_table=detail_table,
            paragraph=p,
            tiny_style=tiny,
            inch=inch,
            info_bg=info_bg,
            pass_a=pass_a,
            pass_b=pass_b,
        )

        append_inventory_pdf_sections(
            findings,
            is_inventory_finding=is_inventory_finding,
            parse_inventory_detail=parse_inventory_detail,
            detail_table=detail_table,
            paragraph=p,
            tiny_style=tiny,
            inch=inch,
            pass_a=pass_a,
            pass_b=pass_b,
        )

        append_transceiver_pdf_sections(
            findings,
            is_transceiver_finding=is_transceiver_finding,
            parse_transceiver_visual_rows=parse_transceiver_visual_rows,
            transceiver_level_class=transceiver_level_class,
            transceiver_bar=pdf_transceiver_bar,
            detail_table=detail_table,
            paragraph=p,
            tiny_style=tiny,
            inch=inch,
            alarm_bg=alarm_bg,
            warn_bg=warn_bg,
            pass_a=pass_a,
        )

        append_stp_root_pdf_sections(
            findings,
            is_stp_root_finding=is_stp_root_finding,
            parse_stp_detail_line=parse_stp_detail_line,
            detail_table=detail_table,
            paragraph=p,
            normal_style=normal,
            tiny_style=tiny,
            inch=inch,
            warn_bg=warn_bg,
            info_bg=info_bg,
            pass_a=pass_a,
            pass_b=pass_b,
        )

        append_mac_correlation_pdf_sections(
            findings,
            is_mac_correlation_finding=is_mac_correlation_finding,
            parse_mac_correlation_detail=parse_mac_correlation_detail,
            detail_table=detail_table,
            paragraph=p,
            normal_style=normal,
            tiny_style=tiny,
            inch=inch,
            moved_bg=warn_bg,
            missing_bg=colors.HexColor("#ffd39b"),
            pass_a=pass_b,
            pass_b=colors.HexColor("#c8eec8"),
            fallback_bg=colors.whitesmoke,
        )

    append_pdf_report_shell(
        story,
        findings,
        pre_file,
        post_file,
        port_map_file,
        paragraph_cls=Paragraph,
        spacer_cls=Spacer,
        table_cls=Table,
        table_style_cls=TableStyle,
        styles=styles,
        normal_style=normal,
        small_style=small,
        colors=colors,
        inch=inch,
        info_bg=info_bg,
        before_inputs=append_structured_detail_sections,
    )
    return story


@unittest.skipIf(Paragraph is None, "reportlab is not installed")
class PdfExportStoryTests(unittest.TestCase):
    def test_story_fingerprint_matches_legacy_and_extracted(self):
        findings = sanitized_pdf_findings()
        legacy = story_fingerprint(legacy_build_pdf_story(findings, "pre.log", "post.log", ""))
        extracted = story_fingerprint(build_pdf_story(findings, "pre.log", "post.log", ""))

        self.assertEqual(len(legacy), len(extracted))
        self.assertEqual(legacy, extracted)

    def test_pdf_highlights_render_status_cards(self):
        findings = [
            Finding("WARN", "Access Port MAC Correlation", "Access-port MACs checked: 40.", ""),
            Finding("PASS", "PoE", "1 previously powered access port(s) still show PoE after change.", ""),
            Finding("PASS", "CDP Neighbors", "2 cdp neighbor record(s) matched after change.", ""),
            Finding("WARN", "Interface Status", "1 mapped port issue(s) require review.", ""),
            Finding("PASS", "Trunks", "No pre-change trunk ports disappeared.", ""),
            Finding("PASS", "STP Root", "2 STP VLAN(s) retained expected root behavior.", ""),
        ]
        story = build_pdf_story(findings, "pre.log", "post.log", "")
        fingerprint = story_fingerprint(story)
        joined = "\n".join(str(item) for item in fingerprint)
        self.assertNotIn("('str', 'Area')", joined)
        self.assertIn("MAC Addresses", joined)
        self.assertIn("PoE Delivery", joined)
        self.assertIn("Neighbors", joined)
        self.assertIn("STP Root", joined)

    def test_before_inputs_wires_section_appenders_in_order(self):
        findings = sanitized_pdf_findings()
        call_order: list[str] = []
        section_names = [
            "append_port_map_pdf_sections",
            "append_poe_pdf_sections",
            "append_neighbor_pdf_sections",
            "append_interface_status_pdf_sections",
            "append_logs_pdf_sections",
            "append_inventory_pdf_sections",
            "append_transceiver_pdf_sections",
            "append_stp_root_pdf_sections",
            "append_mac_correlation_pdf_sections",
        ]

        def make_tracker(name: str):
            def _tracker(*args, **kwargs):
                call_order.append(name)

            return _tracker

        patches = [
            mock.patch(f"src.post_change_validation_pdf.{name}", side_effect=make_tracker(name))
            for name in section_names
        ]
        captured_before_inputs = []

        def capture_shell(*args, **kwargs):
            captured_before_inputs.append(kwargs.get("before_inputs"))

        with mock.patch("src.post_change_validation_pdf.append_pdf_report_shell", side_effect=capture_shell):
            for patcher in patches:
                patcher.start()
            try:
                build_pdf_story(findings, "pre.log", "post.log", "")
                self.assertEqual(1, len(captured_before_inputs))
                self.assertTrue(callable(captured_before_inputs[0]))
                captured_before_inputs[0]()
            finally:
                for patcher in reversed(patches):
                    patcher.stop()

        self.assertEqual(section_names, call_order)

    def test_export_pdf_writes_pdf_file(self):
        findings = sanitized_pdf_findings()
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / "report.pdf"
            export_pdf(findings, "pre.log", "post.log", "", str(out_path))
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 0)

    def test_export_pdf_renders_poe_budget_meter_without_raw_pipe_rows(self):
        findings = [
            Finding(
                "PASS",
                "PoE",
                "26 previously powered access port(s) still show PoE after change.",
                "\n".join(
                    [
                        "POE_BUDGET|pre|1745.00|90.00|1655.00|Available:1745.0(w) Used:90.0(w) Remaining:1655.0(w)",
                        "POE_BUDGET|post|1745.00|209.70|1535.30|Available:1745.0(w) Used:209.7(w) Remaining:1535.3(w)",
                        "POE_SPEED_UPGRADE|7|Gi1/0/2 -> Te1/0/2: 1000 -> 2.5G",
                        "Gi1/0/2 -> Te1/0/2: PoE still delivering | pre=Gi1/0/2 auto on 4.3 | post=Te1/0/2 auto on 4.1",
                    ]
                ),
            )
        ]
        story = build_pdf_story(findings, "pre.log", "post.log", "")
        fingerprint = story_fingerprint(story)
        joined = "\n".join(str(item) for item in fingerprint)
        self.assertIn("PoE Budget", joined)
        self.assertIn("Post-change used 209.70 W / 1745.00 W (12.0%)", joined)
        self.assertIn("Gi1/0/2", joined)
        self.assertNotIn("POE_BUDGET|", joined)
        self.assertNotIn("POE_SPEED_UPGRADE|", joined)

        def collect_drawings(items):
            drawings = []
            for item in items:
                if item[0] == "Drawing":
                    drawings.append(item)
                elif item[0] == "Table":
                    for row in item[1]:
                        drawings.extend(collect_drawings(row))
            return drawings

        drawing_items = collect_drawings(fingerprint)
        self.assertTrue(any(item[1] == poe_budget_bar_width(9.75 * inch) for item in drawing_items))

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / "report.pdf"
            export_pdf(findings, "pre.log", "post.log", "", str(out_path))
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 0)


class PdfExportErrorTests(unittest.TestCase):
    def test_export_pdf_raises_when_reportlab_missing(self):
        findings = sanitized_pdf_findings()
        with mock.patch("src.post_change_validation_pdf.build_pdf_story", side_effect=ImportError("no reportlab")):
            with self.assertRaisesRegex(RuntimeError, "PDF export requires reportlab"):
                export_pdf(findings, "pre.log", "post.log", "", "out.pdf")

    def test_find_browser_pdf_renderer_returns_empty_when_no_candidates_exist(self):
        with mock.patch("src.post_change_validation_pdf.shutil.which", return_value=None):
            with mock.patch("pathlib.Path.exists", return_value=False):
                self.assertEqual("", find_browser_pdf_renderer())

    def test_export_pdf_from_html_browser_raises_when_browser_missing(self):
        findings = sanitized_pdf_findings()
        with mock.patch("src.post_change_validation_pdf.find_browser_pdf_renderer", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "No Edge/Chrome browser executable found"):
                export_pdf_from_html_browser(findings, "pre.log", "post.log", "", "out.pdf")

    def test_export_pdf_from_html_browser_copies_produced_pdf(self):
        findings = sanitized_pdf_findings()
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / "report.pdf"
            browser_root = Path(tmp_dir) / "browser-work"
            browser_root.mkdir()
            browser_pdf = browser_root / "post_change_validation_report.pdf"

            class FakeResult:
                returncode = 0
                stdout = ""
                stderr = ""

            def fake_run(cmd, **kwargs):
                browser_pdf.write_bytes(b"%PDF-1.4 sanitized")
                return FakeResult()

            with mock.patch("src.post_change_validation_pdf.tempfile.mkdtemp", return_value=str(browser_root)):
                with mock.patch("src.post_change_validation_pdf.find_browser_pdf_renderer", return_value="C:\\browser\\msedge.exe"):
                    with mock.patch("src.post_change_validation_pdf.build_html_report", return_value="<html>sanitized</html>"):
                        with mock.patch("src.post_change_validation_pdf.subprocess.run", side_effect=fake_run):
                            renderer = export_pdf_from_html_browser(
                                findings,
                                "pre.log",
                                "post.log",
                                "",
                                str(out_path),
                            )

            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 0)
            self.assertIn("HTML-rendered PDF via msedge.exe", renderer)


if __name__ == "__main__":
    unittest.main()
