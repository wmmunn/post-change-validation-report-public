import re
import unittest
from typing import Dict, List, Optional, Set, Tuple

from src.post_change_validation_analysis_wrappers import has_standalone_industrial_map, standard_uplink_targets_from_map
from src.post_change_validation_models import NeighborRecord, PortMapRow, find_first_interface, interface_sort_key, norm_interface
from src.post_change_validation_neighbor_parsers import parse_cdp_neighbors, parse_lldp_neighbors
from src.post_change_validation_neighbors import clean_neighbor_name, neighbor_names_compatible
from src.post_change_validation_uplinks import (
    apply_observed_neighbor_port_overrides,
    gateway_pair_key,
    infer_gateway_pair_uplink_mappings,
    infer_trunk_uplink_mappings,
    old_uplink_ports_from_evidence,
    parse_trunks,
)


def port_map_snapshot(pm: Dict[str, PortMapRow]) -> Dict[str, tuple[str, str, str, str]]:
    return {old: (row.old_port, row.new_port, row.role, row.note) for old, row in sorted(pm.items())}


def clone_port_map(pm: Dict[str, PortMapRow]) -> Dict[str, PortMapRow]:
    return {old: PortMapRow(row.old_port, row.new_port, row.role, row.note) for old, row in pm.items()}


# The legacy_* helpers below mirror the corresponding inline helper behavior in
# post_change_validation_reviewer_v24.temp. That temp baseline does not include
# the newer lone-25 mixed-stack inference, so that domain behavior is tested
# separately as current expected behavior rather than as temp-baseline equivalence.

# Port Mode Encapsulation Status Native vlan
LEGACY_TRUNK_TABLE_HEADER_PATTERN = re.compile(r"^Port\s+Mode\s+Encapsulation\s+Status", re.IGNORECASE)

# Port Vlans allowed on trunk
LEGACY_TRUNK_TABLE_VLANS_HEADER_PATTERN = re.compile(r"^Port\s+Vlans", re.IGNORECASE)

# Gi1/0/25 on 802.1q trunking 1
LEGACY_TRUNK_INTERFACE_PATTERN = re.compile(r"^(Fa|Gi|Te|Twe|Fi|Fo|Hu|Po)\d")

# site-wl0-gw.example.net
LEGACY_GATEWAY_PAIR_NAME_PATTERN = re.compile(r"^(.*?)([01])(-gw\b.*)$", re.IGNORECASE)

# Gi1/0/25
LEGACY_OLD_GATEWAY_UPLINK_INTERFACE_PATTERN = re.compile(r"^Gi(?:0/\d+|\d+/0/\d+)$")

# Gi1/0/25
LEGACY_24_PORT_UPLINK_PATTERN = re.compile(r"^Gi\d+/0/(?:25|27)$")

# Gi1/0/25
LEGACY_24_PORT_NUMBER_PATTERN = re.compile(r"^Gi\d+/0/(\d+)$")

# Gi1/0/25
LEGACY_STACK_MEMBER_PORT_PATTERN = re.compile(r"^Gi(\d+)/0/(\d+)$")

# -gw
LEGACY_UPLINK_NEIGHBOR_TEXT_PATTERN = re.compile(r"-gw\b|\bgw\d*\b|gateway|c9500|c9[0-9]{3}|router")

# Te1/1/1
LEGACY_MODULE_UPLINK_INTERFACE_PATTERN = re.compile(r"^(?:Te|Twe|Fo|Hu)\d+/1/\d+$")

# Gi1/1
LEGACY_STANDALONE_INDUSTRIAL_TRUNK_INTERFACE_PATTERN = re.compile(r"^(?:Fa|Gi|Te)\d+/\d+$")

# Gi1/0/25
LEGACY_STACK_OLD_UPLINK_INTERFACE_PATTERN = re.compile(r"^Gi(?:0/\d+|\d+/0/\d+)$")

# Gi1/1
LEGACY_STANDALONE_OLD_UPLINK_INTERFACE_PATTERN = re.compile(r"^(?:Fa|Gi)(?:0/\d+|\d+/\d+)$")


def legacy_parse_trunks(section: str) -> Set[str]:
    trunks: Set[str] = set()
    in_port_section = False
    for line in section.splitlines():
        if LEGACY_TRUNK_TABLE_HEADER_PATTERN.match(line):
            in_port_section = True
            continue
        if in_port_section:
            if not line.strip():
                continue
            if LEGACY_TRUNK_TABLE_VLANS_HEADER_PATTERN.match(line):
                break
            parts = line.split()
            if parts:
                port = norm_interface(parts[0])
                if LEGACY_TRUNK_INTERFACE_PATTERN.match(port):
                    trunks.add(port)
    if not trunks:
        for line in section.splitlines():
            if "trunk" in line.lower():
                port = find_first_interface(line)
                if port:
                    trunks.add(port)
    return trunks


