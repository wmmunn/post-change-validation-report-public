# Port Mapping Design

## Purpose

This document freezes the intended architecture for making the Post Change Validation Tool public-ready without breaking validated reporting behavior.

The tool has two distinct responsibilities:

- Analyze pre-change and post-change Cisco command logs.
- Decide how old interfaces should be matched to new interfaces during a refresh.

The public architecture must keep those responsibilities separate. The analyzer should consume clean `PortMapRow` data and evidence from command logs. It should not contain private site-specific migration assumptions.

## Non-Breaking Report Posture

The report must continue serving both purposes:

- Clear visual triage during a live maintenance window.
- Clean textual evidence for long-term ticket archival.

Expected/observed mapping improvements may add clearer detail text inside existing finding structures, but port-mapping work must not redesign the report.

## Architecture Split

The public analyzer core should compare parsed evidence using an already-built port map.

The port-mapping layer should build that port map from one selected strategy:

- Manual operator override.
- Public model profile (JSON under `src/port_mapping/profiles/public/`).
- Same-name fallback.
- Optional operator-local JSON profile for site-specific workflows (not shipped with the public repository).

Observed evidence from MAC, CDP, LLDP, PoE, or interface-status output must not silently rewrite the expected map. Observed evidence is an annotation layer used by the analyzer to explain whether a device appears to have landed somewhere other than the expected post-change port.

## Mapping Precedence

Mapping must follow an explicit, non-guessing order:

1. Manual user overrides.
2. Selected public model profile.
3. Same-name fallback.

Manual overrides are loaded from an optional operator CSV or JSON file and are trusted as the highest-priority expected map.

Public model profiles are evaluated through explicit range and port blocks. They should not contain private environment assumptions.

Same-name fallback applies when no manual override or selected profile rule covers an interface.

Observed placement evidence is not part of this precedence ladder. It is reported separately as comparison evidence.

## Expected vs Observed Ports

The analyzer should distinguish these values:

- `expected_post_port`: the post-change port returned by the mapping strategy.
- `observed_post_port`: a post-change port suggested by MAC, CDP, LLDP, PoE, or interface-status evidence.

Finding logic should preserve this distinction:

- `PASS`: expected port is present and evidence agrees.
- `PASS + EVIDENCE`: expected port evidence is incomplete, but endpoint presence is supported elsewhere.
- `WARN`: expected port is missing and no supporting observed evidence is available.
- `OBSERVED PLACEMENT SHIFT`: observed evidence points to a different post-change port than the expected map.

The tool should force operator review when expected and observed placement differ.

## Public JSON Profile Schema

Public profiles should use flat, explicit, range-based JSON structures. The first public version should avoid custom regex matching as the primary profile mechanism.

Example:

```json
{
  "profile_name": "generic_c9300_48p",
  "description": "Generic 48-port Catalyst access switch refresh template.",
  "fallback": "same_name",
  "access_port_rules": [
    {
      "source_range": "Gi1/0/1-48",
      "target_range": "Gi1/0/1-48",
      "role": "access"
    }
  ],
  "uplink_rules": [
    {
      "source_ports": ["Gi1/0/49", "Gi1/0/50"],
      "target_ports": ["Te1/1/1", "Te1/1/2"],
      "role": "uplink",
      "requires_operator_review": true
    }
  ]
}
```

Potential public profile fields:

- `profile_name`: stable machine-readable profile name.
- `description`: operator-readable summary.
- `source_models`: optional list of source model identifiers.
- `target_models`: optional list of target model identifiers.
- `fallback`: fallback strategy, initially `same_name`.
- `member_rules`: optional per-stack-member rules for asymmetrical stacks.
- `access_port_rules`: range-based access-port mapping rules.
- `uplink_rules`: explicit uplink source and target port rules.
- `standalone_rules`: optional rules for industrial or standalone switch numbering.
- `requires_operator_review`: marks mappings that should be highlighted for human review.

Per-member rules should be preferred when a stack contains asymmetrical source or target hardware, such as one 24-port member and one 48-port member. Each member can declare its own access-port ranges and uplink rules:

