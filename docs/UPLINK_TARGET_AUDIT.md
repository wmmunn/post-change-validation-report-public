# Uplink Target Determination — Design Audit

**Date:** 2026-06-21  
**Scope:** Post-Change Validation Reviewer — uplink **target assignment** only  
**Workspace:** `D:\workplace tooling\post change validation tool`

## User context

A proposed "drift-proof" trunk-scanning design briefly reintroduced hardcoded-port / discovery-order assumptions (first trunk → `Te1/1/1`, second → `Te2/1/8`). This audit inventories every code path that assigns an uplink **destination interface**, classifies each by evidence vs. convention vs. ordering, and records equivalence-test coverage. **No code changes were made.**

**Distinction used throughout:**

- **Detect uplink** — classify a source port as uplink-capable (trunk table, gateway neighbor, role string). Not counted as target assignment.
- **Assign uplink target** — write or select a specific `new_port` destination (`Te1/1/1`, `Te2/1/8`, profile target, etc.).

---

## 1. Executive summary

| Class | Count | Description |
|-------|-------|-------------|
| **(a) Evidence-derived** | 4 | Observed CDP/LLDP override, manual CSV, map-note target lookup, trunk/gateway-gated inference (detection only; targets still convention-sourced) |
| **(b) Order-dependent** | 3 | Gateway-pair lower/higher sort, trunk-pair lower/higher sort, `standard_uplink_targets_from_map` first-match scan order |
| **(c) Hardcoded/convention** | 7 | Stack `Te{first}/1/1` + `Te{last}/1/8`, Gi49–52 pairs, Gi0/15–16, lone port 25→A/27→B, evidence-gated fallback `Te1/1/1`/`Te1/1/8`, JSON profile uplink_rules (×2 profile families counted as one mechanism with sub-entries) |

| Class | Mechanisms | Equivalence-tested | Gap |
|-------|------------|-------------------|-----|
| **(a) Evidence-derived** | 4 | 3 of 4 partial/full | Map-note lookup has no dedicated test |
| **(b) Order-dependent** | 3 | 2 of 3 | Lone-25 path is new behavior, explicitly not legacy-equivalent |
| **(c) Hardcoded/convention** | 7 | 5 of 7 partial | JSON-only profiles, lone 25/27 convention (U-04 fallback now tested) |

**Overall risk posture:** **Moderate** on the default auto-detect path (U-04 fallback now evidence-gated). Most runtime assignments still resolve to convention-based A/B targets (`Te<first>/1/1`, `Te<last>/1/8`) with order-dependent role binding. Observed-neighbor override and manual CSV remain primary safety valves. Gateway-pair inference has strong legacy equivalence coverage; lone-25 trunk inference still lacks legacy parity.

Wrong uplink targets are plausible when physical wiring, platform module layout, or port numbering diverges from environment assumptions. Mitigations exist (observed CDP/LLDP override, manual CSV) but are not automatic.

---

## 2. Methodology

### Files searched

| Area | Paths |
|------|-------|
| Uplink inference | `src/post_change_validation_uplinks.py` |
| Target resolution | `src/post_change_validation_analysis_wrappers.py` (`standard_uplink_targets_from_map`, `extract_uplink_targets_from_map`) |
| Auto port map | `src/port_mapping/private/workplace_profile.py`, `src/post_change_validation_port_map.py` |
| Profile engine | `src/port_mapping/rules.py`, `src/port_mapping/engine.py`, `src/port_mapping/profiles/public/*.json` |
| Orchestration | `src/post_change_validation_analysis.py`, `post_change_validation_reviewer.py` |
| Strategies shim | `src/post_change_validation_mapping_strategies.py` |
| Tests | `tests/test_uplink_inference.py`, `tests/test_port_mapping_workplace_equivalence.py`, `tests/test_port_mapping_strategies.py`, `tests/test_analysis_orchestration_equivalence.py`, `tests/test_transceiver_analysis.py`, `tests/test_manual_csv_loader.py` |
| Docs | `docs/environment-assumptions.md`, `../PORT_MAPPING_DESIGN.md` |

