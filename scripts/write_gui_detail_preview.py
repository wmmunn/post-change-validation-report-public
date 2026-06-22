#!/usr/bin/env python3
"""Write GUI detail formatting preview for sample stack refresh analysis."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import post_change_validation_reviewer as reviewer
from src.post_change_validation_gui_detail_formatting import format_detail_pane, format_detail_summary

SAMPLE = ROOT / "sample_data"
OUT = SAMPLE / "gui_detail_formatting_preview.txt"
TARGET_CATEGORIES = {
    "Access Port MAC Correlation",
    "Interface Status",
    "CDP Neighbors",
    "LLDP Neighbors",
}


def main() -> None:
    pre_path = SAMPLE / "synthetic_stack_refresh_pre.log"
    post_path = SAMPLE / "synthetic_stack_refresh_post.log"
    pre = pre_path.read_text(encoding="utf-8")
    post = post_path.read_text(encoding="utf-8")
    findings = reviewer.analyze(pre, post, "")

    lines = [
        "Post-Change Validation Tool - GUI Detail Formatting Preview",
        f"Sample pair: {pre_path.name} / {post_path.name}",
        "",
        "Launch GUI:",
        "  python post_change_validation_reviewer.py",
        "  Select the pre/post logs above (or D:\\report copies), then Run Validation.",
        "",
    ]

    shown = 0
    for finding in findings:
        if finding.category not in TARGET_CATEGORIES and finding.severity not in ("WARN", "PASS"):
            continue
        if not finding.detail and finding.category not in TARGET_CATEGORIES:
            continue
        lines.extend(
            [
                "=" * 72,
                f"{finding.severity} | {finding.category}",
                finding.finding,
                "",
                "Treeview Detail column:",
                format_detail_summary(finding),
                "",
                "Selected Finding Detail pane:",
                format_detail_pane(finding),
                "",
            ]
        )
        shown += 1
        if shown >= 12:
            break

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({shown} findings)")


if __name__ == "__main__":
    main()
