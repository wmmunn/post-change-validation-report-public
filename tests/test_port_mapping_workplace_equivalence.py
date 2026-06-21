import unittest
from pathlib import Path

import tests.bootstrap  # noqa: F401

from src.post_change_validation_models import PortMapRow
from src.post_change_validation_port_map import auto_build_port_map_from_running_config
from src.port_mapping.engine import PortMappingEngine
from src.port_mapping.private.workplace_profile import WorkplaceProfile
from src.port_mapping.types import PortMapBuildRequest

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


def _legacy_auto_build_port_map_from_running_config(run_cfg: str):
    """Frozen legacy reference copied before Phase 1 extraction."""
    import re
    from typing import Dict, Set, Tuple

    from src.post_change_validation_models import norm_interface

    RUNNING_CONFIG_INTERFACE_PATTERN = re.compile(r"^interface\s+([^\s]+)", re.IGNORECASE | re.MULTILINE)
    STACK_ACCESS_INTERFACE_PATTERN = re.compile(r"^(Gi|Fi|Te)(\d+)/0/(\d+)$")
    STACK_MODULE_INTERFACE_PATTERN = re.compile(r"^(?:Te|Twe|Fo|Hu)(\d+)/1/\d+$")
    STANDALONE_INTERFACE_PATTERN = re.compile(r"^(Fa|Gi|Te)(\d+)/(\d+)$")
    SWITCH_PROVISION_PATTERN = re.compile(r"^switch\s+(\d+)\s+provision\s+(\S+)", re.IGNORECASE | re.MULTILINE)

    def detect_access_prefix_from_model(model: str) -> str:
        m = (model or "").strip().lower()
        if "c9300-24ux" in m or "c9300-24uxb" in m:
            return "Te"
        if "c9300-48un" in m:
            return "Fi"
        if any(token in m for token in ["uxm", "uxg", "48hx"]):
            return "Fi"
        if any(token in m for token in ["48uxm"]):
            return "Te"
        return "Gi"

    def infer_access_prefix_by_member_from_interfaces(run_cfg: str) -> Dict[str, str]:
        counts: Dict[str, Dict[str, int]] = {}
        for m in RUNNING_CONFIG_INTERFACE_PATTERN.finditer(run_cfg or ""):
            intf = norm_interface(m.group(1))
            im = STACK_ACCESS_INTERFACE_PATTERN.match(intf)
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

    def infer_standalone_access_units_from_interfaces(run_cfg: str) -> Dict[tuple[str, str], Set[int]]:
        counts: Dict[tuple[str, str], Set[int]] = {}
        for m in RUNNING_CONFIG_INTERFACE_PATTERN.finditer(run_cfg or ""):
            intf = norm_interface(m.group(1))
            im = STANDALONE_INTERFACE_PATTERN.match(intf)
            if not im:
                continue
            prefix, unit, port_s = im.group(1), im.group(2), im.group(3)
            port = int(port_s)
            if unit == "0" or port == 0:
                continue
            counts.setdefault((prefix, unit), set()).add(port)
        return counts

    def parse_switch_provision(run_cfg: str) -> Dict[str, str]:
        members: Dict[str, str] = {}
        for m in SWITCH_PROVISION_PATTERN.finditer(run_cfg or ""):
            member = m.group(1)
            if member == "0":
                continue
            members[member] = m.group(2)
        return members

    def detect_members_from_interfaces(run_cfg: str) -> Set[str]:
        members: Set[str] = set()
        for m in RUNNING_CONFIG_INTERFACE_PATTERN.finditer(run_cfg or ""):
            intf = norm_interface(m.group(1))
            im = STACK_ACCESS_INTERFACE_PATTERN.match(intf) or STACK_MODULE_INTERFACE_PATTERN.match(intf)
            if im:
                member = im.group(1)
                if member != "0":
                    members.add(member)
        return members

    rows: Dict[str, PortMapRow] = {}
    if not run_cfg.strip():
        return rows, "No post-change running-config section found."

    provisions = parse_switch_provision(run_cfg)
    interface_members = detect_members_from_interfaces(run_cfg)

    if provisions:
        members = sorted(provisions.keys(), key=lambda x: int(x))
    else:
        members = sorted(interface_members, key=lambda x: int(x))
    if not members:
        standalone_units = infer_standalone_access_units_from_interfaces(run_cfg)
        if not standalone_units:
            return rows, "Could not detect stack members from running-config."
        sorted_units = sorted(standalone_units.items(), key=lambda kv: (int(kv[0][1]), kv[0][0]))
        first_unit = sorted_units[0][0][1]
        detail_lines = [
            "Profile: standalone industrial switch mapping",
            "Detected IE-style two-part interface numbering",
            "Detected unit(s): " + ", ".join(f"{prefix}{unit}/x ({len(ports)} ports)" for (prefix, unit), ports in sorted_units),
        ]
        cumulative_offset = 0
        for (standalone_prefix, standalone_unit), standalone_ports in sorted_units:
            max_port = max(standalone_ports)
            for port in range(1, max_port + 1):
                new = f"{standalone_prefix}{standalone_unit}/{port}"
                for old_prefix in ("Fa", "Gi"):
                    old = f"{old_prefix}{standalone_unit}/{port}"
                    rows[old] = PortMapRow(
                        old,
                        new,
                        "standalone_industrial",
                        "Auto IE/IE3300 standalone mapping from two-part interface numbering",
                    )
                    flat_old = f"{old_prefix}{first_unit}/{cumulative_offset + port}"
                    rows.setdefault(
                        flat_old,
                        PortMapRow(
                            flat_old,
                            new,
                            "standalone_industrial",
                            "Auto IE/IE3300 flattened legacy chassis mapping to base/expansion banks",
                        ),
                    )
                    legacy_old = f"{old_prefix}0/{cumulative_offset + port}"
                    rows.setdefault(
                        legacy_old,
                        PortMapRow(
                            legacy_old,
                            new,
                            "standalone_industrial",
                            "Auto IE/IE3300 flattened legacy unit-0 alias to base/expansion banks",
                        ),
                    )
            cumulative_offset += max_port
        first_prefix = sorted_units[0][0][0]
        first_max_port = max(sorted_units[0][1])
        for port in range(1, first_max_port + 1):
            new = f"{first_prefix}{first_unit}/{port}"
            for old_prefix in ("Fa", "Gi"):
                old = f"{old_prefix}0/{port}"
                rows[old] = PortMapRow(
                    old,
                    new,
                    "standalone_industrial",
                    "Auto IE/IE3300 legacy unit-0 alias to first two-part interface bank",
                )
        return rows, "\n".join(detail_lines)

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

    for member in members:
        model = provisions.get(member, "")
        model_prefix = detect_access_prefix_from_model(model)
        interface_prefix = prefix_by_member.get(member)
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

    for member in members:
        rows[f"Gi{member}/0/49"] = PortMapRow(f"Gi{member}/0/49", uplink_a, "uplink", "Auto standard uplink A mapping Gi*/0/49 -> first-member Te/1/1")
        rows[f"Gi{member}/0/50"] = PortMapRow(f"Gi{member}/0/50", uplink_b, "uplink", "Auto standard uplink B mapping Gi*/0/50 -> last-member Te/1/8")
        rows[f"Gi{member}/0/51"] = PortMapRow(f"Gi{member}/0/51", uplink_a, "uplink", "Auto standard uplink A mapping Gi*/0/51 -> first-member Te/1/1")
        rows[f"Gi{member}/0/52"] = PortMapRow(f"Gi{member}/0/52", uplink_b, "uplink", "Auto standard uplink B mapping Gi*/0/52 -> last-member Te/1/8")

    rows["Gi0/15"] = PortMapRow("Gi0/15", uplink_a, "legacy_uplink", "Auto legacy uplink A mapping Gi0/15 -> standard uplink A")
    rows["Gi0/16"] = PortMapRow("Gi0/16", uplink_b, "legacy_uplink", "Auto legacy uplink B mapping Gi0/16 -> standard uplink B")

    return rows, "\n".join(detail_lines)