### Search terms

`uplink`, `trunk`, `Te1/1`, `Te2/1/8`, `Gi1/0/49`, `Gi0/15`, `Gi0/16`, `infer_trunk`, `infer_gateway`, `apply_observed`, `standard_uplink`, `uplink A`, `uplink B`, `target_ports`, port `25`/`27`/`49`–`52`, `WorkplaceProfile`, `gateway_pair`.

### What counts as target assignment

Any code that sets `PortMapRow.new_port` (or equivalent) for a row whose role/note indicates uplink, or selects among candidate `Te*/1/*` module ports as the mapped destination.

**Excluded:** STP root comparison, transceiver matching, MAC/PoE correlation — these **consume** the port map but do not assign uplink targets.

---

## 3. Inventory table

| ID | Location | Mechanism | Target assigned | Class | Equivalence test | Failure scenario |
|----|----------|-----------|-----------------|-------|------------------|------------------|
| U-01 | `src/port_mapping/private/workplace_profile.py:172-175` `_build_port_map_from_running_config` | Stack member order → A/B anchor | `Te{first_member}/1/1`, `Te{last_member}/1/8` | **c** | Y — `test_port_mapping_workplace_equivalence.py` (full map); `test_auto_builds_sanitized_stack_port_map` in `test_transceiver_analysis.py` | 3-member stack where uplink modules are not on first/last member; platform uses `/1/2` not `/1/1` |
| U-02 | `src/port_mapping/private/workplace_profile.py:217-220` | Per-member legacy SFP port pairs | `Gi*/0/49`,`51`→A; `Gi*/0/50`,`52`→B | **c** | Y — same as U-01 | Uplinks on non-standard ports (e.g. `Gi1/0/48`); 24-port member gets 49–52 rows that never existed physically |
| U-03 | `src/port_mapping/private/workplace_profile.py:222-224` | Legacy chassis aliases | `Gi0/15`→A, `Gi0/16`→B | **c** | Y — same as U-01 | Site used `Gi0/13`/`Gi0/14` or single uplink only |
| U-04 | `src/post_change_validation_analysis_wrappers.py` `standard_uplink_targets_from_map` | Scan map notes / `Gi0/15`/`16`; **evidence-backed fallback** (full and partial) | Reads A/B from map; missing side requires Catalyst model + transceiver presence for default **`Te1/1/1`** or **`Te1/1/8`**; full fallback requires both | **c** (+ **b** for first-match scan) | **Y** — `tests/test_standard_uplink_targets_from_map.py` (pass/fail full and partial fallback cases) | Partial or minimal map without uplink rows on unsupported hardware → empty targets + WARN finding |
| U-05 | `src/post_change_validation_uplinks.py:112-166` `infer_gateway_pair_uplink_mappings` | Gateway 0/1 CDP/LLDP pair + interface sort | Lower old port→A, higher→B (values from U-04) | **a** detect + **b** role + **c** target values | Y — `test_gateway_pair_inference_matches_legacy_inline_output` | `wl0-gw` on higher port number than `wl1-gw` → A/B swapped vs physical primary/secondary |
| U-06 | `src/post_change_validation_uplinks.py:203-206` `infer_trunk_uplink_mappings` (≥2 candidates) | Pre-change trunk on `Gi*/0/25\|27`; sorted pair | `ports[0]`→A, `ports[-1]`→B | **a** detect + **b** assign + **c** targets | Y — `test_two_candidate_trunk_uplink_inference_matches_v24_temp_output` | Only `Gi1/0/27` is real uplink but listed after `Gi1/0/25` in sort → 25 gets A incorrectly |
| U-07 | `src/post_change_validation_uplinks.py:184-201` `infer_trunk_uplink_mappings` (lone candidate) | Single trunk on 25 or 27 | Port **25**→A, port **27**→B | **a** detect + **c** port-number convention | **N** — `test_lone_25_trunk_candidate_maps_to_uplink_a_as_current_domain_behavior` documents **intentional** non-equivalence with v24 temp baseline | Sole uplink on `Gi1/0/27` maps to B; operator expects A; mixed-stack lone-25 on 24-port member while 48-port member owns B |
| U-08 | `src/post_change_validation_uplinks.py:231-313` `apply_observed_neighbor_port_overrides` | Post-change CDP/LLDP same remote port | Observed `post_local` (e.g. `Te2/1/1`) | **a** | Y — `test_observed_neighbor_override_matches_legacy_inline_output`; ambiguous case in `test_observed_neighbor_override_ambiguous_post_matches_do_not_change_map` | Multiple post matches on same remote → no override (safe); zero matches leaves wrong convention target |
| U-09 | `src/port_mapping/rules.py:61-93` `build_rows_from_json_profile` | Profile `uplink_rules` zip source→target | Profile-defined (e.g. `Te1/1/1`–`Te1/1/4`) | **c** | Partial — `test_port_mapping_strategies.py` boundary tests only | Operator selects wrong generic profile for hardware |
| U-10 | `src/port_mapping/profiles/public/generic_c9300_48p.json` (and 24p, mgig) | Static uplink_rules | `Gi1/0/49-52` → `Te1/1/1-4` or `Gi1/0/25-28` → same | **c** | Partial — `test_port_mapping_strategies.py` | Non-standard module port layout |
| U-11 | `src/port_mapping/profiles/public/generic_mixed_24_48_to_mgig_stack.json` | Per-member uplink_rules | M1: `25,27`→`Te1/1/1,Te1/1/8`; M2: `49-52`→`Te2/1/1-8` | **c** | Partial — `test_public_mixed_24_48_mgig_profile_uses_member_specific_density` | Same as U-10; encodes first-member/last-member Te convention |
| U-12 | `src/port_mapping/rules.py:146-171` + `src/port_mapping/engine.py:74-82` | Manual CSV override | Operator-supplied `new_port` | **a** | Y — `test_manual_csv_override_takes_priority_over_profile_range`; orchestration with `synthetic_correct_uplinks_port_map.csv` | Operator CSV error (human factor) |
| U-13 | `src/port_mapping/profiles/public/generic_ie3300_standalone.json` | IE uplink_rules | `Gi1/9`,`Gi1/10`→same (same-name) | **c** | Partial — `test_public_ie3300_profile_handles_legacy_source_names` | Industrial fiber ports not 9/10 |
| U-14 | `src/port_mapping/private/workplace_profile.py:114-170` standalone industrial branch | IE two-part mapping only | **No** `Te1/1/1`/`Te1/1/8` forced | n/a (no Catalyst uplink assignment) | Y — workplace equivalence standalone fixture | N/A — uplink targets deferred to inference |

