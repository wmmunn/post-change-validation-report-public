# Post Change Validation Tool — Changelog


## v1.0.3 - Running-config Cisco gate and inventory alias

- Log acceptance gate now checks parsed `show running-config` for the word `cisco` (case-insensitive) instead of strict `show version` IOS/IOS-XE banner signatures.
- Added `show inv` command-section alias mapping to `show inventory` for abbreviated Cisco IOS captures.
- Regenerated standalone Windows EXE; refreshed SHA256 integrity chain in README and `dist/post_change_validation_reviewer.exe.sha256`.


## v1.0.2 - Security pin, CI badges, release integrity

- Pin `pillow>=10.0.1` in requirements for security advisories.
- GitHub Actions CI workflow and README badges (CI, Snyk).
- Regenerated standalone EXE with updated dependency pin; refreshed SHA256 integrity chain.
- PDF PoE budget meter and bar layout (carried from v1.0.1).

## v1.0.1 — PDF PoE budget meter and bar layout

- PDF PoE budget meter aligned with HTML reference rendering.
- PoE bar width fix (686pt, fits within card layout).
- Regenerated sample reports; `scripts/regenerate_sample_reports.py` for reproducible samples.

## v1.0.0 — Initial Public Release

First public release of the Post Change Validation Tool.

### Highlights

- Offline GUI reviewer for pre-change and post-change Cisco switch command logs.
- Modular engine under `src/` with parsers, analysis orchestration, port mapping, and report rendering.
- Single entry point: `post_change_validation_reviewer.py`.
- CustomTkinter GUI with HTML and optional PDF report export.
- Environment-aware port-map auto-detection with manual CSV override support.
- Structured comparisons for interface status, trunks, CDP/LLDP neighbors, MAC tables, STP root, PoE, transceivers, environment, inventory, version, and CPU evidence.
- Summary-first reports with severity counts, category highlight cards, and off-card review visibility.
- JSON port-mapping profiles for generic Catalyst, mGig, mixed-stack, and industrial standalone templates.
- Broad sanitized unit-test coverage across parsers, mapping, analysis, and rendering.

### Analysis capabilities (cumulative)

- Command-section parsing with prompt-prefixed, bare `#show`/`>show`, and abbreviated `sho`/`sh int` forms.
- Port-map auto-build from post-change running-config with stack-member detection and model-aware access prefixes.
- Gateway-pair and trunk-evidence uplink inference with observed CDP/LLDP override support.
- Access-port MAC correlation with side-by-side pre/post validation table.
- Context-aware STP root comparison with path-cost method notes for retained-root cost changes.
- Neighbor missing-advertisement reconciliation using mapped-port MAC and PoE evidence.
- Transceiver threshold visualization with optional pre/post pairing through the port map.
- PoE budget and per-port delivery comparison with observed-placement support.
- Standalone industrial (IE/IE3300) port mapping, neighbor, MAC, PoE, and transceiver handling.

### Safety posture

- Offline, read-only review tool.
- No device connectivity or command execution.
- Findings are operator review evidence, not automatic change approval.
