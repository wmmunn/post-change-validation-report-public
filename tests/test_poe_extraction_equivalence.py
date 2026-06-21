import re
import unittest
from types import SimpleNamespace
from typing import Dict, Optional, Set

from src.post_change_validation_analysis_wrappers import analyze_poe
from src.post_change_validation_models import Finding, NeighborRecord, PoeBudget, PoeEntry, PortMapRow, norm_interface
from src.post_change_validation_neighbor_parsers import parse_cdp_neighbors, parse_lldp_neighbors
from src.post_change_validation_neighbors import neighbor_names_compatible
from src.post_change_validation_poe import (
    compare_poe_delivery,
    parse_poe_budget,
    parse_power_inline,
    poe_budget_detail,
    poe_is_powering,
    poe_still_powering_ports,
)


def legacy_parse_power_inline(section: str) -> Dict[str, PoeEntry]:
    entries: Dict[str, PoeEntry] = {}
    for raw in section.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith(("interface", "module", "available", "used", "remaining", "----", "watts")):
            continue
        parts = line.split()
        if not parts:
            continue
        port = norm_interface(parts[0])
        if not re.match(r"^(Gi|Fi|Te)\d", port):
            continue
        admin = parts[1] if len(parts) > 1 else ""
        oper = parts[2] if len(parts) > 2 else ""
        power = ""
        for tok in parts[3:6]:
            if re.match(r"^\d+(?:\.\d+)?$", tok):
                power = tok
                break
        device = " ".join(parts[4:]) if len(parts) > 4 else ""
        entries[port] = PoeEntry(port=port, admin=admin, oper=oper, power_w=power, device=device, raw=line)
    return entries


def legacy_parse_poe_budget(section: str) -> Optional[PoeBudget]:
    if not section:
        return None
    best: Optional[PoeBudget] = None
    saw_budget_header = False
    for raw in section.splitlines():
        line = raw.strip()
        if not line:
            continue
        nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", line)]
        low = line.lower()
        labeled = re.search(
            r"available\D+(?P<available>\d+(?:\.\d+)?).*?used\D+(?P<used>\d+(?:\.\d+)?).*?remaining\D+(?P<remaining>\d+(?:\.\d+)?)",
            line,
            re.I,
        )
        if labeled:
            budget = PoeBudget(
                float(labeled.group("available")),
                float(labeled.group("used")),
                float(labeled.group("remaining")),
                line,
            )
            if budget.available_w > 0:
                best = budget
            saw_budget_header = False
            continue
        if "available" in low and "used" in low and "remaining" in low:
            saw_budget_header = True
            continue
        if re.match(r"^(?:Fa|Gi|Te|Twe|Fi|Fo|Hu)\d", line, re.I) or line.lower().startswith("totals:"):
            continue
        if len(nums) >= 3 and saw_budget_header:
            available, used, remaining = nums[-3], nums[-2], nums[-1]
            if available > 0 and used >= 0 and remaining >= 0 and abs((used + remaining) - available) <= max(5.0, available * 0.10):
                budget = PoeBudget(available, used, remaining, line)
                if not best or budget.available_w > best.available_w:
                    best = budget
                saw_budget_header = False
    return best


def legacy_poe_budget_detail(pre_sec: str, post_sec: str) -> list[str]:
    pre = legacy_parse_poe_budget(pre_sec)
    post = legacy_parse_poe_budget(post_sec)
    rows: list[str] = []
    if pre:
        rows.append(f"POE_BUDGET|pre|{pre.available_w:.2f}|{pre.used_w:.2f}|{pre.remaining_w:.2f}|{pre.raw.replace('|', '/')}")
    if post:
        rows.append(f"POE_BUDGET|post|{post.available_w:.2f}|{post.used_w:.2f}|{post.remaining_w:.2f}|{post.raw.replace('|', '/')}")
    return rows


def legacy_poe_is_powering(e: Optional[PoeEntry]) -> bool:
    if not e:
        return False
    txt = f"{e.admin} {e.oper} {e.raw}".lower()
    if re.search(r"\b(on|deliver|delivering|powering)\b", txt) and not re.search(r"\b(off|fault|deny|denied|disabled)\b", txt):
        return True
    try:
        return float(e.power_w) > 0.1
    except Exception:
        return False


