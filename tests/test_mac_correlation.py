import unittest

from src.post_change_validation_mac import (
    count_macs,
    mac_correlation_rows,
    mac_expected_present_ports,
    observed_mac_local_map,
    parse_mac_address_table,
)
from src.post_change_validation_models import PortMapRow


class MacCorrelationTests(unittest.TestCase):
    def test_parse_mac_address_table_keeps_interface_rows_only(self):
        section = """
Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
 10     AABB.CCDD.EEFF    DYNAMIC     GigabitEthernet1/0/3
 20     0011.2233.4455    STATIC      CPU
 All    ffff.ffff.ffff    STATIC      Drop
"""

        entries = parse_mac_address_table(section)

        self.assertEqual(1, len(entries))
        self.assertEqual("10", entries[0].vlan)
        self.assertEqual("aabb.ccdd.eeff", entries[0].mac)
        self.assertEqual("Gi1/0/3", entries[0].port)
        self.assertEqual(3, count_macs(section))

    def test_mac_correlation_reports_pass_moved_and_missing(self):
        pre = """
 10     aaaa.bbbb.0001    DYNAMIC     Gi1/0/1
 10     aaaa.bbbb.0002    DYNAMIC     Gi1/0/2
 10     aaaa.bbbb.0003    DYNAMIC     Gi1/0/3
 10     aaaa.bbbb.9999    DYNAMIC     Gi1/0/49
"""
        post = """
 10     aaaa.bbbb.0001    DYNAMIC     Gi2/0/1
 10     aaaa.bbbb.0002    DYNAMIC     Gi2/0/9
"""
        port_map = {
            "Gi1/0/1": PortMapRow("Gi1/0/1", "Gi2/0/1", "access", ""),
            "Gi1/0/2": PortMapRow("Gi1/0/2", "Gi2/0/2", "access", ""),
            "Gi1/0/3": PortMapRow("Gi1/0/3", "Gi2/0/3", "access", ""),
            "Gi1/0/49": PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", ""),
        }

        rows, counts = mac_correlation_rows(pre, post, port_map)

        self.assertEqual({"PASS": 1, "MISSING": 1, "MOVED": 1, "DUPLICATE": 0, "TOTAL": 3}, counts)
        self.assertEqual(
            [
                "PASS|aaaa.bbbb.0001|10|Gi1/0/1|Gi2/0/1|Gi2/0/1|Present on expected mapped access port",
                "MOVED|aaaa.bbbb.0002|10|Gi1/0/2|Gi2/0/2|Gi2/0/9|MAC found post-change on a different port than the inferred map; review only if exact port placement was required",
                "MISSING|aaaa.bbbb.0003|10|Gi1/0/3|Gi2/0/3|Not found|MAC from old local access port not found post-change",
            ],
            rows,
        )
        self.assertEqual({"Gi2/0/1": 1}, mac_expected_present_ports(pre, post, port_map))
        self.assertEqual({"Gi1/0/1": "Gi2/0/1", "Gi1/0/2": "Gi2/0/9"}, observed_mac_local_map(pre, post, port_map))

    def test_observed_mac_local_map_ignores_tied_post_ports(self):
        pre = " 10     aaaa.bbbb.0001    DYNAMIC     Gi1/0/1\n"
        post = """
 10     aaaa.bbbb.0001    DYNAMIC     Gi2/0/1
 10     aaaa.bbbb.0001    DYNAMIC     Gi2/0/2
"""
        port_map = {"Gi1/0/1": PortMapRow("Gi1/0/1", "Gi2/0/1", "access", "")}

        self.assertEqual({}, observed_mac_local_map(pre, post, port_map))


if __name__ == "__main__":
    unittest.main()