---

## 4. Detailed entries

### U-01 — Stack uplink A/B anchor targets

**File:** `src/port_mapping/private/workplace_profile.py`

```172:175:src/port_mapping/private/workplace_profile.py
    first_member = members[0]
    last_member = members[-1]
    uplink_a = f"Te{first_member}/1/1"
    uplink_b = f"Te{last_member}/1/8"
```

All downstream convention mappings (U-02, U-03, U-05, U-06, U-07) consume these anchors.

---

### U-02 — Gi49/50/51/52 → A/B (all stack members)

```216:220:src/port_mapping/private/workplace_profile.py
    for member in members:
        rows[f"Gi{member}/0/49"] = PortMapRow(f"Gi{member}/0/49", uplink_a, "uplink", "Auto standard uplink A mapping Gi*/0/49 -> first-member Te/1/1")
        rows[f"Gi{member}/0/50"] = PortMapRow(f"Gi{member}/0/50", uplink_b, "uplink", "Auto standard uplink B mapping Gi*/0/50 -> last-member Te/1/8")
        rows[f"Gi{member}/0/51"] = PortMapRow(f"Gi{member}/0/51", uplink_a, "uplink", "Auto standard uplink A mapping Gi*/0/51 -> first-member Te/1/1")
        rows[f"Gi{member}/0/52"] = PortMapRow(f"Gi{member}/0/52", uplink_b, "uplink", "Auto standard uplink B mapping Gi*/0/52 -> last-member Te/1/8")
```

