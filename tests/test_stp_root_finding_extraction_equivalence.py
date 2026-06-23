import unittest
from dataclasses import dataclass
from typing import Dict

from src.post_change_validation_analysis_wrappers import analyze_stp_root
from src.post_change_validation_models import Finding
from src.post_change_validation_stp import (
    compare_stp_topology,
    parse_stp_path_cost_method,
    parse_stp_root,
)


@dataclass
class InterfaceStatusStub:
    vlan: str = ""
    speed: str = ""
    type_: str = ""


def _stp_root_section(*rows: str) -> str:
    return "\n".join(rows)


def legacy_analyze_stp_root(
    pre: Dict[str, str],
    post: Dict[str, str],
    old_to_new: Dict[str, str],
    post_if: Dict[str, object],
) -> list[Finding]:
    findings: list[Finding] = []
    pre_stp_records = parse_stp_root(pre.get("show spanning-tree root", ""))
    post_stp_records = parse_stp_root(post.get("show spanning-tree root", ""))
    pre_stp_cost_method = parse_stp_path_cost_method(pre.get("show spanning-tree summary", ""), pre.get("show running-config", ""))
    post_stp_cost_method = parse_stp_path_cost_method(post.get("show spanning-tree summary", ""), post.get("show running-config", ""))
    if pre_stp_records and post_stp_records:
        stp_comparison = compare_stp_topology(
            pre_stp_records,
            post_stp_records,
            old_to_new,
            pre_stp_cost_method,
            post_stp_cost_method,
            post.get("show running-config", ""),
            post_if,
        )
        if stp_comparison.warn_items:
            findings.append(Finding("WARN", "STP Root", f"{len(stp_comparison.warn_items)} STP root item(s) require review.", "\n".join(stp_comparison.warn_items)))
        if stp_comparison.pass_items:
            findings.append(Finding("PASS", "STP Root", f"{len(stp_comparison.pass_items)} STP VLAN(s) retained expected root/mapped root-port behavior.", "\n".join(stp_comparison.pass_items)))
        if stp_comparison.info_items:
            findings.append(Finding("INFO", "STP Root", f"{len(stp_comparison.info_items)} informational STP root item(s).", "\n".join(stp_comparison.info_items)))
    return findings


class StpRootFindingExtractionEquivalenceTests(unittest.TestCase):
    def test_extracted_analyze_stp_root_matches_legacy_for_pass_retained_mapped_root_port(self):
        pre = {
            "show spanning-tree root": _stp_root_section(
                "VLAN0001 32769 0011.2233.4455 4 128.1 P2p Root GigabitEthernet1/0/49"
            ),
            "show spanning-tree summary": "Pathcost method used is short",
            "show running-config": "",
        }
        post = {
            "show spanning-tree root": _stp_root_section(
                "VLAN0001 32769 0011.2233.4455 2000 128.1 P2p Root TenGigabitEthernet1/1/1"
            ),
            "show spanning-tree summary": "Pathcost method used is long",
            "show running-config": "",
        }
        old_to_new = {"Gi1/0/49": "Te1/1/1"}
        post_if = {"Te1/1/1": InterfaceStatusStub(speed="a-10G", type_="SFP-10G")}

        legacy = legacy_analyze_stp_root(pre, post, old_to_new, post_if)
        extracted = analyze_stp_root(pre, post, old_to_new, post_if)

        self.assertEqual(legacy, extracted)
        self.assertEqual(["PASS"], [finding.severity for finding in extracted])
        self.assertIn("root unchanged and root port mapped (Gi1/0/49 -> Te1/1/1); cost changed 4 -> 2000", extracted[0].detail)

    def test_extracted_analyze_stp_root_matches_legacy_for_warn_unexpected_root_port(self):
        pre = {
            "show spanning-tree root": _stp_root_section(
                "VLAN0001 32769 0011.2233.4455 4 128.1 P2p Root GigabitEthernet1/0/49"
            ),
            "show spanning-tree summary": "",
            "show running-config": "",
        }
        post = {
            "show spanning-tree root": _stp_root_section(
                "VLAN0001 32769 0011.2233.4455 4 128.1 P2p Root TenGigabitEthernet1/1/8"
            ),
            "show spanning-tree summary": "",
            "show running-config": "",
        }
        old_to_new = {"Gi1/0/49": "Te1/1/1"}

        legacy = legacy_analyze_stp_root(pre, post, old_to_new, {})
        extracted = analyze_stp_root(pre, post, old_to_new, {})

        self.assertEqual(legacy, extracted)
        self.assertEqual(["WARN"], [finding.severity for finding in extracted])
        self.assertIn("expected post=Te1/1/1, actual post=Te1/1/8", extracted[0].detail)


    def test_extracted_analyze_stp_root_matches_legacy_for_silent_when_post_stp_empty(self):
        pre = {
            "show spanning-tree root": _stp_root_section(
                "VLAN0001 32769 0011.2233.4455 4 128.1 P2p Root GigabitEthernet1/0/49"
            ),
            "show spanning-tree summary": "",
            "show running-config": "",
        }
        post = {
            "show spanning-tree root": "",
            "show spanning-tree summary": "",
            "show running-config": "",
        }

        legacy = legacy_analyze_stp_root(pre, post, {}, {})
        extracted = analyze_stp_root(pre, post, {}, {})

        self.assertEqual(legacy, extracted)
        self.assertEqual([], extracted)


if __name__ == "__main__":
    unittest.main()
