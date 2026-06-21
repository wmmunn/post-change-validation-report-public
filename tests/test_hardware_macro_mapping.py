import unittest
from pathlib import Path

import tests.bootstrap  # noqa: F401

from src.port_mapping.engine import PortMappingEngine
from src.port_mapping.hardware_macro import (
    evaluate_access_prefix_from_pid,
    parse_stack_member_models_from_inventory,
)
from src.port_mapping.private.workplace_profile import WorkplaceProfile
from src.port_mapping.types import PortMapBuildRequest

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"

SANITIZED_INVENTORY_TWO_MEMBER = """
NAME: "Switch 1", DESCR: "Cisco C9300"
PID: C9300-48U       , VID: V01  , SN: SANITIZED0001
NAME: "Switch 2", DESCR: "Cisco C9300"
PID: C9300-24UX      , VID: V01  , SN: SANITIZED0002
"""

RUNNING_CONFIG_NO_PROVISION = """
interface GigabitEthernet1/0/1
 description ACCESS-PORT
 switchport access vlan 100
!
interface TenGigabitEthernet2/0/1
 description ACCESS-PORT-ON-24UX
 switchport access vlan 200
!
interface TenGigabitEthernet2/1/8
 description UPLINK-B
 switchport mode trunk
!
"""


class EvaluateAccessPrefixFromPidTests(unittest.TestCase):
    def test_c9300_24ux_maps_to_te(self):
        self.assertEqual("Te", evaluate_access_prefix_from_pid("C9300-24UX"))

    def test_c9300_24u_stays_gi(self):
        self.assertEqual("Gi", evaluate_access_prefix_from_pid("C9300-24U"))

    def test_c9300_48un_maps_to_fi(self):
        self.assertEqual("Fi", evaluate_access_prefix_from_pid("C9300-48UN"))

    def test_c9300_48u_stays_gi(self):
        self.assertEqual("Gi", evaluate_access_prefix_from_pid("C9300-48U"))

    def test_ie_3300_maps_to_gi(self):
        self.assertEqual("Gi", evaluate_access_prefix_from_pid("IE-3300-8T2S"))


class ParseStackMemberModelsFromInventoryTests(unittest.TestCase):
    def test_parses_switch_member_pid_pairs(self):
        self.assertEqual(
            {"1": "C9300-48U", "2": "C9300-24UX"},
            parse_stack_member_models_from_inventory(SANITIZED_INVENTORY_TWO_MEMBER),
        )

    def test_ignores_non_switch_components(self):
        section = """
NAME: "Chassis", DESCR: "Cisco Chassis"
PID: C9300-48U, VID: V01, SN: SANITIZED0003
NAME: "Switch 1", DESCR: "Cisco C9300"
PID: C9300-48UN, VID: V01, SN: SANITIZED0004
"""
        self.assertEqual({"1": "C9300-48UN"}, parse_stack_member_models_from_inventory(section))


class WorkplaceProfileInventoryBackfillTests(unittest.TestCase):
    def test_inventory_backfills_models_when_provision_lines_missing(self):
        rows, detail = WorkplaceProfile().build(
            RUNNING_CONFIG_NO_PROVISION,
            SANITIZED_INVENTORY_TWO_MEMBER,
        )

        self.assertEqual("Te2/0/1", rows["Gi2/0/1"].new_port)
        self.assertEqual("Gi1/0/1", rows["Gi1/0/1"].new_port)
        self.assertIn("switch 2: model=C9300-24UX, access_prefix=Te (model)", detail)

    def test_inventory_only_members_when_no_provision_or_interfaces(self):
        minimal_config = "hostname SANITIZED-SW\n!"
        rows, detail = WorkplaceProfile().build(minimal_config, SANITIZED_INVENTORY_TWO_MEMBER)

        self.assertEqual("Gi1/0/1", rows["Gi1/0/1"].new_port)
        self.assertEqual("Te2/0/1", rows["Gi2/0/1"].new_port)
        self.assertIn("Detected stack members: 1, 2", detail)


class ManualCsvOverridesInventoryTests(unittest.TestCase):
    def test_manual_csv_overrides_inventory_derived_mapping(self):
        manual_csv_text = "old_port,new_port,role,note\nGi2/0/1,Gi9/9/9,access,manual override\n"
        result = PortMappingEngine().build(
            PortMapBuildRequest(
                running_config=RUNNING_CONFIG_NO_PROVISION,
                inventory_section=SANITIZED_INVENTORY_TWO_MEMBER,
                manual_csv_text=manual_csv_text,
                use_workplace_profile=True,
            )
        )

        self.assertEqual("Gi9/9/9", result.rows["Gi2/0/1"].new_port)
        self.assertEqual("Te2/0/2", result.rows["Gi2/0/2"].new_port)


if __name__ == "__main__":
    unittest.main()
