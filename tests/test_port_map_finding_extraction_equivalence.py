import unittest

from src.post_change_validation_analysis_wrappers import analyze_port_map_findings
from src.post_change_validation_models import Finding, PortMapRow


def legacy_analyze_port_map_findings(
    pm: dict[str, PortMapRow],
    port_map_source: str,
    port_map_detail: str,
) -> list[Finding]:
    findings: list[Finding] = []
    if pm:
        findings.append(Finding("INFO", "Port Map", f"Port map loaded with {len(pm)} old-to-new mapping row(s).", f"{port_map_source}\n{port_map_detail}"))
    else:
        findings.append(Finding("WARN", "Port Map", "No port map could be generated or loaded.", f"{port_map_source}\n{port_map_detail}"))
    return findings


class PortMapFindingExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_matches_legacy_for_info_loaded_port_map(self):
        pm = {
            "Gi1/0/1": PortMapRow("Gi1/0/1", "Te1/0/1", "access", "row one"),
            "Gi1/0/2": PortMapRow("Gi1/0/2", "Te1/0/2", "access", "row two"),
        }
        source = "Auto-detected from post-change running-config"
        detail = "Auto-built from running-config."

        legacy = legacy_analyze_port_map_findings(pm, source, detail)
        extracted = analyze_port_map_findings(pm, source, detail)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["INFO"], [finding.severity for finding in extracted])
        self.assertIn("Port map loaded with 2 old-to-new mapping row(s).", extracted[0].finding)

    def test_extracted_matches_legacy_for_warn_missing_port_map(self):
        source = "Auto-detected from post-change running-config"
        detail = "No interfaces found in running-config."

        legacy = legacy_analyze_port_map_findings({}, source, detail)
        extracted = analyze_port_map_findings({}, source, detail)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["WARN"], [finding.severity for finding in extracted])
        self.assertEqual("No port map could be generated or loaded.", extracted[0].finding)


if __name__ == "__main__":
    unittest.main()
