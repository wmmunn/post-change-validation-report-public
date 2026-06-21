# Development & Testing History

This document summarizes how the Post Change Validation Tool was developed and checked before its initial public release. It is background for operators and contributors—not a warranty of completeness.

## Development timeline

Development began in late April 2026 as an early exploratory project. Starting in June 2026, the tool moved into a structured development process — 10 numbered internal releases (v15–v24), each with an expanding automated test suite (140 to 227 tests by the final internal checkpoint) — before the v1.0.0 public release.

Capabilities accumulated over that period and are reflected in the changelog's cumulative analysis list: command-section parsing, environment-aware port mapping, uplink inference, access-port MAC correlation, STP root comparison, neighbor reconciliation, transceiver and PoE checks, and standalone industrial switch handling.

The public release consolidated a modular engine under `src/`, a single GUI entry point, sanitized documentation, and a unittest suite covering parsers, port mapping, analysis orchestration, and report rendering.

## Structured review of sensitive logic

Before release, selected areas of inference logic—especially port-map construction and uplink target assignment—were reviewed using a structured audit process:

1. **Inventory** — Identify each code path that assigns or selects a mapped destination (for example, expected post-change uplink ports).
2. **Classify** — Label each path as evidence-driven (manual override, observed neighbor port, map note), convention-based (typical Catalyst refresh patterns), or order-dependent (sorted port pairs, scan order).
3. **Map tests** — Record which paths are covered by sanitized unit tests or equivalence tests, and which rely on partial or boundary-only coverage.
4. **Record gaps** — Document paths with no equivalence baseline, intentional behavior changes, or reliance on operator override when auto-detection confidence is low.

That audit informed test additions and documentation updates (including environment assumptions). It did **not** remove the need for manual CSV override or operator review when site layout diverges from generic refresh patterns.

## Equivalence testing

Regression checks use **equivalence testing against known-good prior behavior**: sanitized fixtures are run through the current modular engine and compared to frozen reference behavior captured in test helpers or prior inline logic. Coverage is deliberate and selective—not a full wiring or site-layout matrix. It includes, among other areas:

- Port-map auto-build: legacy-inline parity for one two-member stack running-config fixture and one standalone industrial fixture (plus empty running-config). This does not cover larger stacks, JSON profile variants, or non-standard module layouts.
- Uplink inference: dedicated legacy-inline equivalence tests for gateway 0/1 pair mapping and two-candidate 25/27 trunk inference (when a stack member has both candidates). Observed post-change CDP/LLDP neighbor override is also covered at the same bar. Lone 25/27 trunk inference on mixed stacks is newer intentional behavior with its own expected-output tests; it is **not** claimed equivalent to the prior inline baseline, which made no assignment in that scenario. Evidence-gated standard uplink target fallback is unit-tested separately, not as legacy-inline equivalence.
- End-to-end analysis: three sanitized pre/post log pairs (synthetic uplink scenario with auto-detect, the same pair with manual CSV, and minimal command sections)—not a comprehensive orchestration matrix. The synthetic uplink pair exercises convention-based port-map targets and observed-neighbor override; it does not trigger gateway-pair or same-member 25/27 trunk inference paths.
- Per-category finding extraction (legacy-inline): command sections, neighbors, neighbor parser extraction, MAC count, access-port MAC correlation, STP root, PoE, trunks, interface status, port map findings, logs, switch detail, and dot1x. Transceiver parsing and delivery logic has targeted unit tests only—no dedicated finding-extraction equivalence suite. Version, inventory, environment, and CPU checks appear only indirectly through orchestration fixtures.

Where behavior was intentionally changed, tests document the new expected output rather than claiming parity with the older baseline.

Tests use synthetic or sanitized fixtures only. They do not replay customer command logs.

## Unit and integration tests

The public release includes a broad unittest suite under `tests/`. From the project root:

```text
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

PDF-related tests skip automatically when `reportlab` is not installed.

## What this process does not guarantee

Development, structured audits, and equivalence testing **do not guarantee that all issues in a real refresh will be found**. The tool compares parsed log evidence against documented assumptions; it cannot see physical wiring, undocumented design intent, or log sections that were never captured.

**Operators must independently verify** findings against design documentation, change runbooks, and on-site checks. Manual port-map override remains available when auto-detection or default conventions do not match the migration.

Findings are review evidence, not automatic change approval or closure.

## Related documents

- [README](../README.md) — confirmed inputs, outputs, and safety boundaries
- [Environment Assumptions](environment-assumptions.md) — default port-map and uplink conventions
- [HISTORY.md](../HISTORY.md) — public release changelog
