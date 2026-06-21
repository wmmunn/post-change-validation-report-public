import unittest
from typing import Dict, Optional, Set

from src.post_change_validation_analysis_wrappers import analyze_access_port_mac_correlation
from src.post_change_validation_mac import mac_correlation_rows
from src.post_change_validation_models import Finding, PortMapRow


def legacy_analyze_access_port_mac_correlation(
    pre_mac_section: str,
    post_mac_section: str,
    pm: Dict[str, PortMapRow],
    exclude_old_ports: Optional[Set[str]] = None,
) -> list[Finding]:
    if not pm:
        return []
    mac_rows, mac_counts = mac_correlation_rows(pre_mac_section, post_mac_section, pm, exclude_old_ports)
    if mac_counts.get("TOTAL", 0):
        summary = (
            f"Access-port MACs checked: {mac_counts.get('TOTAL', 0)}; "
            f"present on expected port: {mac_counts.get('PASS', 0)}; "
            f"missing: {mac_counts.get('MISSING', 0)}; "
            f"present on non-inferred port: {mac_counts.get('MOVED', 0)}."
        )
        sev = "WARN" if mac_counts.get("MISSING", 0) or mac_counts.get("MOVED", 0) else "PASS"
        detail = "status|mac|vlan|pre_port|expected_post_port|actual_post_port|note\n" + "\n".join(mac_rows)
        return [Finding(sev, "Access Port MAC Correlation", summary, detail)]
    return [Finding("INFO", "Access Port MAC Correlation", "No pre-change local access-port MACs were available to correlate.", "This may mean the MAC table section was missing, empty, aged out, or only contained trunk-learned MACs.")]


def _access_port_map() -> Dict[str, PortMapRow]:
    return {
        "Gi1/0/1": PortMapRow("Gi1/0/1", "Gi2/0/1", "access", ""),
        "Gi1/0/2": PortMapRow("Gi1/0/2", "Gi2/0/2", "access", ""),
        "Gi1/0/3": PortMapRow("Gi1/0/3", "Gi2/0/3", "access", ""),
        "Gi1/0/49": PortMapRow("Gi1/0/49", "Te1/1/1", "uplink", ""),
    }


class AccessPortMacCorrelationFindingExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_analyze_access_port_mac_correlation_matches_legacy_for_pass_all_on_mapped_ports(self):
        pre = """
 10     aaaa.bbbb.0001    DYNAMIC     Gi1/0/1
 10     aaaa.bbbb.0002    DYNAMIC     Gi1/0/2
"""
        post = """
 10     aaaa.bbbb.0001    DYNAMIC     Gi2/0/1
 10     aaaa.bbbb.0002    DYNAMIC     Gi2/0/2
"""
        port_map = _access_port_map()

        legacy = legacy_analyze_access_port_mac_correlation(pre, post, port_map)
        extracted = analyze_access_port_mac_correlation(pre, post, port_map)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["PASS"], [finding.severity for finding in extracted])
        self.assertIn("present on expected port: 2", extracted[0].finding)

    def test_extracted_analyze_access_port_mac_correlation_matches_legacy_for_warn_missing(self):
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
        port_map = _access_port_map()

        legacy = legacy_analyze_access_port_mac_correlation(pre, post, port_map)
        extracted = analyze_access_port_mac_correlation(pre, post, port_map)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["WARN"], [finding.severity for finding in extracted])
        self.assertIn("missing: 1", extracted[0].finding)

    def test_extracted_analyze_access_port_mac_correlation_matches_legacy_for_warn_moved(self):
        pre = " 10     aaaa.bbbb.0002    DYNAMIC     Gi1/0/2\n"
        post = " 10     aaaa.bbbb.0002    DYNAMIC     Gi2/0/9\n"
        port_map = _access_port_map()

        legacy = legacy_analyze_access_port_mac_correlation(pre, post, port_map)
        extracted = analyze_access_port_mac_correlation(pre, post, port_map)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["WARN"], [finding.severity for finding in extracted])
        self.assertIn("present on non-inferred port: 1", extracted[0].finding)

    def test_extracted_analyze_access_port_mac_correlation_matches_legacy_for_info_no_correlatable_macs(self):
        pre = " 10     aaaa.bbbb.9999    DYNAMIC     Gi1/0/49\n"
        post = " 10     aaaa.bbbb.9999    DYNAMIC     Te1/1/1\n"
        port_map = _access_port_map()

        legacy = legacy_analyze_access_port_mac_correlation(pre, post, port_map)
        extracted = analyze_access_port_mac_correlation(pre, post, port_map)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["INFO"], [finding.severity for finding in extracted])
        self.assertEqual(
            "No pre-change local access-port MACs were available to correlate.",
            extracted[0].finding,
        )

    def test_extracted_analyze_access_port_mac_correlation_matches_legacy_for_silent_empty_pm(self):
        pre = " 10     aaaa.bbbb.0001    DYNAMIC     Gi1/0/1\n"
        post = " 10     aaaa.bbbb.0001    DYNAMIC     Gi2/0/1\n"

        legacy = legacy_analyze_access_port_mac_correlation(pre, post, {})
        extracted = analyze_access_port_mac_correlation(pre, post, {})

        self.assertEqual(legacy, extracted)
        self.assertEqual([], extracted)

    def test_extracted_analyze_access_port_mac_correlation_matches_legacy_for_exclude_old_ports_uplink_exclusion(self):
        pre = " 10     aaaa.bbbb.0001    DYNAMIC     Gi1/1\n"
        post = " 10     aaaa.bbbb.0001    DYNAMIC     Gi2/1\n"
        port_map = {"Gi1/1": PortMapRow("Gi1/1", "Gi2/1", "standalone_industrial", "")}
        exclude_old_ports = {"Gi1/1"}

        legacy_excluded = legacy_analyze_access_port_mac_correlation(pre, post, port_map, exclude_old_ports)
        extracted_excluded = analyze_access_port_mac_correlation(pre, post, port_map, exclude_old_ports)
        legacy_included = legacy_analyze_access_port_mac_correlation(pre, post, port_map)
        extracted_included = analyze_access_port_mac_correlation(pre, post, port_map)

        self.assertEqual(legacy_excluded, extracted_excluded)
        self.assertEqual(legacy_included, extracted_included)
        self.assertEqual(["INFO"], [finding.severity for finding in extracted_excluded])
        self.assertEqual(["PASS"], [finding.severity for finding in extracted_included])


if __name__ == "__main__":
    unittest.main()
