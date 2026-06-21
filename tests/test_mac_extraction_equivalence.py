import re
import unittest
from typing import Dict, List, Optional, Set, Tuple

from src.post_change_validation_mac import (
    count_macs,
    is_access_map_row,
    mac_correlation_rows,
    mac_expected_present_ports,
    norm_mac,
    observed_mac_local_map,
    parse_mac_address_table,
)
from src.post_change_validation_models import MacEntry, PortMapRow, norm_interface


def legacy_count_macs(section: str) -> int:
    return len(re.findall(r"\b[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}\b", section, re.I))


def legacy_norm_mac(mac: str) -> str:
    return (mac or "").strip().lower()


def legacy_parse_mac_address_table(section: str) -> List[MacEntry]:
    entries: List[MacEntry] = []
    mac_pat = re.compile(
        r"(?P<vlan>\*?\s*\d+|All)\s+(?P<mac>[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\s+(?P<type>\S+)\s+(?P<port>\S+)",
        re.I,
    )
    for raw in section.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith(("vlan", "----", "mac address", "total", "legend")):
            continue
        m = mac_pat.search(line)
        if not m:
            continue
        port = norm_interface(m.group("port"))
        if not re.match(r"^(Gi|Te|Twe|Fi|Fo|Hu|Po|Ap)\d", port):
            continue
        vlan = re.sub(r"\D", "", m.group("vlan")) or m.group("vlan")
        entries.append(MacEntry(vlan=vlan, mac=legacy_norm_mac(m.group("mac")), type_=m.group("type"), port=port, raw=line))
    return entries


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


def legacy_mac_correlation_rows(
    pre_mac_section: str,
    post_mac_section: str,
    pm: Dict[str, PortMapRow],
    exclude_old_ports: Optional[Set[str]] = None,
) -> Tuple[List[str], Dict[str, int]]:
    exclude_old_ports = {norm_interface(p) for p in (exclude_old_ports or set())}
    pre_entries = legacy_parse_mac_address_table(pre_mac_section)
    post_entries = legacy_parse_mac_address_table(post_mac_section)
    access_map = {old: row.new_port for old, row in pm.items() if row.new_port and legacy_is_access_map_row(row) and norm_interface(old) not in exclude_old_ports}
    access_old_ports = set(access_map)

    pre_access = [e for e in pre_entries if e.port in access_old_ports]

    post_by_mac: Dict[str, List[MacEntry]] = {}
    for e in post_entries:
        post_by_mac.setdefault(e.mac, []).append(e)

    rows: List[str] = []
    counts = {"PASS": 0, "MISSING": 0, "MOVED": 0, "DUPLICATE": 0, "TOTAL": 0}
    seen: Set[Tuple[str, str, str]] = set()
    for e in sorted(pre_access, key=lambda x: (x.port, x.vlan, x.mac)):
        key = (e.mac, e.vlan, e.port)
        if key in seen:
            continue
        seen.add(key)
        expected = access_map.get(e.port, "")
        candidates = post_by_mac.get(e.mac, [])
        same_vlan = [c for c in candidates if str(c.vlan) == str(e.vlan)] or candidates
        expected_hits = [c for c in same_vlan if c.port == expected]
        counts["TOTAL"] += 1
        if expected_hits:
            status = "PASS"
            actual = expected
            note = "Present on expected mapped access port"
        elif same_vlan:
            status = "MOVED"
            actual = ", ".join(sorted({c.port for c in same_vlan}))
            note = "MAC found post-change on a different port than the inferred map; review only if exact port placement was required"
        else:
            status = "MISSING"
            actual = "Not found"
            note = "MAC from old local access port not found post-change"
        counts[status] = counts.get(status, 0) + 1
        safe = lambda v: str(v).replace("|", "/")
        rows.append("|".join([status, safe(e.mac), safe(e.vlan), safe(e.port), safe(expected), safe(actual), safe(note)]))
    return rows, counts


def legacy_mac_expected_present_ports(
    pre_mac_section: str,
    post_mac_section: str,
    pm: Dict[str, PortMapRow],
    exclude_old_ports: Optional[Set[str]] = None,
) -> Dict[str, int]:
    present: Dict[str, int] = {}
    rows, _counts = legacy_mac_correlation_rows(pre_mac_section, post_mac_section, pm, exclude_old_ports)
    for row in rows:
        parts = row.split("|")
        if len(parts) < 5 or parts[0] != "PASS":
            continue
        expected_port = parts[4]
        if expected_port:
            present[expected_port] = present.get(expected_port, 0) + 1
    return present


