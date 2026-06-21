import unittest
from unittest.mock import Mock

import tests.bootstrap  # noqa: F401

from src.port_mapping.engine import PortMappingEngine
from src.port_mapping.private.workplace_profile import WorkplaceProfile
from src.port_mapping.types import PortMapBuildRequest


class PortMappingEngineDITests(unittest.TestCase):
    def test_build_uses_injected_runtime_profile_builder(self):
        mock_builder = Mock()
        mock_builder.profile_name = "injected_profile"
        mock_builder.build.return_value = ({}, "Injected detail.")

        engine = PortMappingEngine(runtime_profile_builder=mock_builder)
        result = engine.build(
            PortMapBuildRequest(running_config="interface Gi1/0/1", use_workplace_profile=True)
        )

        mock_builder.build.assert_called_once_with("interface Gi1/0/1", "")
        self.assertEqual(result.detail, "Injected detail.")
        self.assertEqual(result.profile_name, "injected_profile")

    def test_default_runtime_profile_builder_is_workplace(self):
        engine = PortMappingEngine()
        result = engine.build(PortMapBuildRequest(running_config="", use_workplace_profile=True))
        self.assertEqual(result.profile_name, WorkplaceProfile.profile_name)

    def test_manual_csv_path_skips_workplace_auto_build(self):
        from pathlib import Path

        fixture_root = Path(__file__).resolve().parent / "fixtures"
        map_path = str(fixture_root / "synthetic_correct_uplinks_port_map.csv")

        engine = PortMappingEngine()
        result = engine.build(PortMapBuildRequest(manual_csv_path=map_path))

        self.assertEqual(3, len(result.rows))
        self.assertIn("loaded 3 mapping row(s) from 3 data row(s)", result.detail)
        self.assertEqual("", result.profile_name)


if __name__ == "__main__":
    unittest.main()
