"""Workplace-specific runtime port-map builder (private profile)."""

from __future__ import annotations

import re
from typing import Dict, Set, Tuple

from src.post_change_validation_models import PortMapRow, norm_interface

from src.port_mapping.hardware_macro import (
    evaluate_access_prefix_from_pid,
    parse_stack_member_models_from_inventory,
)

# interface TenGigabitEthernet2/0/1
RUNNING_CONFIG_INTERFACE_PATTERN = re.compile(r"^interface\s+([^\s]+)", re.IGNORECASE | re.MULTILINE)
# interface GigabitEthernet1/0/1
STACK_ACCESS_INTERFACE_PATTERN = re.compile(r"^(Gi|Fi|Te)(\d+)/0/(\d+)$")
# interface TenGigabitEthernet2/1/8
STACK_MODULE_INTERFACE_PATTERN = re.compile(r"^(?:Te|Twe|Fo|Hu)(\d+)/1/\d+$")
# interface GigabitEthernet1/1
STANDALONE_INTERFACE_PATTERN = re.compile(r"^(Fa|Gi|Te)(\d+)/(\d+)$")
# switch 1 provision c9300-48u
SWITCH_PROVISION_PATTERN = re.compile(r"^switch\s+(\d+)\s+provision\s+(\S+)", re.IGNORECASE | re.MULTILINE)


def detect_access_prefix_from_model(model: str) -> str:
    return evaluate_access_prefix_from_pid(model)


def infer_access_prefix_by_member_from_interfaces(running_config: str) -> Dict[str, str]:
    counts: Dict[str, Dict[str, int]] = {}
    for m in RUNNING_CONFIG_INTERFACE_PATTERN.finditer(running_config or ""):
        intf = norm_interface(m.group(1))
        im = STACK_ACCESS_INTERFACE_PATTERN.match(intf)
        if not im:
            continue
        prefix, member, port_s = im.group(1), im.group(2), im.group(3)
        port = int(port_s)
        if 1 <= port <= 48:
            counts.setdefault(member, {}).setdefault(prefix, 0)
            counts[member][prefix] += 1
    result: Dict[str, str] = {}
    for member, fam_counts in counts.items():
        result[member] = max(fam_counts.items(), key=lambda kv: kv[1])[0]
    return result


def infer_standalone_access_from_interfaces(running_config: str) -> Tuple[str, str, Set[int]]:
    counts = infer_standalone_access_units_from_interfaces(running_config)
    if not counts:
        return "", "", set()
    (prefix, unit), ports = max(counts.items(), key=lambda kv: (len(kv[1]), kv[0][0] == "Gi"))
    return prefix, unit, ports


def infer_standalone_access_units_from_interfaces(running_config: str) -> Dict[Tuple[str, str], Set[int]]:
    counts: Dict[Tuple[str, str], Set[int]] = {}
    for m in RUNNING_CONFIG_INTERFACE_PATTERN.finditer(running_config or ""):
        intf = norm_interface(m.group(1))
        im = STANDALONE_INTERFACE_PATTERN.match(intf)
        if not im:
            continue
        prefix, unit, port_s = im.group(1), im.group(2), im.group(3)
        port = int(port_s)
        if unit == "0" or port == 0:
            continue
        counts.setdefault((prefix, unit), set()).add(port)
    return counts


def parse_switch_provision(running_config: str) -> Dict[str, str]:
    members: Dict[str, str] = {}
    for m in SWITCH_PROVISION_PATTERN.finditer(running_config or ""):
        member = m.group(1)
        if member == "0":
            continue
        members[member] = m.group(2)
    return members


def detect_members_from_interfaces(running_config: str) -> Set[str]:
    members: Set[str] = set()
    for m in RUNNING_CONFIG_INTERFACE_PATTERN.finditer(running_config or ""):
        intf = norm_interface(m.group(1))
        im = STACK_ACCESS_INTERFACE_PATTERN.match(intf) or STACK_MODULE_INTERFACE_PATTERN.match(intf)
        if im:
            member = im.group(1)
            if member != "0":
                members.add(member)
    return members


