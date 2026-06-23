"""Tests for GenericProfile fallback used when private profile is missing."""

import unittest

from src.port_mapping.profiles.generic import GenericProfile


class TestPortMappingEngineGenericFallback(unittest.TestCase):
    def test_generic_profile_build_returns_empty_map_and_message(self) -> None:
        profile = GenericProfile()
        result = profile.build("", "")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        rows, detail = result
        self.assertEqual(rows, {})
        self.assertIsInstance(detail, str)
        self.assertTrue(detail.strip())


if __name__ == "__main__":
    unittest.main()
