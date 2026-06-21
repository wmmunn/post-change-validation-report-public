import unittest
from dataclasses import dataclass
from pathlib import Path

from src.post_change_validation_analysis_wrappers import analyze_interface_status
from src.post_change_validation_interface_status import (
    build_uncovered_connected_detail_lines,
    compare_mapped_interface_status,
    infer_uncovered_port_role,
    parse_interface_status,
    parse_running_config_interface_blocks,
)
from src.post_change_validation_models import PortMapRow
from src.port_mapping.engine import PortMappingEngine
from src.port_mapping.types import PortMapBuildRequest

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


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


class InterfaceStatusComparisonTests(unittest.TestCase):
    def test_mapped_connected_ports_pass(self):
        result = compare_mapped_interface_status(
            {"Gi1/0/1": status("Gi1/0/1", "connected")},
            {"Te1/0/1": status("Te1/0/1", "connected")},
            {"Gi1/0/1": PortMapRow("Gi1/0/1", "Te1/0/1", "access", "mGig access mapping")},
        )

        self.assertEqual(1, len(result.connected_pass))
        self.assertIn("Gi1/0/1 -> Te1/0/1", result.connected_pass[0])
        self.assertEqual([], result.connected_warn)

    def test_observed_placement_connected_port_passes(self):
        result = compare_mapped_interface_status(
            {"Gi1/0/25": status("Gi1/0/25", "connected")},
            {
                "Te1/0/25": status("Te1/0/25", "notconnect"),
                "Te1/1/1": status("Te1/1/1", "connected"),
            },
            {"Gi1/0/25": PortMapRow("Gi1/0/25", "Te1/0/25", "access", "profile inference")},
            observed_neighbor_ports={"Gi1/0/25": "Te1/1/1"},
        )

        self.assertEqual(1, len(result.connected_pass))
        self.assertIn("Gi1/0/25 -> Te1/1/1", result.connected_pass[0])
        self.assertIn("inferred map expected Te1/0/25", result.connected_pass[0])
        self.assertEqual([], result.connected_warn)
        self.assertIn("Te1/1/1", result.post_covered)

    def test_connected_pre_port_warns_when_mapped_post_port_is_down(self):
        result = compare_mapped_interface_status(
            {"Gi1/0/2": status("Gi1/0/2", "connected")},
            {"Te1/0/2": status("Te1/0/2", "notconnect")},
            {"Gi1/0/2": PortMapRow("Gi1/0/2", "Te1/0/2", "access", "operator review")},
        )

        self.assertEqual([], result.connected_pass)
        self.assertEqual(1, len(result.connected_warn))
        self.assertIn("was connected before, now notconnect", result.connected_warn[0])
        self.assertIn("note=operator review", result.connected_warn[0])

    def test_unchanged_down_count_increments_for_ports_down_before_and_after(self):
        result = compare_mapped_interface_status(
            {
                "Gi1/0/3": status("Gi1/0/3", "notconnect"),
                "Gi1/0/4": status("Gi1/0/4", "disabled"),
            },
            {
                "Te1/0/3": status("Te1/0/3", "notconnect"),
                "Te1/0/4": status("Te1/0/4", "disabled"),
            },
            {
                "Gi1/0/3": PortMapRow("Gi1/0/3", "Te1/0/3", "access", ""),
                "Gi1/0/4": PortMapRow("Gi1/0/4", "Te1/0/4", "access", ""),
            },
        )

        self.assertEqual(2, result.unchanged_down)
        self.assertEqual([], result.connected_pass)
        self.assertEqual([], result.connected_warn)

    def test_manual_csv_mapped_old_port_on_post_is_not_uncovered(self):
        result = compare_mapped_interface_status(
            {
                "Fi2/0/1": status("Fi2/0/1", "connected"),
                "Fi2/0/2": status("Fi2/0/2", "connected"),
            },
            {
                "Fi2/0/1": status("Fi2/0/1", "connected"),
                "Fi2/0/2": status("Fi2/0/2", "connected"),
            },
            {
                "Fi2/0/1": PortMapRow("Fi2/0/1", "Te2/0/1", "access", "manual CSV maps to different post port"),
                "Fi2/0/2": PortMapRow("Fi2/0/2", "Te2/0/2", "access", "manual CSV maps to different post port"),
            },
        )

        self.assertEqual([], result.uncovered_connected)

    def test_manual_csv_fi_ports_on_post_generate_no_uncovered_detail_lines(self):
        pre_if = {
            "Fi2/0/1": status("Fi2/0/1", "connected"),
            "Fi2/0/2": status("Fi2/0/2", "connected"),
        }
        post_if = {
            "Fi2/0/1": status("Fi2/0/1", "connected"),
            "Fi2/0/2": status("Fi2/0/2", "connected"),
            "Te1/0/6": status("Te1/0/6", "connected"),
        }
        build_result = PortMappingEngine().build(
            PortMapBuildRequest(
                manual_csv_path=str(FIXTURE_ROOT / "fi_access_port_map.csv"),
                use_workplace_profile=False,
            )
        )

        result = compare_mapped_interface_status(pre_if, post_if, build_result.rows)
        self.assertEqual([], [port for port in result.uncovered_connected if port.startswith("Fi2/0/")])
        self.assertEqual(["Te1/0/6"], result.uncovered_connected)

        findings = analyze_interface_status(pre_if, post_if, build_result.rows)
        uncovered_findings = [
            finding for finding in findings
            if finding.severity == "INFO" and "not covered by the port map" in finding.finding
        ]
        self.assertEqual(1, len(uncovered_findings))
        self.assertNotIn("Fi2/0/1", uncovered_findings[0].detail)
        self.assertNotIn("Fi2/0/2", uncovered_findings[0].detail)
        self.assertIn("uncovered -> Te1/0/6", uncovered_findings[0].detail)

    def test_five_gige_status_line_parses_to_canonical_fi_and_is_covered(self):
        status_section = "\n".join(
            [
                "Port      Name               Status       Vlan       Duplex  Speed Type",
                "FiveGigE2/0/1  User Port       connected    100        a-full  a-1000 10/100/1000BaseTX",
            ]
        )
        post_if = parse_interface_status(status_section)
        self.assertIn("Fi2/0/1", post_if)

        result = compare_mapped_interface_status(
            {"Fi2/0/1": status("Fi2/0/1", "connected")},
            post_if,
            {"Fi2/0/1": PortMapRow("Fi2/0/1", "Fi2/0/1", "access", "CSV same-name map")},
        )
        self.assertEqual([], result.uncovered_connected)
        self.assertEqual([], build_uncovered_connected_detail_lines(result.uncovered_connected, post_if))

    def test_mapped_new_port_matches_expanded_post_interface_name(self):
        result = compare_mapped_interface_status(
            {"Gi2/0/1": status("Gi2/0/1", "connected")},
            {"FiveGigabitEthernet2/0/1": status("FiveGigabitEthernet2/0/1", "connected")},
            {"Gi2/0/1": PortMapRow("Gi2/0/1", "Fi2/0/1", "access", "manual CSV new_port short form")},
        )

        self.assertEqual([], result.uncovered_connected)

    def test_mapped_new_port_matches_short_post_interface_name(self):
        result = compare_mapped_interface_status(
            {"Gi2/0/1": status("Gi2/0/1", "connected")},
            {"Fi2/0/1": status("Fi2/0/1", "connected")},
            {"Gi2/0/1": PortMapRow("Gi2/0/1", "Fi2/0/1", "access", "manual CSV new_port short form")},
        )

        self.assertEqual([], result.uncovered_connected)

    def test_mapped_ports_are_not_uncovered_when_names_differ_only_by_case(self):
        result = compare_mapped_interface_status(
            {"gi2/0/1": status("gi2/0/1", "connected")},
            {"GigabitEthernet2/0/1": status("GigabitEthernet2/0/1", "connected")},
            {"gi2/0/1": PortMapRow("gi2/0/1", "Te2/0/1", "access", "case-insensitive CSV keys")},
        )

        self.assertEqual([], result.uncovered_connected)

    def test_uncovered_connected_post_ports_are_reported(self):
        result = compare_mapped_interface_status(
            {"Gi1/0/5": status("Gi1/0/5", "connected")},
            {
                "Te1/0/5": status("Te1/0/5", "connected"),
                "Te1/0/6": status("Te1/0/6", "connected"),
                "Ap1/0/1": status("Ap1/0/1", "connected"),
            },
            {"Gi1/0/5": PortMapRow("Gi1/0/5", "Te1/0/5", "access", "")},
        )

        self.assertEqual(["Te1/0/6"], result.uncovered_connected)

    def test_uncovered_connected_detail_lines_include_role_status_and_post_evidence(self):
        post_if = {
            "Te1/0/6": status("Te1/0/6", "connected"),
        }
        run_cfg = (Path(__file__).resolve().parent / "fixtures" / "sanitized_stack_running_config.cfg").read_text(encoding="utf-8")
        blocks = parse_running_config_interface_blocks(run_cfg)

        detail_lines = build_uncovered_connected_detail_lines(
            ["Te1/0/6"],
            post_if,
            post_running_config=run_cfg,
            post_trunks=set(),
        )

        self.assertEqual(1, len(detail_lines))
        self.assertIn("uncovered -> Te1/0/6 role=access: connected", detail_lines[0])
        self.assertIn(": connected | post=Te1/0/6 connected", detail_lines[0])
        self.assertEqual("access", infer_uncovered_port_role("Gi1/0/1", None, blocks.get("Gi1/0/1", "")))
        self.assertEqual("trunk", infer_uncovered_port_role("Gi1/0/49", None, blocks.get("Gi1/0/49", "")))


if __name__ == "__main__":
    unittest.main()
