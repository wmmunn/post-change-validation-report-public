"""Pure CDP/LLDP neighbor parsers."""

from __future__ import annotations

import re

from src.post_change_validation_models import INT_RE, NeighborRecord, find_first_interface, norm_interface
from src.post_change_validation_neighbors import clean_neighbor_name


# router-1.net.example  Gig 1/0/25       120             R S I   C9500     Twe 1/0/22
CDP_CAPABILITY_TOKEN_PATTERN = re.compile(r"[A-Z,]+")

# switch.example       Gi1/0/3     120     B,R     Gi0/1
LLDP_TABLE_ROW_PATTERN = re.compile(
    r"(?P<local>(?:Gi|GigabitEthernet|Te|TenGigabitEthernet|Twe|TwentyFiveGigE|TwentyFiveGigabitEthernet|Fi|FiveGigabitEthernet|Fo|FortyGigabitEthernet|Hu|HundredGigE)\d+(?:/\d+){1,3})\s+"
    r"(?P<hold>\d+)\s+(?P<cap>[A-Z,]+)\s+(?P<remote>\S+)\s*$",
    re.IGNORECASE,
)

# B,R
LLDP_CAPABILITY_TOKEN_PATTERN = re.compile(r"[A-Z,]+")


def parse_cdp_neighbors(section: str) -> list[NeighborRecord]:
    records: list[NeighborRecord] = []
    pending_device = ""

    for raw in section.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith(("device id", "capability", "total", "---")):
            continue

        ints = list(INT_RE.finditer(line))

        # CDP often wraps long Device IDs onto their own line. Save the device
        # name and combine it with the next row that starts with interface data.
        if len(ints) < 2:
            if not find_first_interface(line):
                pending_device = clean_neighbor_name(line)
            continue

        local_m = ints[0]
        remote_m = ints[-1]
        before_local = line[:local_m.start()].strip()
        neighbor = clean_neighbor_name(before_local or pending_device or "unknown")
        pending_device = ""

        local = norm_interface(local_m.group(0))
        remote = norm_interface(remote_m.group(0))
        between = line[local_m.end():remote_m.start()].strip()
        toks = between.split()
        platform = toks[-1] if toks else ""
        cap_tokens = [t for t in toks if CDP_CAPABILITY_TOKEN_PATTERN.fullmatch(t)]
        cap = " ".join(cap_tokens)
        records.append(NeighborRecord("cdp", neighbor, local, remote, platform, cap, raw=line))
    return records


def parse_lldp_neighbors(section: str) -> list[NeighborRecord]:
    records: list[NeighborRecord] = []
    pending_device = ""

    for raw in section.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith(("device id", "local intf", "capability", "total", "---", "(")):
            continue

        table_m = LLDP_TABLE_ROW_PATTERN.search(line)
        if table_m:
            neighbor = clean_neighbor_name(line[:table_m.start("local")].strip() or pending_device or "unknown")
            pending_device = ""
            remote_raw = table_m.group("remote")
            remote = norm_interface(remote_raw)
            records.append(
                NeighborRecord(
                    "lldp",
                    neighbor,
                    norm_interface(table_m.group("local")),
                    remote or remote_raw,
                    capability=table_m.group("cap"),
                    raw=line,
                )
            )
            continue

        ints = list(INT_RE.finditer(line))
        if not ints:
            # LLDP can also wrap long Device IDs.
            pending_device = clean_neighbor_name(line)
            continue

        local_m = ints[0]
        before_local = line[:local_m.start()].strip()
        neighbor = clean_neighbor_name(before_local or pending_device or "unknown")
        pending_device = ""

        local = norm_interface(local_m.group(0))
        after_local = line[local_m.end():].strip()
        toks = after_local.split()
        if not toks:
            records.append(NeighborRecord("lldp", neighbor, local, "unknown", raw=line))
            continue

        remote = norm_interface(toks[-1])
        if not remote:
            remote = toks[-1]

        middle = " ".join(toks[:-1])
        cap = " ".join(t for t in middle.split() if LLDP_CAPABILITY_TOKEN_PATTERN.fullmatch(t))
        records.append(NeighborRecord("lldp", neighbor, local, remote, capability=cap, raw=line))
    return records
