"""High-level analysis wrappers that compose parser results into findings."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, NamedTuple, Optional, Set

from src.post_change_validation_interface_status import (
    build_uncovered_connected_detail_lines,
    compare_mapped_interface_status,
)
from src.post_change_validation_mac import count_macs, mac_correlation_rows
from src.post_change_validation_models import Finding, NeighborRecord, PortMapRow, norm_interface
from src.post_change_validation_stp import (
    compare_stp_topology,
    parse_stp_path_cost_method,
    parse_stp_root,
)
from src.post_change_validation_neighbor_parsers import parse_cdp_neighbors, parse_lldp_neighbors
from src.post_change_validation_neighbors import compare_neighbors, neighbor_names_compatible
from src.post_change_validation_poe import compare_poe_delivery
from src.post_change_validation_transceivers import compare_transceiver_delivery, parse_transceiver_detail
from src.post_change_validation_trunks import compare_mapped_trunks


def analyze_port_map_findings(
    pm: Dict[str, PortMapRow],
    port_map_source: str,
    port_map_detail: str,
) -> List[Finding]:
    findings: List[Finding] = []
    if pm:
        findings.append(Finding("INFO", "Port Map", f"Port map loaded with {len(pm)} old-to-new mapping row(s).", f"{port_map_source}\n{port_map_detail}"))
    else:
        findings.append(Finding("WARN", "Port Map", "No port map could be generated or loaded.", f"{port_map_source}\n{port_map_detail}"))
    return findings


def analyze_command_sections_findings(pre: Dict[str, str], post: Dict[str, str]) -> List[Finding]:
    findings: List[Finding] = []
    findings.append(Finding("INFO", "Command Sections", f"Pre-change sections found: {len(pre)}", ", ".join(sorted(pre.keys()))))
    findings.append(Finding("INFO", "Command Sections", f"Post-change sections found: {len(post)}", ", ".join(sorted(post.keys()))))
    if not pre or not post:
        findings.append(Finding("FAIL", "Command Sections", "One or both logs had zero command sections parsed.", "Check whether command prompts or script formatting changed. v8 supports prompt-prefixed lines such as switch#show int status."))
    return findings


def analyze_trunks(
    pre_trunk_section: str,
    post_trunk_section: str,
    old_to_new: Dict[str, str],
) -> List[Finding]:
    from src.post_change_validation_uplinks import parse_trunks

    findings: List[Finding] = []
    pre_tr = parse_trunks(pre_trunk_section)
    post_tr = parse_trunks(post_trunk_section)
    trunk_comparison = compare_mapped_trunks(pre_tr, post_tr, old_to_new)
    if trunk_comparison.has_evidence:
        if trunk_comparison.missing:
            findings.append(Finding("WARN", "Trunks", f"{len(trunk_comparison.missing)} pre-change trunk port(s) missing after change.", "\n".join(trunk_comparison.missing)))
        else:
            detail = "\n".join(trunk_comparison.matched_mapped) if trunk_comparison.matched_mapped else ""
            findings.append(Finding("PASS", "Trunks", f"No pre-change trunk ports disappeared; {len(trunk_comparison.matched_mapped)} matched through the port map.", detail))
    return findings


def analyze_switch_detail_findings(switch_detail_section: str) -> List[Finding]:
    findings: List[Finding] = []
    sw = switch_detail_section
    if sw:
        if re.search(r"active|ready|standby", sw, re.I):
            findings.append(Finding("PASS", "Switch Detail", "Post-change switch detail section is present and contains active/ready/standby wording.", ""))
        else:
            findings.append(Finding("INFO", "Switch Detail", "Post-change switch detail section is present.", ""))
    return findings


def analyze_dot1x_findings(dot1x_section: str) -> List[Finding]:
    findings: List[Finding] = []
    dot = dot1x_section
    if dot:
        if re.search(r"auth|unauth|mab|dot1x|authorized", dot, re.I):
            findings.append(Finding("INFO", "Dot1x", "Dot1x summary section found.", ""))
        else:
            findings.append(Finding("INFO", "Dot1x", "Dot1x summary section found, but no common auth state keywords detected.", ""))
    return findings


DEFAULT_STANDARD_UPLINK_A = "Te1/1/1"
DEFAULT_STANDARD_UPLINK_B = "Te1/1/8"

# c9300-48u
SUPPORTED_CATALYST_FAMILY_PATTERN = re.compile(r"\bc(?:9200|9300|9500)\w*", re.IGNORECASE)

# cisco C9300-48U
VERSION_CATALYST_MODEL_PATTERN = re.compile(r"cisco\s+C(?:9200|9300|9500)\w*", re.IGNORECASE)


class StandardUplinkTargetsResult(NamedTuple):
    uplink_a: str
    uplink_b: str
    review_reason: str = ""


def collect_hardware_model_strings(version_section: str, inventory_section: str) -> List[str]:
    """Collect model/PID strings from show version and show inventory evidence."""
    models: List[str] = []
    for record in parse_inventory_records(inventory_section):
        for key in ("pid", "description"):
            value = (record.get(key) or "").strip()
            if value:
                models.append(value)
    for raw in (version_section or "").splitlines():
        line = raw.strip()
        if line:
            models.append(line)
    return models


def is_known_catalyst_platform(version_section: str, inventory_section: str) -> bool:
    """Return True when version or inventory evidence matches a supported Catalyst family."""
    for text in collect_hardware_model_strings(version_section, inventory_section):
        if SUPPORTED_CATALYST_FAMILY_PATTERN.search(text):
            return True
        if VERSION_CATALYST_MODEL_PATTERN.search(text):
            return True
    return False


def transceiver_detail_includes_interfaces(transceiver_section: str, *targets: str) -> bool:
    """Return True when every target interface appears in parsed transceiver detail."""
    if not transceiver_section or not targets:
        return False
    present = {norm_interface(port) for port in parse_transceiver_detail(transceiver_section)}
    return all(norm_interface(target) in present for target in targets if target)


def uplink_fallback_review_finding(review_reason: str) -> Finding:
    return Finding(
        "WARN",
        "Port Map",
        "Standard uplink target fallback unavailable.",
        review_reason,
    )


def _confirm_single_standard_uplink_fallback_target(
    fallback_target: str,
    *,
    version_section: str,
    inventory_section: str,
    transceiver_section: str,
) -> str:
    """Return review_reason when a single fallback target cannot be confirmed; else ""."""
    if not is_known_catalyst_platform(version_section, inventory_section):
        return (
            "Unknown or unsupported platform; cannot infer standard uplink target "
            f"{fallback_target} without explicit map A/B rows."
        )
    if not transceiver_detail_includes_interfaces(transceiver_section, fallback_target):
        return (
            f"Standard uplink target {fallback_target} not confirmed in transceiver detail; "
            "manual review required."
        )
    return ""


def _confirm_standard_uplink_fallback(
    fallback_a: str,
    fallback_b: str,
    *,
    version_section: str,
    inventory_section: str,
    transceiver_section: str,
) -> StandardUplinkTargetsResult:
    for target in (fallback_a, fallback_b):
        review_reason = _confirm_single_standard_uplink_fallback_target(
            target,
            version_section=version_section,
            inventory_section=inventory_section,
            transceiver_section=transceiver_section,
        )
        if review_reason:
            if "unsupported platform" in review_reason:
                return StandardUplinkTargetsResult(
                    "",
                    "",
                    "Unknown or unsupported platform; cannot infer standard uplink targets "
                    f"{fallback_a} / {fallback_b} without explicit map A/B rows.",
                )
            return StandardUplinkTargetsResult(
                "",
                "",
                f"Standard uplink targets {fallback_a} / {fallback_b} not confirmed in transceiver detail; manual review required.",
            )
    return StandardUplinkTargetsResult(fallback_a, fallback_b)


def standard_uplink_targets_from_map(
    pm: Dict[str, PortMapRow],
    *,
    version_section: str = "",
    inventory_section: str = "",
    transceiver_section: str = "",
) -> StandardUplinkTargetsResult:
    """Find standard uplink A/B targets from map rows with evidence-backed fallback."""
    a = ""
    b = ""
    for row in pm.values():
        note = (row.note or "").lower()
        old = norm_interface(row.old_port)
        if not a and ("uplink a" in note or old in {"Gi0/15"}):
            a = row.new_port
        if not b and ("uplink b" in note or old in {"Gi0/16"}):
            b = row.new_port

    if a and b:
        return StandardUplinkTargetsResult(a, b)
    if a and not b:
        review_reason = _confirm_single_standard_uplink_fallback_target(
            DEFAULT_STANDARD_UPLINK_B,
            version_section=version_section,
            inventory_section=inventory_section,
            transceiver_section=transceiver_section,
        )
        if review_reason:
            return StandardUplinkTargetsResult("", "", review_reason)
        return StandardUplinkTargetsResult(a, DEFAULT_STANDARD_UPLINK_B)
    if b and not a:
        review_reason = _confirm_single_standard_uplink_fallback_target(
            DEFAULT_STANDARD_UPLINK_A,
            version_section=version_section,
            inventory_section=inventory_section,
            transceiver_section=transceiver_section,
        )
        if review_reason:
            return StandardUplinkTargetsResult("", "", review_reason)
        return StandardUplinkTargetsResult(DEFAULT_STANDARD_UPLINK_A, b)

    return _confirm_standard_uplink_fallback(
        DEFAULT_STANDARD_UPLINK_A,
        DEFAULT_STANDARD_UPLINK_B,
        version_section=version_section,
        inventory_section=inventory_section,
        transceiver_section=transceiver_section,
    )


def extract_uplink_targets_from_map(
    pm: Dict[str, PortMapRow],
    *,
    version_section: str = "",
    inventory_section: str = "",
    transceiver_section: str = "",
) -> tuple[Set[str], str]:
    uplinks: Set[str] = set()
    for row in pm.values():
        role = (row.role or "").lower()
        note = (row.note or "").lower()
        if "uplink" in role or "uplink" in note:
            if row.new_port:
                uplinks.add(norm_interface(row.new_port))
    targets = standard_uplink_targets_from_map(
        pm,
        version_section=version_section,
        inventory_section=inventory_section,
        transceiver_section=transceiver_section,
    )
    if targets.uplink_a:
        uplinks.add(norm_interface(targets.uplink_a))
    if targets.uplink_b:
        uplinks.add(norm_interface(targets.uplink_b))
    return {u for u in uplinks if u}, targets.review_reason


def observed_neighbor_local_map(pre_sections: Dict[str, str], post_sections: Dict[str, str]) -> Dict[str, str]:
    """Map pre local ports to observed post local ports by neighbor identity."""
    if not pre_sections or not post_sections:
        return {}
    pre_recs: List[NeighborRecord] = []
    post_recs: List[NeighborRecord] = []
    for parser, section in [(parse_cdp_neighbors, "show cdp neighbors"), (parse_lldp_neighbors, "show lldp neighbors")]:
        pre_recs.extend(parser(pre_sections.get(section, "")))
        post_recs.extend(parser(post_sections.get(section, "")))
    post_by_remote: Dict[str, List[NeighborRecord]] = {}
    for pr in post_recs:
        post_by_remote.setdefault(norm_interface(pr.remote_interface), []).append(pr)
    observed: Dict[str, str] = {}
    for r in pre_recs:
        remote = norm_interface(r.remote_interface)
        matches = [pr for pr in post_by_remote.get(remote, []) if neighbor_names_compatible(r.neighbor, pr.neighbor)]
        if len(matches) == 1:
            observed[norm_interface(r.local_interface)] = norm_interface(matches[0].local_interface)
    return observed


def has_standalone_industrial_map(pm: Dict[str, PortMapRow]) -> bool:
    return any((row.role or "") == "standalone_industrial" for row in pm.values())


def _interface_status_value(if_map: Mapping[str, Any], port: str) -> str:
    entry = if_map.get(port)
    return entry.status if entry else "missing"


def analyze_interface_status(
    pre_if: Mapping[str, Any],
    post_if: Mapping[str, Any],
    pm: Optional[Dict[str, PortMapRow]],
    observed_neighbor_ports: Mapping[str, str] | None = None,
    observed_mac_ports: Mapping[str, str] | None = None,
    post_running_config: str = "",
    post_trunks: Set[str] | None = None,
) -> List[Finding]:
    findings: List[Finding] = []
    if pm:
        interface_status = compare_mapped_interface_status(
            pre_if,
            post_if,
            pm,
            observed_neighbor_ports=observed_neighbor_ports,
            observed_mac_ports=observed_mac_ports,
        )
        if interface_status.connected_warn:
            findings.append(Finding("WARN", "Interface Status", f"{len(interface_status.connected_warn)} mapped port issue(s) require review.", "\n".join(interface_status.connected_warn)))
        if interface_status.connected_pass:
            findings.append(Finding("PASS", "Interface Status", f"{len(interface_status.connected_pass)} mapped connected port(s) remained connected after change.", "\n".join(interface_status.connected_pass)))
        if interface_status.unchanged_down:
            findings.append(Finding("INFO", "Interface Status", f"{interface_status.unchanged_down} mapped port(s) remained not connected/disabled.", "Suppressed detailed unchanged-down rows."))
        if interface_status.uncovered_connected:
            uncovered_detail = "\n".join(
                build_uncovered_connected_detail_lines(
                    interface_status.uncovered_connected,
                    post_if,
                    post_running_config=post_running_config,
                    post_trunks=post_trunks,
                )
            )
            findings.append(
                Finding(
                    "INFO",
                    "Interface Status",
                    f"{len(interface_status.uncovered_connected)} connected post-change port(s) were not covered by the port map.",
                    uncovered_detail,
                )
            )
    else:
        missing = [p for p, st in pre_if.items() if st.status == "connected" and _interface_status_value(post_if, p) != "connected"]
        new = [p for p, st in post_if.items() if st.status == "connected" and _interface_status_value(pre_if, p) != "connected"]
        if missing:
            findings.append(Finding("WARN", "Interface Status", f"{len(missing)} port(s) were connected before but not connected after.", "\n".join(missing)))
        if new:
            findings.append(Finding("INFO", "Interface Status", f"{len(new)} port(s) are newly connected after change.", "\n".join(new)))
    return findings


def analyze_neighbors(
    pre: Dict[str, str],
    post: Dict[str, str],
    old_to_new: Dict[str, str],
    mac_present_ports: Dict[str, int],
    poe_powered_ports: Set[str],
    post_if: Dict[str, object],
) -> List[Finding]:
    findings: List[Finding] = []
    for proto, parser, section_name in [("CDP", parse_cdp_neighbors, "show cdp neighbors"), ("LLDP", parse_lldp_neighbors, "show lldp neighbors")]:
        pre_section = pre.get(section_name, "")
        post_section = post.get(section_name, "")
        pre_recs = parser(pre_section)
        post_recs = parser(post_section)
        if pre_section and not pre_recs:
            findings.append(Finding("INFO", f"{proto} Neighbors", f"Pre-change {proto.lower()} section found, but no neighbor records were parsed.", "This may be normal if no neighbors were present, or the parser may need adjustment for this output format."))
        if post_section and not post_recs:
            findings.append(Finding("INFO", f"{proto} Neighbors", f"Post-change {proto.lower()} section found, but no neighbor records were parsed.", "This may be normal if no neighbors were present, or the parser may need adjustment for this output format."))
        neighbor_comparison = compare_neighbors(
            pre_recs,
            post_recs,
            old_to_new,
            mac_present_ports=mac_present_ports,
            poe_powered_ports=poe_powered_ports,
            post_if=post_if,
        )
        if neighbor_comparison.missing:
            findings.append(Finding("WARN", f"{proto} Neighbors", f"{len(neighbor_comparison.missing)} {proto.lower()} neighbor record(s) missing after change.", "\n".join(neighbor_comparison.missing)))
        if neighbor_comparison.missing_with_presence_evidence:
            findings.append(Finding("INFO", f"{proto} Neighbors", f"{len(neighbor_comparison.missing_with_presence_evidence)} {proto.lower()} neighbor advertisement(s) missing, but endpoint evidence is present on the mapped port.", "\n".join(neighbor_comparison.missing_with_presence_evidence)))
        if neighbor_comparison.matched:
            findings.append(Finding("PASS", f"{proto} Neighbors", f"{len(neighbor_comparison.matched)} {proto.lower()} neighbor record(s) matched after change.", "\n".join(neighbor_comparison.matched)))
        if neighbor_comparison.new:
            findings.append(Finding("INFO", f"{proto} Neighbors", f"{len(neighbor_comparison.new)} new {proto.lower()} neighbor record(s) appeared after change.", "\n".join(neighbor_comparison.new)))
    return findings


def analyze_poe(
    pre_sec: str,
    post_sec: str,
    pm: Dict[str, PortMapRow],
    pre_if: Optional[Dict[str, object]] = None,
    post_if: Optional[Dict[str, object]] = None,
    pre_sections: Optional[Dict[str, str]] = None,
    post_sections: Optional[Dict[str, str]] = None,
) -> List[Finding]:
    findings: List[Finding] = []
    if not pre_sec and not post_sec:
        return findings
    observed_ports = observed_neighbor_local_map(pre_sections or {}, post_sections or {})
    comparison = compare_poe_delivery(pre_sec, post_sec, pm, pre_if or {}, post_if or {}, observed_ports)
    if not comparison.parsed_pre_rows and not comparison.parsed_post_rows:
        findings.append(Finding("INFO", "PoE", "Power inline output found, but no interface rows were parsed.", "\n".join(comparison.evidence_lines + ["Parser may need adjustment for this output format."])))
        return findings
    if comparison.missing:
        findings.append(Finding("WARN", "PoE", f"{len(comparison.missing)} access port(s) appear to have lost PoE after change.", "\n".join(comparison.evidence_lines + comparison.missing)))
    if comparison.restored:
        findings.append(Finding("PASS", "PoE", f"{len(comparison.restored)} previously powered access port(s) still show PoE after change.", "\n".join(comparison.evidence_lines + comparison.restored[:80]) + ("\n... truncated ..." if len(comparison.restored) > 80 else "")))
    if not comparison.missing and not comparison.restored:
        findings.append(Finding("INFO", "PoE", "PoE sections parsed, but no pre-change powered access ports were found for mapped comparison.", "\n".join(comparison.evidence_lines + [f"Parsed pre rows={comparison.parsed_pre_rows}, post rows={comparison.parsed_post_rows}"])))
    return findings


def analyze_transceivers(
    pre_section: str,
    post_section: str,
    pm: Dict[str, PortMapRow],
    *,
    version_section: str = "",
    inventory_section: str = "",
) -> List[Finding]:
    if not pre_section and not post_section:
        return []
    findings: List[Finding] = []
    entries = parse_transceiver_detail(post_section)
    pre_entries = parse_transceiver_detail(pre_section)
    uplinks, review_reason = extract_uplink_targets_from_map(
        pm,
        version_section=version_section,
        inventory_section=inventory_section,
        transceiver_section=post_section,
    )
    if review_reason:
        findings.append(uplink_fallback_review_finding(review_reason))
    comparison = compare_transceiver_delivery(pre_entries, entries, pm, uplinks, has_standalone_industrial_map(pm))
    if not entries:
        findings.append(Finding("INFO", "Transceiver", "Transceiver detail output found, but no interface readings were parsed.", "Parser may need adjustment for this output format."))
        return findings
    if not comparison.matched_target_rows:
        findings.append(Finding("INFO", "Transceiver", f"Parsed transceiver detail for {comparison.parsed_post_rows} interface(s), but none matched known uplink/optic targets.", comparison.unmatched_detail))
        return findings
    if comparison.warn_blocks:
        findings.append(Finding("WARN", "Transceiver", f"{len(comparison.warn_blocks)} transceiver reading block(s) may contain alarm/warning text.", "\n\n".join(comparison.warn_blocks)[:12000]))
    if comparison.info_blocks:
        findings.append(Finding("INFO", "Transceiver", f"{len(comparison.info_blocks)} transceiver detail block(s) captured for review.", "\n\n".join(comparison.info_blocks)[:12000]))
    return findings


# Fan Bad
ENVIRONMENT_HEALTH_CONCERN_PATTERN = re.compile(r"fail|fault|bad|critical|shutdown|not ok|over.?temp|alarm")

# Fan 1 OK
ENVIRONMENT_HEALTH_OK_PATTERN = re.compile(r"\bok\b|normal|good")

# Threshold legend
ENVIRONMENT_LEGEND_PATTERN = re.compile(r"threshold|legend")


def analyze_environment(section: str) -> List[Finding]:
    if not section:
        return []
    bad_lines = []
    ok_count = 0
    for raw in section.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if ENVIRONMENT_HEALTH_CONCERN_PATTERN.search(low):
            if not ENVIRONMENT_LEGEND_PATTERN.search(low):
                bad_lines.append(line)
        elif ENVIRONMENT_HEALTH_OK_PATTERN.search(low):
            ok_count += 1
    if bad_lines:
        return [Finding("WARN", "Environment", f"{len(bad_lines)} possible environment health concern line(s) found.", "\n".join(bad_lines[:80]))]
    return [Finding("PASS", "Environment", "Environment output found with no obvious fault/fail/alarm keywords.", f"OK/normal/good lines detected: {ok_count}")]


# NAME: "Switch 1", DESCR: "Cisco C9300"
INVENTORY_NAME_DESCR_PATTERN = re.compile(r'NAME:\s*"?(?P<name>[^",]+)"?\s*,\s*DESCR:\s*"?(?P<descr>[^"]+)"?', re.IGNORECASE)

# PID: C9300-48U
INVENTORY_PID_PATTERN = re.compile(r"PID:\s*(?P<pid>[^,]+)", re.IGNORECASE)

# VID: V01
INVENTORY_VID_PATTERN = re.compile(r"VID:\s*(?P<vid>[^,]+)", re.IGNORECASE)

# SN: SANITIZED1234
INVENTORY_SERIAL_PATTERN = re.compile(r"SN:\s*(?P<sn>[^,\s]+)", re.IGNORECASE)


def parse_inventory_records(section: str) -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    for raw in section.splitlines():
        line = raw.strip()
        if not line:
            continue
        name_m = INVENTORY_NAME_DESCR_PATTERN.search(line)
        if name_m:
            if current and (current.get("pid") or current.get("serial")):
                records.append(current)
            current = {
                "component": name_m.group("name").strip(),
                "description": name_m.group("descr").strip(),
                "pid": "",
                "vid": "",
                "serial": "",
            }
            continue
        pid_m = INVENTORY_PID_PATTERN.search(line)
        vid_m = INVENTORY_VID_PATTERN.search(line)
        sn_m = INVENTORY_SERIAL_PATTERN.search(line)
        if pid_m or vid_m or sn_m:
            if current is None:
                current = {"component": "", "description": "", "pid": "", "vid": "", "serial": ""}
            if pid_m:
                current["pid"] = pid_m.group("pid").strip()
            if vid_m:
                current["vid"] = vid_m.group("vid").strip()
            if sn_m:
                current["serial"] = sn_m.group("sn").strip()
    if current and (current.get("pid") or current.get("serial")):
        records.append(current)
    return records


def analyze_inventory(section: str) -> List[Finding]:
    if not section:
        return []
    records = parse_inventory_records(section)
    if records:
        models = [r.get("pid", "") for r in records if r.get("pid")]
        serials = [r.get("serial", "") for r in records if r.get("serial")]
        detail_rows = ["component|description|pid|vid|serial"]
        for r in records[:80]:
            safe = lambda v: str(v).replace("|", "/")
            detail_rows.append("|".join([
                safe(r.get("component", "")),
                safe(r.get("description", "")),
                safe(r.get("pid", "")),
                safe(r.get("vid", "")),
                safe(r.get("serial", "")),
            ]))
        return [Finding("INFO", "Inventory", f"Inventory parsed: {len(models)} PID/model value(s), {len(serials)} serial value(s).", "\n".join(detail_rows))]

    models = []
    serials = []
    for raw in section.splitlines():
        line = raw.strip()
        pid_m = INVENTORY_PID_PATTERN.search(line)
        if pid_m:
            models.append(pid_m.group("pid").strip())
        sn_m = INVENTORY_SERIAL_PATTERN.search(line)
        if sn_m:
            serials.append(sn_m.group("sn").strip())
    detail = "Models/PIDs:\n" + "\n".join(models[:40]) + "\n\nSerials:\n" + "\n".join(serials[:40])
    if models or serials:
        return [Finding("INFO", "Inventory", f"Inventory parsed: {len(models)} PID/model value(s), {len(serials)} serial value(s).", detail)]
    return [Finding("INFO", "Inventory", "Inventory section found, but no PID/SN values were parsed.", section[:2000])]


# Cisco IOS XE Software, Version 17.09.04
VERSION_DOCUMENTATION_LINE_PATTERN = re.compile(
    r"Cisco IOS XE Software|Version\s+\d|uptime is|System image file|Model Number|cisco\s+C\d",
    re.IGNORECASE,
)


def analyze_version(section: str) -> List[Finding]:
    if not section:
        return []
    lines = []
    for raw in section.splitlines():
        line = raw.strip()
        if VERSION_DOCUMENTATION_LINE_PATTERN.search(line):
            lines.append(line)
    return [Finding("INFO", "Version", "Version section captured for documentation.", "\n".join(lines[:40]) or section[:2000])]


# CPU utilization for five seconds: 9%
CPU_FIVE_SECOND_UTILIZATION_PATTERN = re.compile(r"CPU utilization for five seconds:\s*(\d+)%", re.IGNORECASE)


def analyze_cpu(section: str) -> List[Finding]:
    if not section:
        return []
    m = CPU_FIVE_SECOND_UTILIZATION_PATTERN.search(section)
    if m:
        val = int(m.group(1))
        sev = "WARN" if val >= 80 else "INFO"
        return [Finding(sev, "CPU", f"CPU five-second utilization: {val}%", "High CPU during immediate post-change may be transient; review only if sustained or paired with symptoms.")]
    return [Finding("INFO", "CPU", "CPU section found for documentation, but utilization line was not parsed.", section[:2000])]


# Jun 20 12:03:04 %PM-4-ERR_DISABLE: err-disable caused by loop on Gi1/0/3
HIGH_RISK_LOG_PATTERN = re.compile(r"DUPADDR|ERR-?DISABLE|PM-4-ERR_DISABLE|LOOP|UDLD|SPANTREE.*(?:BLOCK|LOOP|INCONSIST|ROOTGUARD|BPDU)|AUTHMGR.*FAIL|MAB.*FAIL|DOT1X.*FAIL|SECURITY", re.I)


def analyze_logs(post_logging_section: str) -> List[Finding]:
    high = [ln.strip() for ln in post_logging_section.splitlines() if HIGH_RISK_LOG_PATTERN.search(ln)]
    if high:
        return [Finding("INFO", "Logs", f"Log review recommended: {len(high)} message(s); correlate with approved change activity.", "\n".join(high[:80]))]
    return [Finding("PASS", "Logs", "No high-risk log keywords found.", "")]


def analyze_stp_root(
    pre: Dict[str, str],
    post: Dict[str, str],
    old_to_new: Dict[str, str],
    post_if: Dict[str, object],
) -> List[Finding]:
    findings: List[Finding] = []
    pre_stp_records = parse_stp_root(pre.get("show spanning-tree root", ""))
    post_stp_records = parse_stp_root(post.get("show spanning-tree root", ""))
    pre_stp_cost_method = parse_stp_path_cost_method(pre.get("show spanning-tree summary", ""), pre.get("show running-config", ""))
    post_stp_cost_method = parse_stp_path_cost_method(post.get("show spanning-tree summary", ""), post.get("show running-config", ""))
    if pre_stp_records and post_stp_records:
        stp_comparison = compare_stp_topology(
            pre_stp_records,
            post_stp_records,
            old_to_new,
            pre_stp_cost_method,
            post_stp_cost_method,
            post.get("show running-config", ""),
            post_if,
        )
        if stp_comparison.warn_items:
            findings.append(Finding("WARN", "STP Root", f"{len(stp_comparison.warn_items)} STP root item(s) require review.", "\n".join(stp_comparison.warn_items)))
        if stp_comparison.pass_items:
            findings.append(Finding("PASS", "STP Root", f"{len(stp_comparison.pass_items)} STP VLAN(s) retained expected root/mapped root-port behavior.", "\n".join(stp_comparison.pass_items)))
        if stp_comparison.info_items:
            findings.append(Finding("INFO", "STP Root", f"{len(stp_comparison.info_items)} informational STP root item(s).", "\n".join(stp_comparison.info_items)))
    return findings


def analyze_access_port_mac_correlation(
    pre_mac_section: str,
    post_mac_section: str,
    pm: Dict[str, PortMapRow],
    exclude_old_ports: Optional[Set[str]] = None,
) -> List[Finding]:
    if not pm:
        return []
    mac_rows, mac_counts = mac_correlation_rows(pre_mac_section, post_mac_section, pm, exclude_old_ports)
    if mac_counts.get("TOTAL", 0):
        summary = (
            f"Access-port MACs checked: {mac_counts.get('TOTAL', 0)}; "
            f"present on expected port: {mac_counts.get('PASS', 0)}; "
            f"missing: {mac_counts.get('MISSING', 0)}; "
            f"present on non-inferred port: {mac_counts.get('MOVED', 0)}."
        )
        sev = "WARN" if mac_counts.get("MISSING", 0) or mac_counts.get("MOVED", 0) else "PASS"
        detail = "status|mac|vlan|pre_port|expected_post_port|actual_post_port|note\n" + "\n".join(mac_rows)
        return [Finding(sev, "Access Port MAC Correlation", summary, detail)]
    return [Finding("INFO", "Access Port MAC Correlation", "No pre-change local access-port MACs were available to correlate.", "This may mean the MAC table section was missing, empty, aged out, or only contained trunk-learned MACs.")]


def analyze_mac_count(pre_mac_section: str, post_mac_section: str) -> List[Finding]:
    pre_mac = count_macs(pre_mac_section)
    post_mac = count_macs(post_mac_section)
    if pre_mac and post_mac:
        if post_mac < max(1, int(pre_mac * 0.6)):
            return [Finding("WARN", "MAC Table", f"MAC address count dropped from {pre_mac} to {post_mac}.", "")]
        return [Finding("PASS", "MAC Table", f"MAC address count acceptable: {pre_mac} before, {post_mac} after.", "")]
    return []
