import unittest
from pathlib import Path

from src.post_change_validation_mapping_strategies import (
    build_strategy_port_map,
    load_json_profile,
    load_manual_csv_port_map,
)


PROFILE_ROOT = Path(__file__).resolve().parents[1] / "src" / "port_mapping" / "profiles"


class PortMappingStrategyTests(unittest.TestCase):
    def test_same_name_fallback_maps_interface_to_itself(self):
        port_map = build_strategy_port_map(
            {"profile_name": "same_name_only", "fallback": "same_name"},
            ["GigabitEthernet1/0/1"],
        )

        self.assertEqual(port_map["Gi1/0/1"].new_port, "Gi1/0/1")
        self.assertEqual(port_map["Gi1/0/1"].role, "same_name")
        self.assertIn("fallback", port_map["Gi1/0/1"].note.lower())

    def test_manual_csv_override_takes_priority_over_profile_range(self):
        manual_csv = """old_port,new_port,role,note
GigabitEthernet1/0/1,TenGigabitEthernet1/1/3,uplink,operator supplied override
"""
        profile = {
            "profile_name": "generic_range",
            "fallback": "same_name",
            "access_port_rules": [
                {
                    "source_range": "Gi1/0/1-2",
                    "target_range": "Gi1/0/1-2",
                    "role": "access",
                }
            ],
        }

        port_map = build_strategy_port_map(
            profile,
            ["Gi1/0/1", "Gi1/0/2"],
            manual_overrides=load_manual_csv_port_map(manual_csv),
        )

        self.assertEqual(port_map["Gi1/0/1"].new_port, "Te1/1/3")
        self.assertEqual(port_map["Gi1/0/1"].role, "uplink")
        self.assertEqual(port_map["Gi1/0/2"].new_port, "Gi1/0/2")
        self.assertEqual(port_map["Gi1/0/2"].role, "access")

    def test_generic_model_profile_resolves_access_and_uplink_boundaries(self):
        profile = {
            "profile_name": "generic_c9300_48p",
            "description": "Generic 48-port Catalyst access switch refresh template.",
            "fallback": "same_name",
            "access_port_rules": [
                {
                    "source_range": "Gi1/0/1-48",
                    "target_range": "Gi1/0/1-48",
                    "role": "access",
                }
            ],
            "uplink_rules": [
                {
                    "source_ports": ["Gi1/0/49", "Gi1/0/50"],
                    "target_ports": ["Te1/1/1", "Te1/1/2"],
                    "role": "uplink",
                }
            ],
        }

        port_map = build_strategy_port_map(
            profile,
            ["Gi1/0/1", "Gi1/0/48", "Gi1/0/49", "Gi1/0/50"],
        )

        self.assertEqual(port_map["Gi1/0/1"].new_port, "Gi1/0/1")
        self.assertEqual(port_map["Gi1/0/48"].new_port, "Gi1/0/48")
        self.assertEqual(port_map["Gi1/0/49"].new_port, "Te1/1/1")
        self.assertEqual(port_map["Gi1/0/50"].new_port, "Te1/1/2")
        self.assertEqual(port_map["Gi1/0/49"].role, "uplink")

    def test_public_same_name_profile_loads_from_disk(self):
        profile = load_json_profile(PROFILE_ROOT / "public" / "same_name.json")

        port_map = build_strategy_port_map(profile, ["GigabitEthernet1/0/1", "TenGigabitEthernet1/1/1"])

        self.assertEqual(port_map["Gi1/0/1"].new_port, "Gi1/0/1")
        self.assertEqual(port_map["Te1/1/1"].new_port, "Te1/1/1")
        self.assertEqual(port_map["Gi1/0/1"].role, "same_name")

    def test_public_c9300_48p_profile_boundaries_load_from_disk(self):
        profile = load_json_profile(PROFILE_ROOT / "public" / "generic_c9300_48p.json")

        port_map = build_strategy_port_map(profile, ["Gi1/0/1", "Gi1/0/48", "Gi1/0/49", "Gi1/0/52"])

        self.assertEqual(port_map["Gi1/0/1"].new_port, "Gi1/0/1")
        self.assertEqual(port_map["Gi1/0/48"].new_port, "Gi1/0/48")
        self.assertEqual(port_map["Gi1/0/49"].new_port, "Te1/1/1")
        self.assertEqual(port_map["Gi1/0/52"].new_port, "Te1/1/4")

    def test_public_c9300_24p_profile_boundaries_load_from_disk(self):
        profile = load_json_profile(PROFILE_ROOT / "public" / "generic_c9300_24p.json")

        port_map = build_strategy_port_map(profile, ["Gi1/0/1", "Gi1/0/24", "Gi1/0/25", "Gi1/0/28"])

        self.assertEqual(port_map["Gi1/0/1"].new_port, "Gi1/0/1")
        self.assertEqual(port_map["Gi1/0/24"].new_port, "Gi1/0/24")
        self.assertEqual(port_map["Gi1/0/25"].new_port, "Te1/1/1")
        self.assertEqual(port_map["Gi1/0/28"].new_port, "Te1/1/4")

    def test_public_mgig_profile_can_change_access_prefix(self):
        profile = load_json_profile(PROFILE_ROOT / "public" / "generic_c9300_mgig.json")

        port_map = build_strategy_port_map(profile, ["Gi1/0/1", "Gi1/0/48", "Gi1/0/49"])

        self.assertEqual(port_map["Gi1/0/1"].new_port, "Te1/0/1")
        self.assertEqual(port_map["Gi1/0/48"].new_port, "Te1/0/48")
        self.assertEqual(port_map["Gi1/0/49"].new_port, "Te1/1/1")

    def test_public_mixed_24_48_mgig_profile_uses_member_specific_density(self):
        profile = load_json_profile(PROFILE_ROOT / "public" / "generic_mixed_24_48_to_mgig_stack.json")

        port_map = build_strategy_port_map(
            profile,
            ["Gi1/0/1", "Gi1/0/24", "Gi1/0/25", "Gi1/0/48", "Gi2/0/1", "Gi2/0/48", "Gi2/0/52"],
        )

        self.assertEqual(port_map["Gi1/0/1"].new_port, "Te1/0/1")
        self.assertEqual(port_map["Gi1/0/24"].new_port, "Te1/0/24")
        self.assertEqual(port_map["Gi1/0/25"].new_port, "Te1/1/1")
        self.assertEqual(port_map["Gi1/0/48"].new_port, "Gi1/0/48")
        self.assertEqual(port_map["Gi1/0/48"].role, "same_name")
        self.assertEqual(port_map["Gi2/0/1"].new_port, "Te2/0/1")
        self.assertEqual(port_map["Gi2/0/48"].new_port, "Te2/0/48")
        self.assertEqual(port_map["Gi2/0/52"].new_port, "Te2/1/8")

    def test_public_ie3300_profile_handles_legacy_source_names(self):
        profile = load_json_profile(PROFILE_ROOT / "public" / "generic_ie3300_standalone.json")

        port_map = build_strategy_port_map(profile, ["Gi1/1", "Fa1/2", "Gi0/8", "Gi1/9"])

        self.assertEqual(port_map["Gi1/1"].new_port, "Gi1/1")
        self.assertEqual(port_map["Fa1/2"].new_port, "Gi1/2")
        self.assertEqual(port_map["Gi0/8"].new_port, "Gi1/8")
        self.assertEqual(port_map["Gi1/9"].new_port, "Gi1/9")
        self.assertEqual(port_map["Gi0/8"].role, "legacy_access")

    def test_manual_csv_override_still_wins_over_disk_profile(self):
        profile = load_json_profile(PROFILE_ROOT / "public" / "generic_c9300_48p.json")
        manual_csv = """old_port,new_port,role,note
Gi1/0/49,Te1/1/8,uplink,operator selected alternate uplink
"""

        port_map = build_strategy_port_map(
            profile,
            ["Gi1/0/49"],
            manual_overrides=load_manual_csv_port_map(manual_csv),
        )

        self.assertEqual(port_map["Gi1/0/49"].new_port, "Te1/1/8")
        self.assertEqual(port_map["Gi1/0/49"].note, "operator selected alternate uplink")

    def test_malformed_range_fails_with_clear_error(self):
        profile = {
            "profile_name": "bad_range",
            "fallback": "same_name",
            "access_port_rules": [
                {
                    "source_range": "Gi1/0/48-1",
                    "target_range": "Gi1/0/1-48",
                    "role": "access",
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "end precedes start"):
            build_strategy_port_map(profile, ["Gi1/0/1"])


if __name__ == "__main__":
    unittest.main()
