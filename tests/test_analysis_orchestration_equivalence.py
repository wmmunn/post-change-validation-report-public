import tempfile
import unittest
from pathlib import Path

from src.post_change_validation_analysis import run_analysis, sort_findings
from src.post_change_validation_analysis_wrappers import (
    analyze_access_port_mac_correlation,
    analyze_command_sections_findings,
    analyze_cpu,
    analyze_dot1x_findings,
    analyze_environment,
    analyze_interface_status,
    analyze_inventory,
    analyze_logs,
    analyze_mac_count,
    analyze_neighbors,
    analyze_poe,
    analyze_port_map_findings,
    analyze_stp_root,
    analyze_switch_detail_findings,
    analyze_transceivers,
    analyze_trunks,
    analyze_version,
    observed_neighbor_local_map,
)
from src.post_change_validation_command_sections import split_sections
from src.post_change_validation_interface_status import parse_interface_status
from src.post_change_validation_mac import mac_expected_present_ports, observed_mac_local_map
from src.post_change_validation_models import Finding
from src.post_change_validation_poe import poe_still_powering_ports
from src.post_change_validation_port_map import auto_build_port_map_from_running_config
from src.port_mapping.engine import PortMappingEngine
from src.port_mapping.types import PortMapBuildRequest
from src.post_change_validation_uplinks import (
    apply_observed_neighbor_port_overrides,
    infer_gateway_pair_uplink_mappings,
    infer_trunk_uplink_mappings,
    old_uplink_ports_from_evidence,
    parse_trunks,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


def legacy_analyze(pre_text: str, post_text: str, port_map_path: str = "") -> list[Finding]:
    findings: list[Finding] = []
    pre = split_sections(pre_text)
    post = split_sections(post_text)
    if port_map_path:
        build_result = PortMappingEngine().build(
            PortMapBuildRequest(
                manual_csv_path=port_map_path,
                use_workplace_profile=False,
            )
        )
        pm = build_result.rows
        port_map_source = f"Manual CSV override: {port_map_path}"
        port_map_detail = build_result.detail or (
            "Manual port map CSV was selected but no mapping rows were loaded. "
            "Expected columns: old_port, new_port (optional: role, note)."
        )
    else:
        pm, port_map_detail = auto_build_port_map_from_running_config(post.get("show running-config", ""))
        port_map_source = "Auto-detected from post-change running-config"
    inferred_gateway_maps: list[str] = []
    inferred_trunk_maps: list[str] = []
    observed_neighbor_overrides: list[str] = []
    if pm and not port_map_path:
        inferred_gateway_maps, _gateway_review = infer_gateway_pair_uplink_mappings(
            pre,
            pm,
            version_section=post.get("show version", ""),
            inventory_section=post.get("show inventory", ""),
            transceiver_section=post.get("show interfaces transceiver detail", ""),
        )
        inferred_trunk_maps, _trunk_review = infer_trunk_uplink_mappings(
            pre,
            pm,
            version_section=post.get("show version", ""),
            inventory_section=post.get("show inventory", ""),
            transceiver_section=post.get("show interfaces transceiver detail", ""),
        )
        observed_neighbor_overrides = apply_observed_neighbor_port_overrides(pre, post, pm)

    old_to_new = {k: v.new_port for k, v in pm.items() if v.new_port}
    mac_excluded_old_ports = old_uplink_ports_from_evidence(pre) if pm else set()
    observed_neighbor_ports = observed_neighbor_local_map(pre, post) if pm else {}
    observed_mac_ports = observed_mac_local_map(pre.get("show mac address-table", ""), post.get("show mac address-table", ""), pm, mac_excluded_old_ports) if pm else {}

    if inferred_gateway_maps:
        port_map_detail = port_map_detail + "\n\nInferred gateway 0/1 uplink pair mapping(s):\n" + "\n".join(inferred_gateway_maps)
    if inferred_trunk_maps:
        port_map_detail = port_map_detail + "\n\nInferred 24-port trunk uplink mapping(s):\n" + "\n".join(inferred_trunk_maps)
    if observed_neighbor_overrides:
        port_map_detail = port_map_detail + "\n\nObserved post-change neighbor override(s):\n" + "\n".join(observed_neighbor_overrides)

    findings.extend(analyze_port_map_findings(pm, port_map_source, port_map_detail))
    findings.extend(analyze_command_sections_findings(pre, post))

    pre_if = parse_interface_status(pre.get("show interfaces status", ""))
    post_if = parse_interface_status(post.get("show interfaces status", ""))

    findings.extend(analyze_interface_status(
        pre_if,
        post_if,
        pm if pm else None,
        observed_neighbor_ports=observed_neighbor_ports,
        observed_mac_ports=observed_mac_ports,
        post_running_config=post.get("show running-config", ""),
        post_trunks=parse_trunks(post.get("show interfaces trunk", "")),
    ))

    findings.extend(analyze_trunks(
        pre.get("show interfaces trunk", ""),
        post.get("show interfaces trunk", ""),
        old_to_new,
    ))

    mac_present_ports = mac_expected_present_ports(pre.get("show mac address-table", ""), post.get("show mac address-table", ""), pm, mac_excluded_old_ports) if pm else {}
    poe_powered_ports = poe_still_powering_ports(pre.get("show power inline", ""), post.get("show power inline", ""), pm) if pm else set()

    findings.extend(analyze_neighbors(pre, post, old_to_new, mac_present_ports, poe_powered_ports, post_if))

    findings.extend(analyze_logs(post.get("show logging", "")))

    if pm:
        findings.extend(analyze_access_port_mac_correlation(
            pre.get("show mac address-table", ""),
            post.get("show mac address-table", ""),
            pm,
            mac_excluded_old_ports,
        ))

    findings.extend(analyze_mac_count(pre.get("show mac address-table", ""), post.get("show mac address-table", "")))

    findings.extend(analyze_stp_root(pre, post, old_to_new, post_if))

    findings.extend(analyze_switch_detail_findings(post.get("show switch detail", "")))

    findings.extend(
        analyze_transceivers(
            pre.get("show interfaces transceiver detail", ""),
            post.get("show interfaces transceiver detail", ""),
            pm,
            version_section=post.get("show version", ""),
            inventory_section=post.get("show inventory", ""),
        )
    )
    findings.extend(analyze_poe(pre.get("show power inline", ""), post.get("show power inline", ""), pm, pre_if, post_if, pre, post))
    findings.extend(analyze_environment(post.get("show environment all", "")))
    findings.extend(analyze_inventory(post.get("show inventory", "")))
    findings.extend(analyze_version(post.get("show version", "")))
    findings.extend(analyze_cpu(post.get("show processes cpu", "")))

    findings.extend(analyze_dot1x_findings(post.get("show dot1x all summary", "")))

    return sort_findings(findings)


class AnalysisOrchestrationEquivalenceTests(unittest.TestCase):
    def test_run_analysis_matches_legacy_for_auto_detected_uplink_fixture(self):
        pre_text = (FIXTURE_ROOT / "synthetic_correct_uplinks_pre.log").read_text(encoding="utf-8")
        post_text = (FIXTURE_ROOT / "synthetic_correct_uplinks_post.log").read_text(encoding="utf-8")

        legacy = legacy_analyze(pre_text, post_text, "")
        extracted = run_analysis(pre_text, post_text, "")

        self.assertEqual(legacy, extracted)

    def test_run_analysis_matches_legacy_for_manual_port_map_fixture(self):
        pre_text = (FIXTURE_ROOT / "synthetic_correct_uplinks_pre.log").read_text(encoding="utf-8")
        post_text = (FIXTURE_ROOT / "synthetic_correct_uplinks_post.log").read_text(encoding="utf-8")
        map_path = str(FIXTURE_ROOT / "synthetic_correct_uplinks_port_map.csv")

        legacy = legacy_analyze(pre_text, post_text, map_path)
        extracted = run_analysis(pre_text, post_text, map_path)

        self.assertEqual(legacy, extracted)

    def test_run_analysis_matches_legacy_for_minimal_sanitized_sections(self):
        pre_text = (FIXTURE_ROOT / "sanitized_command_sections.log").read_text(encoding="utf-8")
        post_text = pre_text

        legacy = legacy_analyze(pre_text, post_text, "")
        extracted = run_analysis(pre_text, post_text, "")

        self.assertEqual(legacy, extracted)

    def test_reviewer_analyze_delegates_to_run_analysis(self):
        import post_change_validation_reviewer as reviewer

        pre_text = (FIXTURE_ROOT / "synthetic_correct_uplinks_pre.log").read_text(encoding="utf-8")
        post_text = (FIXTURE_ROOT / "synthetic_correct_uplinks_post.log").read_text(encoding="utf-8")

        self.assertEqual(run_analysis(pre_text, post_text, ""), reviewer.analyze(pre_text, post_text, ""))


if __name__ == "__main__":
    unittest.main()
