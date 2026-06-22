"""PDF section appenders for structured post-change report detail tables."""

from __future__ import annotations

from typing import Callable, Iterable


def append_port_map_pdf_sections(
    findings: Iterable[object],
    *,
    is_port_map_finding: Callable[[object], bool],
    parse_port_map_detail: Callable[[str], list],
    detail_table: Callable,
    paragraph: Callable,
    tiny_style,
    inch: float,
    info_bg,
    pass_a,
) -> None:
    for finding in findings:
        if not is_port_map_finding(finding):
            continue
        rows = []
        backgrounds = []
        for idx, parsed in enumerate(parse_port_map_detail(finding.detail)):
            rows.append(
                [
                    paragraph(parsed.get("section", ""), tiny_style),
                    paragraph(parsed.get("item", ""), tiny_style),
                    paragraph(parsed.get("value", ""), tiny_style),
                    paragraph(parsed.get("note", ""), tiny_style),
                ]
            )
            backgrounds.append(info_bg if idx % 2 == 0 else pass_a)
        detail_table(
            "Port Map Detail",
            finding.finding,
            ["Section", "Item", "Value / Target", "Note"],
            rows,
            [1.65 * inch, 1.55 * inch, 3.25 * inch, 3.0 * inch],
            backgrounds,
            tiny_style,
        )


def append_logs_pdf_sections(
    findings: Iterable[object],
    *,
    is_logs_finding: Callable[[object], bool],
    parse_log_detail_line: Callable[[str], dict],
    detail_table: Callable,
    paragraph: Callable,
    tiny_style,
    inch: float,
    info_bg,
    pass_a,
    pass_b,
) -> None:
    for finding in findings:
        if not is_logs_finding(finding):
            continue
        rows = []
        backgrounds = []
        for idx, line in enumerate([ln for ln in (finding.detail or "").splitlines() if ln.strip()]):
            parsed = parse_log_detail_line(line)
            rows.append([paragraph(parsed["prefix"], tiny_style), paragraph(parsed["message"], tiny_style)])
            backgrounds.append(info_bg if finding.finding.startswith("Log review recommended") else (pass_a if idx % 2 == 0 else pass_b))
        detail_table(
            "Logs Detail",
            finding.finding,
            ["Time/Prefix", "Message"],
            rows,
            [1.45 * inch, 8.1 * inch],
            backgrounds,
            tiny_style,
        )


def append_poe_pdf_sections(
    findings: Iterable[object],
    *,
    is_poe_finding: Callable[[object], bool],
    parse_poe_detail_line: Callable[[str], dict],
    poe_budget_card: Callable[[str], object] | None,
    detail_table: Callable,
    paragraph: Callable,
    tiny_style,
    inch: float,
    warn_bg,
    pass_a,
    pass_b,
) -> None:
    for finding in findings:
        if not is_poe_finding(finding):
            continue
        rows = []
        backgrounds = []
        for idx, line in enumerate(
            [
                ln
                for ln in (finding.detail or "").splitlines()
                if ln.strip()
                and not ln.startswith("...")
                and not ln.startswith("POE_BUDGET|")
                and not ln.startswith("POE_SPEED_UPGRADE|")
            ]
        ):
            parsed = parse_poe_detail_line(line)
            rows.append(
                [
                    paragraph(parsed["pre_port"], tiny_style),
                    paragraph(parsed["post_port"], tiny_style),
                    paragraph(parsed["status"], tiny_style),
                    paragraph(parsed["pre"], tiny_style),
                    paragraph(parsed["post"], tiny_style),
                ]
            )
            backgrounds.append(warn_bg if finding.severity == "WARN" else (pass_a if idx % 2 == 0 else pass_b))
        before_table = None
        if poe_budget_card:
            card = poe_budget_card(finding.detail)
            if card is not None:
                before_table = [card]
        if not rows and not before_table:
            continue
        detail_table(
            "PoE Detail",
            finding.finding,
            ["Pre Port", "Post Port", "Status", "Pre Evidence", "Post Evidence"],
            rows,
            [0.8 * inch, 0.8 * inch, 1.25 * inch, 3.45 * inch, 3.45 * inch],
            backgrounds,
            tiny_style,
            before_table=before_table,
        )


