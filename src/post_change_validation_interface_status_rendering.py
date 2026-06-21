"""Interface-status report detail parsing and HTML rendering helpers."""

from __future__ import annotations

import html
import re
from typing import Dict


INTERFACE_DETAIL_PATTERN = re.compile(
    r"(?P<pre>\S+)(?:\s+->\s+(?P<post>\S+))?\s+role=(?P<role>[^:]+):\s*(?P<status>[^|]+)"
)
INTERFACE_DETAIL_FIELD_PATTERN = re.compile(r"\|\s*(?P<key>pre|post|note)=([^|]+)")
# Fi2/0/1
BARE_INTERFACE_PORT_LINE_PATTERN = re.compile(r"^(?:Gi|Te|Twe|Fi|Fo|Hu|Po|Ap|Fa)\d+(?:/\d+)+$")


def parse_interface_detail_line(line: str) -> Dict[str, str]:
    item = {"pre_port": "", "post_port": "", "role": "", "status": "", "pre": "", "post": "", "note": ""}
    raw = line.strip()
    m = INTERFACE_DETAIL_PATTERN.match(raw)
    if m:
        item["pre_port"] = m.group("pre").strip()
        item["post_port"] = (m.group("post") or "").strip()
        item["role"] = m.group("role").strip()
        item["status"] = m.group("status").strip()
    elif BARE_INTERFACE_PORT_LINE_PATTERN.match(raw):
        item["post_port"] = raw
    else:
        item["status"] = raw
    for part_m in INTERFACE_DETAIL_FIELD_PATTERN.finditer(raw):
        item[part_m.group("key")] = part_m.group(2).strip()
    return item


def build_interface_status_html(severity: str, detail: str) -> str:
    rows = []
    for idx, line in enumerate([ln for ln in (detail or "").splitlines() if ln.strip()]):
        r = parse_interface_detail_line(line)
        cls = "iface-pass-a" if idx % 2 == 0 else "iface-pass-b"
        if severity == "WARN":
            cls = "iface-warn"
        elif severity == "INFO":
            cls = "iface-info"
        rows.append(
            "<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                cls,
                html.escape(r["pre_port"]),
                html.escape(r["post_port"]),
                html.escape(r["role"]),
                html.escape(r["status"]),
                html.escape(r["pre"]),
                html.escape(r["post"]),
                html.escape(r["note"]),
            )
        )
    if not rows:
        return f"<pre>{html.escape(detail)}</pre>"
    return """
<table class='detail-table iface-table'>
<tr><th>Pre Port</th><th>Post Port</th><th>Role</th><th>Status</th><th>Pre Evidence</th><th>Post Evidence</th><th>Note</th></tr>
%s
</table>
""" % "".join(rows)
