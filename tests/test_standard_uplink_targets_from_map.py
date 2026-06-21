import unittest

from src.post_change_validation_analysis_wrappers import (
    StandardUplinkTargetsResult,
    uplink_fallback_review_finding,
    standard_uplink_targets_from_map,
)
from src.post_change_validation_models import PortMapRow

SANITIZED_INVENTORY_C9300 = """
NAME: "Switch 1", DESCR: "Cisco C9300"
PID: C9300-48U       , VID: V01  , SN: SANITIZED0001
"""

SANITIZED_VERSION_C9300 = """
Cisco IOS XE Software, Version 17.09.04
cisco C9300-48U (K9M) processor with 1398091K/6147K bytes of memory.
"""

SANITIZED_TRANSCEIVER_BOTH_UPLINKS = """
Te1/1/1 25.20 89.00 85.00 -5.00 -9.00
Te1/1/8 25.10 89.00 85.00 -5.00 -9.00
"""

SANITIZED_TRANSCEIVER_MISSING_B = """
Te1/1/1 25.20 89.00 85.00 -5.00 -9.00
"""

SANITIZED_TRANSCEIVER_MISSING_A = """
Te1/1/8 25.10 89.00 85.00 -5.00 -9.00
"""

SANITIZED_TRANSCEIVER_ONLY_B = """
Te1/1/8 25.10 89.00 85.00 -5.00 -9.00
"""

SANITIZED_TRANSCEIVER_ONLY_A = """
Te1/1/1 25.20 89.00 85.00 -5.00 -9.00
"""


