"""Port-map loading and auto-generation for Post Change Validation Tool."""

from __future__ import annotations

from typing import Dict, Tuple

from src.post_change_validation_models import PortMapRow
from src.port_mapping.private.workplace_profile import (
    WorkplaceProfile,
    detect_access_prefix_from_model,
    detect_members_from_interfaces,
    infer_access_prefix_by_member_from_interfaces,
    infer_standalone_access_from_interfaces,
    infer_standalone_access_units_from_interfaces,
    parse_switch_provision,
)
from src.port_mapping.rules import load_manual_csv_file

__all__ = [
    "PortMapRow",
    "detect_access_prefix_from_model",
    "detect_members_from_interfaces",
    "infer_access_prefix_by_member_from_interfaces",
    "infer_standalone_access_from_interfaces",
    "infer_standalone_access_units_from_interfaces",
    "parse_switch_provision",
    "auto_build_port_map_from_running_config",
    "load_port_map",
]


def auto_build_port_map_from_running_config(
    run_cfg: str,
    inventory_section: str = "",
) -> Tuple[Dict[str, PortMapRow], str]:
    return WorkplaceProfile().build(running_config=run_cfg, inventory_section=inventory_section)


def load_port_map(path: str) -> Dict[str, PortMapRow]:
    return load_manual_csv_file(path)
