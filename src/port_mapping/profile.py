"""Profile loading, validation, and JSON application."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Protocol, runtime_checkable

from src.post_change_validation_models import PortMapRow

from src.port_mapping.exceptions import ProfileLoadError, ProfileValidationError
from src.port_mapping.rules import apply_same_name_fallback, build_rows_from_json_profile


@runtime_checkable
class RuntimeProfileBuilder(Protocol):
    profile_name: str

    def build(self, running_config: str, inventory_section: str = "") -> tuple[Dict[str, PortMapRow], str]:
        ...


@dataclass(frozen=True)
class LoadedProfile:
    profile_name: str
    path: Path
    data: Mapping[str, Any]


_REQUIRED_PROFILE_KEYS = ("profile_name",)


def validate_profile_schema(profile: Mapping[str, Any]) -> None:
    if not isinstance(profile, dict):
        raise ProfileValidationError("Port-mapping profile must be a JSON object.")

    for key in _REQUIRED_PROFILE_KEYS:
        if key not in profile:
            raise ProfileValidationError(f"Port-mapping profile missing required key: {key}")

    fallback = profile.get("fallback")
    if fallback is not None and fallback != "same_name":
        raise ProfileValidationError(f"Unsupported fallback strategy: {fallback!r}")


def load_json_profile(path: str | Path) -> Dict[str, Any]:
    profile_path = Path(path)
    try:
        with profile_path.open(encoding="utf-8") as profile_file:
            profile = json.load(profile_file)
    except OSError as exc:
        raise ProfileLoadError(f"Unable to read profile {profile_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileLoadError(f"Invalid JSON in profile {profile_path}: {exc}") from exc

    if not isinstance(profile, dict):
        raise ProfileValidationError("Port-mapping profile must be a JSON object.")
    return profile


def load_catalog(profile_root: str | Path) -> Dict[str, LoadedProfile]:
    root = Path(profile_root)
    catalog: Dict[str, LoadedProfile] = {}
    for path in sorted(root.glob("**/*.json")):
        data = load_json_profile(path)
        validate_profile_schema(data)
        name = str(data.get("profile_name", "")).strip()
        if name:
            catalog[name] = LoadedProfile(profile_name=name, path=path, data=data)
    return catalog


def apply_json_profile(
    profile: Mapping[str, Any],
    source_interfaces: Iterable[str],
) -> Dict[str, PortMapRow]:
    validate_profile_schema(profile)
    source_ports = [port for port in source_interfaces]
    rows = build_rows_from_json_profile(profile, source_ports)
    if profile.get("fallback") == "same_name":
        apply_same_name_fallback(rows, source_ports)
    return rows
