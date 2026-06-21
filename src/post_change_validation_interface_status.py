"""Pure interface-status parsing and comparison helpers for Post Change Validation Tool."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Set

from src.post_change_validation_models import PortMapRow, canonical_interface_name, norm_interface

# interface GigabitEthernet1/0/1
RUNNING_CONFIG_INTERFACE_LINE_RE = re.compile(r"^interface\s+(\S+)", re.IGNORECASE)
#  switchport mode trunk
SWITCHPORT_MODE_TRUNK_RE = re.compile(r"^\s*switchport mode trunk\b", re.IGNORECASE | re.MULTILINE)
#  switchport mode access
SWITCHPORT_MODE_ACCESS_RE = re.compile(r"^\s*switchport mode access\b", re.IGNORECASE | re.MULTILINE)
#  switchport access vlan 100
SWITCHPORT_ACCESS_VLAN_RE = re.compile(r"^\s*switchport access vlan\s+(\S+)", re.IGNORECASE | re.MULTILINE)


@dataclass
class InterfaceStatus:
    port: str
    status: str
    vlan: str = ""
    duplex: str = ""
    speed: str = ""
    type_: str = ""
    raw: str = ""


STATUS_WORDS = {"connected", "notconnect", "disabled", "err-disabled", "inactive", "sfpAbsent", "sfpabsent", "monitoring", "suspended"}

# Gi1/0/1   User Port          connected    100        a-full  a-1000 10/100/1000BaseTX
INTERFACE_STATUS_PORT_PREFIX_RE = re.compile(r"^(Gi|Te|Twe|Fi|Fo|Hu|Po|Ap)\d")


def parse_interface_status(section: str) -> Dict[str, InterfaceStatus]:
    out: Dict[str, InterfaceStatus] = {}
    for raw in section.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lower().startswith(("port ", "---")):
            continue
        parts = line.split()
        if not parts:
            continue
        port = canonical_interface_name(parts[0])
        if not port or not INTERFACE_STATUS_PORT_PREFIX_RE.match(port):
            continue
        status_idx = None
        for i, tok in enumerate(parts[1:], start=1):
            if tok in STATUS_WORDS:
                status_idx = i
                break
        if status_idx is None:
            continue
        status = parts[status_idx]
        vlan = parts[status_idx + 1] if len(parts) > status_idx + 1 else ""
        duplex = parts[status_idx + 2] if len(parts) > status_idx + 2 else ""
        speed = parts[status_idx + 3] if len(parts) > status_idx + 3 else ""
        type_ = " ".join(parts[status_idx + 4:]) if len(parts) > status_idx + 4 else ""
        out[port] = InterfaceStatus(port, status, vlan, duplex, speed, type_, raw=line.strip())
    return out


def parse_running_config_interface_blocks(running_config: str) -> Dict[str, str]:
    blocks: Dict[str, str] = {}
    current_port: str | None = None
    current_lines: list[str] = []
    for raw_line in (running_config or "").splitlines():
        match = RUNNING_CONFIG_INTERFACE_LINE_RE.match(raw_line)
        if match:
            if current_port is not None:
                blocks[current_port] = "\n".join(current_lines).strip()
            current_port = norm_interface(match.group(1))
            current_lines = []
            continue
        if current_port is not None:
            stripped = raw_line.strip()
            if stripped and not raw_line.startswith((" ", "\t")) and not stripped.startswith("!"):
                blocks[current_port] = "\n".join(current_lines).strip()
                current_port = None
                current_lines = []
                continue
            current_lines.append(raw_line)
    if current_port is not None:
        blocks[current_port] = "\n".join(current_lines).strip()
    return blocks


def infer_uncovered_port_role(
    port: str,
    post_status: InterfaceStatus | None,
    config_block: str = "",
    post_trunks: Set[str] | None = None,
) -> str:
    post_trunks = post_trunks or set()
    block = config_block or ""
    if SWITCHPORT_MODE_TRUNK_RE.search(block):
        return "trunk"
    if SWITCHPORT_MODE_ACCESS_RE.search(block) or SWITCHPORT_ACCESS_VLAN_RE.search(block):
        return "access"
    if port in post_trunks:
        return "uplink"
    vlan = (getattr(post_status, "vlan", "") or "").lower()
    if post_status and vlan == "trunk":
        return "trunk"
    if post_status and vlan:
        return "access"
    return "unknown"


def format_uncovered_connected_detail_line(
    port: str,
    post_status: InterfaceStatus | None,
    role: str,
) -> str:
    status_word = getattr(post_status, "status", "unknown") if post_status else "unknown"
    post_evidence = getattr(post_status, "raw", "") if post_status and getattr(post_status, "raw", "") else port
    return f"uncovered -> {port} role={role}: {status_word} | post={post_evidence}"


def build_uncovered_connected_detail_lines(
    ports: list[str],
    post_if: Mapping[str, InterfaceStatus],
    post_running_config: str = "",
    post_trunks: Set[str] | None = None,
) -> list[str]:
    config_blocks = parse_running_config_interface_blocks(post_running_config)
    return [
        format_uncovered_connected_detail_line(
            port,
            post_if.get(port),
            infer_uncovered_port_role(
                port,
                post_if.get(port),
                config_blocks.get(port, ""),
                post_trunks=post_trunks,
            ),
        )
        for port in ports
    ]


@dataclass
class InterfaceStatusComparison:
    connected_pass: list[str] = field(default_factory=list)
    connected_warn: list[str] = field(default_factory=list)
    unchanged_down: int = 0
    uncovered_connected: list[str] = field(default_factory=list)
    post_covered: Set[str] = field(default_factory=set)


def _register_covered_port(covered: Set[str], port: str) -> None:
    canon = canonical_interface_name(port)
    if canon:
        covered.add(canon)


def _covered_ports_from_port_map(port_map: Mapping[str, PortMapRow]) -> Set[str]:
    covered: Set[str] = set()
    for old, row in port_map.items():
        _register_covered_port(covered, old)
        _register_covered_port(covered, row.old_port)
        _register_covered_port(covered, row.new_port)
    return covered


def _is_post_port_covered(
    port: str,
    covered_post_ports: Set[str],
    port_map: Mapping[str, PortMapRow],
) -> bool:
    """Return True when a post-change port is mapped by the port map."""
    canon = canonical_interface_name(port)
    if not canon:
        return False
    if canon in covered_post_ports:
        return True
    for old, row in port_map.items():
        for mapped in (old, row.old_port, row.new_port):
            if mapped and canonical_interface_name(mapped) == canon:
                return True
    return False


def compare_mapped_interface_status(
    pre_if: Mapping[str, Any],
    post_if: Mapping[str, Any],
    port_map: Mapping[str, PortMapRow],
    observed_neighbor_ports: Mapping[str, str] | None = None,
    observed_mac_ports: Mapping[str, str] | None = None,
) -> InterfaceStatusComparison:
    observed_neighbor_ports = observed_neighbor_ports or {}
    observed_mac_ports = observed_mac_ports or {}
    result = InterfaceStatusComparison()
    covered_post_ports = _covered_ports_from_port_map(port_map)

    for old, row in sorted(port_map.items(), key=lambda kv: kv[0]):
        new = row.new_port
        pre_status = pre_if.get(old)
        post_status = post_if.get(new) if new else None
        if new:
            result.post_covered.add(new)
            _register_covered_port(covered_post_ports, new)
        if not pre_status:
            continue
        if not post_status:
            if pre_status.status == "connected":
                note = f" | note={row.note}" if row.note else ""
                observed = observed_neighbor_ports.get(old) or observed_mac_ports.get(old)
                observed_status = post_if.get(observed) if observed else None
                if observed and observed != new and observed_status and observed_status.status == "connected":
                    result.post_covered.add(observed)
                    _register_covered_port(covered_post_ports, observed)
                    result.connected_pass.append(
                        f"{old} -> {observed} role={row.role}: remained connected on observed post port; "
                        f"inferred map expected {new or '(no mapped post port)'} | pre={pre_status.raw} | post={observed_status.raw}"
                    )
                else:
                    result.connected_warn.append(
                        f"{old} -> {new or '(no mapped post port)'} role={row.role}: was connected before, post port not found | pre={pre_status.raw}{note}"
                    )
            continue
        if pre_status.status == "connected" and post_status.status == "connected":
            result.connected_pass.append(f"{old} -> {new} role={row.role}: remained connected | pre={pre_status.raw} | post={post_status.raw}")
        elif pre_status.status == "connected" and post_status.status != "connected":
            observed = observed_neighbor_ports.get(old) or observed_mac_ports.get(old)
            observed_status = post_if.get(observed) if observed else None
            if observed and observed != new and observed_status and observed_status.status == "connected":
                result.post_covered.add(observed)
                _register_covered_port(covered_post_ports, observed)
                result.connected_pass.append(
                    f"{old} -> {observed} role={row.role}: remained connected on observed post port; "
                    f"inferred map expected {new} | pre={pre_status.raw} | post={observed_status.raw}"
                )
            else:
                note = f" | note={row.note}" if row.note else ""
                result.connected_warn.append(
                    f"{old} -> {new} role={row.role}: was connected before, now {post_status.status} | pre={pre_status.raw} | post={post_status.raw}{note}"
                )
        elif pre_status.status != "connected" and post_status.status != "connected":
            result.unchanged_down += 1

    result.uncovered_connected = sorted(
        port
        for port, status in post_if.items()
        if status.status == "connected"
        and not port.startswith("Ap")
        and not _is_post_port_covered(port, covered_post_ports, port_map)
    )
    return result
