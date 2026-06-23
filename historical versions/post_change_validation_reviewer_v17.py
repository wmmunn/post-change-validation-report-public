#!/usr/bin/env python3
"""
Post-Change Validation Reviewer v17
Offline GUI tool for comparing pre/post Cisco switch refresh command logs.

Key behavior:
- Auto-detects environment-specific port mapping from post-change running-config by default
- Optional port map CSV override: old_port,new_port,role,note
- Built-in environment profile supports legacy Gi0/15/Gi0/16, Gi*/0/25/27 for 24-port layouts, Gi*/0/49/50, Gi*/0/51/52 uplinks and stack-aware uplink placement
- Fixes false stack member 0 detection from management interfaces such as Gi0/0
- Interface status comparison uses port map
- Trunk comparison uses port map
- CDP/LLDP comparison uses structured neighbor objects and mapped local interface
- Suppresses noisy per-port unchanged-notconnect rows; summarizes instead
- Exports HTML and PDF reports
- v10: context-aware STP root analysis; VLAN 4 isolation/remediation root changes are INFO, not WARN
- v11: adds Gi*/0/49 -> uplink A and Gi*/0/50 -> uplink B environment mapping
- v12: adds 24-port legacy uplink mapping Gi*/0/25 -> uplink A and Gi*/0/27 -> uplink B
- v13: adds gateway 0/1 neighbor-pair uplink inference; lower old port -> uplink A, higher old port -> uplink B
- v14: adds TenGigabitEthernet Te*/0/* access-port awareness
- v15: adds explicit model-based access detection, including c9300-24ux -> Te*/0/* access ports
- v16: fixes over-aggressive 24-port uplink mapping; 25/27 are only uplinks when trunk/gateway evidence supports it, and observed post-change neighbor ports can override default uplink targets
- v17: strengthens observed CDP/LLDP uplink overrides; same remote port + gateway/uplink evidence can override default stack uplink target even when neighbor names differ/truncate

PDF export requires: pip install reportlab
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import os
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "Post-Change Validation Reviewer"
APP_VERSION = "0.17"

# ----------------------------- data models -----------------------------

@dataclass
class Finding:
    severity: str
    category: str
    finding: str
    detail: str = ""

@dataclass
class PortMapRow:
    old_port: str
    new_port: str
    role: str = ""
    note: str = ""

@dataclass(frozen=True)
class NeighborRecord:
    protocol: str
    neighbor: str
    local_interface: str
    remote_interface: str = "unknown"
    platform: str = ""
    capability: str = ""
    raw: str = ""

@dataclass
class InterfaceStatus:
    port: str
    status: str
    vlan: str = ""
    duplex: str = ""
    speed: str = ""
    type_: str = ""
    raw: str = ""

# ----------------------------- normalization -----------------------------

INT_PREFIXES = {
    "gi": "Gi", "gig": "Gi", "gigabit": "Gi", "gigabitethernet": "Gi",
    "te": "Te", "ten": "Te", "twe": "Twe", "twentyfive": "Twe", "twentyfivegigabitethernet": "Twe",
    "fi": "Fi", "five": "Fi", "fivegigabit": "Fi", "fivegigabitethernet": "Fi",
    "fo": "Fo", "forty": "Fo", "fortygigabitethernet": "Fo",
    "hu": "Hu", "hundred": "Hu", "hundredgigabitethernet": "Hu",
    "po": "Po", "port-channel": "Po", "portchannel": "Po",
    "ap": "Ap", "app": "Ap",
}

INT_RE = re.compile(r"\b(?P<prefix>Gi|Gig|GigabitEthernet|Te|Ten|TenGigabitEthernet|Twe|TwentyFiveGigE|TwentyFiveGigabitEthernet|Fi|FiveGigabitEthernet|Fo|FortyGigabitEthernet|Hu|HundredGigE|Po|Port-channel|PortChannel|Ap)\s*(?P<num>\d+(?:/\d+){1,3})\b", re.I)


def norm_interface(s: str) -> str:
    if not s:
        return ""
    s = s.strip().replace("Ethernet", "Ethernet")
    m = INT_RE.search(s)
    if not m:
        # common already-short no-space forms
        m2 = re.search(r"\b(Gi|Te|Twe|Fi|Fo|Hu|Po|Ap)(\d+(?:/\d+){1,3})\b", s, re.I)
        if not m2:
            return s.strip()
        prefix = m2.group(1).lower()
        num = m2.group(2)
    else:
        prefix = m.group("prefix").lower()
        num = m.group("num")
    prefix = prefix.replace("gigabitethernet", "gi").replace("tengigabitethernet", "te")
    prefix = prefix.replace("fivegigabitethernet", "fi").replace("twentyfivegige", "twe").replace("twentyfivegigabitethernet", "twe")
    prefix = prefix.replace("fortygigabitethernet", "fo").replace("hundredgige", "hu")
    prefix = INT_PREFIXES.get(prefix, prefix[:2].capitalize())
    return f"{prefix}{num}"


def find_first_interface(text: str) -> str:
    m = INT_RE.search(text or "")
    return norm_interface(m.group(0)) if m else ""


def neighbor_key(rec: NeighborRecord, port_map_old_to_new: Dict[str, str]) -> Tuple[str, str]:
    local = norm_interface(rec.local_interface)
    local = port_map_old_to_new.get(local, local)
    remote = norm_interface(rec.remote_interface) if rec.remote_interface != "unknown" else "unknown"
    return (local, remote)

# ----------------------------- command splitting -----------------------------

COMMAND_ALIASES = {
    "show int status": "show interfaces status",
    "show interfaces status": "show interfaces status",
    "show spanning-tree root": "show spanning-tree root",
    "show cdp neighbor": "show cdp neighbors",
    "show cdp neighbors": "show cdp neighbors",
    "show lldp neighbor": "show lldp neighbors",
    "show lldp neighbors": "show lldp neighbors",
    "show int trunk": "show interfaces trunk",
    "show interfaces trunk": "show interfaces trunk",
    "show mac address-table": "show mac address-table",
    "show log": "show logging",
    "show logging": "show logging",
    "show running-config": "show running-config",
    "show switch detail": "show switch detail",
    "show dot1x all summary": "show dot1x all summary",
}

COMMAND_PATTERNS = sorted(COMMAND_ALIASES.keys(), key=len, reverse=True)


def canonical_command(cmd: str) -> str:
    cmd = re.sub(r"\s*\|.*$", "", cmd.strip().lower())
    cmd = re.sub(r"\s+", " ", cmd)
    return COMMAND_ALIASES.get(cmd, cmd)


def normalize_command_line(line: str) -> Optional[str]:
    """Return canonical command from a raw log line.

    v5 was too strict and only matched lines that started directly with
    "show ...". Real SecureCRT/PuTTY logs commonly contain prompts such
    as "switchname#show int status", which caused zero command sections.
    """
    cleaned = line.strip()
    # Remove common IOS/NX-style prompt text before # or >.
    cleaned = re.sub(r"^[\w.()/: -]+[#>]\s*", "", cleaned)
    cleaned = cleaned.strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    base = cleaned.split("|")[0].strip()
    for pattern in COMMAND_PATTERNS:
        if base == pattern or base.startswith(pattern + " "):
            return COMMAND_ALIASES[pattern]
    return None


def split_sections(text: str) -> Dict[str, str]:
    sections: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in text.splitlines():
        cmd = normalize_command_line(line)
        if cmd:
            current = cmd
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line.rstrip("\n"))
    return {k: "\n".join(v).strip("\n") for k, v in sections.items()}

# ----------------------------- parsers -----------------------------

STATUS_WORDS = {"connected", "notconnect", "disabled", "err-disabled", "inactive", "sfpAbsent", "sfpabsent", "monitoring", "suspended"}


def parse_interface_status(section: str) -> Dict[str, InterfaceStatus]:
    out: Dict[str, InterfaceStatus] = {}
    for raw in section.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lower().startswith(("port ", "---")):
            continue
        # Port field is first token; Description may contain spaces until status token.
        parts = line.split()
        if not parts:
            continue
        port = norm_interface(parts[0])
        if not re.match(r"^(Gi|Te|Twe|Fi|Fo|Hu|Po|Ap)\d", port):
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


def parse_trunks(section: str) -> Set[str]:
    trunks: Set[str] = set()
    in_port_section = False
    for line in section.splitlines():
        if re.match(r"^Port\s+Mode\s+Encapsulation\s+Status", line, re.I):
            in_port_section = True
            continue
        if in_port_section:
            if not line.strip():
                continue
            if re.match(r"^Port\s+Vlans", line, re.I):
                break
            parts = line.split()
            if parts:
                p = norm_interface(parts[0])
                if re.match(r"^(Gi|Te|Twe|Fi|Fo|Hu|Po)\d", p):
                    trunks.add(p)
    # fallback: first interface token on each trunk-ish line
    if not trunks:
        for line in section.splitlines():
            if "trunk" in line.lower():
                p = find_first_interface(line)
                if p:
                    trunks.add(p)
    return trunks


def clean_neighbor_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\s+", " ", name)
    return name


def parse_cdp_neighbors(section: str) -> List[NeighborRecord]:
    records: List[NeighborRecord] = []
    pending_device = ""

    for raw in section.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith(("device id", "capability", "total", "---")):
            continue

        ints = list(INT_RE.finditer(line))

        # CDP often wraps long Device IDs onto their own line. Save the device
        # name and combine it with the next row that starts with interface data.
        if len(ints) < 2:
            if not find_first_interface(line) and not re.search(r"\b\d+\b", line):
                pending_device = clean_neighbor_name(line)
            continue

        local_m = ints[0]
        remote_m = ints[-1]
        before_local = line[:local_m.start()].strip()
        neighbor = clean_neighbor_name(before_local or pending_device or "unknown")
        pending_device = ""

        local = norm_interface(local_m.group(0))
        remote = norm_interface(remote_m.group(0))
        between = line[local_m.end():remote_m.start()].strip()
        toks = between.split()
        platform = toks[-1] if toks else ""
        cap_tokens = [t for t in toks if re.fullmatch(r"[A-Z,]+", t)]
        cap = " ".join(cap_tokens)
        records.append(NeighborRecord("cdp", neighbor, local, remote, platform, cap, raw=line))
    return records


def parse_lldp_neighbors(section: str) -> List[NeighborRecord]:
    records: List[NeighborRecord] = []
    pending_device = ""

    for raw in section.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith(("device id", "local intf", "capability", "total", "---")):
            continue

        ints = list(INT_RE.finditer(line))
        if len(ints) < 2:
            # LLDP can also wrap long Device IDs.
            if not find_first_interface(line):
                pending_device = clean_neighbor_name(line)
            continue

        local_m = ints[0]
        remote_m = ints[-1]
        before_local = line[:local_m.start()].strip()
        neighbor = clean_neighbor_name(before_local or pending_device or "unknown")
        pending_device = ""

        local = norm_interface(local_m.group(0))
        remote = norm_interface(remote_m.group(0))
        middle = line[local_m.end():remote_m.start()].strip()
        toks = middle.split()
        cap = " ".join(t for t in toks if re.search(r"[A-Za-z]", t))
        records.append(NeighborRecord("lldp", neighbor, local, remote, capability=cap, raw=line))
    return records


def count_macs(section: str) -> int:
    return len(re.findall(r"\b[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}\b", section, re.I))

@dataclass
class STPRootRecord:
    vlan: str
    root_id: str
    cost: int
    root_port: str = ""
    raw: str = ""


def vlan_num(vlan: str) -> int:
    m = re.search(r"(\d+)$", vlan or "")
    return int(m.group(1)) if m else -1


def norm_vlan(vlan: str) -> str:
    n = vlan_num(vlan)
    return f"VLAN{n:04d}" if n >= 0 else (vlan or "").strip()


def parse_stp_root(section: str) -> Dict[str, STPRootRecord]:
    """Parse 'show spanning-tree root' into per-VLAN records."""
    out: Dict[str, STPRootRecord] = {}
    for raw in section.splitlines():
        line = raw.strip()
        if not line or not line.upper().startswith("VLAN"):
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        vlan = norm_vlan(parts[0])
        if not re.fullmatch(r"\d+", parts[1]) or not re.fullmatch(r"[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}", parts[2]):
            continue
        root_id = f"{parts[1]} {parts[2].lower()}"
        try:
            cost = int(parts[3])
        except Exception:
            cost = -1
        root_port = norm_interface(parts[7]) if len(parts) >= 8 else ""
        out[vlan] = STPRootRecord(vlan=vlan, root_id=root_id, cost=cost, root_port=root_port, raw=line)
    return out


STP_INFO_VLANS = {"VLAN0004"}
STP_INFO_VLAN_NOTES = {
    "VLAN0004": "VLAN 4 is classified in this environment as a security isolation/remediation VLAN; root changes are informational unless trunk/forwarding reachability is also broken."
}

# ----------------------------- port map -----------------------------


def detect_access_prefix_from_model(model: str) -> str:
    """Return the environment access-port prefix implied by a provisioned model.

    This is intentionally environment-specific, not universal Cisco behavior.
    The post-change running-config may contain lines such as:

        switch 1 provision c9300-24ux
        switch 1 provision c9300-48un

    In this refresh workflow, c9300-24ux access ports are TenGigabitEthernet
    in the X/0/Y access-port space, while c9300-48un access ports are
    FiveGigabitEthernet. Unknown models fall back to Gi unless interface-block
    evidence overrides this elsewhere.
    """
    m = (model or "").strip().lower()

    # Strong explicit model mappings seen in this environment.
    # c9300-24ux uses TeX/0/Y access interfaces.
    if "c9300-24ux" in m or "c9300-24uxb" in m:
        return "Te"

    # c9300-48un uses FiX/0/Y access interfaces.
    if "c9300-48un" in m:
        return "Fi"

    # Other known multi-gig Catalyst 9300 variants commonly use Fi.
    if any(token in m for token in ["uxm", "uxg", "48hx"]):
        return "Fi"

    # Other known 10G access variants, if encountered.
    if any(token in m for token in ["48uxm"]):
        return "Te"

    return "Gi"


def infer_access_prefix_by_member_from_interfaces(run_cfg: str) -> Dict[str, str]:
    """Infer access-port family per stack member from interface blocks.

    Example interface blocks:
      interface GigabitEthernet1/0/1  -> Gi member 1
      interface FiveGigabitEthernet3/0/12 -> Fi member 3
      interface TenGigabitEthernet1/0/12 -> Te member 1
    """
    counts: Dict[str, Dict[str, int]] = {}
    for m in re.finditer(r"^interface\s+([^\s]+)", run_cfg or "", re.I | re.M):
        intf = norm_interface(m.group(1))
        # Access ports are the /0/ slot. In this environment they may be
        # Gi, Fi, or Te depending on the Catalyst model. Te*/1/* is handled
        # separately as uplink/module space and must not be confused with
        # Te*/0/* access ports.
        im = re.match(r"^(Gi|Fi|Te)(\d+)/0/(\d+)$", intf)
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


def parse_switch_provision(run_cfg: str) -> Dict[str, str]:
    """Return stack member -> provisioned model from running-config.

    Member 0 is intentionally ignored. Interfaces such as Gi0/0 are usually
    management-side interfaces and are not stack members.
    """
    members: Dict[str, str] = {}
    for m in re.finditer(r"^switch\s+(\d+)\s+provision\s+(\S+)", run_cfg or "", re.I | re.M):
        member = m.group(1)
        if member == "0":
            continue
        members[member] = m.group(2)
    return members


def detect_members_from_interfaces(run_cfg: str) -> Set[str]:
    """Infer stack members from switchport-shaped interfaces only.

    This deliberately ignores member 0 and management-style interfaces like
    Gi0/0 / GigabitEthernet0/0. Valid stack access/uplink interfaces in this
    workflow look like Gi1/0/1, Fi2/0/24, Te5/1/8, etc.
    """
    members: Set[str] = set()
    for m in re.finditer(r"^interface\s+([^\s]+)", run_cfg or "", re.I | re.M):
        intf = norm_interface(m.group(1))
        im = re.match(r"^(?:Gi|Fi|Te)(\d+)/0/\d+$", intf) or re.match(r"^(?:Te|Twe|Fo|Hu)(\d+)/1/\d+$", intf)
        if im:
            member = im.group(1)
            if member != "0":
                members.add(member)
    return members


def auto_build_port_map_from_running_config(run_cfg: str) -> Tuple[Dict[str, PortMapRow], str]:
    """Auto-build environment-specific refresh port maps from post running-config.

    This is intentionally not generic Cisco behavior. It encodes the standard
    refresh conventions used in this environment:

      Access ports:
        old GiX/0/1-48 -> new GiX/0/1-48, FiX/0/1-48, or TeX/0/1-48, detected per member
        legacy old Gi0/1-48 -> new first-member access port, except 15/16

      Uplinks:
        old GiX/0/25 and GiX/0/27 are 24-port uplink A/B candidates
        old GiX/0/49 and GiX/0/50 are uplink A/B candidates
        old GiX/0/51 and GiX/0/52 are uplink A/B candidates
        legacy old Gi0/15 and Gi0/16 are uplink A/B candidates

      New uplink placement:
        single switch: uplink A -> Te1/1/1, uplink B -> Te1/1/8
        stack:         uplink A -> Te<first member>/1/1,
                       uplink B -> Te<last member>/1/8

    Manual CSV remains available as an override for nonstandard migrations.
    """
    rows: Dict[str, PortMapRow] = {}
    if not run_cfg.strip():
        return rows, "No post-change running-config section found."

    provisions = parse_switch_provision(run_cfg)
    interface_members = detect_members_from_interfaces(run_cfg)

    # Prefer explicit switch provision lines when present. They are the most
    # authoritative source for stack membership. Interface-derived detection is
    # only a fallback for sparse configs that lack provision statements.
    if provisions:
        members = sorted(provisions.keys(), key=lambda x: int(x))
    else:
        members = sorted(interface_members, key=lambda x: int(x))
    if not members:
        return rows, "Could not detect stack members from running-config."

    first_member = members[0]
    last_member = members[-1]
    uplink_a = f"Te{first_member}/1/1"
    uplink_b = f"Te{last_member}/1/8"
    stack_size = len(members)

    prefix_by_member = infer_access_prefix_by_member_from_interfaces(run_cfg)
    detail_lines = [
        "Profile: environment standard refresh mapping",
        f"Detected stack members: {', '.join(members)}",
        f"Detected stack size: {stack_size}",
        f"Standard uplink A target: {uplink_a}",
        f"Standard uplink B target: {uplink_b}",
    ]

    # Access ports for normal stack-member style old interfaces.
    # Note: Te is valid here only as TeX/0/Y access space. Uplink/module
    # ports remain TeX/1/Y and are mapped separately below.
    for member in members:
        model = provisions.get(member, "")
        model_prefix = detect_access_prefix_from_model(model)
        interface_prefix = prefix_by_member.get(member)
        # Strong known model mappings win; otherwise interface evidence is preferred.
        if (model or "").lower().startswith("c9300-24ux") or (model or "").lower().startswith("c9300-48un"):
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

    # Legacy single-switch access style old interfaces: Gi0/x.
    # Preserve the known legacy uplink ports 15/16 for uplink mapping below.
    first_model = provisions.get(first_member, "")
    first_model_prefix = detect_access_prefix_from_model(first_model)
    if (first_model or "").lower().startswith("c9300-24ux") or (first_model or "").lower().startswith("c9300-48un"):
        first_prefix = first_model_prefix
    else:
        first_prefix = prefix_by_member.get(first_member) or first_model_prefix
    for port in range(1, 49):
        if port in (15, 16):
            continue
        old = f"Gi0/{port}"
        new = f"{first_prefix}{first_member}/0/{port}"
        rows[old] = PortMapRow(old, new, "legacy_access", "Auto legacy Gi0/x access mapping to first stack member")

    # Environment-standard uplink candidates. Map to the calculated target
    # uplinks, not necessarily the same member number as the old port.
    for member in members:
        # Environment-standard uplink variants seen in refreshes:
        # - GiX/0/49 + GiX/0/52 on some older 48-port layouts
        # - GiX/0/51 + GiX/0/52 on other older 48-port layouts
        # - GiX/0/49 + GiX/0/50 is also supported as a paired convention
        # v16: GiX/0/25 + GiX/0/27 are only promoted to uplinks later if
        # pre-change trunk/gateway evidence supports it.
        rows[f"Gi{member}/0/49"] = PortMapRow(f"Gi{member}/0/49", uplink_a, "uplink", "Auto standard uplink A mapping Gi*/0/49 -> first-member Te/1/1")
        rows[f"Gi{member}/0/50"] = PortMapRow(f"Gi{member}/0/50", uplink_b, "uplink", "Auto standard uplink B mapping Gi*/0/50 -> last-member Te/1/8")
        rows[f"Gi{member}/0/51"] = PortMapRow(f"Gi{member}/0/51", uplink_a, "uplink", "Auto standard uplink A mapping Gi*/0/51 -> first-member Te/1/1")
        rows[f"Gi{member}/0/52"] = PortMapRow(f"Gi{member}/0/52", uplink_b, "uplink", "Auto standard uplink B mapping Gi*/0/52 -> last-member Te/1/8")

    # Legacy 2960-style uplinks used in this environment.
    rows["Gi0/15"] = PortMapRow("Gi0/15", uplink_a, "legacy_uplink", "Auto legacy uplink A mapping Gi0/15 -> standard uplink A")
    rows["Gi0/16"] = PortMapRow("Gi0/16", uplink_b, "legacy_uplink", "Auto legacy uplink B mapping Gi0/16 -> standard uplink B")

    return rows, "\n".join(detail_lines)

def load_port_map(path: str) -> Dict[str, PortMapRow]:
    rows: Dict[str, PortMapRow] = {}
    if not path:
        return rows
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            old = norm_interface(r.get("old_port", ""))
            new = norm_interface(r.get("new_port", ""))
            if old:
                rows[old] = PortMapRow(old, new, (r.get("role", "") or "").strip(), (r.get("note", "") or "").strip())
    return rows


def interface_sort_key(intf: str) -> Tuple[int, int, int, int, str]:
    """Sort interfaces numerically where possible."""
    n = norm_interface(intf)
    m = re.match(r"^(Gi|Fi|Te|Twe|Fo|Hu)(\d+)(?:/(\d+))?(?:/(\d+))?$", n)
    if not m:
        return (9999, 9999, 9999, 9999, n)
    nums = [int(x) if x is not None else 0 for x in m.groups()[1:]]
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2], 0, n)


def gateway_pair_key(name: str) -> Optional[Tuple[str, str]]:
    """Return (base_key, pair_side) for environment gateway 0/1 neighbor names.

    Examples:
      eorwdw-wl0-gw.net.example.com -> (eorwdw-wlX-gw.net.example.com, "0")
      eorwdw-wl1-gw.net.example.com -> (eorwdw-wlX-gw.net.example.com, "1")

    This intentionally handles the environment convention where gateway pairs
    are named with a 0/1 immediately before '-gw'.
    """
    n = (name or "").strip().lower()
    m = re.search(r"^(.*?)([01])(-gw\b.*)$", n, re.I)
    if not m:
        return None
    return (m.group(1) + "X" + m.group(3), m.group(2))


def standard_uplink_targets_from_map(pm: Dict[str, PortMapRow]) -> Tuple[str, str]:
    """Find the environment standard uplink A/B targets from existing map rows."""
    a = ""
    b = ""
    for row in pm.values():
        note = (row.note or "").lower()
        old = norm_interface(row.old_port)
        if not a and ("uplink a" in note or old in {"Gi0/15"}):
            a = row.new_port
        if not b and ("uplink b" in note or old in {"Gi0/16"}):
            b = row.new_port
    # fallback for single-switch defaults if map was manually minimal
    return (a or "Te1/1/1", b or "Te1/1/8")


def infer_gateway_pair_uplink_mappings(pre_sections: Dict[str, str], pm: Dict[str, PortMapRow]) -> List[str]:
    """Infer uplink mappings from pre-change gateway 0/1 neighbor pairs.

    Environment rule:
      If a gateway 0/1 pair is detected on two old local interfaces, the lower
      old interface number maps to standard uplink A and the higher old
      interface number maps to standard uplink B.

    This augments/overrides access mappings for those old ports and makes CDP,
    LLDP, interface-status, and trunk comparisons align to the actual refresh
    standard without enumerating every historical uplink pair.
    """
    uplink_a, uplink_b = standard_uplink_targets_from_map(pm)
    if not uplink_a or not uplink_b:
        return []

    recs: List[NeighborRecord] = []
    recs.extend(parse_cdp_neighbors(pre_sections.get("show cdp neighbors", "")))
    recs.extend(parse_lldp_neighbors(pre_sections.get("show lldp neighbors", "")))

    groups: Dict[str, List[NeighborRecord]] = {}
    for r in recs:
        pair = gateway_pair_key(r.neighbor)
        if not pair:
            continue
        base, side = pair
        local = norm_interface(r.local_interface)
        # Only infer from old copper/uplink-style Gi interfaces.
        if not re.match(r"^Gi(?:0/\d+|\d+/0/\d+)$", local):
            continue
        groups.setdefault(base, []).append(r)

    inferred: List[str] = []
    seen_pairs: Set[Tuple[str, str]] = set()
    for base, items in sorted(groups.items()):
        # Unique by local interface, only useful when at least two distinct ports exist.
        by_local: Dict[str, NeighborRecord] = {norm_interface(i.local_interface): i for i in items}
        locals_sorted = sorted(by_local.keys(), key=interface_sort_key)
        if len(locals_sorted) < 2:
            continue
        low = locals_sorted[0]
        high = locals_sorted[-1]
        if (low, high) in seen_pairs:
            continue
        seen_pairs.add((low, high))

        # Avoid nonsensical inference if both are the same or already map to the same target.
        if low == high:
            continue

        pm[low] = PortMapRow(
            low,
            uplink_a,
            "inferred_gateway_uplink",
            f"v13 inferred gateway 0/1 pair: lower old interface -> uplink A ({uplink_a})",
        )
        pm[high] = PortMapRow(
            high,
            uplink_b,
            "inferred_gateway_uplink",
            f"v13 inferred gateway 0/1 pair: higher old interface -> uplink B ({uplink_b})",
        )
        low_name = by_local[low].neighbor
        high_name = by_local[high].neighbor
        inferred.append(f"{low} ({low_name}) -> {uplink_a}; {high} ({high_name}) -> {uplink_b}")

    return inferred



def infer_trunk_uplink_mappings(pre_sections: Dict[str, str], pm: Dict[str, PortMapRow]) -> List[str]:
    """Infer legacy 24-port uplinks only from actual pre-change trunk evidence."""
    uplink_a, uplink_b = standard_uplink_targets_from_map(pm)
    pre_trunks = sorted(parse_trunks(pre_sections.get("show interfaces trunk", "")), key=interface_sort_key)
    candidates = [norm_interface(p) for p in pre_trunks if re.match(r"^Gi\d+/0/(?:25|27)$", norm_interface(p))]
    if len(candidates) < 2:
        return []
    by_member: Dict[str, List[str]] = {}
    for p in candidates:
        m = re.match(r"^Gi(\d+)/0/(\d+)$", p)
        if m:
            by_member.setdefault(m.group(1), []).append(p)
    inferred: List[str] = []
    for member, ports in sorted(by_member.items(), key=lambda kv: int(kv[0])):
        ports = sorted(set(ports), key=interface_sort_key)
        if len(ports) < 2:
            continue
        low, high = ports[0], ports[-1]
        pm[low] = PortMapRow(low, uplink_a, "legacy_24port_uplink", f"v16 inferred from pre-change trunk table: lower 24-port trunk -> uplink A ({uplink_a})")
        pm[high] = PortMapRow(high, uplink_b, "legacy_24port_uplink", f"v16 inferred from pre-change trunk table: higher 24-port trunk -> uplink B ({uplink_b})")
        inferred.append(f"{low} -> {uplink_a}; {high} -> {uplink_b}")
    return inferred


def looks_like_uplink_neighbor(rec: NeighborRecord) -> bool:
    text = f"{rec.neighbor} {rec.platform} {rec.capability} {rec.raw}".lower()
    return bool(re.search(r"-gw\b|\bgw\b|gateway|c9500|c9[0-9]{3}|router", text))


def looks_like_new_uplink_interface(port: str) -> bool:
    """Return True for expected post-change uplink/module ports, not access ports.

    TeX/1/Y is the normal uplink-module shape in this environment. We also
    allow Twe/Fo/Hu module ports for future-proofing. TeX/0/Y access ports are
    deliberately excluded.
    """
    p = norm_interface(port)
    return bool(re.match(r"^(?:Te|Twe|Fo|Hu)\d+/1/\d+$", p))


def neighbor_names_compatible(a: str, b: str) -> bool:
    """Loose comparison for CDP/LLDP names that may be wrapped/truncated.

    Prefer exact matches, but allow suffix/substring matches because long CDP
    device IDs can wrap or be partially captured in real command logs.
    """
    aa = clean_neighbor_name(a).lower()
    bb = clean_neighbor_name(b).lower()
    if not aa or not bb:
        return False
    if aa == bb:
        return True
    if aa in bb or bb in aa:
        return True
    # Compare a compact form to handle odd spacing/wrapping artifacts.
    ac = re.sub(r"[^a-z0-9]", "", aa)
    bc = re.sub(r"[^a-z0-9]", "", bb)
    return bool(ac and bc and (ac in bc or bc in ac))


def apply_observed_neighbor_port_overrides(pre_sections: Dict[str, str], post_sections: Dict[str, str], pm: Dict[str, PortMapRow]) -> List[str]:
    """Trust observed post-change CDP/LLDP neighbor ports over assumed uplink targets.

    v17 strengthens v16: default environment uplink placement is only a starting
    assumption. If the same gateway/device is seen post-change with the same
    remote port on a Te*/1/* uplink, use the observed post local port. This
    handles one-off exceptions such as old Gi1/0/52 mapping to Te2/1/1 instead
    of the standard Te2/1/8.
    """
    pre_recs: List[NeighborRecord] = []
    post_recs: List[NeighborRecord] = []
    for parser, section in [(parse_cdp_neighbors, "show cdp neighbors"), (parse_lldp_neighbors, "show lldp neighbors")]:
        pre_recs.extend(parser(pre_sections.get(section, "")))
        post_recs.extend(parser(post_sections.get(section, "")))

    post_by_neighbor_remote: Dict[Tuple[str, str], List[NeighborRecord]] = {}
    post_by_remote: Dict[str, List[NeighborRecord]] = {}
    for r in post_recs:
        remote = norm_interface(r.remote_interface)
        key = (clean_neighbor_name(r.neighbor).lower(), remote)
        post_by_neighbor_remote.setdefault(key, []).append(r)
        post_by_remote.setdefault(remote, []).append(r)

    pre_trunks = parse_trunks(pre_sections.get("show interfaces trunk", ""))
    overrides: List[str] = []
    for r in pre_recs:
        old_local = norm_interface(r.local_interface)
        if not re.match(r"^Gi(?:0/\d+|\d+/0/\d+)$", old_local):
            continue

        current = pm.get(old_local)
        role = (current.role if current else "") or ""
        old_is_uplink = ("uplink" in role.lower() or old_local in pre_trunks or looks_like_uplink_neighbor(r))
        if not old_is_uplink:
            continue

        remote = norm_interface(r.remote_interface)
        exact_key = (clean_neighbor_name(r.neighbor).lower(), remote)
        matches = list(post_by_neighbor_remote.get(exact_key, []))

        # If the exact name match failed because of CDP wrapping/truncation, fall
        # back to same remote port plus compatible gateway/uplink identity.
        if not matches:
            for cand in post_by_remote.get(remote, []):
                if not looks_like_new_uplink_interface(cand.local_interface):
                    continue
                if neighbor_names_compatible(r.neighbor, cand.neighbor) or (looks_like_uplink_neighbor(r) and looks_like_uplink_neighbor(cand)):
                    matches.append(cand)

        # Keep only observed post-change uplink/module ports. This prevents an
        # access-port neighbor with the same remote string from overriding map.
        matches = [m for m in matches if looks_like_new_uplink_interface(m.local_interface)]
        if len(matches) != 1:
            continue

        post_local = norm_interface(matches[0].local_interface)
        current_new = norm_interface(current.new_port) if current else ""
        if current_new == post_local:
            continue

        pm[old_local] = PortMapRow(
            old_local,
            post_local,
            "observed_neighbor_uplink_override",
            f"v17 observed post-change CDP/LLDP neighbor evidence overrides default target: {r.neighbor}, remote {remote}",
        )
        overrides.append(f"{old_local} -> {post_local} ({r.neighbor}, remote {remote})")
    return overrides

# ----------------------------- analysis -----------------------------

HIGH_RISK_LOG_PAT = re.compile(r"DUPADDR|ERR-?DISABLE|PM-4-ERR_DISABLE|LOOP|UDLD|SPANTREE.*(?:BLOCK|LOOP|INCONSIST|ROOTGUARD|BPDU)|AUTHMGR.*FAIL|MAB.*FAIL|DOT1X.*FAIL|SECURITY", re.I)


def analyze(pre_text: str, post_text: str, port_map_path: str = "") -> List[Finding]:
    findings: List[Finding] = []
    pre = split_sections(pre_text)
    post = split_sections(post_text)
    if port_map_path:
        pm = load_port_map(port_map_path)
        port_map_source = f"Manual CSV override: {port_map_path}"
        port_map_detail = "Manual port map CSV selected."
    else:
        pm, port_map_detail = auto_build_port_map_from_running_config(post.get("show running-config", ""))
        port_map_source = "Auto-detected from post-change running-config"
    inferred_gateway_maps: List[str] = []
    inferred_trunk_maps: List[str] = []
    observed_neighbor_overrides: List[str] = []
    if pm and not port_map_path:
        inferred_gateway_maps = infer_gateway_pair_uplink_mappings(pre, pm)
        inferred_trunk_maps = infer_trunk_uplink_mappings(pre, pm)
        observed_neighbor_overrides = apply_observed_neighbor_port_overrides(pre, post, pm)

    old_to_new = {k: v.new_port for k, v in pm.items() if v.new_port}
    new_to_old = {v.new_port: k for k, v in pm.items() if v.new_port}

    if inferred_gateway_maps:
        port_map_detail = port_map_detail + "\n\nInferred gateway 0/1 uplink pair mapping(s):\n" + "\n".join(inferred_gateway_maps)
    if inferred_trunk_maps:
        port_map_detail = port_map_detail + "\n\nInferred 24-port trunk uplink mapping(s):\n" + "\n".join(inferred_trunk_maps)
    if observed_neighbor_overrides:
        port_map_detail = port_map_detail + "\n\nObserved post-change neighbor override(s):\n" + "\n".join(observed_neighbor_overrides)

    if pm:
        findings.append(Finding("INFO", "Port Map", f"Port map loaded with {len(pm)} old-to-new mapping row(s).", f"{port_map_source}\n{port_map_detail}"))
    else:
        findings.append(Finding("WARN", "Port Map", "No port map could be generated or loaded.", f"{port_map_source}\n{port_map_detail}"))
    findings.append(Finding("INFO", "Command Sections", f"Pre-change sections found: {len(pre)}", ", ".join(sorted(pre.keys()))))
    findings.append(Finding("INFO", "Command Sections", f"Post-change sections found: {len(post)}", ", ".join(sorted(post.keys()))))
    if not pre or not post:
        findings.append(Finding("FAIL", "Command Sections", "One or both logs had zero command sections parsed.", "Check whether command prompts or script formatting changed. v8 supports prompt-prefixed lines such as switch#show int status."))

    # Interface status
    pre_if = parse_interface_status(pre.get("show interfaces status", ""))
    post_if = parse_interface_status(post.get("show interfaces status", ""))
    connected_pass: List[str] = []
    connected_warn: List[str] = []
    unchanged_down = 0
    post_covered: Set[str] = set()

    if pm:
        for old, row in sorted(pm.items(), key=lambda kv: kv[0]):
            new = row.new_port
            a = pre_if.get(old)
            b = post_if.get(new) if new else None
            if new:
                post_covered.add(new)
            if not a:
                continue
            if not b:
                if a.status == "connected":
                    note = f" | note={row.note}" if row.note else ""
                    connected_warn.append(f"{old} -> {new or '(no mapped post port)'} role={row.role}: was connected before, post port not found | pre={a.raw}{note}")
                continue
            if a.status == "connected" and b.status == "connected":
                connected_pass.append(f"{old} -> {new} role={row.role}: remained connected | pre={a.raw} | post={b.raw}")
            elif a.status == "connected" and b.status != "connected":
                note = f" | note={row.note}" if row.note else ""
                connected_warn.append(f"{old} -> {new} role={row.role}: was connected before, now {b.status} | pre={a.raw} | post={b.raw}{note}")
            elif a.status != "connected" and b.status != "connected":
                unchanged_down += 1
        if connected_warn:
            findings.append(Finding("WARN", "Interface Status", f"{len(connected_warn)} mapped port issue(s) require review.", "\n".join(connected_warn)))
        if connected_pass:
            findings.append(Finding("PASS", "Interface Status", f"{len(connected_pass)} mapped connected port(s) remained connected after change.", "\n".join(connected_pass)))
        if unchanged_down:
            findings.append(Finding("INFO", "Interface Status", f"{unchanged_down} mapped port(s) remained not connected/disabled.", "Suppressed detailed unchanged-down rows."))
        uncovered_connected = sorted(p for p, st in post_if.items() if st.status == "connected" and p not in post_covered and p not in new_to_old)
        if uncovered_connected:
            findings.append(Finding("INFO", "Interface Status", f"{len(uncovered_connected)} connected post-change port(s) were not covered by the port map.", "\n".join(uncovered_connected)))
    else:
        missing = [p for p, st in pre_if.items() if st.status == "connected" and post_if.get(p, InterfaceStatus(p, "missing")).status != "connected"]
        new = [p for p, st in post_if.items() if st.status == "connected" and pre_if.get(p, InterfaceStatus(p, "missing")).status != "connected"]
        if missing:
            findings.append(Finding("WARN", "Interface Status", f"{len(missing)} port(s) were connected before but not connected after.", "\n".join(missing)))
        if new:
            findings.append(Finding("INFO", "Interface Status", f"{len(new)} port(s) are newly connected after change.", "\n".join(new)))

    # Trunks
    pre_tr = parse_trunks(pre.get("show interfaces trunk", ""))
    post_tr = parse_trunks(post.get("show interfaces trunk", ""))
    if pre_tr or post_tr:
        missing_tr = []
        matched_tr = []
        for p in sorted(pre_tr):
            expected = old_to_new.get(p, p)
            if expected in post_tr:
                if expected != p:
                    matched_tr.append(f"{p} -> {expected}")
            else:
                missing_tr.append(f"{p} expected post {expected}")
        if missing_tr:
            findings.append(Finding("WARN", "Trunks", f"{len(missing_tr)} pre-change trunk port(s) missing after change.", "\n".join(missing_tr)))
        else:
            detail = "\n".join(matched_tr) if matched_tr else ""
            findings.append(Finding("PASS", "Trunks", f"No pre-change trunk ports disappeared; {len(matched_tr)} matched through the port map.", detail))

    # CDP/LLDP neighbors
    for proto, parser, section_name in [("CDP", parse_cdp_neighbors, "show cdp neighbors"), ("LLDP", parse_lldp_neighbors, "show lldp neighbors")]:
        pre_recs = parser(pre.get(section_name, ""))
        post_recs = parser(post.get(section_name, ""))
        pre_by_key = {neighbor_key(r, old_to_new): r for r in pre_recs}
        post_by_key = {neighbor_key(r, {}): r for r in post_recs}
        missing = []
        matched = []
        for key, r in pre_by_key.items():
            if key in post_by_key:
                pr = post_by_key[key]
                if norm_interface(r.local_interface) != norm_interface(pr.local_interface):
                    matched.append(f"{r.neighbor}: {norm_interface(r.local_interface)} -> {norm_interface(pr.local_interface)}, remote {key[1]}")
                else:
                    matched.append(f"{r.neighbor}: {key[0]}, remote {key[1]}")
            else:
                expected_local, expected_remote = key
                missing.append(f"{r.neighbor} on {norm_interface(r.local_interface)}, remote {norm_interface(r.remote_interface)} | expected post local {expected_local}, remote {expected_remote} | raw={r.raw}")
        new = []
        for key, r in post_by_key.items():
            if key not in pre_by_key:
                new.append(f"{r.neighbor} on {norm_interface(r.local_interface)}, remote {norm_interface(r.remote_interface)} | raw={r.raw}")
        if missing:
            findings.append(Finding("WARN", f"{proto} Neighbors", f"{len(missing)} {proto.lower()} neighbor record(s) missing after change.", "\n".join(missing)))
        if matched:
            findings.append(Finding("PASS", f"{proto} Neighbors", f"{len(matched)} {proto.lower()} neighbor record(s) matched after change.", "\n".join(matched[:20])))
        if new:
            findings.append(Finding("INFO", f"{proto} Neighbors", f"{len(new)} new {proto.lower()} neighbor record(s) appeared after change.", "\n".join(new)))

    # Logs
    post_logs = post.get("show logging", "")
    high = [ln.strip() for ln in post_logs.splitlines() if HIGH_RISK_LOG_PAT.search(ln)]
    if high:
        findings.append(Finding("WARN", "Logs", f"High-risk log messages found: {len(high)}", "\n".join(high[:80])))
    else:
        findings.append(Finding("PASS", "Logs", "No high-risk log keywords found.", ""))

    # MAC count
    pre_mac = count_macs(pre.get("show mac address-table", ""))
    post_mac = count_macs(post.get("show mac address-table", ""))
    if pre_mac and post_mac:
        if post_mac < max(1, int(pre_mac * 0.6)):
            findings.append(Finding("WARN", "MAC Table", f"MAC address count dropped from {pre_mac} to {post_mac}.", ""))
        else:
            findings.append(Finding("PASS", "MAC Table", f"MAC address count acceptable: {pre_mac} before, {post_mac} after.", ""))

    # STP root - context-aware per-VLAN comparison
    pre_stp_records = parse_stp_root(pre.get("show spanning-tree root", ""))
    post_stp_records = parse_stp_root(post.get("show spanning-tree root", ""))
    if pre_stp_records and post_stp_records:
        stp_pass = []
        stp_warn = []
        stp_info = []
        all_vlans = sorted(set(pre_stp_records) | set(post_stp_records), key=vlan_num)
        for vlan in all_vlans:
            a = pre_stp_records.get(vlan)
            b = post_stp_records.get(vlan)
            if a and not b:
                if vlan in STP_INFO_VLANS:
                    stp_info.append(f"{vlan}: present pre-change but absent post-change. {STP_INFO_VLAN_NOTES.get(vlan, '')}".strip())
                else:
                    stp_warn.append(f"{vlan}: present pre-change but missing post-change | pre={a.raw}")
                continue
            if b and not a:
                stp_info.append(f"{vlan}: appears post-change only | post={b.raw}")
                continue
            if not a or not b:
                continue

            mapped_pre_port = old_to_new.get(a.root_port, a.root_port) if a.root_port else ""
            post_port = b.root_port or ""
            root_same = a.root_id == b.root_id
            port_same = mapped_pre_port == post_port
            cost_same = a.cost == b.cost
            was_local_root = (a.cost == 0 and not a.root_port)
            is_local_root = (b.cost == 0 and not b.root_port)

            if root_same and port_same:
                if cost_same:
                    stp_pass.append(f"{vlan}: root unchanged, root port unchanged/mapped ({a.root_port or 'local root'} -> {post_port or 'local root'})")
                else:
                    stp_pass.append(f"{vlan}: root unchanged and root port mapped ({a.root_port or 'local root'} -> {post_port or 'local root'}); cost changed {a.cost} -> {b.cost}")
                continue

            if vlan in STP_INFO_VLANS:
                stp_info.append(
                    f"{vlan}: STP root/role changed but classified as security isolation/remediation VLAN. "
                    f"pre root={a.root_id}, cost={a.cost}, port={a.root_port or 'local root'}; "
                    f"post root={b.root_id}, cost={b.cost}, port={post_port or 'local root'}. "
                    f"{STP_INFO_VLAN_NOTES.get(vlan, '')}"
                )
                continue

            if not root_same:
                root_context = ""
                if was_local_root and not is_local_root:
                    root_context = " Local switch was root before and is no longer root."
                elif not was_local_root and is_local_root:
                    root_context = " Local switch became root post-change."
                stp_warn.append(
                    f"{vlan}: root bridge changed. pre root={a.root_id}, cost={a.cost}, port={a.root_port or 'local root'}; "
                    f"post root={b.root_id}, cost={b.cost}, port={post_port or 'local root'}.{root_context}"
                )
            elif not port_same:
                stp_warn.append(
                    f"{vlan}: root bridge unchanged but root port changed unexpectedly. "
                    f"pre port={a.root_port or 'local root'} expected post={mapped_pre_port or 'local root'}, actual post={post_port or 'local root'}"
                )
            elif not cost_same:
                stp_info.append(f"{vlan}: only STP cost changed {a.cost} -> {b.cost}; root and mapped port are unchanged.")

        if stp_warn:
            findings.append(Finding("WARN", "STP Root", f"{len(stp_warn)} STP root item(s) require review.", "\n".join(stp_warn)))
        if stp_pass:
            findings.append(Finding("PASS", "STP Root", f"{len(stp_pass)} STP VLAN(s) retained expected root/mapped root-port behavior.", "\n".join(stp_pass)))
        if stp_info:
            findings.append(Finding("INFO", "STP Root", f"{len(stp_info)} informational STP root item(s).", "\n".join(stp_info)))

    # Switch detail
    sw = post.get("show switch detail", "")
    if sw:
        if re.search(r"active|ready|standby", sw, re.I):
            findings.append(Finding("PASS", "Switch Detail", "Post-change switch detail section is present and contains active/ready/standby wording.", ""))
        else:
            findings.append(Finding("INFO", "Switch Detail", "Post-change switch detail section is present.", ""))

    # Dot1x
    dot = post.get("show dot1x all summary", "")
    if dot:
        if re.search(r"auth|unauth|mab|dot1x|authorized", dot, re.I):
            findings.append(Finding("INFO", "Dot1x", "Dot1x summary section found.", ""))
        else:
            findings.append(Finding("INFO", "Dot1x", "Dot1x summary section found, but no common auth state keywords detected.", ""))

    return sort_findings(findings)


def sort_findings(findings: List[Finding]) -> List[Finding]:
    order = {"FAIL": 0, "WARN": 1, "PASS": 2, "INFO": 3}
    return sorted(findings, key=lambda f: (order.get(f.severity, 9), f.category, f.finding))

# ----------------------------- reports -----------------------------


def severity_counts(findings: List[Finding]) -> Dict[str, int]:
    return {s: sum(1 for f in findings if f.severity == s) for s in ["FAIL", "WARN", "PASS", "INFO"]}


def overall_status(findings: List[Finding]) -> str:
    if any(f.severity == "FAIL" for f in findings):
        return "FAIL"
    if any(f.severity == "WARN" for f in findings):
        return "WARN"
    return "PASS"


def build_html_report(findings: List[Finding], pre_file: str, post_file: str, port_map_file: str) -> str:
    counts = severity_counts(findings)
    rows = []
    for f in findings:
        rows.append(f"<tr class='{f.severity.lower()}'><td>{html.escape(f.severity)}</td><td>{html.escape(f.category)}</td><td>{html.escape(f.finding)}</td><td><pre>{html.escape(f.detail)}</pre></td></tr>")
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Post-Change Validation Report</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 28px; }}
h1 {{ margin-bottom: 0; }}
.summary {{ font-size: 18px; margin: 12px 0 20px; }}
table {{ border-collapse: collapse; width: 100%; margin: 14px 0; }}
th, td {{ border: 1px solid #bbb; padding: 7px; vertical-align: top; }}
th {{ background: #ddd; text-align: left; }}
pre {{ white-space: pre-wrap; margin: 0; font-family: Consolas, monospace; font-size: 12px; }}
.fail td:first-child {{ font-weight: bold; color: #9b0000; }}
.warn td:first-child {{ font-weight: bold; color: #9a6200; }}
.pass td:first-child {{ font-weight: bold; color: #176b1d; }}
.info td:first-child {{ color: #444; }}
</style></head><body>
<h1>Post-Change Validation Report</h1>
<div class='summary'><b>Overall Status:</b> {overall_status(findings)} &nbsp; FAIL: {counts['FAIL']} WARN: {counts['WARN']} PASS: {counts['PASS']} INFO: {counts['INFO']}</div>
<table><tr><th>Field</th><th>Value</th></tr>
<tr><td>App</td><td>{APP_NAME} {APP_VERSION}</td></tr>
<tr><td>Generated</td><td>{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
<tr><td>Pre-change file</td><td>{html.escape(pre_file)}</td></tr>
<tr><td>Post-change file</td><td>{html.escape(post_file)}</td></tr>
<tr><td>Port map file</td><td>{html.escape(port_map_file or 'None')}</td></tr>
</table>
<table><tr><th>Severity</th><th>Category</th><th>Finding</th><th>Detail</th></tr>
{''.join(rows)}
</table></body></html>"""


def export_pdf(findings: List[Finding], pre_file: str, post_file: str, port_map_file: str, out_path: str) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    except Exception as e:
        raise RuntimeError("PDF export requires reportlab. Install with: pip install reportlab") from e

    doc = SimpleDocTemplate(out_path, pagesize=letter, rightMargin=0.35*inch, leftMargin=0.35*inch, topMargin=0.35*inch, bottomMargin=0.35*inch)
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    small = ParagraphStyle("small", parent=normal, fontName="Courier", fontSize=7, leading=8)
    title = styles["Title"]
    story = [Paragraph("Post-Change Validation Report", title), Spacer(1, 8)]
    counts = severity_counts(findings)
    story.append(Paragraph(f"<b>Overall Status: {overall_status(findings)}</b>", styles["Heading2"]))
    story.append(Paragraph(f"FAIL: {counts['FAIL']} &nbsp;&nbsp; WARN: {counts['WARN']} &nbsp;&nbsp; PASS: {counts['PASS']} &nbsp;&nbsp; INFO: {counts['INFO']}", normal))
    story.append(Spacer(1, 8))

    meta = [["Field", "Value"], ["App", f"{APP_NAME} {APP_VERSION}"], ["Generated", dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')], ["Pre-change file", pre_file], ["Post-change file", post_file], ["Port map file", port_map_file or "None"]]
    meta_table = Table([[Paragraph(html.escape(str(c)), normal) for c in row] for row in meta], colWidths=[1.45*inch, 6.0*inch])
    meta_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.lightgrey), ("GRID", (0,0), (-1,-1), 0.25, colors.grey), ("VALIGN", (0,0), (-1,-1), "TOP")]))
    story.extend([meta_table, Spacer(1, 12)])

    data = [["Severity", "Category", "Finding", "Detail"]]
    for f in findings:
        detail = f.detail
        if len(detail) > 2500:
            detail = detail[:2500] + "\n... truncated ..."
        data.append([f.severity, f.category, Paragraph(html.escape(f.finding), normal), Paragraph(html.escape(detail).replace("\n", "<br/>"), small)])
    tbl = Table(data, colWidths=[0.65*inch, 1.15*inch, 2.0*inch, 3.65*inch], repeatRows=1)
    tbl.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.lightgrey), ("GRID", (0,0), (-1,-1), 0.25, colors.grey), ("VALIGN", (0,0), (-1,-1), "TOP"), ("FONTSIZE", (0,0), (-1,-1), 8)]))
    story.append(tbl)
    doc.build(story)

# ----------------------------- GUI -----------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION} - created by William Munn")
        self.geometry("1150x760")
        self.pre_file = tk.StringVar()
        self.post_file = tk.StringVar()
        self.port_map_file = tk.StringVar()
        self.findings: List[Finding] = []
        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        for idx, (label, var, cmd) in enumerate([
            ("Pre-change log", self.pre_file, self.pick_pre),
            ("Post-change log", self.post_file, self.pick_post),
            ("Port map CSV override (optional - leave blank for auto-detect)", self.port_map_file, self.pick_map),
        ]):
            ttk.Label(top, text=label).grid(row=idx, column=0, sticky="w", pady=3)
            ttk.Entry(top, textvariable=var, width=115).grid(row=idx, column=1, sticky="we", padx=6, pady=3)
            ttk.Button(top, text="Browse", command=cmd).grid(row=idx, column=2, pady=3)
        top.columnconfigure(1, weight=1)
        btns = ttk.Frame(self, padding=(10,0,10,8))
        btns.pack(fill="x")
        ttk.Button(btns, text="Run Validation", command=self.run_validation).pack(side="left", padx=(0,6))
        ttk.Button(btns, text="Export HTML", command=self.save_html).pack(side="left", padx=6)
        ttk.Button(btns, text="Export PDF", command=self.save_pdf).pack(side="left", padx=6)
        ttk.Button(btns, text="Clear", command=self.clear).pack(side="left", padx=6)

        self.summary = ttk.Label(self, text="Load pre/post logs and run validation.", padding=(10,0,10,8), font=("Segoe UI", 11, "bold"))
        self.summary.pack(fill="x")

        cols = ("severity", "category", "finding", "detail")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for col, width in [("severity", 80), ("category", 160), ("finding", 360), ("detail", 520)]:
            self.tree.heading(col, text=col.title())
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0,10))
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)

        detail_frame = ttk.LabelFrame(self, text="Selected Finding Detail", padding=8)
        detail_frame.pack(fill="both", expand=False, padx=10, pady=(0,10))
        self.detail_text = tk.Text(detail_frame, height=8, wrap="word")
        self.detail_text.pack(fill="both", expand=True)

    def pick_pre(self): self.pre_file.set(filedialog.askopenfilename(title="Select pre-change log", filetypes=[("Text files", "*.txt *.log"), ("All files", "*.*")]) or self.pre_file.get())
    def pick_post(self): self.post_file.set(filedialog.askopenfilename(title="Select post-change log", filetypes=[("Text files", "*.txt *.log"), ("All files", "*.*")]) or self.post_file.get())
    def pick_map(self): self.port_map_file.set(filedialog.askopenfilename(title="Select port map CSV", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]) or self.port_map_file.get())

    def run_validation(self):
        try:
            if not self.pre_file.get() or not self.post_file.get():
                messagebox.showwarning("Missing files", "Select both pre-change and post-change log files.")
                return
            pre_text = Path(self.pre_file.get()).read_text(encoding="utf-8", errors="ignore")
            post_text = Path(self.post_file.get()).read_text(encoding="utf-8", errors="ignore")
            self.findings = analyze(pre_text, post_text, self.port_map_file.get())
            self.populate()
        except Exception as e:
            messagebox.showerror("Validation error", f"{e}\n\n{traceback.format_exc()}")

    def populate(self):
        self.tree.delete(*self.tree.get_children())
        counts = severity_counts(self.findings)
        self.summary.config(text=f"Overall Status: {overall_status(self.findings)}    FAIL: {counts['FAIL']}  WARN: {counts['WARN']}  PASS: {counts['PASS']}  INFO: {counts['INFO']}")
        for idx, f in enumerate(self.findings):
            detail_preview = f.detail.replace("\n", " | ")[:300]
            self.tree.insert("", "end", iid=str(idx), values=(f.severity, f.category, f.finding, detail_preview))

    def show_detail(self, _evt=None):
        sel = self.tree.selection()
        self.detail_text.delete("1.0", "end")
        if not sel:
            return
        f = self.findings[int(sel[0])]
        self.detail_text.insert("end", f"{f.severity} - {f.category}\n{f.finding}\n\n{f.detail}")

    def save_html(self):
        if not self.findings:
            messagebox.showwarning("Nothing to export", "Run validation first.")
            return
        path = filedialog.asksaveasfilename(title="Save HTML report", defaultextension=".html", filetypes=[("HTML", "*.html")])
        if not path:
            return
        Path(path).write_text(build_html_report(self.findings, self.pre_file.get(), self.post_file.get(), self.port_map_file.get()), encoding="utf-8")
        messagebox.showinfo("Saved", f"HTML report saved:\n{path}")

    def save_pdf(self):
        if not self.findings:
            messagebox.showwarning("Nothing to export", "Run validation first.")
            return
        path = filedialog.asksaveasfilename(title="Save PDF report", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        try:
            export_pdf(self.findings, self.pre_file.get(), self.post_file.get(), self.port_map_file.get(), path)
            messagebox.showinfo("Saved", f"PDF report saved:\n{path}")
        except Exception as e:
            messagebox.showerror("PDF export error", str(e))

    def clear(self):
        self.findings = []
        self.tree.delete(*self.tree.get_children())
        self.detail_text.delete("1.0", "end")
        self.summary.config(text="Load pre/post logs and run validation.")

if __name__ == "__main__":
    App().mainloop()
