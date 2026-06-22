"""HTML and PDF report-shell helpers for post-change validation reports."""

from __future__ import annotations

import datetime as dt
import html
import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Set, Tuple

from src.post_change_validation_interface_status_rendering import build_interface_status_html as build_interface_status_html_detail
from src.post_change_validation_inventory_rendering import build_inventory_html as build_inventory_html_detail
from src.post_change_validation_logs_rendering import build_logs_html as build_logs_html_detail
from src.post_change_validation_mac_rendering import build_mac_correlation_html as build_mac_correlation_html_detail
from src.post_change_validation_neighbor_rendering import build_neighbor_html as build_neighbor_html_detail
from src.post_change_validation_poe_rendering import build_poe_html as build_poe_html_detail
from src.post_change_validation_port_map_rendering import build_port_map_html as build_port_map_html_detail
from src.post_change_validation_stp_rendering import build_stp_root_html as build_stp_root_html_detail
from src.post_change_validation_transceiver_rendering import build_transceiver_html as build_transceiver_html_detail


APP_NAME = "Post-Change Validation Reviewer"
APP_VERSION = "1.0.0"

TOP_CARD_CATEGORIES = {
    "Access Port MAC Correlation",
    "MAC Table",
    "PoE",
    "CDP Neighbors",
    "LLDP Neighbors",
    "Interface Status",
    "Trunks",
    "STP Root",
}


def severity_counts(findings: Iterable[object]) -> Dict[str, int]:
    counts = {"FAIL": 0, "WARN": 0, "PASS": 0, "INFO": 0}
    for finding in findings:
        counts[getattr(finding, "severity", "INFO")] = counts.get(getattr(finding, "severity", "INFO"), 0) + 1
    return counts


def overall_status(findings: Iterable[object]) -> str:
    findings = list(findings)
    if any(f.severity == "FAIL" for f in findings):
        return "FAIL"
    if any(f.severity == "WARN" for f in findings):
        return "WARN"
    return "PASS"


def display_severity(finding: object) -> str:
    if finding.category == "Logs" and finding.finding.startswith("Log review recommended"):
        return "REVIEW"
    return finding.severity


def off_card_blocking_findings(findings: Iterable[object]) -> List[object]:
    return [
        finding
        for finding in findings
        if (
            (finding.severity in {"FAIL", "WARN"} and finding.category not in TOP_CARD_CATEGORIES)
            or (finding.category == "Logs" and finding.finding.startswith("Log review recommended"))
        )
    ]


def review_callout_class(findings: Iterable[object]) -> str:
    off_card = off_card_blocking_findings(findings)
    if off_card and all(finding.category == "Logs" for finding in off_card):
        return "review-required neutral"
    return "review-required"


def build_review_required_html(findings: Iterable[object]) -> str:
    findings = list(findings)
    off_card = off_card_blocking_findings(findings)
    if not off_card:
        return ""
    items = "".join(
        "<li><b>%s - %s:</b> %s</li>"
        % (
            html.escape(display_severity(finding)),
            html.escape(finding.category),
            html.escape(finding.finding),
        )
        for finding in off_card
    )
    return (
        "<div class='%s'>"
        "<div class='review-title'>Review required outside top cards</div>"
        "<ul>%s</ul>"
        "</div>"
    ) % (review_callout_class(findings), items)


def summary_status_for_categories(findings: Iterable[object], categories: Set[str], absent_text: str) -> Tuple[str, str]:
    matched = [finding for finding in findings if finding.category in categories]
    if not matched:
        return ("INFO", absent_text)
    if any(finding.severity == "FAIL" for finding in matched):
        severity = "FAIL"
    elif any(finding.severity == "WARN" for finding in matched):
        severity = "WARN"
    elif any(finding.severity == "PASS" for finding in matched):
        severity = "PASS"
    else:
        severity = "INFO"
    primary = next((finding for finding in matched if finding.severity == severity), matched[0])
    return (severity, primary.finding)


