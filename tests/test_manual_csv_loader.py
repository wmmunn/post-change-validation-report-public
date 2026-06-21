import unittest
from pathlib import Path

import tests.bootstrap  # noqa: F401

from src.port_mapping.engine import PortMappingEngine
from src.port_mapping.rules import load_manual_csv_file_with_detail, parse_manual_csv
from src.port_mapping.types import PortMapBuildRequest

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


class ManualCsvLoaderTests(unittest.TestCase):
    def test_title_case_headers_load_three_rows(self):
        csv_path = FIXTURE_ROOT / "manual_port_map_title_case_headers.csv"
        rows, detail = load_manual_csv_file_with_detail(str(csv_path))

        self.assertEqual(3, len(rows))
        self.assertEqual("Te1/1/1", rows["Gi1/0/25"].new_port)
        self.assertIn("loaded 3 mapping row(s) from 3 data row(s)", detail)

    def test_partial_three_row_canonical_headers_load(self):
        csv_text = """old_port,new_port,role,note
Gi1/0/1,Gi1/0/1,access,row one
Gi1/0/2,Gi1/0/2,access,row two
Gi1/0/3,Te1/0/3,access,row three
"""
        rows, detail = parse_manual_csv(csv_text)

        self.assertEqual(3, len(rows))
        self.assertIn("loaded 3 mapping row(s) from 3 data row(s)", detail)

    def test_unrecognized_headers_return_clear_detail_not_silent_empty(self):
        csv_text = """source,target,comment
Gi1/0/1,Gi1/0/1,ignored
"""
        rows, detail = parse_manual_csv(csv_text)

        self.assertEqual({}, rows)
        self.assertIn("did not include recognizable old/new port columns", detail)
        self.assertIn("source, target, comment", detail)

    def test_engine_manual_csv_path_surfaces_parse_detail_when_empty(self):
        csv_text = "bad_header,other\nGi1/0/1,Gi1/0/1\n"
        result = PortMappingEngine().build(
            PortMapBuildRequest(
                manual_csv_text=csv_text,
                use_workplace_profile=False,
            )
        )

        self.assertEqual({}, result.rows)
        self.assertIn("did not include recognizable old/new port columns", result.detail)


if __name__ == "__main__":
    unittest.main()