def legacy_gateway_pair_key(name: str) -> Optional[Tuple[str, str]]:
    normalized = (name or "").strip().lower()
    match = LEGACY_GATEWAY_PAIR_NAME_PATTERN.search(normalized)
    if not match:
        return None
    return (match.group(1) + "X" + match.group(3), match.group(2))


def legacy_looks_like_uplink_neighbor(record: NeighborRecord) -> bool:
    text = f"{record.neighbor} {record.platform} {record.capability} {record.raw}".lower()
    cap_tokens = {token.strip().upper() for token in re.split(r"[\s,]+", record.capability or "") if token.strip()}
    if "R" in cap_tokens:
        return True
    return bool(LEGACY_UPLINK_NEIGHBOR_TEXT_PATTERN.search(text))


def legacy_looks_like_new_uplink_interface(
    port: str,
    standalone_industrial: bool = False,
    post_trunks: Optional[Set[str]] = None,
) -> bool:
    normalized = norm_interface(port)
    post_trunks = post_trunks or set()
    if (
        standalone_industrial
        and normalized in post_trunks
        and LEGACY_STANDALONE_INDUSTRIAL_TRUNK_INTERFACE_PATTERN.match(normalized)
    ):
        return True
    return bool(LEGACY_MODULE_UPLINK_INTERFACE_PATTERN.match(normalized))


def legacy_infer_gateway_pair_uplink_mappings(
    pre_sections: Dict[str, str],
    pm: Dict[str, PortMapRow],
) -> List[str]:
    if has_standalone_industrial_map(pm):
        return []
    targets = standard_uplink_targets_from_map(pm)
    uplink_a, uplink_b = targets.uplink_a, targets.uplink_b
    if not uplink_a or not uplink_b:
        return []

    records: List[NeighborRecord] = []
    records.extend(parse_cdp_neighbors(pre_sections.get("show cdp neighbors", "")))
    records.extend(parse_lldp_neighbors(pre_sections.get("show lldp neighbors", "")))

    groups: Dict[str, List[NeighborRecord]] = {}
    for record in records:
        pair = legacy_gateway_pair_key(record.neighbor)
        if not pair:
            continue
        base, _side = pair
        local = norm_interface(record.local_interface)
        if not LEGACY_OLD_GATEWAY_UPLINK_INTERFACE_PATTERN.match(local):
            continue
        groups.setdefault(base, []).append(record)

    inferred: List[str] = []
    seen_pairs: Set[Tuple[str, str]] = set()
    for _base, items in sorted(groups.items()):
        by_local: Dict[str, NeighborRecord] = {norm_interface(item.local_interface): item for item in items}
        locals_sorted = sorted(by_local.keys(), key=interface_sort_key)
        if len(locals_sorted) < 2:
            continue
        low = locals_sorted[0]
        high = locals_sorted[-1]
        if (low, high) in seen_pairs:
            continue
        seen_pairs.add((low, high))
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


def legacy_infer_trunk_uplink_mappings(pre_sections: Dict[str, str], pm: Dict[str, PortMapRow]) -> List[str]:
    if has_standalone_industrial_map(pm):
        return []
    targets = standard_uplink_targets_from_map(pm)
    uplink_a, uplink_b = targets.uplink_a, targets.uplink_b
    pre_trunks = sorted(legacy_parse_trunks(pre_sections.get("show interfaces trunk", "")), key=interface_sort_key)
    candidates = [norm_interface(port) for port in pre_trunks if LEGACY_24_PORT_UPLINK_PATTERN.match(norm_interface(port))]
    if len(candidates) < 2:
        return []
    by_member: Dict[str, List[str]] = {}
    for port in candidates:
        match = LEGACY_STACK_MEMBER_PORT_PATTERN.match(port)
        if match:
            by_member.setdefault(match.group(1), []).append(port)
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


