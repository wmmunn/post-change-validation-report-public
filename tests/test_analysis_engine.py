import unittest
from pathlib import Path
from unittest.mock import Mock

import tests.bootstrap  # noqa: F401

from src.post_change_validation_analysis import AnalysisEngine
from src.post_change_validation_models import Finding
from src.port_mapping.engine import PortMappingEngine

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


class AnalysisEngineTests(unittest.TestCase):
    def test_execute_returns_findings_and_reports_progress(self):
        mock_builder = Mock()
        mock_builder.profile_name = "mock_profile"
        mock_builder.build.return_value = ({}, "Mock auto-build detail.")

        port_engine = PortMappingEngine(runtime_profile_builder=mock_builder)
        engine = AnalysisEngine(port_mapping_engine=port_engine)

        pre_text = (FIXTURE_ROOT / "sanitized_command_sections.log").read_text(encoding="utf-8")
        progress_calls: list[tuple[str, float]] = []

        def progress_callback(stage: str, progress: float) -> None:
            progress_calls.append((stage, progress))

        report = engine.execute(pre_text, pre_text, progress_callback=progress_callback)

        self.assertIsInstance(report.findings, list)
        for finding in report.findings:
            self.assertIsInstance(finding, Finding)
        self.assertGreater(len(progress_calls), 0)
        mock_builder.build.assert_called_once()
        stages = [stage for stage, _ in progress_calls]
        self.assertIn("Parsing command sections", stages)
        self.assertIn("Building port map", stages)
        self.assertIn("Finalizing", stages)
        self.assertEqual(progress_calls[-1][1], 1.0)

    def test_execute_rejects_unsupported_log_before_parsing(self):
        with self.assertRaises(ValueError) as ctx:
            AnalysisEngine().execute("not-a-valid-log", "not-a-valid-log")

        self.assertIn("Pre-change log", str(ctx.exception))
        self.assertIn("Missing or empty show running-config", str(ctx.exception))

    def test_execute_loads_manual_csv_fixture(self):
        map_path = str(FIXTURE_ROOT / "synthetic_correct_uplinks_port_map.csv")
        pre_text = (FIXTURE_ROOT / "synthetic_correct_uplinks_pre.log").read_text(encoding="utf-8")
        post_text = (FIXTURE_ROOT / "synthetic_correct_uplinks_post.log").read_text(encoding="utf-8")

        report = AnalysisEngine().execute(pre_text, post_text, map_path)
        port_map_findings = [finding for finding in report.findings if finding.category == "Port Map"]

        self.assertEqual(1, len(port_map_findings))
        self.assertEqual("INFO", port_map_findings[0].severity)
        self.assertIn("Port map loaded with 3 old-to-new mapping row(s).", port_map_findings[0].finding)
        self.assertIn(f"Manual CSV override: {map_path}", port_map_findings[0].detail)
        self.assertIn("loaded 3 mapping row(s) from 3 data row(s)", port_map_findings[0].detail)
        self.assertEqual("", report.port_map_profile_name)

    def test_execute_loads_title_case_manual_csv_fixture(self):
        map_path = str(FIXTURE_ROOT / "manual_port_map_title_case_headers.csv")
        pre_text = (FIXTURE_ROOT / "synthetic_correct_uplinks_pre.log").read_text(encoding="utf-8")
        post_text = (FIXTURE_ROOT / "synthetic_correct_uplinks_post.log").read_text(encoding="utf-8")

        report = AnalysisEngine().execute(pre_text, post_text, map_path)
        port_map_findings = [finding for finding in report.findings if finding.category == "Port Map"]

        self.assertEqual(1, len(port_map_findings))
        self.assertEqual("INFO", port_map_findings[0].severity)
        self.assertIn("Port map loaded with 3 old-to-new mapping row(s).", port_map_findings[0].finding)


if __name__ == "__main__":
    unittest.main()
