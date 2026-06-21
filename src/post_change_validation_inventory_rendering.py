from __future__ import annotations

import html
from typing import Dict, List


def parse_inventory_detail(detail: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    lines = [ln for ln in (detail or "").splitlines() if ln.strip()]
    if not lines:
        return rows
    headers = lines[0].split("|")
    for ln in lines[1:]:
        vals = ln.split("|")
        if len(vals) < len(headers):
            vals += [""] * (len(headers) - len(vals))
        rows.append({headers[i]: vals[i] for i in range(len(headers))})
    return rows


def build_inventory_html(detail: str) -> str:
    data = parse_inventory_detail(detail)
    if not data:
        return f"<pre>{html.escape(detail)}</pre>"
    body = []
    for idx, r in enumerate(data):
        cls = "inventory-pass-a" if idx % 2 == 0 else "inventory-pass-b"
        body.append(
            "<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                cls,
                html.escape(r.get("component", "")),
                html.escape(r.get("description", "")),
                html.escape(r.get("pid", "")),
                html.escape(r.get("vid", "")),
                html.escape(r.get("serial", "")),
            )
        )
    return """
<table class='detail-table inventory-table'>
<tr><th>Component</th><th>Description</th><th>PID / Model</th><th>VID</th><th>Serial</th></tr>
%s
</table>
""" % "".join(body)
