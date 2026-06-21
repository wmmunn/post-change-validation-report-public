"""STP report detail parsing and HTML rendering helpers."""

from __future__ import annotations

import html
import re
from typing import Dict


# root unchanged and root port mapped (Gi1/0/49 -> Te1/1/1); cost changed 4 -> 2000.
STP_DETAIL_PORT_MAPPING_PATTERN = re.compile(r"\(([^()]+?)\s*->\s*([^()]+?)\)")

# root bridge unchanged but root port changed unexpectedly. pre port=Gi1/0/49 expected post=Te1/1/1, actual post=Te1/1/8
STP_DETAIL_PRE_PORT_PATTERN = re.compile(r"pre port=([^,;]+)", re.IGNORECASE)

# root bridge unchanged but root port changed unexpectedly. pre port=Gi1/0/49 expected post=Te1/1/1, actual post=Te1/1/8
STP_DETAIL_POST_PORT_PATTERN = re.compile(r"(?:actual post|post port)=([^,;.]+)", re.IGNORECASE)

# root unchanged and root port mapped (Gi1/0/49 -> Te1/1/1); cost changed 4 -> 2000.
STP_DETAIL_COST_CHANGED_PATTERN = re.compile(r"cost changed\s+([0-9-]+)\s*->\s*([0-9-]+)", re.IGNORECASE)

# pre root=32769 0011.2233.4455, cost=4, port=Gi1/0/49; post root=32769 00aa.bbcc.ddee, cost=0, port=local root.
STP_DETAIL_PRE_ROOT_COST_PATTERN = re.compile(r"pre root=.*?cost=([0-9-]+)", re.IGNORECASE)

# pre root=32769 0011.2233.4455, cost=4, port=Gi1/0/49; post root=32769 00aa.bbcc.ddee, cost=0, port=local root.
STP_DETAIL_POST_ROOT_COST_PATTERN = re.compile(r"post root=.*?cost=([0-9-]+)", re.IGNORECASE)

# STP path-cost method: pre=short, post=long.
STP_DETAIL_PATH_COST_METHOD_PATTERN = re.compile(r"STP path-cost method:\s*([^.]*)\.", re.IGNORECASE)

# Post root port evidence: Te1/1/1 speed=a-10G type=SFP-10G.
STP_DETAIL_POST_ROOT_PORT_EVIDENCE_PATTERN = re.compile(r"Post root port evidence:\s*([^.]*)\.", re.IGNORECASE)


def parse_stp_detail_line(line: str) -> Dict[str, str]:
    item = {
        "vlan": "",
        "status": "",
        "pre_port": "",
        "post_port": "",
        "cost": "",
        "context": "",
    }
    raw = line.strip()
    if not raw:
        return item
    vlan, sep, rest = raw.partition(":")
    item["vlan"] = vlan.strip() if sep else ""
    text = rest.strip() if sep else raw
    lower = text.lower()
    if "root unchanged" in lower:
        item["status"] = "Root retained"
    elif "local switch became root" in lower:
        item["status"] = "Local root post-change"
    elif "root bridge changed" in lower:
        item["status"] = "Root changed"
    elif "root bridge unchanged but root port changed" in lower:
        item["status"] = "Root port changed"
    elif "only stp cost changed" in lower or "cost changed" in lower:
        item["status"] = "Cost changed"
    else:
        item["status"] = "Review"

    port_m = STP_DETAIL_PORT_MAPPING_PATTERN.search(text)
    if port_m:
        item["pre_port"] = port_m.group(1).strip()
        item["post_port"] = port_m.group(2).strip()
    else:
        pre_m = STP_DETAIL_PRE_PORT_PATTERN.search(text)
        post_m = STP_DETAIL_POST_PORT_PATTERN.search(text)
        if pre_m:
            item["pre_port"] = pre_m.group(1).strip()
        if post_m:
            item["post_port"] = post_m.group(1).strip()

    cost_m = STP_DETAIL_COST_CHANGED_PATTERN.search(text)
    if cost_m:
        item["cost"] = f"{cost_m.group(1)} -> {cost_m.group(2)}"
    else:
        pre_cost_m = STP_DETAIL_PRE_ROOT_COST_PATTERN.search(text)
        post_cost_m = STP_DETAIL_POST_ROOT_COST_PATTERN.search(text)
        if pre_cost_m and post_cost_m:
            item["cost"] = f"{pre_cost_m.group(1)} -> {post_cost_m.group(1)}"

    context_parts: list[str] = []
    if "path-cost method" in lower:
        method_m = STP_DETAIL_PATH_COST_METHOD_PATTERN.search(text)
        if method_m:
            context_parts.append(method_m.group(1).strip())
        elif "pre=short, post=long" in text:
            context_parts.append("path cost short -> long")
    if "post root port evidence" in lower:
        evidence_m = STP_DETAIL_POST_ROOT_PORT_EVIDENCE_PATTERN.search(text)
        if evidence_m:
            context_parts.append(evidence_m.group(1).strip())
    if "vlan 1 svi is shutdown" in lower:
        context_parts.append("VLAN 1 SVI shutdown context")
    if not context_parts:
        context_parts.append(text)
    item["context"] = "; ".join(context_parts)
    return item


def build_stp_root_html(severity: str, detail: str) -> str:
    body = []
    for idx, line in enumerate([ln for ln in (detail or "").splitlines() if ln.strip()]):
        row = parse_stp_detail_line(line)
        cls = "stp-pass-a" if idx % 2 == 0 else "stp-pass-b"
        if severity == "WARN":
            cls = "stp-warn"
        elif severity == "INFO":
            cls = "stp-info"
        body.append(
            "<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                cls,
                html.escape(row["vlan"]),
                html.escape(row["status"]),
                html.escape(row["pre_port"]),
                html.escape(row["post_port"]),
                html.escape(row["cost"]),
                html.escape(row["context"]),
            )
        )
    return """
<table class='detail-table stp-table'>
<tr><th>VLAN</th><th>Status</th><th>Pre Root Port</th><th>Post Root Port</th><th>Cost</th><th>Context</th></tr>
%s
</table>
""" % "".join(body)
