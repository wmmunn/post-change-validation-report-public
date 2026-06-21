"""Shared data models and interface normalization helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple


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


@dataclass
class MacEntry:
    vlan: str
    mac: str
    type_: str
    port: str
    raw: str = ""


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
class PoeBudget:
    available_w: float = 0.0
    used_w: float = 0.0
    remaining_w: float = 0.0
    raw: str = ""


@dataclass
class PoeEntry:
    port: str
    admin: str = ""
    oper: str = ""
    power_w: str = ""
    device: str = ""
    raw: str = ""


INT_PREFIXES = {
    "fa": "Fa", "fast": "Fa", "fastethernet": "Fa",
    "gi": "Gi", "gig": "Gi", "gigabit": "Gi", "gigabitethernet": "Gi",
    "te": "Te", "ten": "Te", "twe": "Twe", "twentyfive": "Twe", "twentyfivegigabitethernet": "Twe",
    "fi": "Fi", "five": "Fi", "fivegigabit": "Fi", "fivegigabitethernet": "Fi",
    "fo": "Fo", "forty": "Fo", "fortygigabitethernet": "Fo",
    "hu": "Hu", "hundred": "Hu", "hundredgigabitethernet": "Hu",
    "po": "Po", "port-channel": "Po", "portchannel": "Po",
    "ap": "Ap", "app": "Ap",
}

# interface GigabitEthernet1/0/1
INT_RE = re.compile(
    r"\b(?P<prefix>Fa|FastEthernet|Gi|Gig|GigabitEthernet|Te|Ten|TenGigabitEthernet|Twe|TwentyFiveGigE|TwentyFiveGigabitEthernet|Fi|FiveGigabitEthernet|Fo|FortyGigabitEthernet|Hu|HundredGigE|Po|Port-channel|PortChannel|Ap)\s*(?P<num>\d+(?:/\d+){1,3})\b",
    re.IGNORECASE,
)
# Gi1/0/1
SHORT_INTERFACE_PATTERN = re.compile(r"\b(Fa|Gi|Te|Twe|Fi|Fo|Hu|Po|Ap)(\d+(?:/\d+){1,3})\b", re.IGNORECASE)

# FiveGigabitEthernet2/0/1, FiveGigE2/0/1, TenGigabitEthernet1/0/1
_CANONICAL_PREFIX_ALIASES: tuple[tuple[str, str], ...] = (
    ("twentyfivegigabitethernet", "twe"),
    ("twentyfivegige", "twe"),
    ("fivegigabitethernet", "fi"),
    ("fivegigabit", "fi"),
    ("fivegige", "fi"),
    ("fivegig", "fi"),
    ("tengigabitethernet", "te"),
    ("tengige", "te"),
    ("tengig", "te"),
    ("fortygigabitethernet", "fo"),
    ("fortygige", "fo"),
    ("hundredgigabitethernet", "hu"),
    ("hundredgige", "hu"),
    ("fastethernet", "fa"),
    ("gigabitethernet", "gi"),
    ("gigabit", "gi"),
    ("portchannel", "po"),
    ("port-channel", "po"),
)


def norm_interface(s: str) -> str:
    if not s:
        return ""
    s = s.strip().replace("Ethernet", "Ethernet")
    m = INT_RE.search(s)
    if not m:
        m2 = SHORT_INTERFACE_PATTERN.search(s)
        if not m2:
            return s.strip()
        prefix = m2.group(1).lower()
        num = m2.group(2)
    else:
        prefix = m.group("prefix").lower()
        num = m.group("num")
    prefix = prefix.replace("fastethernet", "fa").replace("gigabitethernet", "gi").replace("tengigabitethernet", "te")
    prefix = prefix.replace("fivegigabitethernet", "fi").replace("twentyfivegige", "twe").replace("twentyfivegigabitethernet", "twe")
    prefix = prefix.replace("fortygigabitethernet", "fo").replace("hundredgige", "hu")
    prefix = INT_PREFIXES.get(prefix, prefix[:2].capitalize())
    return f"{prefix}{num}"


def canonical_interface_name(s: str) -> str:
    """Return a canonical short interface name for port-map coverage comparisons."""
    if not s:
        return ""
    text = re.sub(r"\s+", "", s.strip())
    lower = text.lower()
    for long_prefix, short in _CANONICAL_PREFIX_ALIASES:
        if lower.startswith(long_prefix):
            suffix = lower[len(long_prefix) :]
            if suffix and suffix[0].isdigit():
                return norm_interface(f"{short}{suffix}")
    return norm_interface(text)


def find_first_interface(text: str) -> str:
    m = INT_RE.search(text or "")
    return norm_interface(m.group(0)) if m else ""


def interface_sort_key(intf: str) -> Tuple[int, int, int, int, str]:
    n = norm_interface(intf)
    m = re.match(r"^(Fa|Gi|Fi|Te|Twe|Fo|Hu)(\d+)(?:/(\d+))?(?:/(\d+))?$", n)
    if not m:
        return (9999, 9999, 9999, 9999, n)
    nums = [int(x) if x is not None else 0 for x in m.groups()[1:]]
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2], 0, n)
