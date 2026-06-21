# Sample Data — Synthetic Stack Refresh

Sanitized pre/post command-log pair for demonstrating Post Change Validation Tool reports. All hostnames, MAC addresses, serial numbers, and site identifiers are fictional.

## Files

| File | Description |
|------|-------------|
| `synthetic_stack_refresh_pre.log` | Pre-change capture from a fictional two-member WS-C2960XR stack at site `FICSITE01` |
| `synthetic_stack_refresh_post.log` | Post-change capture from a new two-member C9300 stack (48U + 24UX) after refresh |

## Scenario

**Site:** `FICSITE01.example` — access switch `FICSITE01-ACC-SW01`

**Pre-change (2960XR stack):**
- 44 access ports (`Gi1/0/1`–`Gi1/0/20`, `Gi2/0/1`–`Gi2/0/24`); 40 connected, 4 intentionally down
- Trunk uplinks on `Gi1/0/25` and `Gi2/0/52` toward `gw-a.core.example` / `gw-b.core.example`
- Conference-room IP phone on `Gi1/0/15` with CDP, MAC, and PoE evidence

**Post-change (C9300 stack):**
- Auto-detected port map: member-1 access stays `Gi1/0/x`; member-2 access maps `Gi2/0/x` → `Te2/0/x`
- Standard uplinks map to `Te1/1/1` and `Te2/1/8`
- Most access ports remain connected (PASS)

## Expected Finding Highlights

When analyzed with auto-detected port mapping (no manual CSV):

| Severity | Category | What to look for |
|----------|----------|------------------|
| **PASS** | Interface Status | ~41 mapped access/uplink ports remained connected |
| **PASS** | CDP / LLDP Neighbors | Both gateway uplink neighbors matched through the port map |
| **PASS** | Trunks / STP Root | Uplink trunks and root-bridge behavior preserved |
| **INFO** | CDP Neighbors | Phone CDP advertisement missing post-change, but MAC + PoE + connected evidence on mapped `Gi1/0/15` — cross-source downgrade (not WARN) |
| **WARN** | Interface Status | `Gi1/0/18` was connected pre-change, `notconnect` post-change |
| **WARN** | Access Port MAC Correlation | One MAC missing post-change (same desk port as interface WARN) |

## Usage

From the project root:

```text
python post_change_validation_reviewer.py
```

Load `synthetic_stack_refresh_pre.log` and `synthetic_stack_refresh_post.log`. Leave the port-map CSV blank to exercise auto-detection.

Or run analysis from Python:

```text
.venv\Scripts\python.exe scripts\analyze_sample_pair.py
```

## Regenerating

```text
.venv\Scripts\python.exe scripts\generate_stack_refresh_sample.py
```