def protocol_neighbor_summary(proto: str, findings: Iterable[object]) -> str:
    category = f"{proto} Neighbors"
    proto_findings = [finding for finding in findings if finding.category == category]
    if not proto_findings:
        return f"{proto}: no {proto} neighbor evidence summarized."

    blocking = [finding for finding in proto_findings if finding.severity in {"FAIL", "WARN"}]
    if blocking:
        return f"{proto}: {' '.join(finding.finding for finding in blocking[:2])}"

    parts: List[str] = []
    matched_count = 0
    supported_count = 0
    for finding in proto_findings:
        matched_m = re.search(r"(\d+)\s+\w+\s+neighbor record\(s\) matched after change", finding.finding, re.I)
        if matched_m:
            matched_count += int(matched_m.group(1))
        supported_m = re.search(r"(\d+)\s+\w+\s+neighbor advertisement\(s\) missing, but endpoint evidence is present", finding.finding, re.I)
        if supported_m:
            supported_count += int(supported_m.group(1))

    if matched_count:
        parts.append(f"{matched_count} matched")
    if supported_count:
        parts.append(f"{supported_count} advertisement{'s' if supported_count != 1 else ''} cleared by MAC/PoE evidence")
    if parts:
        return f"{proto}: {'; '.join(parts)}."

    info = [finding.finding for finding in proto_findings if finding.severity == "INFO"]
    return f"{proto}: {' '.join(info[:2])}" if info else f"{proto}: no {proto} neighbor evidence summarized."


def neighbor_highlight(findings: Iterable[object]) -> Tuple[str, str, str, str]:
    findings = list(findings)
    neighbor_findings = [finding for finding in findings if finding.category in {"CDP Neighbors", "LLDP Neighbors"}]
    if not neighbor_findings:
        return ("Neighbors", "INFO", "INFO", "No CDP/LLDP neighbor evidence was available to summarize.")

    supported_missing = [
        finding
        for finding in neighbor_findings
        if "advertisement(s) missing, but endpoint evidence is present" in finding.finding
    ]
    if any(finding.severity == "FAIL" for finding in neighbor_findings):
        severity = "FAIL"
    elif any(finding.severity == "WARN" for finding in neighbor_findings):
        severity = "WARN"
    elif any(finding.severity == "PASS" for finding in neighbor_findings):
        severity = "PASS"
    else:
        severity = "INFO"

    text = f"{protocol_neighbor_summary('CDP', findings)} {protocol_neighbor_summary('LLDP', findings)}"
    if supported_missing and not any(finding.severity in {"FAIL", "WARN"} for finding in neighbor_findings):
        return ("Neighbors", "PASS", "PASS + EVIDENCE", text)
    return ("Neighbors", severity, severity, text)


def highlight_for_categories(label: str, findings: Iterable[object], categories: Set[str], absent_text: str) -> Tuple[str, str, str, str]:
    severity, text = summary_status_for_categories(findings, categories, absent_text)
    return (label, severity, severity, text)


def stp_highlight(findings: Iterable[object]) -> Tuple[str, str, str, str]:
    stp_findings = [finding for finding in findings if finding.category == "STP Root"]
    if not stp_findings:
        return ("STP Root", "INFO", "INFO", "No STP root evidence was available to summarize.")
    if any(finding.severity == "FAIL" for finding in stp_findings):
        severity = "FAIL"
    elif any(finding.severity == "WARN" for finding in stp_findings):
        severity = "WARN"
    elif any(finding.severity == "PASS" for finding in stp_findings):
        severity = "PASS"
    else:
        severity = "INFO"
    for finding in stp_findings:
        if "VLAN0001: local switch became root post-change" in finding.detail and "VLAN 1 SVI is shutdown" in finding.detail:
            return ("STP Root", severity, severity, "VLAN 1 local-root state is informational: SVI is shutdown; verify against local VLAN design.")
    primary = next((finding for finding in stp_findings if finding.severity == severity), stp_findings[0])
    return ("STP Root", severity, severity, primary.finding)


def report_highlights(findings: Iterable[object]) -> List[Tuple[str, str, str, str]]:
    findings = list(findings)
    return [
        highlight_for_categories("MAC Addresses", findings, {"Access Port MAC Correlation", "MAC Table"}, "No MAC-table evidence was available to summarize."),
        highlight_for_categories("PoE Delivery", findings, {"PoE"}, "No PoE evidence was available to summarize."),
        neighbor_highlight(findings),
        highlight_for_categories("Interface Status", findings, {"Interface Status"}, "No interface-status comparison was available to summarize."),
        highlight_for_categories("Trunks", findings, {"Trunks"}, "No trunk comparison was available to summarize."),
        stp_highlight(findings),
    ]


