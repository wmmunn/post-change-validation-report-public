import tempfile
import unittest
from pathlib import Path

import post_change_validation_reviewer as reviewer


class PoeNeighborInteractionTests(unittest.TestCase):
    def test_analyze_downgrades_missing_neighbor_when_mapped_post_port_has_poe_evidence(self):
        pre_text = """
SW1#show version
Cisco IOS XE Software, Version 17.09.04

SW1#show cdp neighbors
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
phone-1.example  Gig 1/0/3        120        H           PHONE     Gig 0/1

SW1#show power inline
Interface Admin Oper Power Device Class Max
Gi1/0/3 auto on 6.3 IP Phone 3 30.0
"""
        post_text = """
SW2#show version
Cisco IOS XE Software, Version 17.09.04

SW2#show cdp neighbors
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID

SW2#show power inline
Interface Admin Oper Power Device Class Max
Te1/0/3 auto delivering 6.1 IP Phone 3 30.0
"""
        csv_text = "old_port,new_port,role,note\nGi1/0/3,Te1/0/3,access,sanitized phone\n"

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            tmp.write(csv_text)
            map_path = tmp.name
        try:
            findings = reviewer.analyze(pre_text, post_text, map_path)
        finally:
            Path(map_path).unlink(missing_ok=True)

        cdp_neighbor_findings = [
            f
            for f in findings
            if f.category == "CDP Neighbors" and "endpoint evidence is present on the mapped port" in f.finding
        ]

        self.assertEqual(["INFO"], [f.severity for f in cdp_neighbor_findings])
        self.assertIn("endpoint evidence is present on the mapped port", cdp_neighbor_findings[0].finding)
        self.assertIn("PoE still delivering on mapped post port", cdp_neighbor_findings[0].detail)


if __name__ == "__main__":
    unittest.main()
