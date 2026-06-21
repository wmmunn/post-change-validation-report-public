"""Plain-text GUI detail formatting using existing structured detail parsers."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from post_change_validation_report_shell import (
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
from src.post_change_validation_interface_status_rendering import parse_interface_detail_line
from src.post_change_validation_inventory_rendering import parse_inventory_detail
from src.post_change_validation_logs_rendering import parse_log_detail_line
from src.post_change_validation_mac_rendering import parse_mac_correlation_detail
from src.post_change_validation_neighbor_rendering import parse_neighbor_detail_line
from src.post_change_validation_poe_rendering import (
    parse_poe_budget_detail,
    parse_poe_detail_line,
    parse_poe_speed_upgrade_detail,
)
from src.post_change_validation_port_map_rendering import parse_port_map_detail
from src.post_change_validation_stp_rendering import parse_stp_detail_line
from src.post_change_validation_transceivers import parse_transceiver_visual_rows

_DETAIL_PREVIEW_MAX = 300
_MAC_ISSUE_STATUSES = frozenset({"MISSING", "MOVED"})


def _truncate(text: str, max_len: int = _DETAIL_PREVIEW_MAX) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."


def _detail_lines(detail: str) -> List[str]:
    return [ln for ln in (detail or "").splitlines() if ln.strip()]


def _labeled_block(fields: Sequence[Tuple[str, str]]) -> str:
    return "\n".join(f"{label}: {value}" for label, value in fields if value)


def _mac_status_counts(rows: List[Dict[str, str]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        status = row.get("status", "") or "UNKNOWN"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _mac_issue_summary(row: Dict[str, str]) -> str:
    status = row.get("status", "")
    mac = row.get("mac", "")
    port = row.get("pre_port") or row.get("actual_post_port", "")
    expected = row.get("expected_post_port", "")
    actual = row.get("actual_post_port", "")
    note = row.get("note", "")
    parts = [status, mac]
    if port:
        parts.append(f"on {port}")
    if expected and actual and expected != actual:
        parts.append(f"(expected {expected}, actual {actual})")
    elif expected and actual == "Not found":
        parts.append(f"(expected {expected})")
    if note:
        parts.append(f"- {note}")
    return " ".join(part for part in parts if part)


def _mac_summary(rows: List[Dict[str, str]], finding: object) -> str:
    if not rows:
        return _truncate(finding.detail)
    counts = _mac_status_counts(rows)
    if finding.severity in ("WARN", "FAIL"):
        for row in rows:
            if row.get("status") in _MAC_ISSUE_STATUSES:
                return _truncate(_mac_issue_summary(row))
    count_parts = ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))
    return _truncate(f"{len(rows)} rows: {count_parts}")


def _mac_detail(rows: List[Dict[str, str]]) -> str:
    blocks = []
    for row in rows:
        block = _labeled_block(
            [
                ("Status", row.get("status", "")),
                ("MAC Address", row.get("mac", "")),
                ("VLAN", row.get("vlan", "")),
                ("Pre Port", row.get("pre_port", "")),
                ("Expected Post Port", row.get("expected_post_port", "")),
                ("Actual Post Port", row.get("actual_post_port", "")),
                ("Note", row.get("note", "")),
            ]
        )
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _interface_port_label(row: Dict[str, str]) -> str:
    pre_port = row.get("pre_port", "")
    post_port = row.get("post_port", "")
    if pre_port and post_port and pre_port != post_port:
        return f"{pre_port}->{post_port}"
    return post_port or pre_port or "port"


def _interface_line_summary(row: Dict[str, str]) -> str:
    port = _interface_port_label(row)
    status = row.get("status", "")
    if status:
        return f"{port}: {status}"
    return port


def _interface_summary(lines: List[str], finding: object) -> str:
    if not lines:
        return _truncate(finding.detail)
    parsed = [parse_interface_detail_line(line) for line in lines]
    if finding.severity in ("WARN", "FAIL"):
        return _truncate(_interface_line_summary(parsed[0]))
    if finding.severity == "PASS" and len(parsed) > 1:
        return _truncate(f"{len(parsed)} ports remained connected")
    if len(parsed) == 1:
        return _truncate(_interface_line_summary(parsed[0]))
    return _truncate(f"{len(parsed)} ports: {_interface_line_summary(parsed[0])}")


def _interface_detail(lines: List[str]) -> str:
    blocks = []
    for line in lines:
        row = parse_interface_detail_line(line)
        block = _labeled_block(
            [
                ("Pre Port", row.get("pre_port", "")),
                ("Post Port", row.get("post_port", "")),
                ("Role", row.get("role", "")),
                ("Status", row.get("status", "")),
                ("Pre Evidence", row.get("pre", "")),
                ("Post Evidence", row.get("post", "")),
                ("Note", row.get("note", "")),
            ]
        )
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _neighbor_line_summary(row: Dict[str, str]) -> str:
    neighbor = row.get("neighbor", "")
    local = row.get("local", "")
    post_local = row.get("post_local", "")
    remote = row.get("remote", "")
    status = row.get("status", "")
    if status in {"Matched", "Matched mapped"}:
        if local and post_local and local != post_local:
            return f"{neighbor} {local}->{post_local}, remote {remote}".strip(", ")
        port = local or post_local
        return f"{neighbor} {port}, remote {remote}".strip()
    if status == "Missing advertisement":
        return f"missing {neighbor} on {local} (expected {post_local})"
    if status == "New":
        return f"new {neighbor} on {post_local}, remote {remote}"
    if status:
        return f"{status}: {neighbor or row.get('evidence', '')}".strip(": ")
    return neighbor or row.get("evidence", "")


def _neighbor_summary(lines: List[str], finding: object) -> str:
    if not lines:
        return _truncate(finding.detail)
    parsed = [parse_neighbor_detail_line(line) for line in lines]
    first = _neighbor_line_summary(parsed[0])
    matched = sum(1 for row in parsed if row.get("status") in {"Matched", "Matched mapped"})
    if matched and len(parsed) > 1:
        return _truncate(f"{matched} matched: {first}")
    if len(parsed) == 1:
        return _truncate(first)
    return _truncate(f"{len(parsed)} records: {first}")


def _neighbor_detail(lines: List[str]) -> str:
    blocks = []
    for line in lines:
        row = parse_neighbor_detail_line(line)
        block = _labeled_block(
            [
                ("Status", row.get("status", "")),
                ("Neighbor", row.get("neighbor", "")),
                ("Pre Local", row.get("local", "")),
                ("Post Local", row.get("post_local", "")),
                ("Remote", row.get("remote", "")),
                ("Evidence", row.get("evidence", "")),
            ]
        )
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _poe_port_lines(detail: str) -> List[str]:
    return [
        line
        for line in _detail_lines(detail)
        if not line.startswith("...")
        and not line.startswith("POE_BUDGET|")
        and not line.startswith("POE_SPEED_UPGRADE|")
    ]


def _poe_budget_summary(detail: str) -> str:
    budgets = parse_poe_budget_detail(detail)
    post = budgets.get("post") or budgets.get("pre")
    if not post:
        return ""
    available = float(post["available"])
    used = float(post["used"])
    remaining = float(post.get("remaining", max(0.0, available - used)))
    pct = 0.0 if available <= 0 else min(100.0, max(0.0, (used / available) * 100.0))
    return f"budget {used:.1f}/{available:.1f} W ({pct:.0f}%), remaining {remaining:.1f} W"


def _poe_summary(detail: str, finding: object) -> str:
    lines = _poe_port_lines(detail)
    budget = _poe_budget_summary(detail)
    if lines:
        row = parse_poe_detail_line(lines[0])
        line_summary = _interface_line_summary(
            {
                "pre_port": row.get("pre_port", ""),
                "post_port": row.get("post_port", ""),
                "status": row.get("status", ""),
            }
        )
        if len(lines) > 1:
            prefix = f"{len(lines)} ports"
            if budget:
                return _truncate(f"{prefix}; {budget}; {line_summary}")
            return _truncate(f"{prefix}: {line_summary}")
        if budget:
            return _truncate(f"{budget}; {line_summary}")
        return _truncate(line_summary)
    if budget:
        return _truncate(budget)
    return _truncate(finding.detail)


def _poe_detail(detail: str) -> str:
    sections: List[str] = []
    budget = _poe_budget_summary(detail)
    if budget:
        sections.append(f"Budget: {budget}")
    speed = parse_poe_speed_upgrade_detail(detail)
    if speed:
        sections.append(f"Speed upgrade endpoints: {speed.get('count', '')}")
        evidence = str(speed.get("evidence", "")).strip()
        if evidence:
            sections.append(f"Evidence: {evidence}")
    blocks = []
    for line in _poe_port_lines(detail):
        row = parse_poe_detail_line(line)
        block = _labeled_block(
            [
                ("Pre Port", row.get("pre_port", "")),
                ("Post Port", row.get("post_port", "")),
                ("Status", row.get("status", "")),
                ("Pre Evidence", row.get("pre", "")),
                ("Post Evidence", row.get("post", "")),
            ]
        )
        if block:
            blocks.append(block)
    if blocks:
        sections.append("\n\n".join(blocks))
    return "\n\n".join(section for section in sections if section)


def _stp_summary(lines: List[str], finding: object) -> str:
    if not lines:
        return _truncate(finding.detail)
    row = parse_stp_detail_line(lines[0])
    vlan = row.get("vlan", "")
    status = row.get("status", "")
    ports = _interface_port_label(
        {"pre_port": row.get("pre_port", ""), "post_port": row.get("post_port", "")}
    )
    summary = f"{vlan}: {status}" if vlan else status
    if ports and ports != "port":
        summary = f"{summary}; {ports}"
    if len(lines) > 1:
        return _truncate(f"{len(lines)} VLANs; {summary}")
    return _truncate(summary)


def _stp_detail(lines: List[str]) -> str:
    blocks = []
    for line in lines:
        row = parse_stp_detail_line(line)
        block = _labeled_block(
            [
                ("VLAN", row.get("vlan", "")),
                ("Status", row.get("status", "")),
                ("Pre Root Port", row.get("pre_port", "")),
                ("Post Root Port", row.get("post_port", "")),
                ("Cost", row.get("cost", "")),
                ("Context", row.get("context", "")),
            ]
        )
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _port_map_summary(rows: List[Dict[str, str]], finding: object) -> str:
    if not rows:
        return _truncate(finding.detail)
    mappings = [row for row in rows if row.get("item") not in {"Source", "Note"} and row.get("value")]
    if not mappings:
        return _truncate(rows[0].get("value", finding.detail))
    first = mappings[0]
    first_text = f"{first.get('item', '')}->{first.get('value', '')}"
    note = first.get("note", "")
    if note:
        first_text = f"{first_text} ({note})"
    if len(mappings) > 1:
        return _truncate(f"{len(mappings)} mappings; {first_text}")
    return _truncate(first_text)


def _port_map_detail(rows: List[Dict[str, str]]) -> str:
    blocks = []
    for row in rows:
        block = _labeled_block(
            [
                ("Section", row.get("section", "")),
                ("Item", row.get("item", "")),
                ("Value", row.get("value", "")),
                ("Note", row.get("note", "")),
            ]
        )
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _inventory_summary(rows: List[Dict[str, str]], finding: object) -> str:
    if not rows:
        return _truncate(finding.detail)
    first = rows[0]
    component = first.get("component", "")
    pid = first.get("pid", "")
    if len(rows) > 1:
        return _truncate(f"{len(rows)} components; {component} {pid}".strip())
    return _truncate(f"{component} {pid}".strip() or finding.detail)


def _inventory_detail(rows: List[Dict[str, str]]) -> str:
    blocks = []
    for row in rows:
        block = _labeled_block(
            [
                ("Component", row.get("component", "")),
                ("Description", row.get("description", "")),
                ("PID", row.get("pid", "")),
                ("VID", row.get("vid", "")),
                ("Serial", row.get("serial", "")),
            ]
        )
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _logs_summary(lines: List[str], finding: object) -> str:
    if not lines:
        return _truncate(finding.detail)
    parsed = parse_log_detail_line(lines[0])
    message = parsed.get("message", lines[0])
    if len(lines) > 1:
        return _truncate(f"{len(lines)} messages; {message}")
    return _truncate(message)


def _logs_detail(lines: List[str]) -> str:
    blocks = []
    for line in lines:
        parsed = parse_log_detail_line(line)
        block = _labeled_block(
            [
                ("Time/Prefix", parsed.get("prefix", "")),
                ("Message", parsed.get("message", "")),
            ]
        )
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _transceiver_summary(detail: str, finding: object) -> str:
    rows = parse_transceiver_visual_rows(detail)
    if not rows:
        return _truncate(finding.detail)
    first = rows[0]
    iface = str(first.get("interface", ""))
    metric = str(first.get("metric", ""))
    unit = str(first.get("unit", ""))
    value = first.get("value")
    value_text = f"{unit} {float(value):.2f}".strip() if value is not None else ""
    summary = f"{iface} {metric} {value_text}".strip()
    if len(rows) > 1:
        return _truncate(f"{len(rows)} readings; {summary}")
    return _truncate(summary)


def _transceiver_detail(detail: str) -> str:
    blocks = []
    for row in parse_transceiver_visual_rows(detail):
        pre_value = row.get("pre_value")
        pre_text = ""
        if pre_value is not None:
            unit = str(row.get("unit", ""))
            pre_text = f"{unit} {float(pre_value):.2f}".strip()
        post_value = row.get("value")
        post_text = ""
        if post_value is not None:
            unit = str(row.get("unit", ""))
            post_text = f"{unit} {float(post_value):.2f}".strip()
        block = _labeled_block(
            [
                ("Interface", str(row.get("interface", ""))),
                ("Metric", str(row.get("metric", ""))),
                ("Pre", pre_text),
                ("Post", post_text),
                ("Low Alarm", str(row.get("low_alarm", ""))),
                ("Low Warn", str(row.get("low_warn", ""))),
                ("High Warn", str(row.get("high_warn", ""))),
                ("High Alarm", str(row.get("high_alarm", ""))),
            ]
        )
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def format_detail_summary(finding: object) -> str:
    detail = finding.detail or ""
    if is_mac_correlation_finding(finding):
        return _mac_summary(parse_mac_correlation_detail(detail), finding)
    if is_interface_status_finding(finding):
        return _interface_summary(_detail_lines(detail), finding)
    if is_neighbor_finding(finding):
        return _neighbor_summary(_detail_lines(detail), finding)
    if is_poe_finding(finding):
        return _poe_summary(detail, finding)
    if is_stp_root_finding(finding):
        return _stp_summary(_detail_lines(detail), finding)
    if is_port_map_finding(finding):
        return _port_map_summary(parse_port_map_detail(detail), finding)
    if is_inventory_finding(finding):
        return _inventory_summary(parse_inventory_detail(detail), finding)
    if is_logs_finding(finding):
        return _logs_summary(_detail_lines(detail), finding)
    if is_transceiver_finding(finding):
        return _transceiver_summary(detail, finding)
    return _truncate(detail.replace("\n", " | "))


def format_detail_pane(finding: object) -> str:
    detail = finding.detail or ""
    if is_mac_correlation_finding(finding):
        formatted = _mac_detail(parse_mac_correlation_detail(detail))
    elif is_interface_status_finding(finding):
        formatted = _interface_detail(_detail_lines(detail))
    elif is_neighbor_finding(finding):
        formatted = _neighbor_detail(_detail_lines(detail))
    elif is_poe_finding(finding):
        formatted = _poe_detail(detail)
    elif is_stp_root_finding(finding):
        formatted = _stp_detail(_detail_lines(detail))
    elif is_port_map_finding(finding):
        formatted = _port_map_detail(parse_port_map_detail(detail))
    elif is_inventory_finding(finding):
        formatted = _inventory_detail(parse_inventory_detail(detail))
    elif is_logs_finding(finding):
        formatted = _logs_detail(_detail_lines(detail))
    elif is_transceiver_finding(finding):
        formatted = _transceiver_detail(detail)
    else:
        formatted = detail.strip()
    return formatted or detail.strip()
