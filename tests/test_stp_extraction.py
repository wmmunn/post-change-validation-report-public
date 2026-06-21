import unittest
from dataclasses import dataclass

from src.post_change_validation_stp import (
    STP_INFO_VLAN_NOTES,
    STP_INFO_VLANS,
    STPRootRecord,
    access_ports_in_vlan,
    compare_stp_topology,
    interface_block,
    parse_stp_path_cost_method,
    parse_stp_root,
    stp_cost_change_note,
    stp_vlan1_local_root_context,
    svi_is_shutdown,
)


@dataclass
class InterfaceStatusStub:
    vlan: str = ""
    speed: str = ""
    type_: str = ""


class StpExtractionTests(unittest.TestCase):
    def test_parse_stp_root_normalizes_vlan_and_root_port(self):
        section = """
VLAN0001 32769 0011.2233.4455 4 128.1 P2p Root GigabitEthernet1/0/49
VLAN4    32772 00AA.BBCC.DDEE 0 0      -   local
"""

        records = parse_stp_root(section)

        self.assertEqual(["VLAN0001", "VLAN0004"], sorted(records))
        self.assertEqual("32769 0011.2233.4455", records["VLAN0001"].root_id)
        self.assertEqual("Gi1/0/49", records["VLAN0001"].root_port)
        self.assertEqual("32772 00aa.bbcc.ddee", records["VLAN0004"].root_id)

    def test_parse_stp_path_cost_method_uses_summary_or_running_config(self):
        self.assertEqual("long", parse_stp_path_cost_method("Pathcost method used is long"))
        self.assertEqual("short", parse_stp_path_cost_method("", "spanning-tree path-cost method short"))

    def test_stp_cost_change_note_includes_method_and_port_evidence(self):
        pre = STPRootRecord("VLAN0001", "32769 0011.2233.4455", 4, "Gi1/0/49")
        post = STPRootRecord("VLAN0001", "32769 0011.2233.4455", 2000, "Te1/1/1")
        post_if = {"Te1/1/1": InterfaceStatusStub(speed="a-10G", type_="SFP-10G")}

        note = stp_cost_change_note(pre, post, "short", "long", post_if)

        self.assertIn("STP path-cost method: pre=short, post=long.", note)
        self.assertIn("Post root port evidence: Te1/1/1 speed=a-10G type=SFP-10G.", note)
        self.assertIn("Cost change 4 -> 2000 is consistent", note)

    def test_vlan1_shutdown_context_counts_access_ports(self):
        running_config = """
interface Vlan1
 description unused local vlan
 shutdown
interface Vlan4
 no shutdown
"""
        post_if = {
            "Gi1/0/1": InterfaceStatusStub(vlan="1"),
            "Gi1/0/2": InterfaceStatusStub(vlan="1"),
            "Gi1/0/3": InterfaceStatusStub(vlan="4"),
        }

        self.assertIn("description unused local vlan", interface_block(running_config, "Vlan1"))
        self.assertTrue(svi_is_shutdown(running_config, "VLAN0001"))
        self.assertEqual(2, access_ports_in_vlan(post_if, "VLAN0001"))
        self.assertIn("2 post-change access/status port(s)", stp_vlan1_local_root_context("VLAN0001", running_config, post_if))

    def test_compare_stp_topology_reports_retained_mapped_root_port(self):
        pre = {"VLAN0001": STPRootRecord("VLAN0001", "32769 0011.2233.4455", 4, "Gi1/0/49")}
        post = {"VLAN0001": STPRootRecord("VLAN0001", "32769 0011.2233.4455", 2000, "Te1/1/1")}

        comparison = compare_stp_topology(pre, post, {"Gi1/0/49": "Te1/1/1"}, "short", "long", "", {})

        self.assertEqual([], comparison.warn_items)
        self.assertEqual([], comparison.info_items)
        self.assertEqual(1, len(comparison.pass_items))
        self.assertIn("root unchanged and root port mapped (Gi1/0/49 -> Te1/1/1); cost changed 4 -> 2000", comparison.pass_items[0])
        self.assertIn("STP path-cost method: pre=short, post=long.", comparison.pass_items[0])

    def test_compare_stp_topology_warns_for_unexpected_root_port_change(self):
        pre = {"VLAN0001": STPRootRecord("VLAN0001", "32769 0011.2233.4455", 4, "Gi1/0/49")}
        post = {"VLAN0001": STPRootRecord("VLAN0001", "32769 0011.2233.4455", 4, "Te1/1/8")}

        comparison = compare_stp_topology(pre, post, {"Gi1/0/49": "Te1/1/1"}, "", "", "", {})

        self.assertEqual([], comparison.pass_items)
        self.assertEqual([], comparison.info_items)
        self.assertEqual(1, len(comparison.warn_items))
        self.assertIn("expected post=Te1/1/1, actual post=Te1/1/8", comparison.warn_items[0])

    def test_compare_stp_topology_public_default_warns_for_vlan4_root_change(self):
        pre = {"VLAN0004": STPRootRecord("VLAN0004", "32772 0011.2233.4455", 4, "Gi1/0/49")}
        post = {"VLAN0004": STPRootRecord("VLAN0004", "32772 00aa.bbcc.ddee", 0, "")}

        comparison = compare_stp_topology(pre, post, {}, "", "", "", {})

        self.assertEqual([], comparison.pass_items)
        self.assertEqual([], comparison.info_items)
        self.assertEqual(1, len(comparison.warn_items))
        self.assertIn("root bridge changed", comparison.warn_items[0])

    def test_compare_stp_topology_allows_private_vlan4_informational_override(self):
        pre = {"VLAN0004": STPRootRecord("VLAN0004", "32772 0011.2233.4455", 4, "Gi1/0/49")}
        post = {"VLAN0004": STPRootRecord("VLAN0004", "32772 00aa.bbcc.ddee", 0, "")}

        comparison = compare_stp_topology(pre, post, {}, "", "", "", {}, STP_INFO_VLANS, STP_INFO_VLAN_NOTES)

        self.assertEqual([], comparison.pass_items)
        self.assertEqual([], comparison.warn_items)
        self.assertEqual(1, len(comparison.info_items))
        self.assertIn("classified as security isolation/remediation VLAN", comparison.info_items[0])

    def test_compare_stp_topology_keeps_vlan1_shutdown_local_root_informational(self):
        running_config = """
interface Vlan1
 shutdown
"""
        pre = {"VLAN0001": STPRootRecord("VLAN0001", "32769 0011.2233.4455", 4, "Gi1/0/49")}
        post = {"VLAN0001": STPRootRecord("VLAN0001", "32769 00aa.bbcc.ddee", 0, "")}

        comparison = compare_stp_topology(pre, post, {}, "", "", running_config, {})

        self.assertEqual([], comparison.pass_items)
        self.assertEqual([], comparison.warn_items)
        self.assertEqual(1, len(comparison.info_items))
        self.assertIn("local switch became root post-change, but classified as informational based on VLAN 1 context", comparison.info_items[0])


if __name__ == "__main__":
    unittest.main()