def status_icon_html(severity: str) -> str:
    return {
        "PASS": "&#10003;",
        "WARN": "!",
        "FAIL": "X",
        "INFO": "i",
    }.get(severity, "i")


def build_highlights_html(findings: Iterable[object]) -> str:
    cards = []
    for label, severity, status_label, text in report_highlights(findings):
        cards.append(
            "<div class='highlight-card %s'>"
            "<div class='highlight-status'><span class='status-icon'>%s</span><span>%s</span></div>"
            "<div class='highlight-title'>%s</div>"
            "<div class='highlight-text'>%s</div>"
            "</div>"
            % (
                severity.lower(),
                status_icon_html(severity),
                html.escape(status_label),
                html.escape(label),
                html.escape(text),
            )
        )
    return "<div class='highlights'>%s</div>" % "".join(cards)


def _is_report_sample_absolute_path(normalized: str) -> bool:
    """Preserve full paths under D:\\report for public sample audit trails."""
    lower = normalized.lower()
    return lower == "d:/report" or lower.startswith("d:/report/")


def display_input_path(path: str) -> str:
    """Return a report-safe path label: keep relative paths, basename only for absolute paths."""
    if not path:
        return "None"
    normalized = path.replace("\\", "/")
    if _is_report_sample_absolute_path(normalized):
        return str(Path(path))
    candidate = Path(normalized)
    if candidate.is_absolute() or (len(normalized) > 1 and normalized[1] == ":"):
        return candidate.name
    return normalized


def report_inputs_rows(pre_file: str, post_file: str, port_map_file: str) -> str:
    rows = report_input_values(pre_file, post_file, port_map_file)
    return "".join(f"<tr><td>{html.escape(label)}</td><td>{html.escape(value)}</td></tr>" for label, value in rows)


