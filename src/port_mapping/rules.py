"""Shared port-mapping rule helpers and CSV/JSON row builders."""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional

from src.post_change_validation_models import PortMapRow, canonical_interface_name, norm_interface

# Gi1/0/1-48
INTERFACE_RANGE_PATTERN = re.compile(r"^(?P<base>[A-Za-z]+\d+(?:/\d+)*)/(?P<start>\d+)-(?P<end>\d+)$")


def expand_interface_range(interface_range: str) -> List[str]:
    value = (interface_range or "").strip()
    match = INTERFACE_RANGE_PATTERN.match(value)
    if not match:
        port = norm_interface(value)
        return [port] if port else []

    start = int(match.group("start"))
    end = int(match.group("end"))
    if end < start:
        raise ValueError(f"Interface range end precedes start: {interface_range!r}")

    first_port = norm_interface(f"{match.group('base')}/{start}")
    base = first_port.rsplit("/", 1)[0]
    return [f"{base}/{port}" for port in range(start, end + 1)]


def expand_parallel_ranges(source_range: str, target_range: str) -> List[tuple[str, str]]:
    source_ports = expand_interface_range(source_range)
    target_ports = expand_interface_range(target_range)
    if len(source_ports) != len(target_ports):
        raise ValueError(f"Interface range length mismatch: {source_range!r} -> {target_range!r}")
    return list(zip(source_ports, target_ports))


def build_rows_from_json_profile(
    profile: Mapping[str, Any],
    source_interfaces: Iterable[str],
) -> Dict[str, PortMapRow]:
    source_ports = [norm_interface(port) for port in source_interfaces if norm_interface(port)]
    rows: Dict[str, PortMapRow] = {}

    for member_rule in profile.get("member_rules", []) or []:
        member_label = str(member_rule.get("member", "")).strip()
        note_prefix = f"Profile member {member_label}" if member_label else "Profile member"
        for rule in member_rule.get("access_port_rules", []) or []:
            for old, new in expand_parallel_ranges(rule.get("source_range", ""), rule.get("target_range", "")):
                if not source_ports or old in source_ports:
                    rows[old] = PortMapRow(
                        old,
                        new,
                        (rule.get("role", "") or "access").strip(),
                        f"{note_prefix} access-port range mapping",
                    )

        for rule in member_rule.get("uplink_rules", []) or []:
            source = [norm_interface(port) for port in rule.get("source_ports", []) or []]
            target = [norm_interface(port) for port in rule.get("target_ports", []) or []]
            for old, new in zip(source, target):
                if old and new and (not source_ports or old in source_ports):
                    rows[old] = PortMapRow(
                        old,
                        new,
                        (rule.get("role", "") or "uplink").strip(),
                        f"{note_prefix} uplink mapping",
                    )

    for rule in profile.get("access_port_rules", []) or []:
        for old, new in expand_parallel_ranges(rule.get("source_range", ""), rule.get("target_range", "")):
            if not source_ports or old in source_ports:
                rows[old] = PortMapRow(
                    old,
                    new,
                    (rule.get("role", "") or "access").strip(),
                    "Profile access-port range mapping",
                )

    for rule in profile.get("uplink_rules", []) or []:
        source = [norm_interface(port) for port in rule.get("source_ports", []) or []]
        target = [norm_interface(port) for port in rule.get("target_ports", []) or []]
        for old, new in zip(source, target):
            if old and new and (not source_ports or old in source_ports):
                rows[old] = PortMapRow(
                    old,
                    new,
                    (rule.get("role", "") or "uplink").strip(),
                    "Profile uplink mapping",
                )

    return rows


def apply_same_name_fallback(
    rows: Dict[str, PortMapRow],
    source_interfaces: Iterable[str],
) -> Dict[str, PortMapRow]:
    for port in source_interfaces:
        normalized = norm_interface(port)
        if normalized:
            rows.setdefault(normalized, PortMapRow(normalized, normalized, "same_name", "Same-name fallback mapping"))
    return rows


# old_port,new_port,role,note
MANUAL_CSV_HEADER_NORMALIZE_PATTERN = re.compile(r"[\s_\-]+")