def legacy_apply_observed_neighbor_port_overrides(
    pre_sections: Dict[str, str],
    post_sections: Dict[str, str],
    pm: Dict[str, PortMapRow],
) -> List[str]:
    pre_records: List[NeighborRecord] = []
    post_records: List[NeighborRecord] = []
    for parser, section in [(parse_cdp_neighbors, "show cdp neighbors"), (parse_lldp_neighbors, "show lldp neighbors")]:
        pre_records.extend(parser(pre_sections.get(section, "")))
        post_records.extend(parser(post_sections.get(section, "")))

    post_by_neighbor_remote: Dict[Tuple[str, str], List[NeighborRecord]] = {}
    post_by_remote: Dict[str, List[NeighborRecord]] = {}
    for record in post_records:
        remote = norm_interface(record.remote_interface)
        key = (clean_neighbor_name(record.neighbor).lower(), remote)
        post_by_neighbor_remote.setdefault(key, []).append(record)
        post_by_remote.setdefault(remote, []).append(record)

    standalone_industrial = has_standalone_industrial_map(pm)
    pre_trunks = legacy_parse_trunks(pre_sections.get("show interfaces trunk", ""))
    post_trunks = legacy_parse_trunks(post_sections.get("show interfaces trunk", ""))
    overrides: List[str] = []
    for record in pre_records:
        old_local = norm_interface(record.local_interface)
        if standalone_industrial:
            valid_old_local = bool(LEGACY_STANDALONE_OLD_UPLINK_INTERFACE_PATTERN.match(old_local))
        else:
            valid_old_local = bool(LEGACY_STACK_OLD_UPLINK_INTERFACE_PATTERN.match(old_local))
        if not valid_old_local:
            continue

        current = pm.get(old_local)
        role = (current.role if current else "") or ""
        old_is_uplink = "uplink" in role.lower() or old_local in pre_trunks or legacy_looks_like_uplink_neighbor(record)
        if not old_is_uplink:
            continue

        remote = norm_interface(record.remote_interface)
        exact_key = (clean_neighbor_name(record.neighbor).lower(), remote)
        matches = list(post_by_neighbor_remote.get(exact_key, []))

        if not matches:
            for candidate in post_by_remote.get(remote, []):
                if not legacy_looks_like_new_uplink_interface(candidate.local_interface, standalone_industrial, post_trunks):
                    continue
                if neighbor_names_compatible(record.neighbor, candidate.neighbor) or (
                    legacy_looks_like_uplink_neighbor(record) and legacy_looks_like_uplink_neighbor(candidate)
                ):
                    matches.append(candidate)

        matches = [
            match
            for match in matches
            if legacy_looks_like_new_uplink_interface(match.local_interface, standalone_industrial, post_trunks)
        ]
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
            f"v17 observed post-change CDP/LLDP neighbor evidence overrides default target: {record.neighbor}, remote {remote}",
        )
        overrides.append(f"{old_local} -> {post_local} ({record.neighbor}, remote {remote})")
    return overrides