def _assert_port_maps_equal(test_case: unittest.TestCase, expected: dict[str, PortMapRow], actual: dict[str, PortMapRow]) -> None:
    test_case.assertEqual(set(expected.keys()), set(actual.keys()))
    for key in expected:
        test_case.assertEqual(expected[key].old_port, actual[key].old_port, msg=f"mismatch old_port for {key}")
        test_case.assertEqual(expected[key].new_port, actual[key].new_port, msg=f"mismatch new_port for {key}")
        test_case.assertEqual(expected[key].role, actual[key].role, msg=f"mismatch role for {key}")
        test_case.assertEqual(expected[key].note, actual[key].note, msg=f"mismatch note for {key}")


class WorkplaceProfileEquivalenceTests(unittest.TestCase):
    def _assert_all_builders_match(self, run_cfg: str) -> None:
        legacy_rows, legacy_detail = _legacy_auto_build_port_map_from_running_config(run_cfg)

        profile_rows, profile_detail = WorkplaceProfile().build(run_cfg)
        _assert_port_maps_equal(self, legacy_rows, profile_rows)
        self.assertEqual(legacy_detail, profile_detail)

        engine_result = PortMappingEngine().build(PortMapBuildRequest(running_config=run_cfg))
        _assert_port_maps_equal(self, legacy_rows, engine_result.rows)
        self.assertEqual(legacy_detail, engine_result.detail)
        self.assertEqual("workplace_environment_standard", engine_result.profile_name)

        shim_rows, shim_detail = auto_build_port_map_from_running_config(run_cfg)
        _assert_port_maps_equal(self, legacy_rows, shim_rows)
        self.assertEqual(legacy_detail, shim_detail)

    def test_workplace_profile_matches_legacy_auto_build_for_stack_fixture(self):
        run_cfg = (FIXTURE_ROOT / "sanitized_stack_running_config.cfg").read_text(encoding="utf-8")
        self._assert_all_builders_match(run_cfg)

    def test_workplace_profile_matches_legacy_auto_build_for_standalone_fixture(self):
        run_cfg = (FIXTURE_ROOT / "sanitized_standalone_industrial_running_config.cfg").read_text(encoding="utf-8")
        self._assert_all_builders_match(run_cfg)

    def test_workplace_profile_matches_legacy_for_empty_running_config(self):
        self._assert_all_builders_match("")


if __name__ == "__main__":
    unittest.main()
