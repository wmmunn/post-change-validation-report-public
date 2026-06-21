"""CDP/LLDP report detail parsing and HTML rendering helpers."""

from __future__ import annotations

import html
import re
from typing import Dict


NEIGHBOR_RAW_EVIDENCE_PATTERN = re.compile(r"\|\s*raw=(.+)$")
NEIGHBOR_MISSING_PATTERN = re.compile(
    r"(?P<neighbor>.+?)\s+on\s+(?P<local>\S+),\s+remote\s+(?P<remote>.*?)\s+\|\s+expected post local\s+(?P<post>\S+),\s+remote\s+(?P<expected_remote>.+)$"
)
NEIGHBOR_NEW_PATTERN = re.compile(r"(?P<neighbor>.+?)\s+on\s+(?P<local>\S+),\s+remote\s+(?P<remote>.+)$")
NEIGHBOR_MAPPED_PATTERN = re.compile(r"(?P<neighbor>.+?):\s+(?P<local>\S+)\s+->\s+(?P<post>\S+),\s+remote\s+(?P<remote>.+)$")
NEIGHBOR_MATCHED_PATTERN = re.compile(r"(?P<neighbor>.+?):\s+(?P<local>\S+),\s+remote\s+(?P<remote>.+)$")


def parse_neighbor_detail_line(line: str) -> Dict[str, str]:
    item = {"neighbor": "", "status": "", "local": "", "post_local": "", "remote": "", "evidence": ""}
    raw = line.strip()
    base, *_support = raw.split("| supporting evidence:", 1)
    if _support:
        item["evidence"] = _support[0].strip()
    raw_m = NEIGHBOR_RAW_EVIDENCE_PATTERN.search(base)
    if raw_m and not item["evidence"]:
        item["evidence"] = raw_m.group(1).strip()
    base = NEIGHBOR_RAW_EVIDENCE_PATTERN.sub("", base).strip()

    if "expected post local" in base:
        m = NEIGHBOR_MISSING_PATTERN.match(base)
        if m:
            item["status"] = "Missing advertisement"
            item["neighbor"] = m.group("neighbor").strip()
            item["local"] = m.group("local").strip()
            item["post_local"] = m.group("post").strip()
            item["remote"] = m.group("remote").strip()
            if not item["evidence"]:
                item["evidence"] = f"expected remote {m.group('expected_remote').strip()}"
            return item

    if " on " in base and " | " not in base:
        m = NEIGHBOR_NEW_PATTERN.match(base)
        if m:
            item["status"] = "New"
            item["neighbor"] = m.group("neighbor").strip()
            item["post_local"] = m.group("local").strip()
            item["remote"] = m.group("remote").strip()
            return item

    mapped_m = NEIGHBOR_MAPPED_PATTERN.match(base)
    if mapped_m:
        item["status"] = "Matched mapped"
        item["neighbor"] = mapped_m.group("neighbor").strip()
        item["local"] = mapped_m.group("local").strip()
        item["post_local"] = mapped_m.group("post").strip()
        item["remote"] = mapped_m.group("remote").strip()
        return item

    matched_m = NEIGHBOR_MATCHED_PATTERN.match(base)
    if matched_m:
        item["status"] = "Matched"
        item["neighbor"] = matched_m.group("neighbor").strip()
        item["local"] = matched_m.group("local").strip()
        item["post_local"] = matched_m.group("local").strip()
        item["remote"] = matched_m.group("remote").strip()
        return item

    item["status"] = "Review"
    item["evidence"] = raw
    return item


def build_neighbor_html(severity: str, detail: str) -> str:
    rows = []
    for idx, line in enumerate([ln for ln in (detail or "").splitlines() if ln.strip()]):
        r = parse_neighbor_detail_line(line)
        cls = "neighbor-pass-a" if idx % 2 == 0 else "neighbor-pass-b"
        if severity == "WARN":
            cls = "neighbor-warn"
        elif severity == "INFO":
            cls = "neighbor-info"
        rows.append(
            "<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                cls,
                html.escape(r["status"]),
                html.escape(r["neighbor"]),
                html.escape(r["local"]),
                html.escape(r["post_local"]),
                html.escape(r["remote"]),
                html.escape(r["evidence"]),
            )
        )
    if not rows:
        return f"<pre>{html.escape(detail)}</pre>"
    return """
<table class='detail-table neighbor-table'>
<tr><th>Status</th><th>Neighbor</th><th>Pre Local</th><th>Post Local</th><th>Remote</th><th>Evidence</th></tr>
%s
</table>
""" % "".join(rows)
