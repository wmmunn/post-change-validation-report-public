# Environment Assumptions

This document describes the default network-validation assumptions baked into the Post Change Validation Tool. These are generic refresh patterns for common Cisco Catalyst and industrial switch migrations—not site-specific policy.

## Supported Platforms and Logs

The tool is intentionally scoped to **Cisco IOS and IOS-XE** switch command logs. Before parsing, it requires a recognizable IOS or IOS-XE software line in `show version`.

**Out of scope:** NX-OS (Nexus), IOS-XR, ASA, and other Cisco OS families. Their CLI output, interface syntax, and command shapes differ enough that auto-parsers and port-map inference would be unreliable. Unsupported logs are hard-stopped at file selection and again before analysis.

Review these assumptions before relying on auto-detected port maps or default uplink inference during a change window.

## Port Mapping

### Auto-detection source

When no manual CSV override is supplied, the tool builds an expected old-to-new port map from the post-change `show running-config` section (and related inventory evidence when available).

### Stack member detection

- Stack members are inferred from `switch N provision` lines when present.
- When provision lines are missing, member numbers are inferred from interface naming patterns.
- Management interfaces such as `Gi0/0` must not be treated as stack member `0`.

### Access-port prefix detection

Access-port naming depends on detected hardware model and PID evidence:

- Standard Catalyst access ports typically map through `Gi` or `Te` prefixes depending on model.
- `c9300-24ux`-class hardware may use `Te*/0/*` for access ports.
- `c9300-48un`-class hardware may use `Fi` (FiveGigabitEthernet) for access ports.
- TenGigabitEthernet `Te*/0/*` access-port awareness applies on supported newer models.

### Standalone industrial switches

For IE/IE3300-style standalone devices:

- Two-part interface numbering such as `GigabitEthernet1/1` is supported.
- Legacy `Fa0/x`, `Fa1/x`, `Gi0/x`, and `Gi1/x` forms may map to detected post-change ports.
- Flattened legacy chassis aliases may map high-numbered base ports to expansion-module ports when multiple interface banks are detected.
- Catalyst-style forced uplink targets (`Te1/1/1` / `Te1/1/8`) are not applied unless trunk or neighbor evidence supports uplink classification.

### Default uplink targets (stack migrations)

For typical Catalyst stack refreshes:

- Uplink A target: `Te<first stack member>/1/1`
- Uplink B target: `Te<last stack member>/1/8`

Legacy source uplink candidates may include:

- `Gi0/15`, `Gi0/16`
- `Gi*/0/49`, `Gi*/0/50`, `Gi*/0/51`, `Gi*/0/52`
- `Gi*/0/25`, `Gi*/0/27` on 24-port layouts **only when trunk or gateway evidence supports uplink inference**

Observed post-change CDP/LLDP neighbor ports may override default uplink targets when trunk or gateway evidence agrees.

## Expected vs Observed Placement

The tool distinguishes:

- **Expected post port** — from the port map (manual CSV, profile, or auto-build).
- **Observed post port** — suggested by MAC, CDP, LLDP, PoE, or interface-status evidence.

When expected and observed placement differ, findings call for operator review rather than silent remapping.

## STP Root Comparison

- Retained root with mapped root-port changes may report path-cost method context from `show spanning-tree summary`.
- VLAN 1 local-root changes may be informational when the post-change VLAN 1 SVI is administratively shutdown; operators should still verify local VLAN design intent.
- Optional informational VLAN overrides may be supplied by environment-specific profiles; the public default treats all VLANs consistently unless explicitly configured.

## Neighbor and Endpoint Evidence

- Missing CDP/LLDP advertisements may downgrade to informational findings when mapped-port MAC or PoE evidence shows the endpoint is still present.
- Gateway-style neighbor names and router-capability flags contribute to uplink inference but are not sole proof of uplink status.

## Manual Override Precedence

A manual port-map CSV (or JSON profile override) always takes precedence over auto-detection and generic JSON profiles.

Use manual overrides for nonstandard migrations, asymmetric hardware, or when auto-detection confidence is low.

## Safety Reminder

These assumptions help prioritize review findings during a refresh. They do not replace operator judgment, design documentation, or post-change validation runbooks.

For background on how the tool was developed and tested before its public release, see [Development & Testing History](development-and-testing-history.md).
