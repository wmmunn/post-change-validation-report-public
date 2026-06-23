"""Pure STP root parsing and context helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from src.post_change_validation_models import norm_interface


@dataclass
class STPRootRecord:
    vlan: str
    root_id: str
    cost: int
    root_port: str = ""
    raw: str = ""


@dataclass
class STPTopologyComparison:
    pass_items: list[str]
    warn_items: list[str]
    info_items: list[str]



# VLAN0001 32769 0011.2233.4455 4 128.1 P2p Gi1/0/49
STP_ROOT_ROW_BRIDGE_ID_PATTERN = re.compile(r"[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}")

# Pathcost method used is long
STP_SUMMARY_PATH_COST_METHOD_PATTERN = re.compile(r"path\s*cost\s+method\s+used\s+is\s+(short|long)", re.IGNORECASE)

# Pathcost method used is short
STP_SUMMARY_PATHCOST_METHOD_PATTERN = re.compile(r"pathcost\s+method\s+used\s+is\s+(short|long)", re.IGNORECASE)

# spanning-tree pathcost method long
STP_CONFIG_PATHCOST_METHOD_PATTERN = re.compile(r"spanning-tree\s+pathcost\s+method\s+(short|long)", re.IGNORECASE)

# spanning-tree path-cost method long
STP_CONFIG_PATH_COST_METHOD_PATTERN = re.compile(r"spanning-tree\s+path-cost\s+method\s+(short|long)", re.IGNORECASE)

# interface Vlan1
INTERFACE_HEADER_PATTERN = re.compile(r"^interface\s+(.+)$", re.IGNORECASE)

# shutdown
INTERFACE_SHUTDOWN_PATTERN = re.compile(r"(?m)^\s*shutdown\s*$")


def vlan_num(vlan: str) -> int:
    m = re.search(r"(\d+)$", vlan or "")
    return int(m.group(1)) if m else -1


def norm_vlan(vlan: str) -> str:
    n = vlan_num(vlan)
    return f"VLAN{n:04d}" if n >= 0 else (vlan or "").strip()


def parse_stp_root(section: str) -> dict[str, STPRootRecord]:
    """Parse 'show spanning-tree root' into per-VLAN records."""
    out: dict[str, STPRootRecord] = {}
    for raw in section.splitlines():
        line = raw.strip()
        if not line or not line.upper().startswith("VLAN"):
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        vlan = norm_vlan(parts[0])
        if not re.fullmatch(r"\d+", parts[1]) or not STP_ROOT_ROW_BRIDGE_ID_PATTERN.fullmatch(parts[2]):
            continue
        root_id = f"{parts[1]} {parts[2].lower()}"
        try:
            cost = int(parts[3])
        except Exception:
            cost = -1
        root_port = norm_interface(parts[7]) if len(parts) >= 8 else ""
        out[vlan] = STPRootRecord(vlan=vlan, root_id=root_id, cost=cost, root_port=root_port, raw=line)
    return out


def parse_stp_path_cost_method(summary_section: str, running_config: str = "") -> str:
    """Return short/long STP path-cost method when command evidence shows it."""
    text = f"{summary_section or ''}\n{running_config or ''}"
    for pattern in [
        STP_SUMMARY_PATH_COST_METHOD_PATTERN,
        STP_SUMMARY_PATHCOST_METHOD_PATTERN,
        STP_CONFIG_PATHCOST_METHOD_PATTERN,
        STP_CONFIG_PATH_COST_METHOD_PATTERN,
    ]:
        m = pattern.search(text)
        if m:
            return m.group(1).lower()
    return ""


def stp_cost_change_note(
    pre_rec: STPRootRecord,
    post_rec: STPRootRecord,
    pre_method: str,
    post_method: str,
    post_if: Mapping[str, object],
) -> str:
    """Explain retained-root STP cost changes when the logs contain context."""
    notes: list[str] = []
    if pre_method or post_method:
        notes.append(f"STP path-cost method: pre={pre_method or 'not found'}, post={post_method or 'not found'}.")
        if pre_method and post_method and pre_method != post_method:
            notes.append("Path-cost method changed, so numeric costs may not be directly comparable.")

    post_port = post_rec.root_port or ""
    post_status = post_if.get(post_port)
    post_speed = str(getattr(post_status, "speed", "") or "").strip()
    post_type = str(getattr(post_status, "type_", "") or "").strip()
    if post_speed or post_type:
        notes.append(f"Post root port evidence: {post_port} speed={post_speed or 'unknown'} type={post_type or 'unknown'}.")

    if pre_rec.cost == 4 and post_rec.cost == 2000:
        notes.append(
            "Cost change 4 -> 2000 is consistent with retained root/root-port behavior after moving from legacy 1G/short-cost style evidence to a 10G/long-cost scale."
        )
    elif pre_rec.cost != post_rec.cost:
        notes.append("Root and mapped root port are retained; cost-only changes are informational unless a manual STP cost policy was expected.")

    return " ".join(notes)


def interface_block(running_config: str, interface_name: str) -> str:
    wanted = interface_name.strip().lower()
    current: str | None = None
    lines: list[str] = []
    for raw in (running_config or "").splitlines():
        line = raw.rstrip()
        m = INTERFACE_HEADER_PATTERN.match(line.strip())
        if m:
            if current == wanted:
                break
            current = m.group(1).strip().lower()
            lines = []
            continue
        if current == wanted:
            lines.append(line)
    return "\n".join(lines)


def svi_is_shutdown(running_config: str, vlan: str) -> bool:
    n = vlan_num(vlan)
    if n < 0:
        return False
    block = interface_block(running_config, f"Vlan{n}")
    return bool(INTERFACE_SHUTDOWN_PATTERN.search(block))


def access_ports_in_vlan(status: Mapping[str, object], vlan: str) -> int:
    n = vlan_num(vlan)
    if n < 0:
        return 0
    return sum(1 for row in status.values() if re.sub(r"\D", "", str(getattr(row, "vlan", "") or "")) == str(n))


def stp_vlan1_local_root_context(vlan: str, post_running_config: str, post_if: Mapping[str, object]) -> str:
    if vlan != "VLAN0001" or not svi_is_shutdown(post_running_config, vlan):
        return ""
    port_count = access_ports_in_vlan(post_if, vlan)
    if port_count:
        return f"VLAN 1 SVI is shutdown and {port_count} post-change access/status port(s) are assigned to VLAN 1; local-root state is lower risk and should be verified against local VLAN design."
    return "VLAN 1 SVI is shutdown; local-root state is lower risk and should be verified against local VLAN design."


def compare_stp_topology(
    pre_records: Mapping[str, STPRootRecord],
    post_records: Mapping[str, STPRootRecord],
    old_to_new: Mapping[str, str],
    pre_cost_method: str,
    post_cost_method: str,
    post_running_config: str,
    post_if: Mapping[str, object],
    info_vlans: set[str] | None = None,
    info_vlan_notes: Mapping[str, str] | None = None,
) -> STPTopologyComparison:
    pass_items: list[str] = []
    warn_items: list[str] = []
    info_items: list[str] = []
    info_vlans = info_vlans or set()
    info_vlan_notes = info_vlan_notes or {}
    all_vlans = sorted(set(pre_records) | set(post_records), key=vlan_num)
    for vlan in all_vlans:
        a = pre_records.get(vlan)
        b = post_records.get(vlan)
        if a and not b:
            if vlan in info_vlans:
                info_items.append(f"{vlan}: present pre-change but absent post-change. {info_vlan_notes.get(vlan, '')}".strip())
            else:
                warn_items.append(f"{vlan}: present pre-change but missing post-change | pre={a.raw}")
            continue
        if b and not a:
            info_items.append(f"{vlan}: appears post-change only | post={b.raw}")
            continue
        if not a or not b:
            continue

        mapped_pre_port = old_to_new.get(a.root_port, a.root_port) if a.root_port else ""
        post_port = b.root_port or ""
        root_same = a.root_id == b.root_id
        port_same = mapped_pre_port == post_port
        cost_same = a.cost == b.cost
        was_local_root = a.cost == 0 and not a.root_port
        is_local_root = b.cost == 0 and not b.root_port

        if root_same and port_same:
            vlan1_context = stp_vlan1_local_root_context(vlan, post_running_config, post_if) if is_local_root else ""
            if cost_same:
                suffix = f" {vlan1_context}" if vlan1_context else ""
                pass_items.append(f"{vlan}: root unchanged, root port unchanged/mapped ({a.root_port or 'local root'} -> {post_port or 'local root'}).{suffix}")
            else:
                context = stp_cost_change_note(a, b, pre_cost_method, post_cost_method, post_if)
                if vlan1_context:
                    context = f"{context} {vlan1_context}".strip()
                suffix = f" {context}" if context else ""
                pass_items.append(f"{vlan}: root unchanged and root port mapped ({a.root_port or 'local root'} -> {post_port or 'local root'}); cost changed {a.cost} -> {b.cost}.{suffix}")
            continue

        if vlan in info_vlans:
            info_items.append(
                f"{vlan}: STP root/role changed but classified as security isolation/remediation VLAN. "
                f"pre root={a.root_id}, cost={a.cost}, port={a.root_port or 'local root'}; "
                f"post root={b.root_id}, cost={b.cost}, port={post_port or 'local root'}. "
                f"{info_vlan_notes.get(vlan, '')}"
            )
            continue

        if not root_same:
            root_context = ""
            if was_local_root and not is_local_root:
                root_context = " Local switch was root before and is no longer root."
            elif not was_local_root and is_local_root:
                root_context = " Local switch became root post-change."
            vlan1_context = stp_vlan1_local_root_context(vlan, post_running_config, post_if) if is_local_root else ""
            if vlan1_context:
                info_items.append(
                    f"{vlan}: local switch became root post-change, but classified as informational based on VLAN 1 context. "
                    f"pre root={a.root_id}, cost={a.cost}, port={a.root_port or 'local root'}; "
                    f"post root={b.root_id}, cost={b.cost}, port={post_port or 'local root'}. {vlan1_context}"
                )
                continue
            warn_items.append(
                f"{vlan}: root bridge changed. pre root={a.root_id}, cost={a.cost}, port={a.root_port or 'local root'}; "
                f"post root={b.root_id}, cost={b.cost}, port={post_port or 'local root'}.{root_context}"
            )
        elif not port_same:
            warn_items.append(
                f"{vlan}: root bridge unchanged but root port changed unexpectedly. "
                f"pre port={a.root_port or 'local root'} expected post={mapped_pre_port or 'local root'}, actual post={post_port or 'local root'}"
            )
        elif not cost_same:
            context = stp_cost_change_note(a, b, pre_cost_method, post_cost_method, post_if)
            suffix = f" {context}" if context else ""
            info_items.append(f"{vlan}: only STP cost changed {a.cost} -> {b.cost}; root and mapped port are unchanged.{suffix}")

    return STPTopologyComparison(pass_items=pass_items, warn_items=warn_items, info_items=info_items)
