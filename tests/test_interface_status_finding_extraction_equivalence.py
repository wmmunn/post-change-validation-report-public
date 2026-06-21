import unittest
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

from src.post_change_validation_analysis_wrappers import analyze_interface_status
from src.post_change_validation_interface_status import (
    build_uncovered_connected_detail_lines,
    compare_mapped_interface_status,
)
from src.post_change_validation_models import Finding, PortMapRow


@dataclass
class StatusRow:
    port: str
    status: str
    raw: str = ""
    vlan: str = "1"


def status(port: str, state: str, vlan: str = "1") -> StatusRow:
    return StatusRow(
        port=port,
        status=state,
        raw=f"{port} {state} {vlan} a-full a-1000 10/100/1000BaseTX",
        vlan=vlan,
    )


def legacy_interface_status_value(if_map: Mapping[str, StatusRow], port: str) -> str:
    entry = if_map.get(port)
    return entry.status if entry else "missing"


def legacy_analyze_interface_status(
    pre_if: Dict[str, StatusRow],
    post_if: Dict[str, StatusRow],
    pm: Optional[Dict[str, PortMapRow]],
    observed_neighbor_ports: Optional[Dict[str, str]] = None,
    observed_mac_ports: Optional[Dict[str, str]] = None,
    post_running_config: str = "",
    post_trunks: Optional[set[str]] = None,
) -> list[Finding]:
    findings: list[Finding] = []
    if pm:
        interface_status = compare_mapped_interface_status(
            pre_if,
            post_if,
            pm,
            observed_neighbor_ports=observed_neighbor_ports,
            observed_mac_ports=observed_mac_ports,
        )
        if interface_status.connected_warn:
            findings.append(Finding("WARN", "Interface Status", f"{len(interface_status.connected_warn)} mapped port issue(s) require review.", "\n".join(interface_status.connected_warn)))
        if interface_status.connected_pass:
            findings.append(Finding("PASS", "Interface Status", f"{len(interface_status.connected_pass)} mapped connected port(s) remained connected after change.", "\n".join(interface_status.connected_pass)))
        if interface_status.unchanged_down:
            findings.append(Finding("INFO", "Interface Status", f"{interface_status.unchanged_down} mapped port(s) remained not connected/disabled.", "Suppressed detailed unchanged-down rows."))
        if interface_status.uncovered_connected:
            uncovered_detail = "\n".join(
                build_uncovered_connected_detail_lines(
                    interface_status.uncovered_connected,
                    post_if,
                    post_running_config=post_running_config,
                    post_trunks=post_trunks,
                )
            )
            findings.append(
                Finding(
                    "INFO",
                    "Interface Status",
                    f"{len(interface_status.uncovered_connected)} connected post-change port(s) were not covered by the port map.",
                    uncovered_detail,
                )
            )
    else:
        missing = [p for p, st in pre_if.items() if st.status == "connected" and legacy_interface_status_value(post_if, p) != "connected"]
        new = [p for p, st in post_if.items() if st.status == "connected" and legacy_interface_status_value(pre_if, p) != "connected"]
        if missing:
            findings.append(Finding("WARN", "Interface Status", f"{len(missing)} port(s) were connected before but not connected after.", "\n".join(missing)))
        if new:
            findings.append(Finding("INFO", "Interface Status", f"{len(new)} port(s) are newly connected after change.", "\n".join(new)))
    return findings


class InterfaceStatusFindingExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_matches_legacy_for_mapped_connected_pass(self):
        pre_if = {"Gi1/0/1": status("Gi1/0/1", "connected")}
        post_if = {"Te1/0/1": status("Te1/0/1", "connected")}
        pm = {"Gi1/0/1": PortMapRow("Gi1/0/1", "Te1/0/1", "access", "mGig access mapping")}

        legacy = legacy_analyze_interface_status(pre_if, post_if, pm)
        extracted = analyze_interface_status(pre_if, post_if, pm)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["PASS"], [finding.severity for finding in extracted])
        self.assertIn("1 mapped connected port(s) remained connected after change", extracted[0].finding)

    def test_extracted_matches_legacy_for_mapped_connected_warn(self):
        pre_if = {"Gi1/0/2": status("Gi1/0/2", "connected")}
        post_if = {"Te1/0/2": status("Te1/0/2", "notconnect")}
        pm = {"Gi1/0/2": PortMapRow("Gi1/0/2", "Te1/0/2", "access", "operator review")}

        legacy = legacy_analyze_interface_status(pre_if, post_if, pm)
        extracted = analyze_interface_status(pre_if, post_if, pm)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["WARN"], [finding.severity for finding in extracted])
        self.assertIn("mapped port issue(s) require review", extracted[0].finding)
        self.assertIn("was connected before, now notconnect", extracted[0].detail)

    def test_extracted_matches_legacy_for_uncovered_connected_info(self):
        pre_if = {"Gi1/0/5": status("Gi1/0/5", "connected")}
        post_if = {
            "Te1/0/5": status("Te1/0/5", "connected"),
            "Te1/0/6": status("Te1/0/6", "connected"),
        }
        pm = {"Gi1/0/5": PortMapRow("Gi1/0/5", "Te1/0/5", "access", "")}

        legacy = legacy_analyze_interface_status(pre_if, post_if, pm)
        extracted = analyze_interface_status(pre_if, post_if, pm)

        self.assertEqual(legacy, extracted)
        info_findings = [finding for finding in extracted if finding.severity == "INFO" and "not covered by the port map" in finding.finding]
        self.assertEqual(1, len(info_findings))
        self.assertIn("uncovered -> Te1/0/6 role=access: connected", info_findings[0].detail)
        self.assertIn("post=Te1/0/6 connected", info_findings[0].detail)

    def test_extracted_matches_legacy_for_no_port_map_warn_and_info(self):
        pre_if = {
            "Gi1/0/1": status("Gi1/0/1", "connected"),
            "Gi1/0/2": status("Gi1/0/2", "notconnect"),
        }
        post_if = {
            "Gi1/0/1": status("Gi1/0/1", "notconnect"),
            "Gi1/0/3": status("Gi1/0/3", "connected"),
        }

        legacy = legacy_analyze_interface_status(pre_if, post_if, None)
        extracted = analyze_interface_status(pre_if, post_if, None)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["WARN", "INFO"], [finding.severity for finding in extracted])
        self.assertIn("Gi1/0/1", extracted[0].detail)
        self.assertIn("Gi1/0/3", extracted[1].detail)


if __name__ == "__main__":
    unittest.main()
