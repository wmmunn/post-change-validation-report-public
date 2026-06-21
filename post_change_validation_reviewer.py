#!/usr/bin/env python3
"""
Post-Change Validation Reviewer v19
Offline GUI tool for comparing pre/post Cisco switch refresh command logs.

Key behavior:
- Auto-detects environment-specific port mapping from post-change running-config by default
- Optional port map CSV override: old_port,new_port,role,note
- Built-in environment profile supports legacy Gi0/15/Gi0/16, Gi*/0/25/27 for 24-port layouts, Gi*/0/49/50, Gi*/0/51/52 uplinks and stack-aware uplink placement
- Fixes false stack member 0 detection from management interfaces such as Gi0/0
- Interface status comparison uses port map
- Trunk comparison uses port map
- CDP/LLDP comparison uses structured neighbor objects and mapped local interface
- Suppresses noisy per-port unchanged-notconnect rows; summarizes instead
- Exports HTML and PDF reports
- v10: context-aware STP root analysis; VLAN 4 isolation/remediation root changes are INFO, not WARN
- v11: adds Gi*/0/49 -> uplink A and Gi*/0/50 -> uplink B environment mapping
- v12: adds 24-port legacy uplink mapping Gi*/0/25 -> uplink A and Gi*/0/27 -> uplink B
- v13: adds gateway 0/1 neighbor-pair uplink inference; lower old port -> uplink A, higher old port -> uplink B
- v14: adds TenGigabitEthernet Te*/0/* access-port awareness
- v15: adds explicit model-based access detection, including c9300-24ux -> Te*/0/* access ports
- v16: fixes over-aggressive 24-port uplink mapping; 25/27 are only uplinks when trunk/gateway evidence supports it, and observed post-change neighbor ports can override default uplink targets
- v17: strengthens observed CDP/LLDP uplink overrides; same remote port + gateway/uplink evidence can override default stack uplink target even when neighbor names differ/truncate
- v18: adds Access Port MAC Correlation with full side-by-side MAC validation table for pre/post local access ports
- v19: adds hardware/health command analysis: transceivers, PoE, environment, inventory, version, and CPU summaries
- v20: adds STP path-cost method context from show spanning-tree summary for cost-only root-retained changes
- v21: recognizes bare #show and >show command prompts in copied logs
- v22: normalizes Cisco show-command abbreviations such as "sho inventory" and improves transceiver table handling
- v23: improves LLDP table parsing and reports when CDP/LLDP sections are present but no neighbor records parse

PDF export requires: pip install reportlab
"""

from __future__ import annotations

from typing import List

from src.post_change_validation_analysis import run_analysis
from src.post_change_validation_analysis_wrappers import (
    analyze_poe,
    analyze_transceivers,
)
from src.post_change_validation_command_sections import (
    COMMAND_ALIASES,
    COMMAND_PATTERNS,
    canonical_command,
    normalize_command_line,
    split_sections,
)
from src.post_change_validation_interface_status import InterfaceStatus, parse_interface_status
import src.post_change_validation_models as shared_models
from src.post_change_validation_neighbor_parsers import parse_cdp_neighbors, parse_lldp_neighbors
from src.post_change_validation_models import Finding, MacEntry, PortMapRow
import src.post_change_validation_port_map as port_map_core
from src.post_change_validation_port_map import (
    auto_build_port_map_from_running_config,
    load_port_map,
)
from src.post_change_validation_uplinks import (
    apply_observed_neighbor_port_overrides,
    infer_trunk_uplink_mappings,
)
from post_change_validation_gui import App

# Compatibility re-exports for tests and downstream callers.
PortMapRow = shared_models.PortMapRow
INT_PREFIXES = shared_models.INT_PREFIXES
INT_RE = shared_models.INT_RE
norm_interface = shared_models.norm_interface
find_first_interface = shared_models.find_first_interface
interface_sort_key = shared_models.interface_sort_key
detect_access_prefix_from_model = port_map_core.detect_access_prefix_from_model
infer_access_prefix_by_member_from_interfaces = port_map_core.infer_access_prefix_by_member_from_interfaces
infer_standalone_access_from_interfaces = port_map_core.infer_standalone_access_from_interfaces
infer_standalone_access_units_from_interfaces = port_map_core.infer_standalone_access_units_from_interfaces
parse_switch_provision = port_map_core.parse_switch_provision
detect_members_from_interfaces = port_map_core.detect_members_from_interfaces


def analyze(pre_text: str, post_text: str, port_map_path: str = "") -> List[Finding]:
    return run_analysis(pre_text, post_text, port_map_path)


if __name__ == "__main__":
    import customtkinter

    customtkinter.set_appearance_mode("System")
    customtkinter.set_default_color_theme("dark-blue")
    App().mainloop()