def append_neighbor_pdf_sections(
    findings: Iterable[object],
    *,
    is_neighbor_finding: Callable[[object], bool],
    parse_neighbor_detail_line: Callable[[str], dict],
    detail_table: Callable,
    paragraph: Callable,
    tiny_style,
    inch: float,
    warn_bg,
    info_bg,
    pass_a,
    pass_b,
) -> None:
    for finding in findings:
        if not is_neighbor_finding(finding):
            continue
        rows = []
        backgrounds = []
        for idx, line in enumerate([ln for ln in (finding.detail or "").splitlines() if ln.strip()]):
            parsed = parse_neighbor_detail_line(line)
            rows.append(
                [
                    paragraph(parsed["status"], tiny_style),
                    paragraph(parsed["neighbor"], tiny_style),
                    paragraph(parsed["local"], tiny_style),
                    paragraph(parsed["post_local"], tiny_style),
                    paragraph(parsed["remote"], tiny_style),
                    paragraph(parsed["evidence"], tiny_style),
                ]
            )
            if finding.severity == "WARN":
                background = warn_bg
            elif finding.severity == "INFO":
                background = info_bg
            else:
                background = pass_a if idx % 2 == 0 else pass_b
            backgrounds.append(background)
        detail_table(
            f"{finding.category} Detail",
            finding.finding,
            ["Status", "Neighbor", "Pre Local", "Post Local", "Remote", "Evidence"],
            rows,
            [1.05 * inch, 2.0 * inch, 0.85 * inch, 0.85 * inch, 1.2 * inch, 3.6 * inch],
            backgrounds,
            tiny_style,
        )


def append_interface_status_pdf_sections(
    findings: Iterable[object],
    *,
    is_interface_status_finding: Callable[[object], bool],
    parse_interface_detail_line: Callable[[str], dict],
    detail_table: Callable,
    paragraph: Callable,
    tiny_style,
    inch: float,
    warn_bg,
    info_bg,
    pass_a,
    pass_b,
) -> None:
    for finding in findings:
        if not is_interface_status_finding(finding):
            continue
        rows = []
        backgrounds = []
        for idx, line in enumerate([ln for ln in (finding.detail or "").splitlines() if ln.strip()]):
            parsed = parse_interface_detail_line(line)
            rows.append(
                [
                    paragraph(parsed["pre_port"], tiny_style),
                    paragraph(parsed["post_port"], tiny_style),
                    paragraph(parsed["role"], tiny_style),
                    paragraph(parsed["status"], tiny_style),
                    paragraph(parsed["pre"], tiny_style),
                    paragraph(parsed["post"], tiny_style),
                    paragraph(parsed["note"], tiny_style),
                ]
            )
            if finding.severity == "WARN":
                background = warn_bg
            elif finding.severity == "INFO":
                background = info_bg
            else:
                background = pass_a if idx % 2 == 0 else pass_b
            backgrounds.append(background)
        detail_table(
            "Interface Status Detail",
            finding.finding,
            ["Pre", "Post", "Role", "Status", "Pre Evidence", "Post Evidence", "Note"],
            rows,
            [0.7 * inch, 0.7 * inch, 0.8 * inch, 0.95 * inch, 2.6 * inch, 2.6 * inch, 1.1 * inch],
            backgrounds,
            tiny_style,
        )


def append_inventory_pdf_sections(
    findings: Iterable[object],
    *,
    is_inventory_finding: Callable[[object], bool],
    parse_inventory_detail: Callable[[str], list],
    detail_table: Callable,
    paragraph: Callable,
    tiny_style,
    inch: float,
    pass_a,
    pass_b,
) -> None:
    for finding in findings:
        if not is_inventory_finding(finding):
            continue
        rows = []
        backgrounds = []
        for idx, parsed in enumerate(parse_inventory_detail(finding.detail)):
            rows.append(
                [
                    paragraph(parsed.get("component", ""), tiny_style),
                    paragraph(parsed.get("description", ""), tiny_style),
                    paragraph(parsed.get("pid", ""), tiny_style),
                    paragraph(parsed.get("vid", ""), tiny_style),
                    paragraph(parsed.get("serial", ""), tiny_style),
                ]
            )
            backgrounds.append(pass_a if idx % 2 == 0 else pass_b)
        detail_table(
            "Inventory Detail",
            finding.finding,
            ["Component", "Description", "PID / Model", "VID", "Serial"],
            rows,
            [2.2 * inch, 2.4 * inch, 1.75 * inch, 0.55 * inch, 1.55 * inch],
            backgrounds,
            tiny_style,
        )


