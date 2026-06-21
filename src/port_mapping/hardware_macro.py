"""Log-driven hardware PID to access-port prefix mapping."""

from __future__ import annotations

import re
from typing import Dict

# C9300-24UX
PID_24UX_PATTERN = re.compile(r"-24ux", re.IGNORECASE)

# C9300-48UN
PID_48UN_PATTERN = re.compile(r"-48un", re.IGNORECASE)

# NAME: "Switch 1", DESCR: "Cisco C9300"
INVENTORY_NAME_DESCR_PATTERN = re.compile(
    r'NAME:\s*"?(?P<name>[^",]+)"?\s*,\s*DESCR:\s*"?(?P<descr>[^"]+)"?',
    re.IGNORECASE,
)

# PID: C9300-48U
INVENTORY_PID_PATTERN = re.compile(r"PID:\s*(?P<pid>[^,]+)", re.IGNORECASE)

# Switch 1
SWITCH_MEMBER_COMPONENT_PATTERN = re.compile(r"^Switch\s+(?P<member>\d+)$", re.IGNORECASE)


def evaluate_access_prefix_from_pid(model: str) -> str:
    """Return access-port prefix (Gi/Fi/Te) inferred from hardware PID/model string."""
    text = (model or "").strip()
    if not text:
        return "Gi"
    if PID_24UX_PATTERN.search(text):
        return "Te"
    if PID_48UN_PATTERN.search(text):
        return "Fi"
    lowered = text.lower()
    if any(token in lowered for token in ("ie-3300", "c9200cx", "c9300")):
        return "Gi"
    return "Gi"


def parse_stack_member_models_from_inventory(section: str) -> Dict[str, str]:
    """Parse show inventory text and return {stack_member: pid} for Switch N records."""
    members: Dict[str, str] = {}
    current_component = ""
    current_pid = ""

    for raw in (section or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        name_m = INVENTORY_NAME_DESCR_PATTERN.search(line)
        if name_m:
            if current_component and current_pid:
                member_m = SWITCH_MEMBER_COMPONENT_PATTERN.match(current_component)
                if member_m:
                    members[member_m.group("member")] = current_pid
            current_component = name_m.group("name").strip()
            current_pid = ""
            continue
        pid_m = INVENTORY_PID_PATTERN.search(line)
        if pid_m:
            current_pid = pid_m.group("pid").strip()

    if current_component and current_pid:
        member_m = SWITCH_MEMBER_COMPONENT_PATTERN.match(current_component)
        if member_m:
            members[member_m.group("member")] = current_pid

    return members