def legacy_is_access_map_row(row: PortMapRow) -> bool:
    role = (row.role or "").lower()
    old = norm_interface(row.old_port)
    new = norm_interface(row.new_port)
    if "uplink" in role or "trunk" in role or old.startswith("Po") or new.startswith("Po"):
        return False
    if re.match(r"^(Gi|Fi|Te)\d+/0/\d+$", old) and re.match(r"^(Gi|Fi|Te)\d+/0/\d+$", new):
        return True
    if role == "standalone_industrial" and re.match(r"^(Fa|Gi|Te)\d+/\d+$", old) and re.match(r"^(Fa|Gi|Te)\d+/\d+$", new):
        return True
    return role == "access"


def legacy_poe_still_powering_ports(pre_sec: str, post_sec: str, pm: Dict[str, PortMapRow]) -> Set[str]:
    if not pre_sec or not post_sec:
        return set()
    pre = legacy_parse_power_inline(pre_sec)
    post = legacy_parse_power_inline(post_sec)
    powered: Set[str] = set()
    for old, row in pm.items():
        if not row.new_port or not legacy_is_access_map_row(row):
            continue
        if legacy_poe_is_powering(pre.get(old)) and legacy_poe_is_powering(post.get(row.new_port)):
            powered.add(row.new_port)
    return powered


def legacy_observed_neighbor_local_map(pre_sections: Dict[str, str], post_sections: Dict[str, str]) -> Dict[str, str]:
    if not pre_sections or not post_sections:
        return {}
    pre_recs: list[NeighborRecord] = []
    post_recs: list[NeighborRecord] = []
    for parser, section in [(parse_cdp_neighbors, "show cdp neighbors"), (parse_lldp_neighbors, "show lldp neighbors")]:
        pre_recs.extend(parser(pre_sections.get(section, "")))
        post_recs.extend(parser(post_sections.get(section, "")))
    post_by_remote: Dict[str, list[NeighborRecord]] = {}
    for pr in post_recs:
        post_by_remote.setdefault(norm_interface(pr.remote_interface), []).append(pr)
    observed: Dict[str, str] = {}
    for r in pre_recs:
        remote = norm_interface(r.remote_interface)
        matches = [pr for pr in post_by_remote.get(remote, []) if neighbor_names_compatible(r.neighbor, pr.neighbor)]
        if len(matches) == 1:
            observed[norm_interface(r.local_interface)] = norm_interface(matches[0].local_interface)
    return observed


def legacy_analyze_poe(
    pre_sec: str,
    post_sec: str,
    pm: Dict[str, PortMapRow],
    pre_if: Optional[Dict[str, object]] = None,
    post_if: Optional[Dict[str, object]] = None,
    pre_sections: Optional[Dict[str, str]] = None,
    post_sections: Optional[Dict[str, str]] = None,
) -> list[Finding]:
    findings: list[Finding] = []
    if not pre_sec and not post_sec:
        return findings
    observed_ports = legacy_observed_neighbor_local_map(pre_sections or {}, post_sections or {})
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


class PoeExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_analyze_poe_matches_legacy_inline_wrapper_with_observed_neighbor_and_budget_evidence(self):
        pre = """
Available:125.0(w) Used:24.3(w) Remaining:100.7(w)
Interface Admin Oper Power Device Class Max
Gi1/9 auto on 6.3 IP Phone 3 30.0
Gi1/10 auto on 8.0 Access Point 4 30.0
"""
        post = """
Module Available Used Remaining
1 400.0 54.3 345.7
Interface Admin Oper Power Device Class Max
Gi2/9 auto off 0.0 n/a n/a 30.0
Gi1/8 auto delivering 6.1 IP Phone 3 30.0
Te1/0/10 auto on 8.4 Access Point 4 30.0
"""
        port_map = {
            "Gi1/9": PortMapRow("Gi1/9", "Gi2/9", "standalone_industrial", "profile inference"),
            "Gi1/10": PortMapRow("Gi1/10", "Te1/0/10", "access", "sanitized access"),
        }
        pre_sections = {
            "show lldp neighbors": "phone-1.example Gi1/9 120 B Gi0/1",
        }
        post_sections = {
            "show lldp neighbors": "phone-1.example Gi1/8 120 B Gi0/1",
        }
        pre_if = {
            "Gi1/10": SimpleNamespace(speed="1000"),
        }
        post_if = {
            "Te1/0/10": SimpleNamespace(speed="2.5G"),
        }

        legacy = legacy_analyze_poe(pre, post, port_map, pre_if, post_if, pre_sections, post_sections)
        extracted = analyze_poe(pre, post, port_map, pre_if, post_if, pre_sections, post_sections)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["PASS"], [finding.severity for finding in extracted])
        self.assertIn("POE_BUDGET|pre|125.00|24.30|100.70", extracted[0].detail)
        self.assertIn("POE_BUDGET|post|400.00|54.30|345.70", extracted[0].detail)
        self.assertIn("POE_SPEED_UPGRADE|1|Gi1/10 -> Te1/0/10: 1000 -> 2.5G", extracted[0].detail)
        self.assertIn("Gi1/9 -> Gi1/8: PoE still delivering on observed neighbor port", extracted[0].detail)

    def test_extracted_poe_helpers_match_legacy_inline_output(self):
        pre = """
Interface Admin Oper Power Device Class Max
Gi1/0/1 auto on 6.3 IP Phone 3 30.0
Gi1/0/2 auto off 0.0 n/a n/a 30.0
Gi1/0/49 auto on 12.1 Uplink Device 4 30.0
Available:125.0(w) Used:24.3(w) Remaining:100.7(w)
"""
        post = """
Interface Admin Oper Power Device Class Max
Gi2/0/1 auto on 6.1 IP Phone 3 30.0
Gi2/0/2 auto off 0.0 n/a n/a 30.0
Totals: 2 ports
Module Available Used Remaining
1 400.0 54.3 345.7
"""
        port_map = {
            "Gi1/0/1": PortMapRow("Gi1/0/1", "Gi2/0/1", "access", ""),
            "Gi1/0/2": PortMapRow("Gi1/0/2", "Gi2/0/2", "access", ""),
            "Gi1/0/49": PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", ""),
        }

        self.assertEqual(legacy_parse_power_inline(pre), parse_power_inline(pre))
        self.assertEqual(legacy_parse_power_inline(post), parse_power_inline(post))
        self.assertEqual(legacy_parse_poe_budget(pre), parse_poe_budget(pre))
        self.assertEqual(legacy_parse_poe_budget(post), parse_poe_budget(post))
        self.assertEqual(legacy_poe_budget_detail(pre, post), poe_budget_detail(pre, post))
        for entry in list(parse_power_inline(pre).values()) + list(parse_power_inline(post).values()):
            self.assertEqual(legacy_poe_is_powering(entry), poe_is_powering(entry))
        self.assertEqual(legacy_poe_still_powering_ports(pre, post, port_map), poe_still_powering_ports(pre, post, port_map))

    def test_extracted_poe_row_parser_matches_legacy_with_delivery_states(self):
        section = """
Available:370.0(w) Used:42.7(w) Remaining:327.3(w)

Interface Admin  Oper       Power   Device              Class Max
--------- ------ ---------- ------- ------------------- ----- ----
Gi1/0/1   auto   on         6.3     IP Phone 8841       3     30.0
Gi1/0/2   auto   off        0.0     n/a                 n/a   30.0
Gi1/0/3   static delivering 15.4    Access Point        4     30.0
Te1/0/4   auto   faulty     0.0     Bad Endpoint        n/a   30.0
Hu1/0/1   auto   on         3.0     ignored-uplink      2     30.0
"""

        self.assertEqual(legacy_parse_power_inline(section), parse_power_inline(section))

    def test_extracted_poe_budget_parser_matches_legacy_table_output(self):
        table = """
Module   Available     Used     Remaining
------   ---------     ----     ---------
1        370.0         42.7     327.3
Gi1/0/1  auto          on       6.3       IP Phone
"""

        self.assertEqual(legacy_parse_poe_budget(table), parse_poe_budget(table))

    def test_extracted_poe_still_powering_ignores_down_access_and_uplink_rows(self):
        pre = """
Gi1/0/1  auto on         6.3  IP Phone 8841 3 30.0
Gi1/0/2  auto on         4.5  Camera        2 30.0
Gi1/0/3  auto off        0.0  n/a           n/a 30.0
Gi1/0/49 auto on         5.0  uplink        2 30.0
"""
        post = """
Te1/0/1 auto delivering 7.1  IP Phone 8841 3 30.0
Te1/0/2 auto off        0.0  Camera        2 30.0
Te1/0/3 auto on         4.0  Spare         2 30.0
Te1/1/1 auto on         5.0  uplink        2 30.0
"""
        port_map = {
            "Gi1/0/1": PortMapRow("Gi1/0/1", "Te1/0/1", "access", ""),
            "Gi1/0/2": PortMapRow("Gi1/0/2", "Te1/0/2", "access", ""),
            "Gi1/0/3": PortMapRow("Gi1/0/3", "Te1/0/3", "access", ""),
            "Gi1/0/49": PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", ""),
        }

        self.assertEqual(legacy_poe_still_powering_ports(pre, post, port_map), poe_still_powering_ports(pre, post, port_map))


if __name__ == "__main__":
    unittest.main()