def _build_port_map_from_running_config(
    running_config: str,
    inventory_section: str = "",
) -> Tuple[Dict[str, PortMapRow], str]:
    rows: Dict[str, PortMapRow] = {}
    if not running_config.strip():
        return rows, "No post-change running-config section found."

    provisions = parse_switch_provision(running_config)
    inventory_models = parse_stack_member_models_from_inventory(inventory_section)
    for member, pid in inventory_models.items():
        if member not in provisions:
            provisions[member] = pid
    interface_members = detect_members_from_interfaces(running_config)

    if provisions:
        members = sorted(provisions.keys(), key=lambda x: int(x))
    else:
        members = sorted(interface_members, key=lambda x: int(x))
    if not members:
        standalone_units = infer_standalone_access_units_from_interfaces(running_config)
        if not standalone_units:
            return rows, "Could not detect stack members from running-config."
        sorted_units = sorted(standalone_units.items(), key=lambda kv: (int(kv[0][1]), kv[0][0]))
        first_unit = sorted_units[0][0][1]
        detail_lines = [
            "Profile: standalone industrial switch mapping",
            "Detected IE-style two-part interface numbering",
            "Detected unit(s): " + ", ".join(f"{prefix}{unit}/x ({len(ports)} ports)" for (prefix, unit), ports in sorted_units),
        ]
        cumulative_offset = 0
        for (standalone_prefix, standalone_unit), standalone_ports in sorted_units:
            max_port = max(standalone_ports)
            for port in range(1, max_port + 1):
                new = f"{standalone_prefix}{standalone_unit}/{port}"
                for old_prefix in ("Fa", "Gi"):
                    old = f"{old_prefix}{standalone_unit}/{port}"
                    rows[old] = PortMapRow(
                        old,
                        new,
                        "standalone_industrial",
                        "Auto IE/IE3300 standalone mapping from two-part interface numbering",
                    )
                    flat_old = f"{old_prefix}{first_unit}/{cumulative_offset + port}"
                    rows.setdefault(
                        flat_old,
                        PortMapRow(
                            flat_old,
                            new,
                            "standalone_industrial",
                            "Auto IE/IE3300 flattened legacy chassis mapping to base/expansion banks",
                        ),
                    )
                    legacy_old = f"{old_prefix}0/{cumulative_offset + port}"
                    rows.setdefault(
                        legacy_old,
                        PortMapRow(
                            legacy_old,
                            new,
                            "standalone_industrial",
                            "Auto IE/IE3300 flattened legacy unit-0 alias to base/expansion banks",
                        ),
                    )
            cumulative_offset += max_port
        first_prefix = sorted_units[0][0][0]
        first_max_port = max(sorted_units[0][1])
        for port in range(1, first_max_port + 1):
            new = f"{first_prefix}{first_unit}/{port}"
            for old_prefix in ("Fa", "Gi"):
                old = f"{old_prefix}0/{port}"
                rows[old] = PortMapRow(
                    old,
                    new,
                    "standalone_industrial",
                    "Auto IE/IE3300 legacy unit-0 alias to first two-part interface bank",
                )
        return rows, "\n".join(detail_lines)

    first_member = members[0]
    last_member = members[-1]
    uplink_a = f"Te{first_member}/1/1"
    uplink_b = f"Te{last_member}/1/8"
    stack_size = len(members)

    prefix_by_member = infer_access_prefix_by_member_from_interfaces(running_config)
    detail_lines = [
        "Profile: environment standard refresh mapping",
        f"Detected stack members: {', '.join(members)}",
        f"Detected stack size: {stack_size}",
        f"Standard uplink A target: {uplink_a}",
        f"Standard uplink B target: {uplink_b}",
    ]

    for member in members:
        model = provisions.get(member, "")
        model_prefix = evaluate_access_prefix_from_pid(model)
        interface_prefix = prefix_by_member.get(member)
        if model_prefix in ("Te", "Fi"):
            prefix = model_prefix
            source = "model"
        else:
            prefix = interface_prefix or model_prefix
            source = "interface scan" if interface_prefix else "model/default"
        detail_lines.append(f"switch {member}: model={model or 'unknown'}, access_prefix={prefix} ({source})")
        for port in range(1, 49):
            old = f"Gi{member}/0/{port}"
            new = f"{prefix}{member}/0/{port}"
            rows[old] = PortMapRow(old, new, "access", f"Auto-detected access mapping ({model or 'interface scan'})")

    first_model = provisions.get(first_member, "")
    first_model_prefix = evaluate_access_prefix_from_pid(first_model)
    if first_model_prefix in ("Te", "Fi"):
        first_prefix = first_model_prefix
    else:
        first_prefix = prefix_by_member.get(first_member) or first_model_prefix
    for port in range(1, 49):
        if port in (15, 16):
            continue
        old = f"Gi0/{port}"
        new = f"{first_prefix}{first_member}/0/{port}"
        rows[old] = PortMapRow(old, new, "legacy_access", "Auto legacy Gi0/x access mapping to first stack member")

    for member in members:
        rows[f"Gi{member}/0/49"] = PortMapRow(f"Gi{member}/0/49", uplink_a, "uplink", "Auto standard uplink A mapping Gi*/0/49 -> first-member Te/1/1")
        rows[f"Gi{member}/0/50"] = PortMapRow(f"Gi{member}/0/50", uplink_b, "uplink", "Auto standard uplink B mapping Gi*/0/50 -> last-member Te/1/8")
        rows[f"Gi{member}/0/51"] = PortMapRow(f"Gi{member}/0/51", uplink_a, "uplink", "Auto standard uplink A mapping Gi*/0/51 -> first-member Te/1/1")
        rows[f"Gi{member}/0/52"] = PortMapRow(f"Gi{member}/0/52", uplink_b, "uplink", "Auto standard uplink B mapping Gi*/0/52 -> last-member Te/1/8")

    rows["Gi0/15"] = PortMapRow("Gi0/15", uplink_a, "legacy_uplink", "Auto legacy uplink A mapping Gi0/15 -> standard uplink A")
    rows["Gi0/16"] = PortMapRow("Gi0/16", uplink_b, "legacy_uplink", "Auto legacy uplink B mapping Gi0/16 -> standard uplink B")

    return rows, "\n".join(detail_lines)


class WorkplaceProfile:
    """Build expected port maps from post-change running-config."""

    profile_name = "workplace_environment_standard"

    def build(self, running_config: str, inventory_section: str = "") -> Tuple[Dict[str, PortMapRow], str]:
        return _build_port_map_from_running_config(running_config, inventory_section)
