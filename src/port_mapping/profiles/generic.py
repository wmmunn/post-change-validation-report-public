"""Generic public profile helpers."""

from __future__ import annotations

from pathlib import Path

from src.port_mapping.profile import load_catalog

PACKAGE_PROFILE_ROOT = Path(__file__).resolve().parent


def discover_public_profiles() -> dict:
    return load_catalog(PACKAGE_PROFILE_ROOT / "public")