# Maps collapsed header text (e.g. "oldport" from "Old Port") to canonical CSV keys.
MANUAL_CSV_HEADER_ALIASES: Dict[str, str] = {
    "oldport": "old_port",
    "sourceport": "old_port",
    "preport": "old_port",
    "fromport": "old_port",
    "newport": "new_port",
    "targetport": "new_port",
    "postport": "new_port",
    "toport": "new_port",
    "role": "role",
    "type": "role",
    "note": "note",
    "notes": "note",
    "comment": "note",
    "comments": "note",
}


def canonical_manual_csv_header(header: str) -> str:
    raw = (header or "").strip().lstrip("\ufeff")
    collapsed = MANUAL_CSV_HEADER_NORMALIZE_PATTERN.sub("", raw.lower())
    return MANUAL_CSV_HEADER_ALIASES.get(collapsed, "")


def remap_manual_csv_row(raw_row: Mapping[str, str]) -> Dict[str, str]:
    mapped: Dict[str, str] = {}
    for key, value in raw_row.items():
        canonical = canonical_manual_csv_header(key)
        if canonical and canonical not in mapped:
            mapped[canonical] = value
    return mapped


def parse_manual_csv(csv_text: str) -> tuple[Dict[str, PortMapRow], str]:
    """Parse manual port-map CSV text and return rows plus operator-facing detail."""
    rows: Dict[str, PortMapRow] = {}
    if not (csv_text or "").strip():
        return rows, "Manual CSV file is empty."

    reader = csv.DictReader(io.StringIO(csv_text))
    raw_headers = list(reader.fieldnames or [])
    mapped_headers = {canonical_manual_csv_header(header) for header in raw_headers}
    has_old_port = "old_port" in mapped_headers
    has_new_port = "new_port" in mapped_headers

    data_row_count = 0
    skipped_row_count = 0
    for raw_row in reader:
        data_row_count += 1
        row = remap_manual_csv_row(raw_row)
        old = canonical_interface_name(row.get("old_port", ""))
        new = canonical_interface_name(row.get("new_port", ""))
        if old:
            rows[old] = PortMapRow(
                old,
                new,
                (row.get("role", "") or "").strip(),
                (row.get("note", "") or "").strip(),
            )
        else:
            skipped_row_count += 1

    if rows:
        return rows, f"Manual port map CSV loaded {len(rows)} mapping row(s) from {data_row_count} data row(s)."

    header_list = ", ".join(raw_headers) if raw_headers else "(none)"
    if not raw_headers:
        return rows, "Manual CSV has no header row. Expected columns: old_port, new_port, role, note."
    if not has_old_port or not has_new_port:
        return rows, (
            "Manual CSV header row did not include recognizable old/new port columns. "
            f"Headers found: {header_list}. Expected old_port and new_port "
            "(also accepted: Old Port, source_port, New Port, etc.)."
        )
    if data_row_count == 0:
        return rows, f"Manual CSV has a header row but no data rows. Headers found: {header_list}."
    return rows, (
        f"Manual CSV had {data_row_count} data row(s) but none produced a valid old_port value. "
        f"Headers found: {header_list}. Skipped rows: {skipped_row_count}."
    )


def load_manual_csv_port_map(csv_text: str) -> Dict[str, PortMapRow]:
    rows, _detail = parse_manual_csv(csv_text)
    return rows


def load_manual_csv_file(path: str) -> Dict[str, PortMapRow]:
    rows, _detail = load_manual_csv_file_with_detail(path)
    return rows


def load_manual_csv_file_with_detail(path: str) -> tuple[Dict[str, PortMapRow], str]:
    if not path:
        return {}, ""
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        return parse_manual_csv(csv_file.read())


def build_strategy_port_map(
    profile: Mapping[str, Any],
    source_interfaces: Iterable[str],
    manual_overrides: Optional[Mapping[str, PortMapRow]] = None,
) -> Dict[str, PortMapRow]:
    source_ports = [norm_interface(port) for port in source_interfaces if norm_interface(port)]
    rows = build_rows_from_json_profile(profile, source_ports)

    if (profile or {}).get("fallback") == "same_name":
        apply_same_name_fallback(rows, source_ports)

    for old, row in (manual_overrides or {}).items():
        rows[norm_interface(old)] = row

    return rows
