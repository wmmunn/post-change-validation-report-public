"""Pure CDP/LLDP neighbor comparison helpers for Post Change Validation Tool."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, Set, Tuple

from src.post_change_validation_models import norm_interface


@dataclass
class NeighborComparison:
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    missing_with_presence_evidence: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)


def clean_neighbor_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\s+", " ", name)
    return name


def neighbor_key(rec: Any, port_map_old_to_new: Mapping[str, str]) -> Tuple[str, str]:
    local = norm_interface(rec.local_interface)
    local = port_map_old_to_new.get(local, local)
    remote = norm_interface(rec.remote_interface) if rec.remote_interface != "unknown" else "unknown"
    return (local, remote)


def preferred_neighbor_name(pre_neighbor: str, post_neighbor: str = "") -> str:
    pre = clean_neighbor_name(pre_neighbor or "")
    post = clean_neighbor_name(post_neighbor or "")
    if pre and pre.lower() != "unknown":
        return pre
    if post and post.lower() != "unknown":
        return post
    return pre or post or "unknown"


def neighbor_names_compatible(a: str, b: str) -> bool:
    """Loose comparison for CDP/LLDP names that may be wrapped/truncated."""
    aa = clean_neighbor_name(a).lower()
    bb = clean_neighbor_name(b).lower()
    if not aa or not bb:
        return False
    if aa == bb:
        return True
    if aa in bb or bb in aa:
        return True
    ac = re.sub(r"[^a-z0-9]", "", aa)
    bc = re.sub(r"[^a-z0-9]", "", bb)
    return bool(ac and bc and (ac in bc or bc in ac))


def post_port_presence_evidence(
    port: str,
    mac_present_ports: Mapping[str, int],
    poe_powered_ports: Set[str],
    post_if: Mapping[str, Any],
) -> list[str]:
    evidence = []
    mac_count = mac_present_ports.get(port, 0)
    if mac_count:
        evidence.append(f"{mac_count} expected MAC(s) present on mapped post port")
    if port in poe_powered_ports:
        evidence.append("PoE still delivering on mapped post port")
    if post_if.get(port) and post_if[port].status == "connected":
        evidence.append("mapped post port is connected")
    return evidence


def compare_neighbors(
    pre_records: Sequence[Any],
    post_records: Sequence[Any],
    old_to_new: Mapping[str, str],
    mac_present_ports: Mapping[str, int] | None = None,
    poe_powered_ports: Set[str] | None = None,
    post_if: Mapping[str, Any] | None = None,
) -> NeighborComparison:
    mac_present_ports = mac_present_ports or {}
    poe_powered_ports = poe_powered_ports or set()
    post_if = post_if or {}
    result = NeighborComparison()

    pre_by_key = {neighbor_key(r, old_to_new): r for r in pre_records}
    post_by_key = {neighbor_key(r, {}): r for r in post_records}
    post_by_remote: dict[str, list[Any]] = {}
    for post_record in post_records:
        post_by_remote.setdefault(norm_interface(post_record.remote_interface), []).append(post_record)

    matched_post_keys: Set[Tuple[str, str]] = set()
    for key, pre_record in pre_by_key.items():
        if key in post_by_key:
            post_record = post_by_key[key]
            matched_post_keys.add(key)
            neighbor = preferred_neighbor_name(pre_record.neighbor, post_record.neighbor)
            if norm_interface(pre_record.local_interface) != norm_interface(post_record.local_interface):
                result.matched.append(
                    f"{neighbor}: {norm_interface(pre_record.local_interface)} -> {norm_interface(post_record.local_interface)}, remote {key[1]}"
                )
            else:
                result.matched.append(f"{neighbor}: {key[0]}, remote {key[1]}")
            continue

        expected_local, expected_remote = key
        observed_matches = [
            post_record
            for post_record in post_by_remote.get(expected_remote, [])
            if neighbor_names_compatible(pre_record.neighbor, post_record.neighbor)
        ]
        if len(observed_matches) == 1:
            post_record = observed_matches[0]
            actual_key = neighbor_key(post_record, {})
            matched_post_keys.add(actual_key)
            neighbor = preferred_neighbor_name(pre_record.neighbor, post_record.neighbor)
            result.matched.append(
                f"{neighbor}: {norm_interface(pre_record.local_interface)} -> {norm_interface(post_record.local_interface)}, remote {expected_remote}"
            )
            continue

        detail = (
            f"{pre_record.neighbor} on {norm_interface(pre_record.local_interface)}, remote {norm_interface(pre_record.remote_interface)} | "
            f"expected post local {expected_local}, remote {expected_remote} | raw={pre_record.raw}"
        )
        evidence = post_port_presence_evidence(expected_local, mac_present_ports, poe_powered_ports, post_if)
        endpoint_present = bool(mac_present_ports.get(expected_local, 0) or expected_local in poe_powered_ports)
        if endpoint_present:
            result.missing_with_presence_evidence.append(f"{detail} | supporting evidence: {'; '.join(evidence)}")
        else:
            if evidence:
                detail = f"{detail} | supporting evidence: {'; '.join(evidence)}"
            result.missing.append(detail)

    for key, post_record in post_by_key.items():
        if key not in pre_by_key and key not in matched_post_keys:
            result.new.append(
                f"{post_record.neighbor} on {norm_interface(post_record.local_interface)}, remote {norm_interface(post_record.remote_interface)} | raw={post_record.raw}"
            )

    return result
