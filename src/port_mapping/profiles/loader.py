"""Discover JSON profiles on disk."""

from __future__ import annotations

from pathlib import Path

from src.port_mapping.profile import LoadedProfile, load_catalog


def discover_json_profiles(root: str | Path) -> dict[str, LoadedProfile]:
    return load_catalog(root)
