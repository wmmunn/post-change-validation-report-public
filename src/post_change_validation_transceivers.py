"""Pure transceiver threshold parsing and classification helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Set, Tuple

from src.post_change_validation_models import PortMapRow, find_first_interface, interface_sort_key, norm_interface


@dataclass
class TransceiverComparison:
    parsed_post_rows: int = 0
    matched_target_rows: int = 0
    unmatched_detail: str = ""
    warn_blocks: list[str] = field(default_factory=list)
    info_blocks: list[str] = field(default_factory=list)


@dataclass
class TransceiverEntry:
    port: str
    lines: List[str] = field(default_factory=list)
    has_alarm: bool = False
    has_warning: bool = False


TRANSCEIVER_METRIC_ORDER = ["Temperature", "Voltage", "Current", "Tx Power", "Rx Power"]
TRANSCEIVER_UNITS = {
    "Temperature": "Celsius",
    "Voltage": "Volts",
    "Current": "mA",
    "Tx Power": "dBm",
    "Rx Power": "dBm",
}

# Te1/1/1 25.20 89.00 85.00 -5.00 -9.00
TRANSCEIVER_INTERFACE_ROW_PATTERN = re.compile(r"^(Gi|Te|Twe|Fi|Fo|Hu)\d")

# Te1/1/1
TRANSCEIVER_MODULE_UPLINK_PATTERN = re.compile(r"^Te\d+/1/\d+$")

# Optical Tx Power Value -5.11 dBm
TRANSCEIVER_METRIC_LINE_PATTERN = re.compile(
    r"^(?P<metric>(?:Optical\s+)?(?:Temperature|Voltage|Current|Tx\s+Power|Rx\s+Power|Transmit\s+Power|Receive\s+Power|Laser\s+Bias\s+Current))\s+"
    r"(?P<kind>Threshold|Value)\s+(?P<body>.+)$",
    re.IGNORECASE,
)

# -5.11
TRANSCEIVER_NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")

# -5.11 dBm
TRANSCEIVER_UNIT_PATTERN = re.compile(r"(dBm|mA|Celsius|Volts?)\b", re.IGNORECASE)

# Optical Tx Power Value -5.11 dBm
TRANSCEIVER_DETAIL_CONTINUATION_PATTERN = re.compile(
    r"dBm|mA|Celsius|Volts|Threshold|Alarm|Warn|\+\+|--",
    re.IGNORECASE,
)

# ++
TRANSCEIVER_ALARM_SYMBOL_PATTERN = re.compile(r"(^|\s)(?:\+\+|--)(\s|$)")

# +
TRANSCEIVER_WARNING_SYMBOL_PATTERN = re.compile(r"(^|\s)[+-](\s|$)")


def transceiver_metric_key(metric: str) -> str:
    cleaned = re.sub(r"\s+", " ", metric.strip())
    aliases = {
        "Optical Tx Power": "Tx Power",
        "Transmit Power": "Tx Power",
        "Optical Rx Power": "Rx Power",
        "Receive Power": "Rx Power",
        "Laser Bias Current": "Current",
    }
    return aliases.get(cleaned, cleaned)


def infer_compact_metric_from_values(numeric: List[float], used_metrics: Set[str], fallback_metric: str) -> str:
    value, high_alarm, high_warn, low_warn, low_alarm = numeric[:5]
    if low_alarm < 0 and high_alarm <= 5:
        if "Tx Power" not in used_metrics:
            return "Tx Power"
        if "Rx Power" not in used_metrics:
            return "Rx Power"
    if high_alarm > 70 and low_alarm < 0:
        return "Temperature"
    if 2.0 <= value <= 4.5 and 2.0 <= low_alarm <= 4.0 and 3.0 <= high_alarm <= 5.0:
        return "Voltage"
    if high_alarm >= 20 and low_alarm >= 0:
        return "Current"
    return fallback_metric


def transceiver_metric_from_header(line: str) -> str:
    low = line.lower()
    if "temperature" in low:
        return "Temperature"
    if "voltage" in low:
        return "Voltage"
    if "current" in low:
        return "Current"
    if "transmit" in low or "tx power" in low:
        return "Tx Power"
    if "receive" in low or "rx power" in low:
        return "Rx Power"
    return ""


def parse_float_token(token: str) -> Optional[float]:
    try:
        return float(token)
    except Exception:
        return None


def compact_transceiver_row(line: str, fallback_metric: str) -> Optional[Dict[str, object]]:
    parts = line.split()
    if len(parts) < 6:
        return None
    iface = norm_interface(parts[0])
    if not TRANSCEIVER_INTERFACE_ROW_PATTERN.match(iface):
        return None
    values = parts[1:]
    # Cisco compact shape is either:
    #   Port Value HighAlarm HighWarn LowWarn LowAlarm
    # or Port Lane Value HighAlarm HighWarn LowWarn LowAlarm
    if len(values) >= 6 and parse_float_token(values[1]) is not None:
        numeric = [parse_float_token(tok) for tok in values[1:6]]
    else:
        numeric = [parse_float_token(tok) for tok in values[:5]]
    if any(v is None for v in numeric):
        return None
    metric = fallback_metric or ""
    return {
        "interface": iface,
        "metric": metric,
        "unit": TRANSCEIVER_UNITS.get(metric, ""),
        "value": numeric[0],
        "high_alarm": numeric[1],
        "high_warn": numeric[2],
        "low_warn": numeric[3],
        "low_alarm": numeric[4],
    }


def split_transceiver_change_blocks(detail: str) -> Dict[str, Dict[str, List[str]]]:
    blocks: Dict[str, Dict[str, List[str]]] = {}
    current_iface = ""
    current_phase = "post"
    for raw in (detail or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        marker = line.upper().rstrip(":")
        if marker == "PRE-CHANGE":
            current_phase = "pre"
            continue
        if marker == "POST-CHANGE":
            current_phase = "post"
            continue
        iface_line = line.rstrip(":")
        iface = norm_interface(iface_line)
        if line.endswith(":") and TRANSCEIVER_INTERFACE_ROW_PATTERN.match(iface):
            if current_iface and current_phase in {"pre", "post"} and not blocks.get(current_iface, {}).get(current_phase):
                continue
            current_iface = iface
            blocks.setdefault(current_iface, {"pre": [], "post": []})
            current_phase = "post"
            continue
        if current_iface:
            blocks.setdefault(current_iface, {"pre": [], "post": []})[current_phase].append(line)
    return blocks


def parse_transceiver_visual_rows(detail: str) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    paired_rows: List[Dict[str, object]] = []
    if "POST-CHANGE:" in (detail or ""):
        blocks = split_transceiver_change_blocks(detail)
        for iface, phases in sorted(blocks.items(), key=lambda kv: interface_sort_key(kv[0])):
            pre_text = f"{iface}:\n" + "\n".join(phases.get("pre", []))
            post_text = f"{iface}:\n" + "\n".join(phases.get("post", []))
            pre_rows = parse_transceiver_visual_rows(pre_text) if phases.get("pre") else []
            post_rows = parse_transceiver_visual_rows(post_text) if phases.get("post") else []
            pre_by_metric = {str(r.get("metric")): r for r in pre_rows}
            for post_row in post_rows:
                merged = dict(post_row)
                pre_row = pre_by_metric.get(str(post_row.get("metric")))
                if pre_row and "value" in pre_row:
                    merged["pre_value"] = pre_row["value"]
                paired_rows.append(merged)
        return paired_rows

    compact_counts: Dict[str, int] = {}
    compact_used: Dict[str, Set[str]] = {}
    pending_metric = ""
    for block in re.split(r"\n\s*\n", detail or ""):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        iface = lines[0].rstrip(":")
        by_metric: Dict[str, Dict[str, object]] = {}
        for line in lines[1:]:
            header_metric = transceiver_metric_from_header(line)
            if header_metric:
                pending_metric = header_metric

            compact = compact_transceiver_row(line, pending_metric)
            if compact:
                compact_iface = str(compact["interface"])
                if not compact["metric"]:
                    idx = compact_counts.get(compact_iface, 0)
                    compact["metric"] = TRANSCEIVER_METRIC_ORDER[idx] if idx < len(TRANSCEIVER_METRIC_ORDER) else f"Metric {idx + 1}"
                inferred_metric = infer_compact_metric_from_values(
                    [
                        float(compact["value"]),
                        float(compact["high_alarm"]),
                        float(compact["high_warn"]),
                        float(compact["low_warn"]),
                        float(compact["low_alarm"]),
                    ],
                    compact_used.setdefault(compact_iface, set()),
                    str(compact["metric"]),
                )
                compact["metric"] = inferred_metric
                compact["unit"] = TRANSCEIVER_UNITS.get(str(compact["metric"]), "")
                compact_used.setdefault(compact_iface, set()).add(str(compact["metric"]))
                compact_counts[compact_iface] = compact_counts.get(compact_iface, 0) + 1
                rows.append(compact)
                pending_metric = ""
                continue

            m = TRANSCEIVER_METRIC_LINE_PATTERN.match(line)
            if not m:
                continue
            metric = transceiver_metric_key(m.group("metric"))
            kind = m.group("kind").lower()
            nums = [float(n) for n in TRANSCEIVER_NUMBER_PATTERN.findall(m.group("body"))]
            unit_m = TRANSCEIVER_UNIT_PATTERN.search(m.group("body"))
            rec = by_metric.setdefault(metric, {"interface": iface, "metric": metric, "unit": ""})
            if unit_m:
                rec["unit"] = unit_m.group(1)
            if kind == "threshold" and len(nums) >= 4:
                rec["high_alarm"], rec["high_warn"], rec["low_warn"], rec["low_alarm"] = nums[:4]
            elif kind == "value" and nums:
                rec["value"] = nums[0]
        for rec in by_metric.values():
            if all(k in rec for k in ["value", "high_alarm", "high_warn", "low_warn", "low_alarm"]):
                rows.append(rec)
    return rows


def transceiver_level_class(value: float, low_alarm: float, low_warn: float, high_warn: float, high_alarm: float) -> str:
    if value <= low_alarm or value >= high_alarm:
        return "alarm"
    if value <= low_warn or value >= high_warn:
        return "warn"
    return "ok"


def parse_transceiver_detail(section: str) -> Dict[str, TransceiverEntry]:
    entries: Dict[str, TransceiverEntry] = {}
    current = ""
    for raw in section.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        first = find_first_interface(line)
        if first and TRANSCEIVER_INTERFACE_ROW_PATTERN.match(first):
            current = first
            entries.setdefault(current, TransceiverEntry(first)).lines.append(line.strip())
        elif current:
            # Keep threshold/value rows after the interface line.
            if TRANSCEIVER_DETAIL_CONTINUATION_PATTERN.search(line):
                entries[current].lines.append(line.strip())
    for e in entries.values():
        joined = "\n".join(e.lines)
        parsed_rows = parse_transceiver_visual_rows(f"{e.port}:\n{joined}")
        if parsed_rows:
            # Prefer numeric threshold evaluation over raw text scanning. The
            # table headers legitimately contain words such as "High Alarm" and
            # "Low Warn", and healthy compact output can still include those
            # labels in detail text.
            levels = [
                transceiver_level_class(
                    float(r["value"]),
                    float(r["low_alarm"]),
                    float(r["low_warn"]),
                    float(r["high_warn"]),
                    float(r["high_alarm"]),
                )
                for r in parsed_rows
                if all(k in r for k in ["value", "low_alarm", "low_warn", "high_warn", "high_alarm"])
            ]
            e.has_alarm = any(level == "alarm" for level in levels)
            e.has_warning = any(level == "warn" for level in levels)
        else:
            # Fallback for unparsed Cisco output that marks conditions with
            # standalone alarm/warning symbols.
            e.has_alarm = bool(TRANSCEIVER_ALARM_SYMBOL_PATTERN.search(joined))
            e.has_warning = bool(TRANSCEIVER_WARNING_SYMBOL_PATTERN.search(joined))
    return entries


def select_transceiver_target_entries(
    post_entries: Mapping[str, TransceiverEntry],
    uplink_targets: Set[str],
    standalone_industrial: bool = False,
) -> Dict[str, TransceiverEntry]:
    if standalone_industrial:
        return dict(post_entries)
    return {
        p: entry
        for p, entry in post_entries.items()
        if p in uplink_targets or TRANSCEIVER_MODULE_UPLINK_PATTERN.match(p)
    }


def transceiver_unmatched_detail(post_entries: Mapping[str, TransceiverEntry]) -> str:
    return "\n\n".join(
        f"{p}:\n" + "\n".join(entry.lines[:12])
        for p, entry in sorted(post_entries.items(), key=lambda kv: interface_sort_key(kv[0]))
    )[:3000]


def transceiver_post_to_old_map(pm: Mapping[str, PortMapRow]) -> Dict[str, str]:
    return {norm_interface(row.new_port): norm_interface(old) for old, row in pm.items() if row.new_port}


def find_pre_transceiver_entry(
    post_port: str,
    idx: int,
    pre_entries: Mapping[str, TransceiverEntry],
    post_to_old: Mapping[str, str],
    pre_candidates: List[Tuple[str, TransceiverEntry]],
    used_pre: Set[str],
) -> Tuple[str, Optional[TransceiverEntry]]:
    old_port = post_to_old.get(post_port, post_port)
    pre_entry = pre_entries.get(old_port) or pre_entries.get(post_port)
    if not pre_entry and idx < len(pre_candidates):
        fallback_old, fallback_entry = pre_candidates[idx]
        if fallback_old not in used_pre:
            old_port = fallback_old
            pre_entry = fallback_entry
    return old_port, pre_entry


def transceiver_comparison_block(
    post_port: str,
    post_entry: TransceiverEntry,
    pre_entry: Optional[TransceiverEntry] = None,
) -> str:
    if pre_entry:
        return f"{post_port}:\nPRE-CHANGE:\n" + "\n".join(pre_entry.lines[:80]) + "\nPOST-CHANGE:\n" + "\n".join(post_entry.lines[:80])
    return f"{post_port}:\nPOST-CHANGE:\n" + "\n".join(post_entry.lines[:80])


def compare_transceiver_delivery(
    pre_entries: Mapping[str, TransceiverEntry],
    post_entries: Mapping[str, TransceiverEntry],
    pm: Mapping[str, PortMapRow],
    uplink_targets: Set[str],
    standalone_industrial: bool = False,
) -> TransceiverComparison:
    target_entries = select_transceiver_target_entries(post_entries, uplink_targets, standalone_industrial)

    comparison = TransceiverComparison(
        parsed_post_rows=len(post_entries),
        matched_target_rows=len(target_entries),
    )
    if post_entries and not target_entries:
        comparison.unmatched_detail = transceiver_unmatched_detail(post_entries)
        return comparison

    post_to_old = transceiver_post_to_old_map(pm)
    pre_candidates = sorted(pre_entries.items(), key=lambda kv: interface_sort_key(kv[0]))
    used_pre: Set[str] = set()
    for idx, (post_port, post_entry) in enumerate(sorted(target_entries.items(), key=lambda kv: interface_sort_key(kv[0]))):
        old_port, pre_entry = find_pre_transceiver_entry(post_port, idx, pre_entries, post_to_old, pre_candidates, used_pre)
        if pre_entry:
            used_pre.add(old_port)
        block = transceiver_comparison_block(post_port, post_entry, pre_entry)
        if post_entry.has_alarm or post_entry.has_warning:
            comparison.warn_blocks.append(block)
        else:
            comparison.info_blocks.append(block)
    return comparison
