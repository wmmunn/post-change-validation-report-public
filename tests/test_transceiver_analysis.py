import unittest
import tempfile
from pathlib import Path

import post_change_validation_reviewer as reviewer
from src.post_change_validation_analysis_wrappers import analyze_inventory

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


HEALTHY_TRANSCEIVER_SECTION = """
Te1/1/1 25.20 89.00 85.00 -5.00 -9.00
Te1/1/1 3.31 3.60 3.50 3.10 3.00
Te1/1/1 5.20 13.00 12.40 2.00 1.00
Te1/1/1 -5.26 1.00 -3.00 -9.51 -13.51
Te1/1/1 -5.11 4.00 0.00 -17.00 -21.04
"""

WARN_TRANSCEIVER_SECTION = """
Te1/1/1 86.00 89.00 85.00 -5.00 -9.00
Te1/1/1 3.31 3.60 3.50 3.10 3.00
Te1/1/1 5.20 13.00 12.40 2.00 1.00
Te1/1/1 -5.26 1.00 -3.00 -9.51 -13.51
Te1/1/1 -5.11 4.00 0.00 -17.00 -21.04
"""


class TransceiverAnalysisTests(unittest.TestCase):
    def test_healthy_compact_threshold_rows_are_info_only(self):
        pm = {
            "Gi1/0/49": reviewer.PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", "uplink A"),
            "Gi1/0/50": reviewer.PortMapRow("Gi1/0/50", "Te1/1/8", "uplink", "uplink B"),
        }
        findings = reviewer.analyze_transceivers("", HEALTHY_TRANSCEIVER_SECTION, pm)

        self.assertEqual(["INFO"], [f.severity for f in findings])
        self.assertIn("detail block", findings[0].finding)

    def test_numeric_warning_threshold_still_reports_warn(self):
        findings = reviewer.analyze_transceivers("", WARN_TRANSCEIVER_SECTION, {})

        self.assertIn("WARN", [f.severity for f in findings])