def legacy_observed_mac_local_map(
    pre_mac_section: str,
    post_mac_section: str,
    pm: Dict[str, PortMapRow],
    exclude_old_ports: Optional[Set[str]] = None,
) -> Dict[str, str]:
    exclude_old_ports = {norm_interface(p) for p in (exclude_old_ports or set())}
    pre_entries = legacy_parse_mac_address_table(pre_mac_section)
    post_entries = legacy_parse_mac_address_table(post_mac_section)
    access_old_ports = {
        norm_interface(old)
        for old, row in pm.items()
        if row.new_port and legacy_is_access_map_row(row) and norm_interface(old) not in exclude_old_ports
    }
    post_by_mac: Dict[str, List[MacEntry]] = {}
    for e in post_entries:
        post_by_mac.setdefault(e.mac, []).append(e)
    observed_counts: Dict[str, Dict[str, int]] = {}
    for e in pre_entries:
        old = norm_interface(e.port)
        if old not in access_old_ports:
            continue
        candidates = post_by_mac.get(e.mac, [])
        same_vlan = [c for c in candidates if str(c.vlan) == str(e.vlan)] or candidates
        for c in same_vlan:
            actual = norm_interface(c.port)
            if actual:
                port_counts = observed_counts.setdefault(old, {})
                port_counts[actual] = port_counts.get(actual, 0) + 1
    observed: Dict[str, str] = {}
    for old, counts in observed_counts.items():
        if not counts:
            continue
        best_port, best_count = max(counts.items(), key=lambda kv: kv[1])
        tied = [port for port, count in counts.items() if count == best_count]
        if len(tied) == 1:
            observed[old] = best_port
    return observed


class MacExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_mac_helpers_match_legacy_inline_output(self):
        pre = """
Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
 10     aaaa.bbbb.0001    DYNAMIC     Gi1/0/1
 10     aaaa.bbbb.0002    DYNAMIC     Gi1/0/2
 10     aaaa.bbbb.0002    DYNAMIC     Gi1/0/2
 10     aaaa.bbbb.0003    DYNAMIC     Gi1/0/3
 20     aaaa.bbbb.0004    DYNAMIC     Gi1/0/4
 10     aaaa.bbbb.9999    DYNAMIC     Gi1/0/49
 All    ffff.ffff.ffff    STATIC      Drop
"""
        post = """
 10     aaaa.bbbb.0001    DYNAMIC     Gi2/0/1
 10     aaaa.bbbb.0002    DYNAMIC     Gi2/0/9
 20     aaaa.bbbb.0004    DYNAMIC     Gi2/0/7
"""
        port_map = {
            "Gi1/0/1": PortMapRow("Gi1/0/1", "Gi2/0/1", "access", ""),
            "Gi1/0/2": PortMapRow("Gi1/0/2", "Gi2/0/2", "access", ""),
            "Gi1/0/3": PortMapRow("Gi1/0/3", "Gi2/0/3", "access", ""),
            "Gi1/0/4": PortMapRow("Gi1/0/4", "Gi2/0/4", "access", ""),
            "Gi1/0/49": PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", ""),
        }

        self.assertEqual(legacy_count_macs(pre), count_macs(pre))
        self.assertEqual(legacy_norm_mac(" AAaa.BBbb.0001 "), norm_mac(" AAaa.BBbb.0001 "))
        self.assertEqual(legacy_parse_mac_address_table(pre), parse_mac_address_table(pre))
        self.assertEqual(legacy_is_access_map_row(port_map["Gi1/0/1"]), is_access_map_row(port_map["Gi1/0/1"]))
        self.assertEqual(legacy_is_access_map_row(port_map["Gi1/0/49"]), is_access_map_row(port_map["Gi1/0/49"]))
        self.assertEqual(legacy_mac_correlation_rows(pre, post, port_map), mac_correlation_rows(pre, post, port_map))
        self.assertEqual(legacy_mac_expected_present_ports(pre, post, port_map), mac_expected_present_ports(pre, post, port_map))
        self.assertEqual(legacy_observed_mac_local_map(pre, post, port_map), observed_mac_local_map(pre, post, port_map))

    def test_extracted_observed_mac_tie_matches_legacy_inline_output(self):
        pre = " 10     aaaa.bbbb.0001    DYNAMIC     Gi1/0/1\n"
        post = """
 10     aaaa.bbbb.0001    DYNAMIC     Gi2/0/1
 10     aaaa.bbbb.0001    DYNAMIC     Gi2/0/2
"""
        port_map = {"Gi1/0/1": PortMapRow("Gi1/0/1", "Gi2/0/1", "access", "")}

        self.assertEqual(legacy_observed_mac_local_map(pre, post, port_map), observed_mac_local_map(pre, post, port_map))


if __name__ == "__main__":
    unittest.main()
