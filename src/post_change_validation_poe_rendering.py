"""PoE report detail parsing and HTML rendering helpers."""

from __future__ import annotations

import html
import re
from typing import Dict, Optional


POE_DETAIL_PORT_PATTERN = re.compile(r"(?P<pre>\S+)\s*->\s*(?P<post>\S+):\s*(?P<status>[^|]+)")
POE_DETAIL_PRE_PATTERN = re.compile(r"\|\s*pre=([^|]+)")
POE_DETAIL_POST_PATTERN = re.compile(r"\|\s*post=(.+)$")


def parse_poe_detail_line(line: str) -> Dict[str, str]:
    item = {"pre_port": "", "post_port": "", "status": "", "pre": "", "post": ""}
    raw = line.strip()
    port_m = POE_DETAIL_PORT_PATTERN.match(raw)
    if port_m:
        item["pre_port"] = port_m.group("pre")
        item["post_port"] = port_m.group("post")
        item["status"] = port_m.group("status").strip()
    else:
        item["status"] = raw
    pre_m = POE_DETAIL_PRE_PATTERN.search(raw)
    post_m = POE_DETAIL_POST_PATTERN.search(raw)
    if pre_m:
        item["pre"] = pre_m.group(1).strip()
    if post_m:
        item["post"] = post_m.group(1).strip()
    return item


def parse_poe_budget_detail(detail: str) -> Dict[str, Dict[str, object]]:
    budgets: Dict[str, Dict[str, object]] = {}
    for line in (detail or "").splitlines():
        if not line.startswith("POE_BUDGET|"):
            continue
        parts = line.split("|", 5)
        if len(parts) < 5:
            continue
        try:
            phase = parts[1]
            budgets[phase] = {
                "available": float(parts[2]),
                "used": float(parts[3]),
                "remaining": float(parts[4]),
                "raw": parts[5] if len(parts) > 5 else "",
            }
        except Exception:
            continue
    return budgets


def parse_poe_speed_upgrade_detail(detail: str) -> Dict[str, object]:
    for line in (detail or "").splitlines():
        if not line.startswith("POE_SPEED_UPGRADE|"):
            continue
        parts = line.split("|", 2)
        if len(parts) < 2:
            continue
        try:
            return {
                "count": int(parts[1]),
                "evidence": parts[2] if len(parts) > 2 else "",
            }
        except Exception:
            continue
    return {}


def poe_budget_pct(value: float, available: float) -> float:
    if available <= 0:
        return 0.0
    return max(0.0, min(100.0, (value / available) * 100.0))


def build_poe_budget_render_data(detail: str) -> Dict[str, object] | None:
    budgets = parse_poe_budget_detail(detail)
    post = budgets.get("post") or budgets.get("pre")
    if not post:
        return None
    available = float(post["available"])
    post_used = float(post["used"])
    pre = budgets.get("pre")
    pre_used = float(pre["used"]) if pre else None
    used_pct = poe_budget_pct(post_used, available)
    pre_pct = poe_budget_pct(pre_used, available) if pre_used is not None else None
    remaining = float(post.get("remaining", max(0.0, available - post_used)))
    delta_text = ""
    context_note = ""
    speed_upgrade = parse_poe_speed_upgrade_detail(detail)
    if pre_used is not None:
        delta_value = post_used - pre_used
        delta_text = f"; delta {delta_value:+.2f} W"
        if delta_value > 0 and used_pct < 70.0 and speed_upgrade:
            context_note = (
                "PoE draw increased after the change, and %s powered mapped endpoint(s) "
                "also negotiated higher post-change interface speed. Post-change utilization remains low."
            ) % speed_upgrade.get("count", "")
        elif delta_value > 0 and used_pct < 70.0:
            context_note = (
                "PoE draw increased after the change, but utilization remains low; "
                "this can be consistent with APs/endpoints negotiating higher access capability after the refresh."
            )
    return {
        "summary": "Post-change used %.2f W / %.2f W (%.1f%%); remaining %.2f W%s"
        % (post_used, available, used_pct, remaining, delta_text),
        "context_note": context_note,
        "pre_pct": pre_pct,
        "post_pct": used_pct,
    }


def build_poe_budget_html(detail: str) -> str:
    data = build_poe_budget_render_data(detail)
    if not data:
        return ""
    used_pct = float(data["post_pct"])
    pre_pct = data.get("pre_pct")
    pre_pct = float(pre_pct) if pre_pct is not None else None
    context_note = str(data.get("context_note") or "")
    if context_note:
        context_note = "<div class='poe-budget-note'>%s</div>" % html.escape(context_note)
    pre_marker = (
        "<span class='poe-budget-marker poe-budget-pre' title='Pre-change used' style='left: %.1f%%'></span>" % pre_pct
        if pre_pct is not None else ""
    )
    bar = (
        "<div class='poe-budget-bar'>"
        "<div class='poe-budget-zone poe-budget-green'></div>"
        "<div class='poe-budget-zone poe-budget-yellow'></div>"
        "<div class='poe-budget-zone poe-budget-red'></div>"
        "%s"
        "<span class='poe-budget-marker poe-budget-post' title='Post-change used' style='left: %.1f%%'></span>"
        "</div>"
    ) % (pre_marker, used_pct)
    return (
        "<div class='poe-budget-card'>"
        "<div class='poe-budget-title'>PoE Budget <span>(gray = pre-change, black = post-change)</span></div>"
        "<div class='poe-budget-summary'>%s</div>"
        "%s"
        "%s"
        "</div>"
    ) % (html.escape(str(data["summary"])), bar, context_note)


def build_poe_html(severity: str, detail: str) -> str:
    body = []
    for idx, line in enumerate(
        [
            ln
            for ln in (detail or "").splitlines()
            if ln.strip()
            and not ln.startswith("...")
            and not ln.startswith("POE_BUDGET|")
            and not ln.startswith("POE_SPEED_UPGRADE|")
        ]
    ):
        r = parse_poe_detail_line(line)
        cls = "poe-pass-a" if idx % 2 == 0 else "poe-pass-b"
        if severity == "WARN":
            cls = "poe-warn"
        elif severity == "INFO":
            cls = "poe-info"
        body.append(
            "<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                cls,
                html.escape(r["pre_port"]),
                html.escape(r["post_port"]),
                html.escape(r["status"]),
                html.escape(r["pre"]),
                html.escape(r["post"]),
            )
        )
    if not body:
        return build_poe_budget_html(detail) or f"<pre>{html.escape(detail)}</pre>"
    return """
%s
<table class='detail-table poe-table'>
<tr><th>Pre Port</th><th>Post Port</th><th>Status</th><th>Pre Evidence</th><th>Post Evidence</th></tr>
%s
</table>
""" % (build_poe_budget_html(detail), "".join(body))
