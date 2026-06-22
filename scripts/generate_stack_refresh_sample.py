#!/usr/bin/env python3
"""One-off generator for synthetic_stack_refresh pre/post sample logs."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sample_data"

HOST_PRE = "FICSITE01-ACC-SW01"
HOST_POST = "FICSITE01-ACC-SW01"

# 44 access ports: Gi1/0/1-20, Gi2/0/1-24
ACCESS_M1 = [f"Gi1/0/{p}" for p in range(1, 21)]
ACCESS_M2 = [f"Gi2/0/{p}" for p in range(1, 25)]
ACCESS_PORTS = ACCESS_M1 + ACCESS_M2

# Deliberate scenario ports
PHONE_PORT_OLD = "Gi1/0/15"
PHONE_PORT_NEW = "Gi1/0/15"  # 48u member keeps Gi prefix
WARN_PORT_OLD = "Gi1/0/18"
WARN_PORT_NEW = "Gi1/0/18"
NOTCONNECT_PORTS = {f"Gi1/0/{p}" for p in (7, 19)} | {f"Gi2/0/{p}" for p in (5, 22)}

UPLINK_A_OLD = "Gi1/0/25"
UPLINK_B_OLD = "Gi2/0/52"
UPLINK_A_NEW = "Te1/1/1"
UPLINK_B_NEW = "Te2/1/8"

GW_A = "gw-a.core.example"
GW_B = "gw-b.core.example"
PHONE_NEIGHBOR = "phone-ficsite01.example"
PHONE_MAC = "aabb.cc01.1500"
DESK_MAC_BASE = 0xAABBCC000100


PHONE_REMOTE = "Gi0/1"


def _port_mac(port: str) -> str:
    """Deterministic synthetic MAC per port name (stable across pre/post)."""
    seed = sum(ord(c) for c in port) * 17 + int(port.split("/")[-1])
    val = DESK_MAC_BASE + seed
    b = val.to_bytes(6, "big")
    return f"{b[0]:02x}{b[1]:02x}.{b[2]:02x}{b[3]:02x}.{b[4]:02x}{b[5]:02x}"


def _mac_for_port(idx: int) -> str:
    del idx  # legacy helper unused after port-stable MACs
    return PHONE_MAC


def _port_label(port: str) -> str:
    mapping = {
        PHONE_PORT_OLD: "conf-room-phone",
        WARN_PORT_OLD: "spare-workstation",
        UPLINK_A_OLD: "to gw-a",
        UPLINK_B_OLD: "to gw-b",
    }
    if port in mapping:
        return mapping[port]
    if port.startswith("Gi1/0/"):
        return f"desk-m1-{port.split('/')[-1]}"
    return f"desk-m2-{port.split('/')[-1]}"


def _map_port(old: str) -> str:
    if old == UPLINK_A_OLD:
        return UPLINK_A_NEW
    if old == UPLINK_B_OLD:
        return UPLINK_B_NEW
    if old.startswith("Gi2/0/"):
        return old.replace("Gi2/0/", "Te2/0/")
    return old


def _status_rows(ports: list[str], connected: set[str], host_style: str) -> list[str]:
    rows = [
        "Port      Name               Status       Vlan       Duplex  Speed Type",
    ]
    all_ports = [UPLINK_A_OLD, UPLINK_B_OLD] + ports if host_style == "pre" else [_map_port(UPLINK_A_OLD), _map_port(UPLINK_B_OLD)] + [_map_port(p) for p in ports]
    conn_set = connected if host_style == "pre" else {_map_port(p) for p in connected}
    for port in all_ports:
        if port in (UPLINK_A_OLD, UPLINK_B_OLD) or port in (UPLINK_A_NEW, UPLINK_B_NEW):
            rows.append(f"{port:<9} {_port_label(UPLINK_A_OLD if '25' in port or port == UPLINK_A_NEW else UPLINK_B_OLD):<18} connected    trunk      a-full  a-1000 1000BaseLX SFP")
            continue
        label = _port_label(port if host_style == "pre" else next((p for p in ACCESS_PORTS if _map_port(p) == port), port))
        if port in conn_set:
            vlan = "912" if "phone" in label else "100"
            rows.append(f"{port:<9} {label:<18} connected    {vlan:<10} a-full  a-1000 10/100/1000BaseTX")
        else:
            rows.append(f"{port:<9} {label:<18} notconnect   100        auto    auto   10/100/1000BaseTX")
    return rows


def _pre_connected() -> set[str]:
    connected = set(ACCESS_PORTS) - NOTCONNECT_PORTS
    return connected


def _post_connected() -> set[str]:
    connected = _pre_connected() - {WARN_PORT_OLD}
    return connected


def _mac_table(ports: list[str], connected: set[str], host_style: str) -> list[str]:
    rows = [
        "          Mac Address Table",
        "-------------------------------------------",
        "Vlan    Mac Address       Type        Ports",
        "----    -----------       --------    -----",
    ]
    for port in ports:
        if port not in connected:
            continue
        if host_style == "post" and port == WARN_PORT_OLD:
            continue
        mapped = _map_port(port) if host_style == "post" else port
        if port == PHONE_PORT_OLD:
            mac = PHONE_MAC
            vlan = "912"
        else:
            mac = _port_mac(port)
            vlan = "100"
        rows.append(f"{vlan:<7} {mac:<17} DYNAMIC     {mapped}")
    return rows


def _cdp_neighbors(host_style: str, include_phone: bool) -> list[str]:
    rows = [
        "Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID",
    ]
    a_local = "Gig 1/0/25" if host_style == "pre" else "Ten 1/1/1"
    b_local = "Gig 2/0/52" if host_style == "pre" else "Ten 2/1/8"
    rows.append(GW_A)
    rows.append(f"                 {a_local:<16} 120             R S I   C9500     Twe 1/0/22")
    rows.append(GW_B)
    rows.append(f"                 {b_local:<16} 120             R S I   C9500     Twe 1/0/23")
    if include_phone:
        rows.append(PHONE_NEIGHBOR)
        phone_local = "Gig 1/0/15" if host_style == "pre" else "Gig 1/0/15"
        rows.append(f"                 {phone_local:<16} 120             H P       IP Phone  {PHONE_REMOTE}")
    return rows


def _lldp_neighbors(host_style: str) -> list[str]:
    return [
        "Local Intf     Hold-time   Capability      Port ID",
        "Te1/1/1        120         B,R             Twe1/0/22",
        "Te2/1/8        120         B,R             Twe1/0/23",
    ] if host_style == "post" else [
        "Local Intf     Hold-time   Capability      Port ID",
        "Gi1/0/25       120         B,R             Twe1/0/22",
        "Gi2/0/52       120         B,R             Twe1/0/23",
    ]


def _trunk_section(host_style: str) -> list[str]:
    if host_style == "pre":
        ports = [UPLINK_A_OLD, UPLINK_B_OLD]
    else:
        ports = [UPLINK_A_NEW, UPLINK_B_NEW]
    rows = [
        "Port        Mode             Encapsulation  Status        Native vlan",
    ]
    for port in ports:
        rows.append(f"{port:<11} on               802.1q         trunking      1")
    rows.append("")
    rows.append("Port        Vlans allowed on trunk")
    for port in ports:
        rows.append(f"{port:<11} 1-4094")
    return rows


def _running_config(host_style: str) -> list[str]:
    if host_style == "pre":
        lines = [
            "version 15.2",
            "!",
            "switch 1 provision ws-c2960xr-48fps-l",
            "switch 2 provision ws-c2960xr-24td-i",
            "!",
        ]
        for port in ACCESS_PORTS + [UPLINK_A_OLD, UPLINK_B_OLD]:
            lines.append(f"interface GigabitEthernet{port[2:]}")
            lines.append(f" description {_port_label(port)}")
            if port in (UPLINK_A_OLD, UPLINK_B_OLD):
                lines.append(" switchport mode trunk")
            elif port == PHONE_PORT_OLD:
                lines.append(" switchport access vlan 912")
            else:
                lines.append(" switchport access vlan 100")
            lines.append("!")
        return lines
    lines = [
        "version 17.9",
        "!",
        "switch 1 provision c9300-48u",
        "switch 2 provision c9300-24ux",
        "!",
    ]
    for port in ACCESS_PORTS:
        new = _map_port(port)
        lines.append(f"interface {'TenGigabitEthernet' if new.startswith('Te') else 'GigabitEthernet'}{new[2:]}")
        lines.append(f" description {_port_label(port)}")
        if port == PHONE_PORT_OLD:
            lines.append(" switchport access vlan 912")
        else:
            lines.append(" switchport access vlan 100")
        lines.append("!")
    for port, desc in ((UPLINK_A_NEW, "to gw-a"), (UPLINK_B_NEW, "to gw-b")):
        lines.append(f"interface TenGigabitEthernet{port[2:]}")
        lines.append(f" description {desc}")
        lines.append(" switchport mode trunk")
        lines.append("!")
    return lines


def _inventory(host_style: str) -> list[str]:
    if host_style == "pre":
        return [
            'NAME: "1", DESCR: "WS-C2960XR-48FPS-L"',
            "PID: WS-C2960XR-48FPS-L , VID: V05  , SN: FCW0000FICS01",
            'NAME: "2", DESCR: "WS-C2960XR-24TD-I"',
            "PID: WS-C2960XR-24TD-I  , VID: V04  , SN: FCW0000FICS02",
        ]
    return [
        'NAME: "1", DESCR: "C9300-48U Stack Member"',
        "PID: C9300-48U          , VID: V02  , SN: FCW0000FICS11",
        'NAME: "2", DESCR: "C9300-24UX Stack Member"',
        "PID: C9300-24UX         , VID: V01  , SN: FCW0000FICS12",
    ]


def _poe(host_style: str) -> list[str]:
    rows = [
        "Module   Available     Used    Remaining",
        "   (W)     (W)         (W)",
        "1        370.0         12.6    357.4",
        "Interface Admin  Oper       Power   Device              Class Max",
        "                             (Watts)",
    ]
    if host_style == "pre" and PHONE_PORT_OLD in _pre_connected():
        rows.append("Gi1/0/15 auto   on         6.3     IP Phone 7960       3     30.0")
    if host_style == "post" and PHONE_PORT_OLD in _post_connected():
        rows.append("Gi1/0/15 auto   on         6.1     IP Phone 7960       3     30.0")
    return rows


def _transceiver_lines(port: str, *, temperature: float = 25.20) -> list[str]:
    return [
        f"{port} {temperature:.2f} 89.00 85.00 -5.00 -9.00",
        f"{port} 3.31 3.60 3.50 3.10 3.00",
        f"{port} 5.20 13.00 12.40 2.00 1.00",
        f"{port} -5.26 1.00 -3.00 -9.51 -13.51",
        f"{port} -5.11 4.00 0.00 -17.00 -21.04",
    ]


def _transceiver_sections(host_style: str) -> list[tuple[str, list[str]]]:
    if host_style == "post":
        uplinks = ((UPLINK_A_NEW, 25.20), (UPLINK_B_NEW, 25.10))
    else:
        uplinks = ((UPLINK_A_OLD, 25.20), (UPLINK_B_OLD, 25.10))
    return [
        (f">show interfaces {port} transceiver detail", _transceiver_lines(port, temperature=temp))
        for port, temp in uplinks
    ]


def _stp_root(host_style: str) -> list[str]:
    if host_style == "pre":
        return [
            "VLAN0001 32769 0011.2233.4455 4 128.25 P2p Root GigabitEthernet1/0/25",
            "VLAN0100 32769 0011.2233.4455 4 128.25 P2p Root GigabitEthernet1/0/25",
        ]
    return [
        "VLAN0001 32769 0011.2233.4455 2000 128.1 P2p Root TenGigabitEthernet1/1/1",
        "VLAN0100 32769 0011.2233.4455 2000 128.1 P2p Root TenGigabitEthernet1/1/1",
    ]


def build_log(host_style: str) -> str:
    host = HOST_PRE if host_style == "pre" else HOST_POST
    connected = _pre_connected() if host_style == "pre" else _post_connected()
    sections: list[tuple[str, list[str]]] = []

    if host_style == "pre":
        version = [
            "Cisco IOS Software, Version 15.2(7)E, RELEASE SOFTWARE (fc3)",
            "Technical Support: http://www.cisco.com/techsupport",
            f"System image file is \"flash:/cat3k_caa-universalk9.152-7.E.bin\"",
            f"{HOST_PRE} uptime is 3 weeks, 2 days, 4 hours, 11 minutes",
        ]
    else:
        version = [
            "Cisco IOS XE Software, Version 17.09.04",
            "Cisco IOS Software [Cupertino], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.9.4, RELEASE SOFTWARE (fc5)",
            f"System image file is \"bootflash:packages.conf\"",
            f"{HOST_POST} uptime is 2 hours, 15 minutes",
        ]

    sections.extend([
        (f"{host}#show version", version),
        (f"{host}#show inventory", _inventory(host_style)),
        (f"{host}#show running-config", _running_config(host_style)),
        (f"{host}#show int status", _status_rows(ACCESS_PORTS, connected, host_style)),
        (f"{host}#show cdp neighbors", _cdp_neighbors(host_style, include_phone=(host_style == "pre"))),
        (f"{host}#show lldp neighbors", _lldp_neighbors(host_style)),
        (f"{host}#show interfaces trunk", _trunk_section(host_style)),
        (f"{host}#show spanning-tree root", _stp_root(host_style)),
        (f"{host}#show spanning-tree summary", ["Pathcost method used is short" if host_style == "pre" else "Pathcost method used is long"]),
        (f"{host}#show mac address-table", _mac_table(ACCESS_PORTS, connected, host_style)),
        (f"{host}#show power inline", _poe(host_style)),
        *[
            (header, body)
            for header, body in _transceiver_sections(host_style)
        ],
        (f"{host}#show switch detail", [
            "Switch/Stack Mac Address : aabb.ccdd.ee00 - Local Mac Address",
            "Mac persistency wait time: Indefinite",
            "                                             H/W   Current",
            "Switch#   Role    Mac Address     Priority Version  State",
            "-------------------------------------------------------------------------------------",
            "1       Active   aabb.ccdd.ee01     15     V02     Ready",
            "2       Standby  aabb.ccdd.ee02     14     V02     Ready",
        ]),
        (f"{host}#show logging", ["*Jun 21 08:00:01.000: %LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet1/0/18, changed state to down"] if host_style == "post" else []),
        (f"{host}#show processes cpu", ["CPU utilization for five seconds: 4%/0%; one minute: 3%; five minutes: 2%"]),
        (f"{host}#show environment all", ["FAN 1 is OK", "FAN 2 is OK", "TEMPERATURE: OK"]),
    ])

    parts: list[str] = []
    for header, body in sections:
        parts.append(header)
        parts.extend(body)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pre = build_log("pre")
    post = build_log("post")
    (OUT / "synthetic_stack_refresh_pre.log").write_text(pre, encoding="utf-8")
    (OUT / "synthetic_stack_refresh_post.log").write_text(post, encoding="utf-8")
    print(f"Wrote {OUT / 'synthetic_stack_refresh_pre.log'}")
    print(f"Wrote {OUT / 'synthetic_stack_refresh_post.log'}")
    print(f"Pre access connected: {len(_pre_connected())}, Post access connected: {len(_post_connected())}")


if __name__ == "__main__":
    main()
