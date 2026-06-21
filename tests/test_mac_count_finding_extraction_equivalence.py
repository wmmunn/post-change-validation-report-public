import unittest

from src.post_change_validation_analysis_wrappers import analyze_mac_count
from src.post_change_validation_mac import count_macs
from src.post_change_validation_models import Finding


def _mac_table_rows(prefix: str, count: int) -> str:
    lines = ["Vlan    Mac Address       Type        Ports"]
    for idx in range(count):
        octet = f"{idx % 256:02x}"
        lines.append(f"10    {octet}{octet}.{octet}{octet}.{octet}{octet}    DYNAMIC     {prefix}{idx % 48 + 1}")
    return "\n".join(lines)


def legacy_analyze_mac_count(pre_mac_section: str, post_mac_section: str) -> list[Finding]:
    pre_mac = count_macs(pre_mac_section)
    post_mac = count_macs(post_mac_section)
    if pre_mac and post_mac:
        if post_mac < max(1, int(pre_mac * 0.6)):
            return [Finding("WARN", "MAC Table", f"MAC address count dropped from {pre_mac} to {post_mac}.", "")]
        return [Finding("PASS", "MAC Table", f"MAC address count acceptable: {pre_mac} before, {post_mac} after.", "")]
    return []


class MacCountFindingExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_analyze_mac_count_matches_legacy_for_pass_acceptable_ratio(self):
        pre = _mac_table_rows("Gi1/0/", 100)
        post = _mac_table_rows("Te1/0/", 70)

        legacy = legacy_analyze_mac_count(pre, post)
        extracted = analyze_mac_count(pre, post)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["PASS"], [finding.severity for finding in extracted])
        self.assertEqual("MAC address count acceptable: 100 before, 70 after.", extracted[0].finding)

    def test_extracted_analyze_mac_count_matches_legacy_for_warn_drop_below_60_percent(self):
        pre = _mac_table_rows("Gi1/0/", 100)
        post = _mac_table_rows("Te1/0/", 50)

        legacy = legacy_analyze_mac_count(pre, post)
        extracted = analyze_mac_count(pre, post)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["WARN"], [finding.severity for finding in extracted])
        self.assertEqual("MAC address count dropped from 100 to 50.", extracted[0].finding)

    def test_extracted_analyze_mac_count_matches_legacy_for_silent_when_missing_evidence(self):
        pre = _mac_table_rows("Gi1/0/", 100)
        post = ""

        legacy = legacy_analyze_mac_count(pre, post)
        extracted = analyze_mac_count(pre, post)

        self.assertEqual(legacy, extracted)
        self.assertEqual([], extracted)


if __name__ == "__main__":
    unittest.main()