def append_transceiver_pdf_sections(
    findings: Iterable[object],
    *,
    is_transceiver_finding: Callable[[object], bool],
    parse_transceiver_visual_rows: Callable[[str], list],
    transceiver_level_class: Callable[[float, float, float, float, float], str],
    transceiver_bar: Callable[[float, object, float, float, float, float], object],
    detail_table: Callable,
    paragraph: Callable,
    tiny_style,
    inch: float,
    alarm_bg,
    warn_bg,
    pass_a,
) -> None:
    for finding in findings:
        if not is_transceiver_finding(finding):
            continue
        rows = []
        backgrounds = []
        for parsed in parse_transceiver_visual_rows(finding.detail):
            value = float(parsed["value"])
            low_alarm = float(parsed["low_alarm"])
            low_warn = float(parsed["low_warn"])
            high_warn = float(parsed["high_warn"])
            high_alarm = float(parsed["high_alarm"])
            unit = str(parsed.get("unit", ""))
            pre_value = parsed.get("pre_value")
            pre_float = float(pre_value) if pre_value is not None else None
            pre_text = f"{unit} {pre_float:.2f}" if pre_float is not None else "n/a"
            delta = f"{value - pre_float:+.2f}" if pre_float is not None else "n/a"
            level = transceiver_level_class(value, low_alarm, low_warn, high_warn, high_alarm)
            rows.append(
                [
                    paragraph(parsed.get("interface", ""), tiny_style),
                    paragraph(parsed.get("metric", ""), tiny_style),
                    paragraph(pre_text, tiny_style),
                    paragraph(f"{unit} {value:.2f}", tiny_style),
                    paragraph(delta, tiny_style),
                    paragraph(f"{unit} {low_alarm:.2f}", tiny_style),
                    paragraph(f"{unit} {low_warn:.2f}", tiny_style),
                    paragraph(f"{unit} {high_warn:.2f}", tiny_style),
                    paragraph(f"{unit} {high_alarm:.2f}", tiny_style),
                    transceiver_bar(value, pre_float, low_alarm, low_warn, high_warn, high_alarm),
                ]
            )
            backgrounds.append(alarm_bg if level == "alarm" else (warn_bg if level == "warn" else pass_a))
        detail_table(
            "Transceiver Detail (gray = pre-change, black = post-change)",
            finding.finding,
            ["Interface", "Metric", "Pre", "Post", "Delta", "Low Alarm", "Low Warn", "High Warn", "High Alarm", "Range"],
            rows,
            [
                0.65 * inch,
                0.85 * inch,
                0.9 * inch,
                0.9 * inch,
                0.55 * inch,
                0.78 * inch,
                0.78 * inch,
                0.78 * inch,
                0.78 * inch,
                2.0 * inch,
            ],
            backgrounds,
            tiny_style,
        )


def append_stp_root_pdf_sections(
    findings: Iterable[object],
    *,
    is_stp_root_finding: Callable[[object], bool],
    parse_stp_detail_line: Callable[[str], dict],
    detail_table: Callable,
    paragraph: Callable,
    normal_style,
    tiny_style,
    inch: float,
    warn_bg,
    info_bg,
    pass_a,
    pass_b,
) -> None:
    for finding in findings:
        if not is_stp_root_finding(finding):
            continue
        rows = []
        backgrounds = []
        for idx, line in enumerate([ln for ln in (finding.detail or "").splitlines() if ln.strip()]):
            parsed = parse_stp_detail_line(line)
            rows.append(
                [
                    paragraph(parsed["vlan"], tiny_style),
                    paragraph(parsed["status"], tiny_style),
                    paragraph(parsed["pre_port"], tiny_style),
                    paragraph(parsed["post_port"], tiny_style),
                    paragraph(parsed["cost"], tiny_style),
                    paragraph(parsed["context"], normal_style),
                ]
            )
            if finding.severity == "WARN":
                background = warn_bg
            elif finding.severity == "INFO":
                background = info_bg
            else:
                background = pass_a if idx % 2 == 0 else pass_b
            backgrounds.append(background)
        detail_table(
            "STP Root Detail",
            finding.finding,
            ["VLAN", "Status", "Pre Port", "Post Port", "Cost", "Context"],
            rows,
            [0.75 * inch, 1.35 * inch, 0.9 * inch, 0.9 * inch, 0.7 * inch, 5.25 * inch],
            backgrounds,
            tiny_style,
        )


def append_mac_correlation_pdf_sections(
    findings: Iterable[object],
    *,
    is_mac_correlation_finding: Callable[[object], bool],
    parse_mac_correlation_detail: Callable[[str], list],
    detail_table: Callable,
    paragraph: Callable,
    normal_style,
    tiny_style,
    inch: float,
    moved_bg,
    missing_bg,
    pass_a,
    pass_b,
    fallback_bg,
) -> None:
    for finding in findings:
        if not is_mac_correlation_finding(finding):
            continue
        rows = []
        backgrounds = []
        pass_index = 0
        for parsed in parse_mac_correlation_detail(finding.detail):
            status = parsed.get("status", "")
            rows.append(
                [
                    paragraph(status, tiny_style),
                    paragraph(parsed.get("mac", ""), tiny_style),
                    paragraph(parsed.get("vlan", ""), tiny_style),
                    paragraph(parsed.get("pre_port", ""), tiny_style),
                    paragraph(parsed.get("expected_post_port", ""), tiny_style),
                    paragraph(parsed.get("actual_post_port", ""), tiny_style),
                    paragraph(parsed.get("note", ""), normal_style),
                ]
            )
            if status == "PASS":
                background = pass_a if pass_index % 2 == 0 else pass_b
                pass_index += 1
            elif status == "MISSING":
                background = missing_bg
            elif status == "MOVED":
                background = moved_bg
            else:
                background = fallback_bg
            backgrounds.append(background)
        detail_table(
            "Access Port MAC Correlation",
            finding.finding,
            ["Status", "MAC", "VLAN", "Pre Port", "Expected Post", "Actual Post", "Note"],
            rows,
            [0.65 * inch, 1.1 * inch, 0.45 * inch, 0.85 * inch, 1.05 * inch, 1.05 * inch, 4.1 * inch],
            backgrounds,
            tiny_style,
        )
