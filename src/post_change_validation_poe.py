"""Pure PoE parsing and evidence helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Set

from src.post_change_validation_mac import is_access_map_row
from src.post_change_validation_models import PoeBudget, PoeEntry, PortMapRow, interface_sort_key, norm_interface


@dataclass
class PoeDeliveryComparison:
    parsed_pre_rows: int = 0
    parsed_post_rows: int = 0
    evidence_lines: list[str] = field(default_factory=list)
    restored: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


# Gi1/0/3 auto on 6.3 IP Phone 3 30.0
POE_INTERFACE_ROW_PORT_PATTERN = re.compile(r"^(Gi|Fi|Te)\d")

# 6.3
POE_POWER_VALUE_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")

# Available:400.0(w) Used:54.3(w) Remaining:345.7(w)
POE_LABELED_BUDGET_PATTERN = re.compile(
    r"available\D+(?P<available>\d+(?:\.\d+)?).*?used\D+(?P<used>\d+(?:\.\d+)?).*?remaining\D+(?P<remaining>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

# 1    400.0    54.3    345.7
POE_NUMERIC_VALUE_PATTERN = re.compile(r"\d+(?:\.\d+)?")

# Gi1/0/3 auto on 6.3 IP Phone 3 30.0
POE_INTERFACE_OR_TOTALS_PATTERN = re.compile(r"^(?:Fa|Gi|Te|Twe|Fi|Fo|Hu)\d", re.IGNORECASE)

# admin on oper on raw "...delivering..."
POE_POWERING_WORD_PATTERN = re.compile(r"\b(on|deliver|delivering|powering)\b")

# admin off oper fault raw "...denied..."
POE_NOT_POWERING_WORD_PATTERN = re.compile(r"\b(off|fault|deny|denied|disabled)\b")


def parse_power_inline(section: str) -> Dict[str, PoeEntry]:
    entries: Dict[str, PoeEntry] = {}
    for raw in section.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith(("interface", "module", "available", "used", "remaining", "----", "watts")):
            continue
        parts = line.split()
        if not parts:
            continue
        port = norm_interface(parts[0])
        if not POE_INTERFACE_ROW_PORT_PATTERN.match(port):
            continue
        # Common Cisco shape: Interface Admin Oper Power Device Class Max
        admin = parts[1] if len(parts) > 1 else ""
        oper = parts[2] if len(parts) > 2 else ""
        power = ""
        for tok in parts[3:6]:
            if POE_POWER_VALUE_PATTERN.match(tok):
                power = tok
                break
        device = " ".join(parts[4:]) if len(parts) > 4 else ""
        entries[port] = PoeEntry(port=port, admin=admin, oper=oper, power_w=power, device=device, raw=line)
    return entries


def parse_poe_budget(section: str) -> Optional[PoeBudget]:
    """Parse aggregate PoE available/used/remaining values when present."""
    if not section:
        return None
    best: Optional[PoeBudget] = None
    saw_budget_header = False
    for raw in section.splitlines():
        line = raw.strip()
        if not line:
            continue
        nums = [float(n) for n in POE_NUMERIC_VALUE_PATTERN.findall(line)]
        low = line.lower()
        labeled = POE_LABELED_BUDGET_PATTERN.search(line)
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
        if POE_INTERFACE_OR_TOTALS_PATTERN.match(line) or line.lower().startswith("totals:"):
            continue
        if len(nums) >= 3 and saw_budget_header:
            # Cisco summary rows are commonly: Module Available Used Remaining.
            available, used, remaining = nums[-3], nums[-2], nums[-1]
            if available > 0 and used >= 0 and remaining >= 0 and abs((used + remaining) - available) <= max(5.0, available * 0.10):
                budget = PoeBudget(available, used, remaining, line)
                if not best or budget.available_w > best.available_w:
                    best = budget
                saw_budget_header = False
    return best


def poe_budget_detail(pre_sec: str, post_sec: str) -> list[str]:
    pre = parse_poe_budget(pre_sec)
    post = parse_poe_budget(post_sec)
    rows: list[str] = []
    if pre:
        rows.append(f"POE_BUDGET|pre|{pre.available_w:.2f}|{pre.used_w:.2f}|{pre.remaining_w:.2f}|{pre.raw.replace('|', '/')}")
    if post:
        rows.append(f"POE_BUDGET|post|{post.available_w:.2f}|{post.used_w:.2f}|{post.remaining_w:.2f}|{post.raw.replace('|', '/')}")
    return rows


def poe_is_powering(e: Optional[PoeEntry]) -> bool:
    if not e:
        return False
    txt = f"{e.admin} {e.oper} {e.raw}".lower()
    if POE_POWERING_WORD_PATTERN.search(txt) and not POE_NOT_POWERING_WORD_PATTERN.search(txt):
        return True
    try:
        return float(e.power_w) > 0.1
    except Exception:
        return False


def poe_still_powering_ports(pre_sec: str, post_sec: str, pm: Mapping[str, PortMapRow]) -> Set[str]:
    if not pre_sec or not post_sec:
        return set()
    pre = parse_power_inline(pre_sec)
    post = parse_power_inline(post_sec)
    powered: Set[str] = set()
    for old, row in pm.items():
        if not row.new_port or not is_access_map_row(row):
            continue
        if poe_is_powering(pre.get(old)) and poe_is_powering(post.get(row.new_port)):
            powered.add(row.new_port)
    return powered


def speed_mbps(speed: str) -> Optional[float]:
    text = (speed or "").strip().lower()
    if not text or text in {"auto", "a-auto", "unknown"}:
        return None
    text = text.replace("a-", "")
    if text in {"10g", "10000"}:
        return 10000.0
    if text in {"5g", "5000"}:
        return 5000.0
    if text in {"2.5g", "2500", "2g5"}:
        return 2500.0
    if text in {"1g", "1000"}:
        return 1000.0
    if text.endswith("g"):
        try:
            return float(text[:-1]) * 1000.0
        except Exception:
            return None
    m = re.search(r"\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


def poe_speed_upgrade_detail(
    access_rows: Mapping[str, PortMapRow],
    pre_poe: Mapping[str, PoeEntry],
    post_poe: Mapping[str, PoeEntry],
    pre_if: Mapping[str, object],
    post_if: Mapping[str, object],
) -> list[str]:
    upgraded: list[str] = []
    for old, row in sorted(access_rows.items(), key=lambda kv: interface_sort_key(kv[0])):
        if not poe_is_powering(pre_poe.get(old)) or not poe_is_powering(post_poe.get(row.new_port)):
            continue
        pre_status = pre_if.get(old)
        post_status = post_if.get(row.new_port)
        pre_status_speed = getattr(pre_status, "speed", "") if pre_status else ""
        post_status_speed = getattr(post_status, "speed", "") if post_status else ""
        pre_speed = speed_mbps(pre_status_speed)
        post_speed = speed_mbps(post_status_speed)
        if pre_speed is None or post_speed is None or post_speed <= pre_speed:
            continue
        upgraded.append(
            "%s -> %s: %s -> %s"
            % (
                old,
                row.new_port,
                (pre_status_speed if pre_status else "unknown"),
                (post_status_speed if post_status else "unknown"),
            )
        )
    if not upgraded:
        return []
    safe = "; ".join(item.replace("|", "/") for item in upgraded[:20])
    return [f"POE_SPEED_UPGRADE|{len(upgraded)}|{safe}"]


def compare_poe_delivery(
    pre_sec: str,
    post_sec: str,
    pm: Mapping[str, PortMapRow],
    pre_if: Optional[Mapping[str, object]] = None,
    post_if: Optional[Mapping[str, object]] = None,
    observed_ports: Optional[Mapping[str, str]] = None,
) -> PoeDeliveryComparison:
    pre = parse_power_inline(pre_sec)
    post = parse_power_inline(post_sec)
    access_rows = {old: row for old, row in pm.items() if row.new_port and is_access_map_row(row)}
    evidence_lines = poe_budget_detail(pre_sec, post_sec)
    evidence_lines += poe_speed_upgrade_detail(access_rows, pre, post, pre_if or {}, post_if or {})
    observed_ports = observed_ports or {}

    comparison = PoeDeliveryComparison(
        parsed_pre_rows=len(pre),
        parsed_post_rows=len(post),
        evidence_lines=evidence_lines,
    )
    for old, row in sorted(access_rows.items(), key=lambda kv: interface_sort_key(kv[0])):
        a = pre.get(old)
        if not poe_is_powering(a):
            continue
        b = post.get(row.new_port)
        if poe_is_powering(b):
            comparison.restored.append(f"{old} -> {row.new_port}: PoE still delivering | pre={a.raw} | post={b.raw}")
        else:
            observed = observed_ports.get(old, "")
            observed_entry = post.get(observed) if observed else None
            if observed and observed != row.new_port and poe_is_powering(observed_entry):
                comparison.restored.append(
                    f"{old} -> {observed}: PoE still delivering on observed neighbor port; inferred map expected {row.new_port} | pre={a.raw} | post={observed_entry.raw}"
                )
            else:
                comparison.missing.append(f"{old} -> {row.new_port}: PoE was delivering before, not detected after | pre={a.raw} | post={(b.raw if b else 'post port not found')}")
    return comparison
