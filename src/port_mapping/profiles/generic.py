"""Generic public profile helpers."""

from __future__ import annotations

from pathlib import Path

from src.port_mapping.profile import load_catalog

PACKAGE_PROFILE_ROOT = Path(__file__).resolve().parent


def discover_public_profiles() -> dict:
    return load_catalog(PACKAGE_PROFILE_ROOT / "public")


class GenericProfile:
    """Public fallback profile used when the private workplace profile is unavailable."""

    profile_name: str = "Generic (no environment profile)"

    def build(self, running_config: str, inventory_section: str = "") -> tuple[dict, str]:
        return {}, "No environment profile available; port mapping will use manual overrides or JSON profiles only."
