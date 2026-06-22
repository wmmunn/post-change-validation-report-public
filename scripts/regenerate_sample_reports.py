#!/usr/bin/env python3
"""Regenerate sample_data HTML/PDF reports from synthetic stack refresh logs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import post_change_validation_reviewer as reviewer
from post_change_validation_report_shell import build_html_report
from src.post_change_validation_pdf import build_pdf_story, export_pdf
from tests.test_pdf_export import story_fingerprint

SAMPLE = ROOT / "sample_data"
PRE = SAMPLE / "synthetic_stack_refresh_pre.log"
POST = SAMPLE / "synthetic_stack_refresh_post.log"


def main() -> None:
    pre = PRE.read_text(encoding="utf-8")
    post = POST.read_text(encoding="utf-8")
    findings = reviewer.analyze(pre, post, "")
    (SAMPLE / "sample_report.html").write_text(
        build_html_report(findings, str(PRE), str(POST), ""),
        encoding="utf-8",
    )
    export_pdf(findings, str(PRE), str(POST), "", str(SAMPLE / "sample_report.pdf"))
    joined = "\n".join(str(item) for item in story_fingerprint(build_pdf_story(findings, str(PRE), str(POST), "")))
    print("Wrote sample_report.html and sample_report.pdf")
    print("PoE budget meter present:", "PoE Budget" in joined and "Post-change used" in joined)
    print("Raw POE_BUDGET rows absent:", "POE_BUDGET|" not in joined)


if __name__ == "__main__":
    main()
