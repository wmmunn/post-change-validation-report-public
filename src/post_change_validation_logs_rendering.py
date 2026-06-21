"""Log report detail parsing and HTML rendering helpers."""

from __future__ import annotations

import html
import re
from typing import Dict


LOG_DETAIL_PATTERN = re.compile(r"(?P<prefix>\S+\s+\d+\s+\S+|\S+\s+\S+)\s+(?P<message>.+)$")


def parse_log_detail_line(line: str) -> Dict[str, str]:
    raw = line.strip()
    line_m = LOG_DETAIL_PATTERN.match(raw)
    if line_m:
        return {
            "prefix": line_m.group("prefix"),
            "message": line_m.group("message"),
        }
    return {"prefix": "", "message": raw}


def build_logs_html(finding: str, detail: str) -> str:
    rows = []
    for idx, line in enumerate([ln for ln in (detail or "").splitlines() if ln.strip()]):
        cls = "log-warn" if finding.startswith("Log review recommended") else ("log-pass-a" if idx % 2 == 0 else "log-pass-b")
        parsed = parse_log_detail_line(line)
        rows.append(
            "<tr class='%s'><td>%s</td><td>%s</td></tr>"
            % (
                cls,
                html.escape(parsed["prefix"]),
                html.escape(parsed["message"]),
            )
        )
    if not rows:
        return f"<pre>{html.escape(detail)}</pre>"
    return """
<table class='detail-table logs-table'>
<tr><th>Time/Prefix</th><th>Message</th></tr>
%s
</table>
""" % "".join(rows)