```json
{
  "profile_name": "generic_mixed_24_48_to_mgig_stack",
  "fallback": "same_name",
  "member_rules": [
    {
      "member": 1,
      "access_port_rules": [
        {
          "source_range": "Gi1/0/1-24",
          "target_range": "Te1/0/1-24",
          "role": "access"
        }
      ],
      "uplink_rules": [
        {
          "source_ports": ["Gi1/0/25"],
          "target_ports": ["Te1/1/1"],
          "role": "uplink",
          "requires_operator_review": true
        }
      ]
    },
    {
      "member": 2,
      "access_port_rules": [
        {
          "source_range": "Gi2/0/1-48",
          "target_range": "Te2/0/1-48",
          "role": "access"
        }
      ],
      "uplink_rules": [
        {
          "source_ports": ["Gi2/0/52"],
          "target_ports": ["Te2/1/8"],
          "role": "uplink",
          "requires_operator_review": true
        }
      ]
    }
  ]
}
```

## Public Profile Candidates

Initial public-safe profiles should be generic and documented as assumptions:

- Same-name mapping.
- Generic Catalyst stack access-port mapping.
- Generic C9200/C9300 24-port access switch profile.
- Generic C9200/C9300 48-port access switch profile.
- Generic C9300 mGig or UX/UN-style access switch profile.
- Generic mixed 24/48-port stack to mGig profile using per-member rules.
- Generic IE/IE3300 standalone industrial profile.
- Custom profile template.

Profiles should explain what they assume and when an operator should prefer a manual map.

## Operator-Local Profile Isolation

Site-specific assumptions must not live in the public analyzer core or the public repository.

Operator-local mappings should live in an untracked file outside version control, for example:

```text
/path/to/my_site_migration_profile.json
```

Or copy and customize the shipped template:

```text
src/port_mapping/profiles/templates/custom_profile_template.json
config.yaml.example
```

The public release loads generic public profiles or same-name fallback by default. Operators may point the tool at a local JSON profile or manual CSV when migrations fall outside the generic templates.

Local profile files must not include credentials, raw command logs, customer names, private topology names, screenshots, or other operational artifacts.

## Manual Override Formats

The current CSV override behavior should remain supported.

Expected CSV columns:

- `old_port`
- `new_port`
- `role`
- `note`

Future JSON overrides may use a direct row list:

```json
{
  "profile_name": "operator_manual_override",
  "mappings": [
    {
      "old_port": "Gi1/0/1",
      "new_port": "Gi1/0/1",
      "role": "access",
      "note": "Operator-provided mapping"
    }
  ]
}
```

Manual override rows should be treated as expected mappings, not observed evidence.

## Roadmap: Multi-Signal Uplink Confidence Detection

- Three independent evidence sources: STP root-port status, CDP neighbor capability flag (router vs switch), and presence in show interfaces trunk.
- These are NOT an AND condition. STP root port is the strongest/primary signal. Trunk membership is corroborating. CDP router-capability is a confidence booster only — switch-to-switch uplinks are a known real-world pattern (fiber path constraints) and must not be penalized for lacking router capability.
- Open design question: does this need to support multiple simultaneous uplinks per switch, since STP only elects one root port but additional trunk links may also be legitimate uplinks (redundant paths, or multiple router connections)? Needs a 'confirmed primary' vs 'probable secondary, unconfirmed by STP' distinction, not a single binary uplink/not-uplink classification.
- This does not replace the existing port-number-convention heuristic (e.g. 2960XR 24-port SFP uplinks starting at interface 25) — it's a stronger, hardware-independent signal to use alongside or ahead of it.

## Refactoring Guidance

Port-mapping refactoring should be incremental and test-backed.

Recommended order:

1. Add sanitized tests for manual CSV loading.
2. Add sanitized tests for same-name fallback behavior.
3. Add sanitized tests for one public JSON profile.
4. Extend public profile parsing in the dedicated port-mapping module.
5. Preserve compatibility re-exports at the entry point until downstream callers migrate.
6. Keep report rendering unchanged.

Do not mass-convert existing working parser logic solely for cleanup. Apply parser standardization rules only to new or functionally modified parser behavior.

## Future UI Direction

The intended long-term UI direction is to transition this app, and the related workflow tools in the suite, to CustomTkinter for a more consistent modern interface.

That migration is explicitly deferred. The current priority is finishing the logic/reporting refactor, preserving validated operator-facing behavior, and keeping the package stable. Do not begin a Tkinter-to-CustomTkinter conversion as part of the current parser, mapping, report, or packaging refactor unless it is opened as a separate design and implementation pass.

## Safety Boundaries

The public tool remains offline and operator-gated.

It must not:

- Connect to devices.
- Execute network commands.
- Modify source logs.
- Infer private site policy from raw examples.
- Hide uncertainty in mapping decisions.

When confidence is low, the tool should report review context rather than guessing.
