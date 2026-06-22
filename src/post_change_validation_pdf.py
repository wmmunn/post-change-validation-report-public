"""PDF export for Post Change Validation reports."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from src.post_change_validation_interface_status_rendering import parse_interface_detail_line
from src.post_change_validation_inventory_rendering import parse_inventory_detail
from src.post_change_validation_logs_rendering import parse_log_detail_line
from src.post_change_validation_mac_rendering import parse_mac_correlation_detail
from src.post_change_validation_models import Finding
from src.post_change_validation_neighbor_rendering import parse_neighbor_detail_line
from src.post_change_validation_poe_rendering import build_poe_budget_render_data, parse_poe_detail_line
from src.post_change_validation_pdf_rendering import append_detail_table, build_poe_budget_pdf_card, pdf_paragraph
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
from src.post_change_validation_port_map_rendering import parse_port_map_detail
from post_change_validation_report_shell import (
    append_pdf_report_shell,
    build_html_report,
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


def find_browser_pdf_renderer() -> str:
    candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
        str(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
        str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def export_pdf_from_html_browser(findings: List[Finding], pre_file: str, post_file: str, port_map_file: str, out_path: str) -> str:
    browser = find_browser_pdf_renderer()
    if not browser:
        raise RuntimeError("No Edge/Chrome browser executable found for HTML-rendered PDF export.")

    html_text = build_html_report(findings, pre_file, post_file, port_map_file)
    out = Path(out_path).resolve()
    tmp_dir = tempfile.mkdtemp(prefix="pcv_pdf_")
    try:
        tmp_root = Path(tmp_dir)
        tmp_path = tmp_root / "post_change_validation_report.html"
        profile_dir = tmp_root / "browser-profile"
        browser_pdf = tmp_root / "post_change_validation_report.pdf"
        tmp_path.write_text(html_text, encoding="utf-8")
        creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        errors = []
        for headless_flag in ["--headless=new", "--headless"]:
            print_modes = [
                ("absolute", f"--print-to-pdf={str(browser_pdf)}"),
                ("relative", "--print-to-pdf=post_change_validation_report.pdf"),
                ("default", "--print-to-pdf"),
            ]
            for mode_name, print_arg in print_modes:
                for existing_pdf in tmp_root.rglob("*.pdf"):
                    try:
                        existing_pdf.unlink()
                    except Exception:
                        pass
                browser_cmd = [
                    browser,
                    headless_flag,
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--allow-file-access-from-files",
                    "--no-first-run",
                    "--window-size=1600,1000",
                    "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=1000",
                    f"--user-data-dir={str(profile_dir)}",
                    "--no-pdf-header-footer",
                    print_arg,
                    tmp_path.resolve().as_uri(),
                ]
                launch_modes = [("direct", browser_cmd, False)]
                cmd_line = subprocess.list2cmdline(browser_cmd)
                launch_modes.append(("shell", cmd_line, True))
                batch_path = tmp_root / "render_pdf.cmd"
                batch_path.write_text("@echo off\r\n" + cmd_line + "\r\n", encoding="utf-8")
                launch_modes.append(("batch", ["cmd.exe", "/d", "/c", str(batch_path)], False))
                for launch_name, cmd, use_shell in launch_modes:
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60, creationflags=creationflags, cwd=str(tmp_root), shell=use_shell)
                    pdf_candidates = [browser_pdf, tmp_root / "post_change_validation_report.pdf", tmp_root / "output.pdf"] + sorted(tmp_root.rglob("*.pdf"))
                    produced_pdf = next((candidate for candidate in pdf_candidates if candidate.exists() and candidate.stat().st_size > 0), None)
                    if result.returncode == 0 and produced_pdf:
                        out.parent.mkdir(parents=True, exist_ok=True)
                        if out.exists():
                            out.unlink()
                        shutil.copy2(produced_pdf, out)
                        return f"HTML-rendered PDF via {Path(browser).name} ({headless_flag}, {mode_name}, {launch_name})"
                    err = (result.stderr or result.stdout or "Browser PDF export failed.").strip()
                    produced = ", ".join(str(p.relative_to(tmp_root)) for p in tmp_root.rglob("*.pdf")) or "no pdf files produced"
                    errors.append(f"{headless_flag}/{mode_name}/{launch_name}: return={result.returncode}; {err[:350]}; {produced}")
        raise RuntimeError("Browser PDF export failed. " + " | ".join(errors))
    finally:
        # Edge/Chrome can briefly keep the temporary profile lockfile open after
        # the headless print command returns. Do not let cleanup noise turn a
        # successful HTML-rendered PDF into a false fallback.
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _paragraph(paragraph_cls, text: object, style, normal_style):
    return pdf_paragraph(paragraph_cls, text, style)


def _detail_table(
    story: list,
    title_text: str,
    finding_text: str,
    header: List[str],
    rows: List[List[object]],
    widths: List[float],
    *,
    styles,
    colors,
    table_cls,
    table_style_cls,
    paragraph_cls,
    spacer_cls,
    header_bg,
    normal_style,
    row_backgrounds: Optional[List[object]] = None,
    header_style=None,
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
        table_cls=table_cls,
        table_style_cls=table_style_cls,
        paragraph_cls=paragraph_cls,
        spacer_cls=spacer_cls,
        header_bg=header_bg,
        normal_style=normal_style,
        row_backgrounds=row_backgrounds,
        header_style=header_style,
        before_table=before_table,
    )


def _pdf_poe_budget_bar(
    drawing_cls,
    rect_cls,
    line_cls,
    colors,
    pre_pct: Optional[float],
    post_pct: float,
    *,
    width: float,
    height: float = 18,
):
    d = drawing_cls(width, height + 4)
    bar_y = 2
    bar_h = height
    zones = [
        (0.0, 0.70, colors.HexColor("#bfe8c4")),
        (0.70, 0.90, colors.HexColor("#ffe19a")),
        (0.90, 1.0, colors.HexColor("#f4b4ad")),
    ]
    for start, end, fill in zones:
        if end > start:
            d.add(rect_cls(start * width, bar_y, (end - start) * width, bar_h, fillColor=fill, strokeColor=None))
    d.add(rect_cls(0, bar_y, width, bar_h, fillColor=None, strokeColor=colors.grey, strokeWidth=0.5))
    if pre_pct is not None:
        pre_x = max(0.0, min(100.0, float(pre_pct))) / 100.0 * width
        d.add(line_cls(pre_x, 0, pre_x, height + 4, strokeColor=colors.HexColor("#7a7a7a"), strokeWidth=1.2))
    post_x = max(0.0, min(100.0, float(post_pct))) / 100.0 * width
    d.add(line_cls(post_x, 0, post_x, height + 4, strokeColor=colors.black, strokeWidth=1.5))
    return d


def _pdf_transceiver_bar(
    drawing_cls,
    rect_cls,
    line_cls,
    colors,
    value: float,
    pre_value: Optional[float],
    low_alarm: float,
    low_warn: float,
    high_warn: float,
    high_alarm: float,
):
    width = 138
    height = 12
    d = drawing_cls(width, height)
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
            d.add(rect_cls(start * width, 1, (end - start) * width, height - 2, fillColor=fill, strokeColor=None))
    d.add(rect_cls(0, 1, width, height - 2, fillColor=None, strokeColor=colors.grey, strokeWidth=0.5))
    if pre_value is not None:
        pre_x = transceiver_scale_pct(float(pre_value), scale_min, scale_max) / 100.0 * width
        d.add(line_cls(pre_x, 0, pre_x, height, strokeColor=colors.grey, strokeWidth=1.2))
    post_x = transceiver_scale_pct(value, scale_min, scale_max) / 100.0 * width
    d.add(line_cls(post_x, 0, post_x, height, strokeColor=colors.black, strokeWidth=1.5))
    return d


def _append_structured_detail_sections(
    findings: List[Finding],
    *,
    detail_table,
    p,
    tiny,
    inch,
    info_bg,
    pass_a,
    pass_b,
    warn_bg,
    alarm_bg,
    normal,
    colors,
    pdf_transceiver_bar,
    poe_budget_card,
) -> None:
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


def build_pdf_story(
    findings: List[Finding],
    pre_file: str,
    post_file: str,
    port_map_file: str,
) -> list:
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.graphics.shapes import Drawing, Rect, Line
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

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

    story: list = []

    def p(text: object, style=normal):
        return _paragraph(Paragraph, text, style, normal)

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
        _detail_table(
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
    ):
        return _pdf_transceiver_bar(
            Drawing,
            Rect,
            Line,
            colors,
            value,
            pre_value,
            low_alarm,
            low_warn,
            high_warn,
            high_alarm,
        )

    def pdf_poe_budget_bar(pre_pct: Optional[float], post_pct: float, width: float):
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
        _append_structured_detail_sections(
            findings,
            detail_table=detail_table,
            p=p,
            tiny=tiny,
            inch=inch,
            info_bg=info_bg,
            pass_a=pass_a,
            pass_b=pass_b,
            warn_bg=warn_bg,
            alarm_bg=alarm_bg,
            normal=normal,
            colors=colors,
            pdf_transceiver_bar=pdf_transceiver_bar,
            poe_budget_card=poe_budget_card,
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


def export_pdf(findings: List[Finding], pre_file: str, post_file: str, port_map_file: str, out_path: str) -> None:
    try:
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate

        story = build_pdf_story(findings, pre_file, post_file, port_map_file)
    except Exception as e:
        raise RuntimeError("PDF export requires reportlab. Install with: pip install reportlab") from e

    doc = SimpleDocTemplate(out_path, pagesize=landscape(letter), rightMargin=0.35*inch, leftMargin=0.35*inch, topMargin=0.35*inch, bottomMargin=0.35*inch)
    doc.build(story)