class StandardUplinkTargetsFromMapTests(unittest.TestCase):
    def test_case_a_map_with_both_uplink_a_and_b_rows(self):
        pm = {
            "Gi1/0/49": PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", "uplink A"),
            "Gi1/0/50": PortMapRow("Gi1/0/50", "Te2/1/8", "uplink", "uplink B"),
        }

        result = standard_uplink_targets_from_map(pm)

        self.assertEqual(StandardUplinkTargetsResult("Te1/1/1", "Te2/1/8"), result)

    def test_case_b_fallback_with_evidence_returns_default_targets(self):
        pm = {
            "Gi1/0/1": PortMapRow("Gi1/0/1", "Te1/0/1", "access", "access mapping"),
        }

        result = standard_uplink_targets_from_map(
            pm,
            version_section=SANITIZED_VERSION_C9300,
            inventory_section=SANITIZED_INVENTORY_C9300,
            transceiver_section=SANITIZED_TRANSCEIVER_BOTH_UPLINKS,
        )

        self.assertEqual(StandardUplinkTargetsResult("Te1/1/1", "Te1/1/8"), result)

    def test_case_c_map_with_only_uplink_a_falls_back_b_to_te1_1_8(self):
        pm = {
            "Gi0/15": PortMapRow("Gi0/15", "Te3/1/1", "legacy_uplink", "uplink A mapping"),
        }

        result = standard_uplink_targets_from_map(
            pm,
            version_section=SANITIZED_VERSION_C9300,
            inventory_section=SANITIZED_INVENTORY_C9300,
            transceiver_section=SANITIZED_TRANSCEIVER_ONLY_B,
        )

        self.assertEqual(StandardUplinkTargetsResult("Te3/1/1", "Te1/1/8"), result)

    def test_case_c_map_with_only_uplink_b_falls_back_a_to_te1_1_1(self):
        pm = {
            "Gi0/16": PortMapRow("Gi0/16", "Te3/1/8", "legacy_uplink", "uplink B mapping"),
        }

        result = standard_uplink_targets_from_map(
            pm,
            version_section=SANITIZED_VERSION_C9300,
            inventory_section=SANITIZED_INVENTORY_C9300,
            transceiver_section=SANITIZED_TRANSCEIVER_ONLY_A,
        )

        self.assertEqual(StandardUplinkTargetsResult("Te1/1/1", "Te3/1/8"), result)

    def test_partial_fallback_unknown_platform_returns_no_targets_and_review_reason(self):
        pm = {
            "Gi0/15": PortMapRow("Gi0/15", "Te3/1/1", "legacy_uplink", "uplink A mapping"),
        }

        result = standard_uplink_targets_from_map(
            pm,
            version_section="Cisco IOS Software, Version 15.2(7)E",
            inventory_section='NAME: "Switch 1", DESCR: "Cisco WS-C3750X"\nPID: WS-C3750X-48T-S, VID: V05, SN: SANITIZED3750',
            transceiver_section=SANITIZED_TRANSCEIVER_ONLY_B,
        )

        self.assertEqual(StandardUplinkTargetsResult("", "", result.review_reason), result)
        self.assertIn("unsupported platform", result.review_reason.lower())
        self.assertIn("Te1/1/8", result.review_reason)

    def test_partial_fallback_missing_transceiver_for_default_side_returns_no_targets(self):
        pm = {
            "Gi0/15": PortMapRow("Gi0/15", "Te3/1/1", "legacy_uplink", "uplink A mapping"),
        }

        result = standard_uplink_targets_from_map(
            pm,
            version_section=SANITIZED_VERSION_C9300,
            inventory_section=SANITIZED_INVENTORY_C9300,
            transceiver_section=SANITIZED_TRANSCEIVER_MISSING_B,
        )

        self.assertEqual("", result.uplink_a)
        self.assertEqual("", result.uplink_b)
        self.assertIn("transceiver detail", result.review_reason.lower())
        self.assertIn("Te1/1/8", result.review_reason)

    def test_partial_fallback_missing_transceiver_for_default_a_returns_no_targets(self):
        pm = {
            "Gi0/16": PortMapRow("Gi0/16", "Te3/1/8", "legacy_uplink", "uplink B mapping"),
        }

        result = standard_uplink_targets_from_map(
            pm,
            version_section=SANITIZED_VERSION_C9300,
            inventory_section=SANITIZED_INVENTORY_C9300,
            transceiver_section=SANITIZED_TRANSCEIVER_MISSING_A,
        )

        self.assertEqual("", result.uplink_a)
        self.assertEqual("", result.uplink_b)
        self.assertIn("transceiver detail", result.review_reason.lower())
        self.assertIn("Te1/1/1", result.review_reason)

    def test_fallback_unknown_platform_returns_no_targets_and_review_reason(self):
        pm = {
            "Gi1/0/1": PortMapRow("Gi1/0/1", "Te1/0/1", "access", "access mapping"),
        }

        result = standard_uplink_targets_from_map(
            pm,
            version_section="Cisco IOS Software, Version 15.2(7)E",
            inventory_section='NAME: "Switch 1", DESCR: "Cisco WS-C3750X"\nPID: WS-C3750X-48T-S, VID: V05, SN: SANITIZED3750',
            transceiver_section=SANITIZED_TRANSCEIVER_BOTH_UPLINKS,
        )

        self.assertEqual(StandardUplinkTargetsResult("", "", result.review_reason), result)
        self.assertIn("unsupported platform", result.review_reason.lower())

    def test_fallback_known_platform_missing_transceiver_returns_no_targets(self):
        pm = {
            "Gi1/0/1": PortMapRow("Gi1/0/1", "Te1/0/1", "access", "access mapping"),
        }

        result = standard_uplink_targets_from_map(
            pm,
            version_section=SANITIZED_VERSION_C9300,
            inventory_section=SANITIZED_INVENTORY_C9300,
            transceiver_section=SANITIZED_TRANSCEIVER_MISSING_B,
        )

        self.assertEqual("", result.uplink_a)
        self.assertEqual("", result.uplink_b)
        self.assertIn("transceiver detail", result.review_reason.lower())

    def test_review_finding_uses_warn_port_map_category(self):
        finding = uplink_fallback_review_finding("manual review required")

        self.assertEqual("WARN", finding.severity)
        self.assertEqual("Port Map", finding.category)
        self.assertIn("fallback unavailable", finding.finding.lower())


if __name__ == "__main__":
    unittest.main()