class UplinkInferenceTests(unittest.TestCase):
    def test_parse_trunks_uses_fallback_interface_anywhere_on_trunk_line(self):
        section = "sanitized note: interface Gi1/0/25 is trunking toward gateway\n"

        self.assertEqual({"Gi1/0/25"}, parse_trunks(section))
        self.assertEqual(legacy_parse_trunks(section), parse_trunks(section))

    def test_old_uplink_ports_from_evidence_combines_trunk_and_gateway_neighbor(self):
        pre_sections = {
            "show interfaces trunk": "Gi1/0/25 on 802.1q trunking 1\n",
            "show cdp neighbors": "SANITIZED-GW0 Gi2/0/52 153 R S I C9500 Te1/0/1\n",
            "show lldp neighbors": "",
        }

        self.assertEqual({"Gi1/0/25", "Gi2/0/52"}, old_uplink_ports_from_evidence(pre_sections))

    def test_gateway_pair_key_normalizes_sanitized_zero_one_gateway_names(self):
        self.assertEqual(
            ("site-wlX-gw.example.net", "0"),
            gateway_pair_key("site-wl0-gw.example.net"),
        )
        self.assertEqual(
            ("site-wlX-gw.example.net", "1"),
            gateway_pair_key("site-wl1-gw.example.net"),
        )

    def test_gateway_pair_inference_overrides_lower_and_higher_old_ports(self):
        pm = {
            "Gi1/0/49": PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", "uplink A"),
            "Gi1/0/50": PortMapRow("Gi1/0/50", "Te1/1/8", "uplink", "uplink B"),
            "Gi1/0/25": PortMapRow("Gi1/0/25", "Te1/0/25", "access", "access mapping"),
            "Gi1/0/27": PortMapRow("Gi1/0/27", "Te1/0/27", "access", "access mapping"),
        }
        pre_sections = {
            "show cdp neighbors": "\n".join(
                [
                    "site-wl1-gw.example.net Gi1/0/27 153 R S I C9500 Te1/0/1",
                    "site-wl0-gw.example.net Gi1/0/25 153 R S I C9500 Te1/0/1",
                ]
            ),
            "show lldp neighbors": "",
        }

        inferred, _review = infer_gateway_pair_uplink_mappings(pre_sections, pm)

        self.assertEqual(["Gi1/0/25 (site-wl0-gw.example.net) -> Te1/1/1; Gi1/0/27 (site-wl1-gw.example.net) -> Te1/1/8"], inferred)
        self.assertEqual("Te1/1/1", pm["Gi1/0/25"].new_port)
        self.assertEqual("Te1/1/8", pm["Gi1/0/27"].new_port)
        self.assertEqual("inferred_gateway_uplink", pm["Gi1/0/25"].role)

    def test_gateway_pair_inference_matches_legacy_inline_output(self):
        original_pm = {
            "Gi1/0/49": PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", "uplink A"),
            "Gi1/0/50": PortMapRow("Gi1/0/50", "Te1/1/8", "uplink", "uplink B"),
            "Gi1/0/25": PortMapRow("Gi1/0/25", "Te1/0/25", "access", "access mapping"),
            "Gi1/0/27": PortMapRow("Gi1/0/27", "Te1/0/27", "access", "access mapping"),
        }
        pre_sections = {
            "show cdp neighbors": "\n".join(
                [
                    "site-wl1-gw.example.net Gi1/0/27 153 R S I C9500 Te1/0/1",
                    "site-wl0-gw.example.net Gi1/0/25 153 R S I C9500 Te1/0/1",
                ]
            ),
            "show lldp neighbors": "",
        }
        legacy_pm = clone_port_map(original_pm)
        extracted_pm = clone_port_map(original_pm)

        legacy = legacy_infer_gateway_pair_uplink_mappings(pre_sections, legacy_pm)
        extracted, _review = infer_gateway_pair_uplink_mappings(pre_sections, extracted_pm)

        self.assertEqual(legacy, extracted)
        self.assertEqual(
            ["Gi1/0/25 (site-wl0-gw.example.net) -> Te1/1/1; Gi1/0/27 (site-wl1-gw.example.net) -> Te1/1/8"],
            extracted,
        )
        self.assertEqual(port_map_snapshot(legacy_pm), port_map_snapshot(extracted_pm))
        self.assertNotEqual(port_map_snapshot(original_pm), port_map_snapshot(extracted_pm))
        self.assertEqual("inferred_gateway_uplink", extracted_pm["Gi1/0/25"].role)
        self.assertEqual("inferred_gateway_uplink", extracted_pm["Gi1/0/27"].role)
        self.assertEqual("Te1/1/1", extracted_pm["Gi1/0/25"].new_port)
        self.assertEqual("Te1/1/8", extracted_pm["Gi1/0/27"].new_port)

    def test_gateway_pair_inference_single_side_no_match_does_not_change_map(self):
        original_pm = {
            "Gi1/0/49": PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", "uplink A"),
            "Gi1/0/50": PortMapRow("Gi1/0/50", "Te1/1/8", "uplink", "uplink B"),
            "Gi1/0/25": PortMapRow("Gi1/0/25", "Te1/0/25", "access", "access mapping"),
        }
        pre_sections = {
            "show cdp neighbors": "site-wl0-gw.example.net Gi1/0/25 153 R S I C9500 Te1/0/1",
            "show lldp neighbors": "",
        }
        legacy_pm = clone_port_map(original_pm)
        extracted_pm = clone_port_map(original_pm)

        legacy = legacy_infer_gateway_pair_uplink_mappings(pre_sections, legacy_pm)
        extracted, _review = infer_gateway_pair_uplink_mappings(pre_sections, extracted_pm)

        self.assertEqual(legacy, extracted)
        self.assertEqual([], extracted)
        self.assertEqual(port_map_snapshot(legacy_pm), port_map_snapshot(extracted_pm))
        self.assertEqual(port_map_snapshot(original_pm), port_map_snapshot(extracted_pm))

    def test_two_candidate_trunk_uplink_inference_matches_v24_temp_output(self):
        original_pm = {
            "Gi1/0/25": PortMapRow("Gi1/0/25", "Te1/0/25", "access", "mGig access mapping"),
            "Gi1/0/27": PortMapRow("Gi1/0/27", "Te1/0/27", "access", "mGig access mapping"),
            "Gi1/0/49": PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", "uplink A"),
            "Gi1/0/50": PortMapRow("Gi1/0/50", "Te1/1/8", "uplink", "uplink B"),
        }
        pre_sections = {
            "show interfaces trunk": "\n".join(
                [
                    "Gi1/0/25 on 802.1q trunking 1",
                    "Gi1/0/27 on 802.1q trunking 1",
                ]
            )
        }
        legacy_pm = clone_port_map(original_pm)
        extracted_pm = clone_port_map(original_pm)

        legacy = legacy_infer_trunk_uplink_mappings(pre_sections, legacy_pm)
        extracted, _review = infer_trunk_uplink_mappings(pre_sections, extracted_pm)

        self.assertEqual(legacy, extracted)
        self.assertEqual(port_map_snapshot(legacy_pm), port_map_snapshot(extracted_pm))

    def test_lone_25_trunk_candidate_maps_to_uplink_a_as_current_domain_behavior(self):
        original_pm = {
            "Gi1/0/25": PortMapRow("Gi1/0/25", "Te1/0/25", "access", "mGig access mapping"),
            "Gi1/0/49": PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", "uplink A"),
            "Gi1/0/50": PortMapRow("Gi1/0/50", "Te2/1/8", "uplink", "uplink B"),
            "Gi2/0/52": PortMapRow("Gi2/0/52", "Te2/1/8", "uplink", "uplink B"),
        }
        pre_sections = {
            "show interfaces trunk": "\n".join(
                [
                    "Gi1/0/25 on 802.1q trunking 1",
                    "Gi2/0/52 on 802.1q trunking 1",
                ]
            )
        }
        temp_baseline_pm = clone_port_map(original_pm)
        extracted_pm = clone_port_map(original_pm)

        temp_baseline = legacy_infer_trunk_uplink_mappings(pre_sections, temp_baseline_pm)
        extracted, _review = infer_trunk_uplink_mappings(pre_sections, extracted_pm)

        self.assertEqual([], temp_baseline)
        self.assertIn("Gi1/0/25 -> Te1/1/1", "\n".join(extracted))
        self.assertEqual("Te1/1/1", extracted_pm["Gi1/0/25"].new_port)

    def test_observed_neighbor_override_matches_legacy_inline_output(self):
        original_pm = {
            "Gi1/0/52": PortMapRow("Gi1/0/52", "Te2/1/8", "uplink", "uplink B"),
        }
        pre_sections = {
            "show cdp neighbors": "sanitized-gw.example.net Gi1/0/52 153 R S I C9500 Te1/0/1\n",
            "show lldp neighbors": "",
            "show interfaces trunk": "Gi1/0/52 on 802.1q trunking 1\n",
        }
        post_sections = {
            "show cdp neighbors": "sanitized-gw.example.net Te2/1/1 153 R S I C9500 Te1/0/1\n",
            "show lldp neighbors": "",
            "show interfaces trunk": "",
        }
        legacy_pm = clone_port_map(original_pm)
        extracted_pm = clone_port_map(original_pm)

        legacy = legacy_apply_observed_neighbor_port_overrides(pre_sections, post_sections, legacy_pm)
        extracted = apply_observed_neighbor_port_overrides(pre_sections, post_sections, extracted_pm)

        self.assertEqual(legacy, extracted)
        self.assertEqual(port_map_snapshot(legacy_pm), port_map_snapshot(extracted_pm))
        self.assertEqual("Te2/1/1", extracted_pm["Gi1/0/52"].new_port)

    def test_observed_neighbor_override_ambiguous_post_matches_do_not_change_map(self):
        original_pm = {
            "Gi1/0/52": PortMapRow("Gi1/0/52", "Te2/1/8", "uplink", "uplink B"),
        }
        pre_sections = {
            "show cdp neighbors": "sanitized-gw.example.net Gi1/0/52 153 R S I C9500 Te1/0/1\n",
            "show lldp neighbors": "",
            "show interfaces trunk": "Gi1/0/52 on 802.1q trunking 1\n",
        }
        post_sections = {
            "show cdp neighbors": "\n".join(
                [
                    "sanitized-gw.example.net Te2/1/1 153 R S I C9500 Te1/0/1",
                    "sanitized-gw.example.net Te2/1/2 153 R S I C9500 Te1/0/1",
                ]
            ),
            "show lldp neighbors": "",
            "show interfaces trunk": "",
        }
        legacy_pm = clone_port_map(original_pm)
        extracted_pm = clone_port_map(original_pm)

        legacy = legacy_apply_observed_neighbor_port_overrides(pre_sections, post_sections, legacy_pm)
        extracted = apply_observed_neighbor_port_overrides(pre_sections, post_sections, extracted_pm)

        self.assertEqual(legacy, extracted)
        self.assertEqual([], extracted)
        self.assertEqual(port_map_snapshot(legacy_pm), port_map_snapshot(extracted_pm))
        self.assertEqual(port_map_snapshot(original_pm), port_map_snapshot(extracted_pm))


if __name__ == "__main__":
    unittest.main()
