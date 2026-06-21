"""Port-map report detail parsing and HTML rendering helpers."""

from __future__ import annotations

import html
import re
from typing import Dict, List


PORT_MAP_MAPPING_PATTERN = re.compile(r"(?P<item>\S+)\s*->\s*(?P<value>[^\s(]+)(?:\s*\((?P<note>.*)\))?$")


def parse_port_map_detail(detail: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    lines = [ln.strip() for ln in (detail or "").splitlines() if ln.strip()]
    if not lines:
        return rows

    rows.append({"section": "Source", "item": "Source", "value": lines[0], "note": ""})
    section = "Summary"
    for line in lines[1:]:
        if line.endswith(":"):
            section = line[:-1]
            continue
        mapping_m = PORT_MAP_MAPPING_PATTERN.match(line)
        if mapping_m:
            rows.append(
                {
                    "section": section,
                    "item": mapping_m.group("item").strip(),
                    "value": mapping_m.group("value").strip(),
                    "note": (mapping_m.group("note") or "").strip(),
                }
            )
            continue
        if ":" in line:
            item, value = line.split(":", 1)
            rows.append({"section": section, "item": item.strip(), "value": value.strip(), "note": ""})
            continue
        rows.append({"section": section, "item": "Note", "value": line, "note": ""})
    return rows


def build_port_map_html(detail: str) -> str:
    data = parse_port_map_detail(detail)
    if not data:
        return f"<pre>{html.escape(detail)}</pre>"
    body = []
    for idx, row in enumerate(data):
        cls = "port-map-a" if idx % 2 == 0 else "port-map-b"
        body.append(
            "<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                cls,
                html.escape(row.get("section", "")),
                html.escape(row.get("item", "")),
                html.escape(row.get("value", "")),
                html.escape(row.get("note", "")),
            )
        )
    return """
<table class='detail-table port-map-table'>
<tr><th>Section</th><th>Item</th><th>Value / Target</th><th>Note</th></tr>
%s
</table>
""" % "".join(body)
