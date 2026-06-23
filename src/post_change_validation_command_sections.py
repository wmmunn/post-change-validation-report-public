"""Command-section parsing for Post Change Validation Tool logs."""

from __future__ import annotations

import re
from typing import Dict, List, Optional


COMMAND_ALIASES = {
    "show int status": "show interfaces status",
    "show interfaces status": "show interfaces status",
    "show spanning-tree root": "show spanning-tree root",
    "show spanning-tree summary": "show spanning-tree summary",
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
    "show env all": "show environment all",
    "show environment all": "show environment all",
    "show power inline": "show power inline",
    "show version": "show version",
    "show processes cpu": "show processes cpu",
    "show inventory": "show inventory",
    "show inv": "show inventory",
    "show int transceiver detail": "show interfaces transceiver detail",
    "show interface transceiver detail": "show interfaces transceiver detail",
    "show interfaces transceiver detail": "show interfaces transceiver detail",
}


COMMAND_PATTERNS = sorted(COMMAND_ALIASES.keys(), key=len, reverse=True)

# show inventory | include C9300
COMMAND_PIPE_SUFFIX_PATTERN = re.compile(r"\s*\|.*$")
# ACCESS-SW01#show int status
PROMPT_PREFIX_PATTERN = re.compile(r"^(?:[\w.()/: -]+)?[#>]\s*")
# sho inventory
# eorwdw-wccadm-pbx-5-sw#sho inv
SHOW_ABBREVIATION_PATTERN = re.compile(r"^(?:sho|sh)\s+")
# show interfaces TenGigabitEthernet1/1/1 transceiver detail
INTERFACE_TRANSCEIVER_DETAIL_PATTERN = re.compile(
    r"^show\s+(?:int|interface|interfaces)\s+\S+\s+transceiver\s+detail$",
    re.IGNORECASE,
)


def canonical_command(cmd: str) -> str:
    cmd = COMMAND_PIPE_SUFFIX_PATTERN.sub("", cmd.strip().lower())
    cmd = re.sub(r"\s+", " ", cmd)
    return COMMAND_ALIASES.get(cmd, cmd)


def normalize_command_line(line: str) -> Optional[str]:
    """Return canonical command from a raw log line."""
    cleaned = line.strip()
    cleaned = PROMPT_PREFIX_PATTERN.sub("", cleaned)
    cleaned = cleaned.strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = SHOW_ABBREVIATION_PATTERN.sub("show ", cleaned)
    base = cleaned.split("|")[0].strip()
    if INTERFACE_TRANSCEIVER_DETAIL_PATTERN.match(base):
        return "show interfaces transceiver detail"
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
