"""Access-port MAC correlation report detail parsing and HTML rendering helpers."""

from __future__ import annotations

import html
from typing import Dict, List


def parse_mac_correlation_detail(detail: str) -> List[Dict[str, str]]:
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


def build_mac_correlation_html(finding: str, detail: str) -> str:
    data = parse_mac_correlation_detail(detail)
    body = []
    pass_i = 0
    for r in data:
        status = r.get("status", "")
        cls = "mac-pass-a"
        if status == "PASS":
            cls = "mac-pass-a" if pass_i % 2 == 0 else "mac-pass-b"
            pass_i += 1
        elif status == "MISSING":
            cls = "mac-missing"
        elif status == "MOVED":
            cls = "mac-moved"
        body.append(
            "<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                cls,
                html.escape(status),
                html.escape(r.get("mac", "")),
                html.escape(r.get("vlan", "")),
                html.escape(r.get("pre_port", "")),
                html.escape(r.get("expected_post_port", "")),
                html.escape(r.get("actual_post_port", "")),
                html.escape(r.get("note", "")),
            )
        )
    return """
<div class='mac-section'>
<h2>Access Port MAC Correlation</h2>
<p><b>%s</b></p>
<table class='mac-table'>
<tr><th>Status</th><th>MAC Address</th><th>VLAN</th><th>Pre Port</th><th>Expected Post Port</th><th>Actual Post Port</th><th>Note</th></tr>
%s
</table>
</div>
""" % (html.escape(finding), "".join(body))