def report_input_values(pre_file: str, post_file: str, port_map_file: str) -> List[Tuple[str, str]]:
    return [
        ("App", f"{APP_NAME} {APP_VERSION}"),
        ("Generated", dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("Pre-change file", display_input_path(pre_file)),
        ("Post-change file", display_input_path(post_file)),
        ("Port map file", display_input_path(port_map_file) if port_map_file else "None"),
    ]


def is_mac_correlation_finding(finding: object) -> bool:
    return finding.category == "Access Port MAC Correlation" and finding.detail.startswith("status|mac|")


def build_mac_correlation_html(finding: object) -> str:
    return build_mac_correlation_html_detail(finding.finding, finding.detail)


def is_port_map_finding(finding: object) -> bool:
    return finding.category == "Port Map" and bool((finding.detail or "").strip())


def build_port_map_html(finding: object) -> str:
    return build_port_map_html_detail(finding.detail)


def is_stp_root_finding(finding: object) -> bool:
    return finding.category == "STP Root" and bool((finding.detail or "").strip())


def build_stp_root_html(finding: object) -> str:
    return build_stp_root_html_detail(finding.severity, finding.detail)


def is_poe_finding(finding: object) -> bool:
    return finding.category == "PoE" and bool((finding.detail or "").strip())


def build_poe_html(finding: object) -> str:
    return build_poe_html_detail(finding.severity, finding.detail)


def is_inventory_finding(finding: object) -> bool:
    return finding.category == "Inventory" and finding.detail.startswith("component|description|pid|")


def build_inventory_html(finding: object) -> str:
    return build_inventory_html_detail(finding.detail)


def is_neighbor_finding(finding: object) -> bool:
    return finding.category in {"CDP Neighbors", "LLDP Neighbors"} and bool((finding.detail or "").strip())


def build_neighbor_html(finding: object) -> str:
    return build_neighbor_html_detail(finding.severity, finding.detail)


def is_interface_status_finding(finding: object) -> bool:
    return finding.category == "Interface Status" and bool((finding.detail or "").strip()) and not finding.detail.startswith("Suppressed ")


def build_interface_status_html(finding: object) -> str:
    return build_interface_status_html_detail(finding.severity, finding.detail)


def is_logs_finding(finding: object) -> bool:
    return finding.category == "Logs" and bool((finding.detail or "").strip())


def build_logs_html(finding: object) -> str:
    return build_logs_html_detail(finding.finding, finding.detail)


def is_transceiver_finding(finding: object) -> bool:
    return finding.category == "Transceiver" and bool((finding.detail or "").strip())


def build_transceiver_html(finding: object) -> str:
    return build_transceiver_html_detail(finding.detail)


def is_structured_detail_finding(finding: object) -> bool:
    return (
        is_stp_root_finding(finding)
        or is_poe_finding(finding)
        or is_neighbor_finding(finding)
        or is_interface_status_finding(finding)
        or is_logs_finding(finding)
        or is_transceiver_finding(finding)
        or is_inventory_finding(finding)
        or is_mac_correlation_finding(finding)
        or is_port_map_finding(finding)
    )


def build_html_report(findings: List[object], pre_file: str, post_file: str, port_map_file: str) -> str:
    counts = severity_counts(findings)
    rows = []
    mac_sections = []
    highlights_html = build_highlights_html(findings)
    review_required_html = build_review_required_html(findings)
    for finding in findings:
        severity = html.escape(display_severity(finding))
        row_prefix = f"<tr class='{display_severity(finding).lower()}'><td>{severity}</td><td>{html.escape(finding.category)}</td><td>{html.escape(finding.finding)}</td><td>"
        if is_mac_correlation_finding(finding):
            mac_sections.append(build_mac_correlation_html(finding))
            rows.append(f"{row_prefix}<pre>Full side-by-side MAC table appears below.</pre></td></tr>")
        elif is_port_map_finding(finding):
            rows.append(f"{row_prefix}{build_port_map_html(finding)}</td></tr>")
        elif is_stp_root_finding(finding):
            rows.append(f"{row_prefix}{build_stp_root_html(finding)}</td></tr>")
        elif is_poe_finding(finding):
            rows.append(f"{row_prefix}{build_poe_html(finding)}</td></tr>")
        elif is_neighbor_finding(finding):
            rows.append(f"{row_prefix}{build_neighbor_html(finding)}</td></tr>")
        elif is_interface_status_finding(finding):
            rows.append(f"{row_prefix}{build_interface_status_html(finding)}</td></tr>")
        elif is_logs_finding(finding):
            rows.append(f"{row_prefix}{build_logs_html(finding)}</td></tr>")
        elif is_transceiver_finding(finding):
            rows.append(f"{row_prefix}{build_transceiver_html(finding)}</td></tr>")
        elif is_inventory_finding(finding):
            rows.append(f"{row_prefix}{build_inventory_html(finding)}</td></tr>")
        else:
            rows.append(f"{row_prefix}<pre>{html.escape(finding.detail)}</pre></td></tr>")
    mac_html = "".join(mac_sections)
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Post-Change Validation Report</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 28px; }}
h1 {{ margin-bottom: 0; }}
.summary {{ font-size: 18px; margin: 12px 0 14px; }}
.counts {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 18px; }}
.count-pill {{ border: 1px solid #bbb; border-radius: 999px; padding: 5px 10px; font-weight: 600; }}
.review-required {{ border: 1px solid #d6a84f; border-left: 7px solid #b7791f; border-radius: 8px; background: #fff8e6; padding: 10px 12px; margin: 0 0 16px; }}
.review-required.neutral {{ border-color: #c9d2d6; border-left-color: #607d8b; background: #f5f7f8; }}
.review-title {{ font-weight: 700; margin-bottom: 4px; }}
.review-required ul {{ margin: 4px 0 0 20px; padding: 0; }}
.review-required li {{ margin: 3px 0; }}
.highlights {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; margin: 12px 0 22px; }}
.highlight-card {{ border: 1px solid #c9d2c9; border-left-width: 7px; border-radius: 8px; padding: 12px; background: #fff; }}
.highlight-card.pass {{ border-left-color: #238636; background: #eef8ef; }}
.highlight-card.warn {{ border-left-color: #b7791f; background: #fff8e6; }}
.highlight-card.fail {{ border-left-color: #b42318; background: #fff1f0; }}
.highlight-card.info {{ border-left-color: #607d8b; background: #f5f7f8; }}
.highlight-status {{ display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 700; color: #333; }}
.status-icon {{ display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 50%; color: white; background: #607d8b; }}
.pass .status-icon {{ background: #238636; }}
.warn .status-icon {{ background: #b7791f; }}
.fail .status-icon {{ background: #b42318; }}
.highlight-title {{ margin-top: 9px; font-size: 17px; font-weight: 700; }}
.highlight-text {{ margin-top: 5px; font-size: 13px; line-height: 1.35; color: #333; }}
@media (max-width: 1500px) {{ .highlights {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
@media (max-width: 800px) {{ .highlights {{ grid-template-columns: 1fr; }} }}
@media print {{ .highlights {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
table {{ border-collapse: collapse; width: 100%; margin: 14px 0; }}
th, td {{ border: 1px solid #bbb; padding: 7px; vertical-align: top; }}
th {{ background: #ddd; text-align: left; }}
pre {{ white-space: pre-wrap; margin: 0; font-family: Consolas, monospace; font-size: 12px; }}
.fail td:first-child {{ font-weight: bold; color: #9b0000; }}
.warn td:first-child {{ font-weight: bold; color: #9a6200; }}
.review td:first-child {{ font-weight: bold; color: #4f5b57; }}
.pass td:first-child {{ font-weight: bold; color: #176b1d; }}
.info td:first-child {{ color: #444; }}
.mac-section {{ page-break-before: always; margin-top: 24px; }}
.mac-table th {{ background: #cfd8dc; }}
.mac-pass-a td {{ background: #dff3df; }}
.mac-pass-b td {{ background: #c8eec8; }}
.mac-missing td {{ background: #ffd39b; }}
.mac-moved td {{ background: #fff2a8; }}
.detail-table {{ margin: 0; font-size: 12px; }}
.detail-table th, .detail-table td {{ border: 1px solid #c7d2c7; padding: 5px 6px; }}
.detail-table th {{ background: #d8e1de; }}
.detail-table td:first-child {{ font-weight: 400; color: #111; }}
.stp-pass-a td {{ background: #eef8ef; }}
.stp-pass-b td {{ background: #dff3df; }}
.stp-info td {{ background: #f5f7f8; }}
.stp-warn td {{ background: #fff2a8; }}
.poe-pass-a td {{ background: #eef8ef; }}
.poe-pass-b td {{ background: #dff3df; }}
.poe-info td {{ background: #f5f7f8; }}
.poe-warn td {{ background: #fff2a8; }}
.poe-budget-card {{ border: 1px solid #c7d2c7; background: #eef8ef; border-radius: 6px; padding: 8px 10px; margin: 0 0 10px; }}
.poe-budget-title {{ font-weight: 700; margin-bottom: 3px; }}
.poe-budget-title span {{ font-size: 11px; font-weight: 400; color: #4f5b57; }}
.poe-budget-summary {{ font-size: 12px; margin-bottom: 6px; }}
.poe-budget-note {{ font-size: 12px; color: #34454d; margin-top: 6px; }}
.poe-budget-bar {{ position: relative; display: flex; height: 18px; min-width: 260px; border: 1px solid #999; border-radius: 4px; overflow: hidden; background: #bfe8c4; }}
.poe-budget-zone {{ height: 100%; }}
.poe-budget-green {{ width: 70%; background: #bfe8c4; }}
.poe-budget-yellow {{ width: 20%; background: #ffe19a; }}
.poe-budget-red {{ width: 10%; background: #f4b4ad; }}
.poe-budget-marker {{ position: absolute; top: -2px; width: 3px; height: 22px; box-shadow: 0 0 0 1px white; }}
.poe-budget-pre {{ background: #7a7a7a; }}
.poe-budget-post {{ background: #111; }}
.inventory-pass-a td {{ background: #eef8ef; }}
.inventory-pass-b td {{ background: #dff3df; }}
.port-map-a td {{ background: #f5f7f8; }}
.port-map-b td {{ background: #eef8ef; }}
.neighbor-pass-a td, .iface-pass-a td, .log-pass-a td {{ background: #eef8ef; }}
.neighbor-pass-b td, .iface-pass-b td, .log-pass-b td {{ background: #dff3df; }}
.neighbor-info td, .iface-info td {{ background: #f5f7f8; }}
.neighbor-warn td, .iface-warn td {{ background: #fff2a8; }}
.log-warn td {{ background: #f5f7f8; }}
.log-warn td:first-child {{ color: #4f5b57; font-weight: 600; }}
.xcvr-ok td {{ background: #eef8ef; }}
.xcvr-warn td {{ background: #fff2a8; }}
.xcvr-alarm td {{ background: #ffd6d2; }}
.xcvr-bar {{ position: relative; display: flex; height: 18px; min-width: 220px; border: 1px solid #999; border-radius: 4px; overflow: hidden; }}
.xcvr-zone {{ height: 100%; }}
.xcvr-alarm-low, .xcvr-alarm-high {{ background: #f4b4ad; }}
.xcvr-warn-low, .xcvr-warn-high {{ background: #ffe19a; }}
.xcvr-ok-zone {{ background: #bfe8c4; }}
.xcvr-marker {{ position: absolute; top: -2px; width: 3px; height: 22px; box-shadow: 0 0 0 1px white; }}
.xcvr-pre-marker {{ background: #7a7a7a; }}
.xcvr-post-marker {{ background: #111; }}
.xcvr-legend {{ display: block; font-size: 11px; font-weight: 400; color: #4f5b57; margin-top: 2px; }}
</style></head><body>
<h1>Post-Change Validation Report</h1>
<div class='summary'><b>Overall Status:</b> {overall_status(findings)}</div>
<div class='counts'><span class='count-pill'>FAIL: {counts['FAIL']}</span><span class='count-pill'>WARN: {counts['WARN']}</span><span class='count-pill'>PASS: {counts['PASS']}</span><span class='count-pill'>INFO: {counts['INFO']}</span></div>
{review_required_html}
{highlights_html}
<table><tr><th>Severity</th><th>Category</th><th>Finding</th><th>Detail</th></tr>
{''.join(rows)}
</table>
{mac_html}
<h2>Report Inputs</h2>
<table><tr><th>Field</th><th>Value</th></tr>
{report_inputs_rows(pre_file, post_file, port_map_file)}
</table>
</body></html>"""


def append_pdf_header(story: list, findings: List[object], *, paragraph_cls, spacer_cls, styles, normal_style) -> None:
    counts = severity_counts(findings)
    story.append(paragraph_cls("Post-Change Validation Report", styles["Title"]))
    story.append(spacer_cls(1, 8))
    story.append(paragraph_cls(f"<b>Overall Status: {overall_status(findings)}</b>", styles["Heading2"]))
    story.append(paragraph_cls(f"FAIL: {counts['FAIL']} &nbsp;&nbsp; WARN: {counts['WARN']} &nbsp;&nbsp; PASS: {counts['PASS']} &nbsp;&nbsp; INFO: {counts['INFO']}", normal_style))
    story.append(spacer_cls(1, 8))


def append_pdf_review_required(story: list, findings: List[object], *, paragraph_cls, spacer_cls, table_cls, table_style_cls, styles, normal_style, colors, inch: float, info_bg) -> None:
    off_card = off_card_blocking_findings(findings)
    if not off_card:
        return
    logs_only = all(finding.category == "Logs" for finding in off_card)
    review_bg = info_bg if logs_only else colors.HexColor("#fff8e6")
    review_head_bg = colors.HexColor("#d8e1de") if logs_only else colors.HexColor("#fff2a8")
    review_rows = [["Severity", "Category", "Finding"]]
    for finding in off_card:
        review_rows.append([display_severity(finding), finding.category, paragraph_cls(html.escape(finding.finding), normal_style)])
    review_tbl = table_cls(review_rows, colWidths=[0.75 * inch, 1.35 * inch, 7.35 * inch], repeatRows=1)
    review_tbl.setStyle(table_style_cls([
        ("BACKGROUND", (0, 0), (-1, 0), review_head_bg),
        ("BACKGROUND", (0, 1), (-1, -1), review_bg),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(paragraph_cls("Review Required Outside Top Cards", styles["Heading3"]))
    story.extend([review_tbl, spacer_cls(1, 10)])


def append_pdf_highlights(story: list, findings: List[object], *, paragraph_cls, spacer_cls, table_cls, table_style_cls, normal_style, colors, inch: float) -> None:
    highlight_rows = [["Area", "Status", "Summary"]]
    highlight_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]
    status_colors = {
        "PASS": colors.HexColor("#dff3df"),
        "WARN": colors.HexColor("#fff2a8"),
        "FAIL": colors.HexColor("#ffd6d2"),
        "INFO": colors.HexColor("#f5f7f8"),
    }
    for idx, (label, severity, status_label, text) in enumerate(report_highlights(findings), start=1):
        highlight_rows.append([
            paragraph_cls(html.escape(label), normal_style),
            paragraph_cls(html.escape(status_label), normal_style),
            paragraph_cls(html.escape(text), normal_style),
        ])
        highlight_styles.append(("BACKGROUND", (0, idx), (-1, idx), status_colors.get(severity, colors.whitesmoke)))
        highlight_styles.append(("TEXTCOLOR", (1, idx), (1, idx), colors.HexColor("#176b1d") if severity == "PASS" else colors.black))
    highlights_tbl = table_cls(highlight_rows, colWidths=[1.55 * inch, 1.05 * inch, 7.25 * inch], repeatRows=1)
    highlights_tbl.setStyle(table_style_cls(highlight_styles))
    story.extend([highlights_tbl, spacer_cls(1, 12)])


def append_pdf_findings_table(story: list, findings: List[object], *, paragraph_cls, table_cls, table_style_cls, normal_style, small_style, colors, inch: float) -> None:
    data = [["Severity", "Category", "Finding", "Detail"]]
    for finding in findings:
        detail = "Structured detail table appears below." if is_structured_detail_finding(finding) else finding.detail
        if len(detail) > 2500:
            detail = detail[:2500] + "\n... truncated ..."
        data.append([
            display_severity(finding),
            finding.category,
            paragraph_cls(html.escape(finding.finding), normal_style),
            paragraph_cls(html.escape(detail).replace("\n", "<br/>"), small_style),
        ])
    table = table_cls(data, colWidths=[0.65 * inch, 1.25 * inch, 2.6 * inch, 5.35 * inch], repeatRows=1)
    table.setStyle(table_style_cls([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(table)


def append_pdf_report_inputs(story: list, pre_file: str, post_file: str, port_map_file: str, *, paragraph_cls, spacer_cls, table_cls, table_style_cls, styles, normal_style, colors, inch: float) -> None:
    story.append(spacer_cls(1, 16))
    story.append(paragraph_cls("Report Inputs", styles["Heading2"]))
    meta = [["Field", "Value"]] + report_input_values(pre_file, post_file, port_map_file)
    meta_table = table_cls([[paragraph_cls(html.escape(str(cell)), normal_style) for cell in row] for row in meta], colWidths=[1.55 * inch, 8.3 * inch])
    meta_table.setStyle(table_style_cls([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(meta_table)


def append_pdf_report_shell(
    story: list,
    findings: List[object],
    pre_file: str,
    post_file: str,
    port_map_file: str,
    *,
    paragraph_cls,
    spacer_cls,
    table_cls,
    table_style_cls,
    styles,
    normal_style,
    small_style,
    colors,
    inch: float,
    info_bg,
    before_inputs: Callable[[], None],
) -> None:
    append_pdf_header(story, findings, paragraph_cls=paragraph_cls, spacer_cls=spacer_cls, styles=styles, normal_style=normal_style)
    append_pdf_review_required(story, findings, paragraph_cls=paragraph_cls, spacer_cls=spacer_cls, table_cls=table_cls, table_style_cls=table_style_cls, styles=styles, normal_style=normal_style, colors=colors, inch=inch, info_bg=info_bg)
    append_pdf_highlights(story, findings, paragraph_cls=paragraph_cls, spacer_cls=spacer_cls, table_cls=table_cls, table_style_cls=table_style_cls, normal_style=normal_style, colors=colors, inch=inch)
    append_pdf_findings_table(story, findings, paragraph_cls=paragraph_cls, table_cls=table_cls, table_style_cls=table_style_cls, normal_style=normal_style, small_style=small_style, colors=colors, inch=inch)
    before_inputs()
    append_pdf_report_inputs(story, pre_file, post_file, port_map_file, paragraph_cls=paragraph_cls, spacer_cls=spacer_cls, table_cls=table_cls, table_style_cls=table_style_cls, styles=styles, normal_style=normal_style, colors=colors, inch=inch)
