"""Pure MAC parsing and access-port correlation helpers."""

from __future__ import annotations

import re
from typing import Dict, Mapping, Optional, Set, Tuple

from src.post_change_validation_models import MacEntry, PortMapRow, norm_interface


# 10    aabb.ccdd.eeff    DYNAMIC     GigabitEthernet1/0/3
MAC_ADDRESS_TABLE_ROW_PATTERN = re.compile(
    r"(?P<vlan>\*?\s*\d+|All)\s+(?P<mac>[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\s+(?P<type>\S+)\s+(?P<port>\S+)",
    re.IGNORECASE,
)

# aabb.ccdd.eeff
CISCO_DOTTED_MAC_PATTERN = re.compile(r"\b[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}\b", re.IGNORECASE)


def count_macs(section: str) -> int:
    return len(CISCO_DOTTED_MAC_PATTERN.findall(section))


def norm_mac(mac: str) -> str:
    return (mac or "").strip().lower()


def parse_mac_address_table(section: str) -> list[MacEntry]:
    """Parse common Cisco 'show mac address-table' output.

    The parser intentionally keeps this conservative. It captures rows that
    contain a VLAN, a dotted Cisco MAC address, a type, and a final interface.
    CPU/static/drop/system entries and non-interface destinations are ignored.
    """
    entries: list[MacEntry] = []
    for raw in section.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith(("vlan", "----", "mac address", "total", "legend")):
            continue
        m = MAC_ADDRESS_TABLE_ROW_PATTERN.search(line)
        if not m:
            continue
        port = norm_interface(m.group("port"))
        if not re.match(r"^(Gi|Te|Twe|Fi|Fo|Hu|Po|Ap)\d", port):
            continue
        vlan = re.sub(r"\D", "", m.group("vlan")) or m.group("vlan")
        entries.append(MacEntry(vlan=vlan, mac=norm_mac(m.group("mac")), type_=m.group("type"), port=port, raw=line))
    return entries


def is_access_map_row(row: PortMapRow) -> bool:
    role = (row.role or "").lower()
    old = norm_interface(row.old_port)
    new = norm_interface(row.new_port)
    if "uplink" in role or "trunk" in role or old.startswith("Po") or new.startswith("Po"):
        return False
    # Access ports are switch-member /0/ access ports. This excludes Te*/1/* uplink-module ports.
    if re.match(r"^(Gi|Fi|Te)\d+/0/\d+$", old) and re.match(r"^(Gi|Fi|Te)\d+/0/\d+$", new):
        return True
    # Standalone IE/IE3300 access ports use two-part numbering such as Gi1/1.
    # Ports proven to be uplinks are reclassified before MAC correlation.
    if role == "standalone_industrial" and re.match(r"^(Fa|Gi|Te)\d+/\d+$", old) and re.match(r"^(Fa|Gi|Te)\d+/\d+$", new):
        return True
    return role == "access"


def mac_correlation_rows(
    pre_mac_section: str,
    post_mac_section: str,
    pm: Mapping[str, PortMapRow],
    exclude_old_ports: Optional[Set[str]] = None,
) -> Tuple[list[str], Dict[str, int]]:
    """Return pipe-delimited table rows for access-port MAC correlation.

    Format: status|mac|vlan|pre_port|expected_post_port|actual_post_port|note
    """
    exclude_old_ports = {norm_interface(p) for p in (exclude_old_ports or set())}
    pre_entries = parse_mac_address_table(pre_mac_section)
    post_entries = parse_mac_address_table(post_mac_section)
    access_map = {
        old: row.new_port
        for old, row in pm.items()
        if row.new_port and is_access_map_row(row) and norm_interface(old) not in exclude_old_ports
    }
    access_old_ports = set(access_map)

    # Only local access-port MACs from the old switch. This avoids downstream MACs learned over trunks.
    pre_access = [e for e in pre_entries if e.port in access_old_ports]

    post_by_mac: Dict[str, list[MacEntry]] = {}
    for e in post_entries:
        post_by_mac.setdefault(e.mac, []).append(e)

    rows: list[str] = []
    counts = {"PASS": 0, "MISSING": 0, "MOVED": 0, "DUPLICATE": 0, "TOTAL": 0}
    seen: Set[Tuple[str, str, str]] = set()
    for e in sorted(pre_access, key=lambda x: (x.port, x.vlan, x.mac)):
        key = (e.mac, e.vlan, e.port)
        if key in seen:
            continue
        seen.add(key)
        expected = access_map.get(e.port, "")
        candidates = post_by_mac.get(e.mac, [])
        # Prefer same VLAN when available, but don't fail solely because VLAN field formatting differs.
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


def mac_expected_present_ports(
    pre_mac_section: str,
    post_mac_section: str,
    pm: Mapping[str, PortMapRow],
    exclude_old_ports: Optional[Set[str]] = None,
) -> Dict[str, int]:
    present: Dict[str, int] = {}
    rows, _counts = mac_correlation_rows(pre_mac_section, post_mac_section, pm, exclude_old_ports)
    for row in rows:
        parts = row.split("|")
        if len(parts) < 5 or parts[0] != "PASS":
            continue
        expected_port = parts[4]
        if expected_port:
            present[expected_port] = present.get(expected_port, 0) + 1
    return present


def observed_mac_local_map(
    pre_mac_section: str,
    post_mac_section: str,
    pm: Mapping[str, PortMapRow],
    exclude_old_ports: Optional[Set[str]] = None,
) -> Dict[str, str]:
    """Map pre local access ports to observed post ports using MAC continuity."""
    exclude_old_ports = {norm_interface(p) for p in (exclude_old_ports or set())}
    pre_entries = parse_mac_address_table(pre_mac_section)
    post_entries = parse_mac_address_table(post_mac_section)
    access_old_ports = {
        norm_interface(old)
        for old, row in pm.items()
        if row.new_port and is_access_map_row(row) and norm_interface(old) not in exclude_old_ports
    }
    post_by_mac: Dict[str, list[MacEntry]] = {}
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
