"""Port-mapping build request/result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Optional

from src.post_change_validation_models import PortMapRow


@dataclass
class PortMapBuildRequest:
    """Inputs for building an expected port map."""

    running_config: str = ""
    inventory_section: str = ""
    profile_path: str = ""
    profile_data: Optional[Mapping[str, object]] = None
    manual_csv_path: str = ""
    manual_csv_text: str = ""
    manual_overrides: Optional[Mapping[str, PortMapRow]] = None
    source_interfaces: Optional[Iterable[str]] = None
    use_workplace_profile: bool = True


@dataclass
class PortMapBuildResult:
    """Built expected port map plus operator-facing detail text."""

    rows: Dict[str, PortMapRow] = field(default_factory=dict)
    detail: str = ""
    profile_name: str = ""