class CommandSectionParsingTests(unittest.TestCase):
    def test_normalizes_prompt_and_show_abbreviation_commands(self):
        cases = {
            "ACCESS-SW01#show int status": "show interfaces status",
            "#sho inventory": "show inventory",
            "eorwdw-wccadm-pbx-5-sw#sho inv": "show inventory",
            ">show interfaces TenGigabitEthernet1/1/1 transceiver detail": "show interfaces transceiver detail",
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(reviewer.normalize_command_line(raw), expected)

    def test_splits_sanitized_command_sections_fixture(self):
        text = (FIXTURE_ROOT / "sanitized_command_sections.log").read_text(encoding="utf-8")

        sections = reviewer.split_sections(text)

        self.assertEqual(
            sorted(sections),
            [
                "show interfaces status",
                "show interfaces transceiver detail",
                "show inventory",
                "show running-config",
                "show version",
            ],
        )
        self.assertIn("Gi1/0/1", sections["show interfaces status"])
        self.assertIn("SANITIZED1234", sections["show inventory"])
        self.assertIn("Te1/1/1", sections["show interfaces transceiver detail"])

    def test_splits_sanitized_sho_inv_inventory_fixture(self):
        text = (FIXTURE_ROOT / "sanitized_sho_inv_inventory.log").read_text(encoding="utf-8")

        sections = reviewer.split_sections(text)
        inventory = sections.get("show inventory", "")

        self.assertIn("show inventory", sections)
        self.assertIn("SANITIZED1234", inventory)
        self.assertIn("C9300-48U", inventory)

        findings = analyze_inventory(inventory)

        self.assertEqual(1, len(findings))
        self.assertEqual("Inventory", findings[0].category)
        self.assertIn("Inventory parsed:", findings[0].finding)
        self.assertTrue(findings[0].detail.startswith("component|description|pid|"))
        self.assertIn("Switch 1|C9300-48U|C9300-48U|V09|SANITIZED1234", findings[0].detail)

    def test_cdp_wrapped_device_id_with_digits_is_preserved(self):
        section = """
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
router-1.net.example
                 Gig 1/0/25       120             R S I   C9500     Twe 1/0/22
"""

        records = reviewer.parse_cdp_neighbors(section)

        self.assertEqual(1, len(records))
        self.assertEqual(records[0].neighbor, "router-1.net.example")
        self.assertEqual(records[0].local_interface, "Gi1/0/25")
        self.assertEqual(records[0].remote_interface, "Twe1/0/22")

    def test_cdp_matched_detail_uses_post_neighbor_when_pre_name_is_unknown(self):
        pre_text = """
SW1#show version
Cisco IOS XE Software, Version 17.09.04

SW1#show running-config
!
hostname cisco-access-sw01
!

SW1#show cdp neighbors
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
                 Gig 1/0/25       120             R S I   C9500     Twe 1/0/22
"""
        post_text = """
SW2#show version
Cisco IOS XE Software, Version 17.09.04

SW2#show running-config
!
hostname cisco-access-sw02
!

SW2#show cdp neighbors
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
router-1.net.example  Ten 1/1/1   120             R S I   C9500     Twe 1/0/22
"""
        csv_text = "old_port,new_port,role,note\nGi1/0/25,Te1/1/1,uplink,sanitized uplink\n"

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            tmp.write(csv_text)
            map_path = tmp.name
        try:
            findings = reviewer.analyze(pre_text, post_text, map_path)
        finally:
            Path(map_path).unlink(missing_ok=True)

        cdp_pass = [f for f in findings if f.category == "CDP Neighbors" and f.severity == "PASS"]

        self.assertEqual(1, len(cdp_pass))
        self.assertIn("router-1.net.example: Gi1/0/25 -> Te1/1/1, remote Twe1/0/22", cdp_pass[0].detail)
        self.assertNotIn("unknown:", cdp_pass[0].detail)

    def test_cdp_two_gateway_neighbors_remain_matched_after_mapping(self):
        pre_text = """
SW1#show version
Cisco IOS XE Software, Version 17.09.04

SW1#show running-config
!
hostname cisco-access-sw01
!

SW1#show cdp neighbors
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
router-1.net.location.com
                 Gig 2/0/52       120             R S I   C9500     Twe 1/0/22
router-0.net.location.com
                 Gig 1/0/25       120             R S I   C9500     Twe 1/0/22
"""
        post_text = """
SW2#show version
Cisco IOS XE Software, Version 17.09.04

SW2#show running-config
!
hostname cisco-access-sw02
!

SW2#show cdp neighbors
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
router-1.net.location.com
                 Ten 2/1/8        120             R S I   C9500     Twe 1/0/22
router-0.net.location.com
                 Ten 1/1/1        120             R S I   C9500     Twe 1/0/22
"""
        csv_text = "\n".join(
            [
                "old_port,new_port,role,note",
                "Gi2/0/52,Te2/1/8,uplink,sanitized uplink",
                "Gi1/0/25,Te1/1/1,uplink,sanitized uplink",
                "",
            ]
        )

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            tmp.write(csv_text)
            map_path = tmp.name
        try:
            findings = reviewer.analyze(pre_text, post_text, map_path)
        finally:
            Path(map_path).unlink(missing_ok=True)

        cdp_pass = [f for f in findings if f.category == "CDP Neighbors" and f.severity == "PASS"]

        self.assertEqual(1, len(cdp_pass))
        self.assertIn("2 cdp neighbor record(s) matched after change.", cdp_pass[0].finding)
        self.assertIn("router-1.net.location.com: Gi2/0/52 -> Te2/1/8, remote Twe1/0/22", cdp_pass[0].detail)
        self.assertIn("router-0.net.location.com: Gi1/0/25 -> Te1/1/1, remote Twe1/0/22", cdp_pass[0].detail)


class PortMapGenerationTests(unittest.TestCase):
    def test_auto_builds_sanitized_stack_port_map(self):
        run_cfg = (FIXTURE_ROOT / "sanitized_stack_running_config.cfg").read_text(encoding="utf-8")

        port_map, detail = reviewer.auto_build_port_map_from_running_config(run_cfg)

        self.assertEqual(port_map["Gi1/0/1"].new_port, "Gi1/0/1")
        self.assertEqual(port_map["Gi2/0/1"].new_port, "Te2/0/1")
        self.assertEqual(port_map["Gi1/0/49"].new_port, "Te1/1/1")
        self.assertEqual(port_map["Gi2/0/52"].new_port, "Te2/1/8")
        self.assertIn("Detected stack members: 1, 2", detail)

    def test_auto_builds_sanitized_standalone_industrial_port_map(self):
        run_cfg = (FIXTURE_ROOT / "sanitized_standalone_industrial_running_config.cfg").read_text(encoding="utf-8")

        port_map, detail = reviewer.auto_build_port_map_from_running_config(run_cfg)

        self.assertEqual(port_map["Gi1/1"].new_port, "Gi1/1")
        self.assertEqual(port_map["Fa1/2"].new_port, "Gi1/2")
        self.assertEqual(port_map["Gi1/3"].new_port, "Gi2/1")
        self.assertEqual(port_map["Gi0/4"].new_port, "Gi2/2")
        self.assertEqual(port_map["Gi1/3"].role, "standalone_industrial")
        self.assertIn("standalone industrial switch mapping", detail)


class ObservedNeighborOverrideTests(unittest.TestCase):
    def test_mixed_24_48_stack_trunk_inference_maps_lone_25_to_uplink_a(self):
        pm = {
            "Gi1/0/25": reviewer.PortMapRow("Gi1/0/25", "Te1/0/25", "access", "mGig access mapping"),
            "Gi1/0/49": reviewer.PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", "uplink A"),
            "Gi1/0/50": reviewer.PortMapRow("Gi1/0/50", "Te2/1/8", "uplink", "uplink B"),
            "Gi2/0/52": reviewer.PortMapRow("Gi2/0/52", "Te2/1/8", "uplink", "uplink B"),
        }
        pre_sections = {
            "show interfaces trunk": "\n".join(
                [
                    "Gi1/0/25 on 802.1q trunking 1",
                    "Gi2/0/52 on 802.1q trunking 1",
                ]
            )
        }

        inferred, _review = reviewer.infer_trunk_uplink_mappings(pre_sections, pm)

        self.assertIn("Gi1/0/25 -> Te1/1/1", "\n".join(inferred))
        self.assertEqual(pm["Gi1/0/25"].new_port, "Te1/1/1")
        self.assertEqual(pm["Gi2/0/52"].new_port, "Te2/1/8")

    def test_observed_override_does_not_duplicate_existing_uplink_target(self):
        pm = {
            "Gi1/0/25": reviewer.PortMapRow("Gi1/0/25", "Te1/1/1", "legacy_24port_uplink", "uplink A"),
            "Gi2/0/52": reviewer.PortMapRow("Gi2/0/52", "Te2/1/8", "uplink", "uplink B"),
        }
        pre_sections = {
            "show cdp neighbors": "SANITIZED-GW0 Gi2/0/52 153 R S I C9500 Te1/0/1\n",
            "show lldp neighbors": "",
            "show interfaces trunk": "Gi2/0/52 on 802.1q trunking 1\n",
        }
        post_sections = {
            "show cdp neighbors": "SANITIZED-GW0 Te1/1/1 153 R S I C9500 Te1/0/1\n",
            "show lldp neighbors": "",
            "show interfaces trunk": "Te1/1/1 on 802.1q trunking 1\n",
        }

        overrides = reviewer.apply_observed_neighbor_port_overrides(pre_sections, post_sections, pm)

        self.assertEqual([], overrides)
        self.assertEqual(pm["Gi2/0/52"].new_port, "Te2/1/8")


if __name__ == "__main__":
    unittest.main()