Note: Applied to **every** member including 24-port switches where ports 49–52 may not exist on legacy source hardware.

---

### U-03 — Gi0/15/Gi0/16 legacy chassis

```222:224:src/port_mapping/private/workplace_profile.py
    rows["Gi0/15"] = PortMapRow("Gi0/15", uplink_a, "legacy_uplink", "Auto legacy uplink A mapping Gi0/15 -> standard uplink A")
    rows["Gi0/16"] = PortMapRow("Gi0/16", uplink_b, "legacy_uplink", "Auto legacy uplink B mapping Gi0/16 -> standard uplink B")
```

---

### U-04 — Standard uplink target lookup + evidence-backed fallback **RESOLVED**

```174:230:src/post_change_validation_analysis_wrappers.py
def standard_uplink_targets_from_map(
    pm: Dict[str, PortMapRow],
    *,
    version_section: str = "",
    inventory_section: str = "",
    transceiver_section: str = "",
) -> StandardUplinkTargetsResult:
    ...
    if a and not b:
        review_reason = _confirm_single_standard_uplink_fallback_target(
            DEFAULT_STANDARD_UPLINK_B, ...
        )
        ...
    if b and not a:
        review_reason = _confirm_single_standard_uplink_fallback_target(
            DEFAULT_STANDARD_UPLINK_A, ...
        )
        ...
    return _confirm_standard_uplink_fallback(
        DEFAULT_STANDARD_UPLINK_A,
        DEFAULT_STANDARD_UPLINK_B,
        ...
    )
```

When map rows lack one or both A/B targets, any **default** side (`Te1/1/1` / `Te1/1/8`) is returned only when:

1. **Model evidence** — `show version` or `show inventory` matches supported Catalyst families (`C9200`, `C9300`, `C9500`) via `SUPPORTED_CATALYST_FAMILY_PATTERN`.
2. **Transceiver evidence** — each proposed default target appears in parsed `show interfaces transceiver detail` output.

Applies to **full fallback** (neither A nor B in map) and **partial fallback** (exactly one side from map; the missing default is evidence-gated via `_confirm_single_standard_uplink_fallback_target`).

If either check fails, the function returns empty targets `("", "")` and a `review_reason`; callers emit a **WARN** `Port Map` finding (`uplink_fallback_review_finding`).

**Scope note:** U-01 workplace profile hardcoding remains separate; this fix applies to fallback paths inside `standard_uplink_targets_from_map` and its callers (`infer_gateway_pair_uplink_mappings`, `infer_trunk_uplink_mappings`, `extract_uplink_targets_from_map`, `analyze_transceivers`).

---

### U-05 — Gateway 0/1 pair inference

Detection: pre-change CDP/LLDP names matching `*0-gw` / `*1-gw` pattern.  
Assignment: sort local interfaces; **lowest → uplink_a**, **highest → uplink_b**.

```139:164:src/post_change_validation_uplinks.py
        locals_sorted = sorted(by_local.keys(), key=interface_sort_key)
        ...
        low = locals_sorted[0]
        high = locals_sorted[-1]
        ...
        pm[low] = PortMapRow(
            low,
            uplink_a,
            "inferred_gateway_uplink",
            f"v13 inferred gateway 0/1 pair: lower old interface -> uplink A ({uplink_a})",
        )
        pm[high] = PortMapRow(
            high,
            uplink_b,
            "inferred_gateway_uplink",
            f"v13 inferred gateway 0/1 pair: higher old interface -> uplink B ({uplink_b})",
        )
```

Does **not** use gateway name suffix `0`/`1` to bind A/B — only port sort order.

---

