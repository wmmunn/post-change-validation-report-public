"""Pure analysis orchestration for Post Change Validation Tool."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

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
    uplink_fallback_review_finding,
)
from src.post_change_validation_command_sections import split_sections
from src.post_change_validation_ios_log_signature import validate_ios_xe_log_signature
from src.post_change_validation_interface_status import parse_interface_status
from src.post_change_validation_mac import mac_expected_present_ports, observed_mac_local_map
from src.post_change_validation_models import Finding
from src.post_change_validation_poe import poe_still_powering_ports
from src.post_change_validation_uplinks import (
    apply_observed_neighbor_port_overrides,
    infer_gateway_pair_uplink_mappings,
    infer_trunk_uplink_mappings,
    old_uplink_ports_from_evidence,
    parse_trunks,
)
from src.port_mapping.engine import PortMappingEngine
from src.port_mapping.types import PortMapBuildRequest


@dataclass(frozen=True)
class AnalysisReport:
    """Structured output from a full pre/post analysis run."""

    findings: list[Finding]
    port_map_profile_name: str
    port_map_source: str
    port_map_detail: str


class AnalysisEngine:
    """Orchestrates pre/post CLI analysis across port mapping and finding wrappers.

    Module stage mapping:
    1. split_sections (command_sections)
    2. PortMappingEngine.build (port_mapping)
    3. uplink inference (uplinks)
    4. analyze_port_map_findings + command sections + interface + trunks +
       neighbor/mac/stp/switch + health wrappers + dot1x (analysis_wrappers)
    5. sort_findings
    """

    def __init__(self, port_mapping_engine: PortMappingEngine | None = None) -> None:
        self._port_mapping_engine = port_mapping_engine or PortMappingEngine()

    def execute(
        self,
        pre_text: str,
        post_text: str,
        port_map_path: str = "",
        *,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> AnalysisReport:
        findings: List[Finding] = []

        def report_progress(stage: str, progress: float) -> None:
            if progress_callback is not None:
                progress_callback(stage, progress)

        for label, text in (("Pre-change log", pre_text), ("Post-change log", post_text)):
            ok, reason = validate_ios_xe_log_signature(text)
            if not ok:
                raise ValueError(f"{label}: {reason}")

        report_progress("Parsing command sections", 0.0)
        pre = split_sections(pre_text)
        post = split_sections(post_text)

        report_progress("Building port map", 0.1)
        port_map_path = (port_map_path or "").strip()
        if port_map_path:
            build_result = self._port_mapping_engine.build(
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
            port_map_profile_name = build_result.profile_name
        else:
            build_result = self._port_mapping_engine.build(
                PortMapBuildRequest(
                    running_config=post.get("show running-config", ""),
                    inventory_section=post.get("show inventory", ""),
                    use_workplace_profile=True,
                )
            )
            pm = build_result.rows
            port_map_detail = build_result.detail
            port_map_source = "Auto-detected from post-change running-config"
            port_map_profile_name = build_result.profile_name

        report_progress("Applying uplink inference", 0.2)
        inferred_gateway_maps: List[str] = []
        inferred_trunk_maps: List[str] = []
        observed_neighbor_overrides: List[str] = []
        uplink_fallback_review_reasons: List[str] = []
        if pm and not port_map_path:
            inferred_gateway_maps, gateway_review = infer_gateway_pair_uplink_mappings(
                pre,
                pm,
                version_section=post.get("show version", ""),
                inventory_section=post.get("show inventory", ""),
                transceiver_section=post.get("show interfaces transceiver detail", ""),
            )
            if gateway_review:
                uplink_fallback_review_reasons.append(gateway_review)
            inferred_trunk_maps, trunk_review = infer_trunk_uplink_mappings(
                pre,
                pm,
                version_section=post.get("show version", ""),
                inventory_section=post.get("show inventory", ""),
                transceiver_section=post.get("show interfaces transceiver detail", ""),
            )
            if trunk_review:
                uplink_fallback_review_reasons.append(trunk_review)
            observed_neighbor_overrides = apply_observed_neighbor_port_overrides(pre, post, pm)

        old_to_new = {k: v.new_port for k, v in pm.items() if v.new_port}
        mac_excluded_old_ports = old_uplink_ports_from_evidence(pre) if pm else set()
        observed_neighbor_ports = observed_neighbor_local_map(pre, post) if pm else {}
        observed_mac_ports = (
            observed_mac_local_map(
                pre.get("show mac address-table", ""),
                post.get("show mac address-table", ""),
                pm,
                mac_excluded_old_ports,
            )
            if pm
            else {}
        )

        if inferred_gateway_maps:
            port_map_detail = (
                port_map_detail + "\n\nInferred gateway 0/1 uplink pair mapping(s):\n"
                + "\n".join(inferred_gateway_maps)
            )
        if inferred_trunk_maps:
            port_map_detail = (
                port_map_detail + "\n\nInferred 24-port trunk uplink mapping(s):\n"
                + "\n".join(inferred_trunk_maps)
            )
        if observed_neighbor_overrides:
            port_map_detail = (
                port_map_detail + "\n\nObserved post-change neighbor override(s):\n"
                + "\n".join(observed_neighbor_overrides)
            )

        report_progress("Evaluating port map and command sections", 0.3)
        findings.extend(analyze_port_map_findings(pm, port_map_source, port_map_detail))
        for review_reason in dict.fromkeys(uplink_fallback_review_reasons):
            findings.append(uplink_fallback_review_finding(review_reason))
        findings.extend(analyze_command_sections_findings(pre, post))

        report_progress("Interface status", 0.4)
        pre_if = parse_interface_status(pre.get("show interfaces status", ""))
        post_if = parse_interface_status(post.get("show interfaces status", ""))

        findings.extend(
            analyze_interface_status(
                pre_if,
                post_if,
                pm if pm else None,
                observed_neighbor_ports=observed_neighbor_ports,
                observed_mac_ports=observed_mac_ports,
                post_running_config=post.get("show running-config", ""),
                post_trunks=parse_trunks(post.get("show interfaces trunk", "")),
            )
        )

        report_progress("Trunks and link state", 0.5)
        findings.extend(
            analyze_trunks(
                pre.get("show interfaces trunk", ""),
                post.get("show interfaces trunk", ""),
                old_to_new,
            )
        )

        mac_present_ports = (
            mac_expected_present_ports(
                pre.get("show mac address-table", ""),
                post.get("show mac address-table", ""),
                pm,
                mac_excluded_old_ports,
            )
            if pm
            else {}
        )
        poe_powered_ports = (
            poe_still_powering_ports(
                pre.get("show power inline", ""),
                post.get("show power inline", ""),
                pm,
            )
            if pm
            else set()
        )

        report_progress("Neighbors", 0.6)
        findings.extend(
            analyze_neighbors(pre, post, old_to_new, mac_present_ports, poe_powered_ports, post_if)
        )

        findings.extend(analyze_logs(post.get("show logging", "")))

        if pm:
            findings.extend(
                analyze_access_port_mac_correlation(
                    pre.get("show mac address-table", ""),
                    post.get("show mac address-table", ""),
                    pm,
                    mac_excluded_old_ports,
                )
            )

        findings.extend(
            analyze_mac_count(pre.get("show mac address-table", ""), post.get("show mac address-table", ""))
        )

        findings.extend(analyze_stp_root(pre, post, old_to_new, post_if))

        report_progress("Switch detail", 0.75)
        findings.extend(analyze_switch_detail_findings(post.get("show switch detail", "")))

        report_progress("Health checks", 0.9)
        findings.extend(
            analyze_transceivers(
                pre.get("show interfaces transceiver detail", ""),
                post.get("show interfaces transceiver detail", ""),
                pm,
                version_section=post.get("show version", ""),
                inventory_section=post.get("show inventory", ""),
            )
        )
        findings.extend(
            analyze_poe(
                pre.get("show power inline", ""),
                post.get("show power inline", ""),
                pm,
                pre_if,
                post_if,
                pre,
                post,
            )
        )
        findings.extend(analyze_environment(post.get("show environment all", "")))
        findings.extend(analyze_inventory(post.get("show inventory", "")))
        findings.extend(analyze_version(post.get("show version", "")))
        findings.extend(analyze_cpu(post.get("show processes cpu", "")))

        findings.extend(analyze_dot1x_findings(post.get("show dot1x all summary", "")))

        report_progress("Finalizing", 1.0)
        sorted_findings = sort_findings(findings)
        return AnalysisReport(
            findings=sorted_findings,
            port_map_profile_name=port_map_profile_name,
            port_map_source=port_map_source,
            port_map_detail=port_map_detail,
        )


def sort_findings(findings: List[Finding]) -> List[Finding]:
    order = {"FAIL": 0, "WARN": 1, "PASS": 2, "INFO": 3}
    return sorted(findings, key=lambda f: (order.get(f.severity, 9), f.category, f.finding))


def run_analysis(pre_text: str, post_text: str, port_map_path: str = "") -> List[Finding]:
    return AnalysisEngine().execute(
        pre_text,
        post_text,
        port_map_path=(port_map_path or "").strip(),
    ).findings
