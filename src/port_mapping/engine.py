"""Port-mapping engine with explicit precedence."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from src.post_change_validation_models import PortMapRow, canonical_interface_name

try:
    from src.port_mapping.private.workplace_profile import WorkplaceProfile as _RuntimeProfile
except ImportError:
    from src.port_mapping.profiles.generic import GenericProfile as _RuntimeProfile
from src.port_mapping.profile import (
    RuntimeProfileBuilder,
    apply_json_profile,
    load_json_profile,
    validate_profile_schema,
)
from src.port_mapping.rules import load_manual_csv_file_with_detail, parse_manual_csv
from src.port_mapping.types import PortMapBuildRequest, PortMapBuildResult

DEFAULT_PROFILE_ROOT = Path(__file__).resolve().parent / "profiles" / "public"


class PortMappingEngine:
    """Build expected port maps using manual, profile, and fallback precedence."""

    def __init__(
        self,
        profile_root: str | Path | None = None,
        runtime_profile_builder: RuntimeProfileBuilder | None = None,
    ) -> None:
        self.profile_root = Path(profile_root) if profile_root else DEFAULT_PROFILE_ROOT
        self._runtime_profile_builder = runtime_profile_builder or _RuntimeProfile()

    def build(self, request: PortMapBuildRequest) -> PortMapBuildResult:
        rows: Dict[str, PortMapRow] = {}
        detail = ""
        profile_name = ""

        manual_overrides: Dict[str, PortMapRow] = {}
        manual_csv_detail = ""
        if request.manual_overrides:
            manual_overrides.update(request.manual_overrides)
        if request.manual_csv_text:
            manual_rows, manual_csv_detail = parse_manual_csv(request.manual_csv_text)
            manual_overrides.update(manual_rows)
        if request.manual_csv_path:
            manual_rows, path_detail = load_manual_csv_file_with_detail(request.manual_csv_path)
            manual_overrides.update(manual_rows)
            if path_detail:
                manual_csv_detail = path_detail

        run_workplace_profile = request.use_workplace_profile
        if run_workplace_profile and not (request.running_config or "").strip():
            if request.manual_csv_path or request.manual_csv_text:
                run_workplace_profile = False

        if request.profile_data is not None or request.profile_path:
            profile = request.profile_data if request.profile_data is not None else load_json_profile(request.profile_path)
            validate_profile_schema(profile)
            profile_name = str(profile.get("profile_name", "")).strip()
            source_interfaces = list(request.source_interfaces or [])
            rows = apply_json_profile(profile, source_interfaces)
            description = str(profile.get("description", "")).strip()
            detail = f"Profile: {profile_name}"
            if description:
                detail = f"{detail}\n{description}"
        elif run_workplace_profile:
            rows, detail = self._runtime_profile_builder.build(
                request.running_config,
                request.inventory_section,
            )
            profile_name = self._runtime_profile_builder.profile_name

        for old, row in manual_overrides.items():
            normalized = canonical_interface_name(old)
            if normalized:
                rows[normalized] = PortMapRow(
                    normalized,
                    canonical_interface_name(row.new_port) if row.new_port else row.new_port,
                    row.role,
                    row.note,
                )

        if manual_csv_detail:
            detail = manual_csv_detail if not detail else f"{detail}\n{manual_csv_detail}"

        return PortMapBuildResult(rows=rows, detail=detail, profile_name=profile_name)

    def build_workplace_from_running_config(self, run_cfg: str) -> PortMapBuildResult:
        return self.build(
            PortMapBuildRequest(
                running_config=run_cfg,
                use_workplace_profile=True,
            )
        )