### U-06 — Trunk pair inference (24-port ports 25/27)

Requires trunk evidence on `Gi*/0/25` or `Gi*/0/27`. Two candidates per member: sorted low→A, high→B.

```203:206:src/post_change_validation_uplinks.py
        low, high = ports[0], ports[-1]
        pm[low] = PortMapRow(low, uplink_a, "legacy_24port_uplink", f"v16 inferred from pre-change trunk table: lower 24-port trunk -> uplink A ({uplink_a})")
        pm[high] = PortMapRow(high, uplink_b, "legacy_24port_uplink", f"v16 inferred from pre-change trunk table: higher 24-port trunk -> uplink B ({uplink_b})")
        inferred.append(f"{low} -> {uplink_a}; {high} -> {uplink_b}")
```

This is **not** "first trunk in discovery order → Te1/1/1" — candidates are filtered to 25/27 pattern then **sorted** by `interface_sort_key`. Still order/convention-sensitive for A/B role.

---

### U-07 — Lone 25/27 trunk candidate (v24+ behavior)

```192:201:src/post_change_validation_uplinks.py
            target = uplink_a if only_port.group(1) == "25" else uplink_b
            if current_new == target:
                continue
            pm[only] = PortMapRow(
                only,
                target,
                "legacy_24port_uplink",
                f"v24 inferred from mixed-stack pre-change trunk table: legacy 24-port trunk -> {'uplink A' if only_port.group(1) == '25' else 'uplink B'} ({target})",
            )
```

**Explicitly not legacy-equivalent** — `test_lone_25_trunk_candidate_maps_to_uplink_a_as_current_domain_behavior` states v24 temp baseline returns `[]` for this case.

---

### U-08 — Observed post-change neighbor override

Assigns target from **unique** post-change CDP/LLDP local interface matching pre remote port (+ gateway/uplink corroboration). Strongest evidence-derived assignment path.

```306:312:src/post_change_validation_uplinks.py
        pm[old_local] = PortMapRow(
            old_local,
            post_local,
            "observed_neighbor_uplink_override",
            f"v17 observed post-change CDP/LLDP neighbor evidence overrides default target: {record.neighbor}, remote {remote}",
        )
        overrides.append(f"{old_local} -> {post_local} ({record.neighbor}, remote {remote})")
```

---

### U-09–U-11 — JSON profile uplink_rules

Profiles declare fixed source→target pairs. Example mixed-stack profile:

```18:24:src/port_mapping/profiles/public/generic_mixed_24_48_to_mgig_stack.json
      "uplink_rules": [
        {
          "source_ports": ["Gi1/0/25", "Gi1/0/27"],
          "target_ports": ["Te1/1/1", "Te1/1/8"],
          "role": "uplink",
          "requires_operator_review": true
        }
```

Used only when operator/engine selects JSON profile path (not default workplace auto-build).

---

### U-12 — Manual CSV

Highest precedence in `PortMappingEngine.build`. Explicit operator intent — treated as **(a)**.

```74:82:src/port_mapping/engine.py
        for old, row in manual_overrides.items():
            normalized = canonical_interface_name(old)
            if normalized:
                rows[normalized] = PortMapRow(
                    normalized,
                    canonical_interface_name(row.new_port) if row.new_port else row.new_port,
                    row.role,
                    row.note,
                )
```

---

### U-14 — Standalone industrial (no forced Te uplink)

Standalone IE path maps access ports only; `docs/environment-assumptions.md:35` states Catalyst-style `Te1/1/1`/`Te1/1/8` are **not** applied unless trunk/neighbor evidence triggers inference (U-06/U-08).

```114:170:src/port_mapping/private/workplace_profile.py
        standalone_units = infer_standalone_access_units_from_interfaces(running_config)
        ...
        return rows, "\n".join(detail_lines)
```

(Standalone branch returns before stack uplink anchor logic at lines 172–175.)

---

## 5. Gateway-pair inference — equivalence test bar (reference)

The gateway-pair path is the **documented bar** for legacy behavioral equivalence:

