#!/usr/bin/env python3
"""Analyze sample_data stack refresh pair and print finding summary."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import post_change_validation_reviewer as reviewer
from src.post_change_validation_ios_log_signature import validate_ios_xe_log_signature

SAMPLE = ROOT / "sample_data"


def main() -> None:
    pre = (SAMPLE / "synthetic_stack_refresh_pre.log").read_text(encoding="utf-8")
    post = (SAMPLE / "synthetic_stack_refresh_post.log").read_text(encoding="utf-8")
    for label, text in [("pre", pre), ("post", post)]:
        ok, reason = validate_ios_xe_log_signature(text)
        print(f"{label} signature: ok={ok} reason={reason!r}")
    findings = reviewer.analyze(pre, post, "")
    counts = Counter(f.severity for f in findings)
    print("Finding counts:", dict(counts))
    print()
    for sev in ("FAIL", "WARN", "PASS", "INFO"):
        items = [f for f in findings if f.severity == sev]
        if not items:
            continue
        print(f"=== {sev} ({len(items)}) ===")
        for f in items:
            print(f"  [{f.category}] {f.finding}")
            if f.detail and sev in ("FAIL", "WARN", "INFO"):
                lines = f.detail.splitlines()
                for line in lines[:8]:
                    print(f"    {line}")
                if len(lines) > 8:
                    print(f"    ... +{len(lines) - 8} more lines")
        print()


if __name__ == "__main__":
    main()