| Test | File | What it proves |
|------|------|----------------|
| `test_gateway_pair_inference_matches_legacy_inline_output` | `tests/test_uplink_inference.py` | Extracted module output identical to frozen `legacy_infer_gateway_pair_uplink_mappings` inline copy |
| `test_gateway_pair_inference_overrides_lower_and_higher_old_ports` | same | Functional: `Gi1/0/25`→`Te1/1/1`, `Gi1/0/27`→`Te1/1/8` |
| `test_gateway_pair_inference_single_side_no_match_does_not_change_map` | same | Negative case: no spurious assignment |
| `test_run_analysis_matches_legacy_for_auto_detected_uplink_fixture` | `tests/test_analysis_orchestration_equivalence.py` | End-to-end with `synthetic_correct_uplinks_*.log` fixtures |

**Pattern:** duplicate legacy inline helper in test file → assert extracted == legacy on same fixtures → assert port map snapshots match.

---

## 6. Gaps / items with no equivalence coverage

| Gap | Risk |
|-----|------|
| ~~**`standard_uplink_targets_from_map` fallback** (`Te1/1/1`/`Te1/1/8`)~~ | **Resolved (U-04)** — evidence-backed full and partial fallback with WARN on failure |
| **Lone-25 trunk inference (U-07)** | New v24 behavior; test explicitly rejects v24 temp parity |
| **JSON-only profiles (U-10, U-11)** | Boundary tests only; no legacy inline equivalence |
| **Gateway name 0/1 vs port sort** | No test where `wl1-gw` is on lower port than `wl0-gw` |
| **Multi-member trunk grouping edge cases** | No test for >2 trunk candidates on same member |
| **Observed override when post target already in trunk set** | `current_new in post_trunks` skip path lightly covered |
| **3+ member stacks** | Workplace equivalence uses 2-member fixture only |

---

## 7. Detection-only paths (not target assignment)

For completeness — these influence uplink **classification** but do not assign destinations:

| Function | File | Role |
|----------|------|------|
| `parse_trunks` | `src/post_change_validation_uplinks.py:63-86` | Collect trunk local ports |
| `old_uplink_ports_from_evidence` | `src/post_change_validation_uplinks.py:89-100` | MAC exclusion set |
| `looks_like_uplink_neighbor` | `src/post_change_validation_uplinks.py:210-215` | Gateway/router CDP heuristics |
| `looks_like_new_uplink_interface` | `src/post_change_validation_uplinks.py:218-228` | Filter post candidates for override |
| `extract_uplink_targets_from_map` | `src/post_change_validation_analysis_wrappers.py:106-119` | Read targets for transceiver analysis |
| STP / trunk / neighbor comparators | various | Consume `old_to_new` map |

---

## 8. Orchestration order (reference)

When no manual CSV is supplied (`src/post_change_validation_analysis.py:116-123`):

1. `WorkplaceProfile.build` → U-01–U-03 (convention targets)
2. `infer_gateway_pair_uplink_mappings` → U-05 (may overwrite access rows)
3. `infer_trunk_uplink_mappings` → U-06/U-07
4. `apply_observed_neighbor_port_overrides` → U-08 (last; evidence wins)

Manual CSV path skips steps 2–4 (`not port_map_path` guard).

```116:123:src/post_change_validation_analysis.py
        report_progress("Applying uplink inference", 0.2)
        inferred_gateway_maps: List[str] = []
        inferred_trunk_maps: List[str] = []
        observed_neighbor_overrides: List[str] = []
        if pm and not port_map_path:
            inferred_gateway_maps = infer_gateway_pair_uplink_mappings(pre, pm)
            inferred_trunk_maps = infer_trunk_uplink_mappings(pre, pm)
            observed_neighbor_overrides = apply_observed_neighbor_port_overrides(pre, post, pm)
```

---

## 9. Explicit statement

**No application or engine code changes were made during this audit.** This document is inventory and classification only; no fixes are proposed.
