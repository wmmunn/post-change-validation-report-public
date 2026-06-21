#!/usr/bin/env python3
"""Post-build verification for PyInstaller EXE (launch smoke + headless export checks)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "post_change_validation_reviewer.exe"
SAMPLE_PRE = ROOT / "sample_data" / "synthetic_stack_refresh_pre.log"
SAMPLE_POST = ROOT / "sample_data" / "synthetic_stack_refresh_post.log"
PREVIEW = ROOT / "sample_data" / "gui_detail_formatting_preview.txt"


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def verify_exe_exists() -> int:
    if not EXE.is_file():
        _fail(f"EXE not found: {EXE}")
    size = EXE.stat().st_size
    print(f"OK: EXE exists ({size} bytes / {size / (1024 * 1024):.2f} MB)")
    return size


def verify_exe_launch(timeout_sec: float = 8.0) -> None:
    print("Launching EXE smoke test ...")
    proc = subprocess.Popen(
        [str(EXE)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(timeout_sec)
        code = proc.poll()
        if code is not None:
            _fail(f"EXE exited early with code {code}")
        print(f"OK: EXE still running after {timeout_sec}s (GUI likely rendered)")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def verify_headless_analysis_and_export() -> None:
    """Same codebase path the EXE bundles; validates analyze + HTML/PDF export."""
    sys.path.insert(0, str(ROOT))
    import post_change_validation_reviewer as reviewer
    from post_change_validation_report_shell import build_html_report
    from src.post_change_validation_gui_detail_formatting import format_detail_pane
    from src.post_change_validation_pdf import export_pdf

    if not SAMPLE_PRE.is_file() or not SAMPLE_POST.is_file():
        _fail(f"Missing sample logs under {ROOT / 'sample_data'}")

    pre = SAMPLE_PRE.read_text(encoding="utf-8")
    post = SAMPLE_POST.read_text(encoding="utf-8")
    findings = reviewer.analyze(pre, post, "")
    if not findings:
        _fail("analyze() returned no findings for synthetic_stack_refresh sample")

    mac_finding = next((f for f in findings if f.category == "Access Port MAC Correlation"), None)
    if mac_finding is None:
        _fail("Expected Access Port MAC Correlation finding in sample analysis")

    detail = format_detail_pane(mac_finding)
    if "|" in detail.splitlines()[0]:
        _fail("Detail pane appears to use raw pipe formatting")
    if "Status:" not in detail:
        _fail("Detail pane missing formatted Status: lines")
    print("OK: findings detail formatting (no raw pipes in MAC pane)")

    with tempfile.TemporaryDirectory() as td:
        html_path = Path(td) / "verify_report.html"
        pdf_path = Path(td) / "verify_report.pdf"
        html_path.write_text(
            build_html_report(findings, str(SAMPLE_PRE), str(SAMPLE_POST), ""),
            encoding="utf-8",
        )
        if html_path.stat().st_size < 500:
            _fail("HTML export too small")
        export_pdf(findings, str(SAMPLE_PRE), str(SAMPLE_POST), "", str(pdf_path))
        if not pdf_path.is_file() or pdf_path.stat().st_size < 500:
            _fail("PDF export missing or too small")
        if pdf_path.read_bytes()[:4] != b"%PDF":
            _fail("PDF export does not start with %PDF header")
    print("OK: HTML and PDF export via reportlab")


def verify_bundle_markers() -> None:
    """Inspect one-file archive for critical bundled assets."""
    try:
        from PyInstaller.archive.readers import CArchiveReader
    except ImportError:
        print("SKIP: PyInstaller archive reader unavailable for bundle inspection")
        return

    reader = CArchiveReader(str(EXE))
    names = set(reader.toc.keys())
    required_fragments = [
        "customtkinter\\assets\\themes\\dark-blue.json",
        "customtkinter\\assets\\fonts\\CustomTkinter_shapes_font.otf",
        "reportlab\\fonts\\Vera.ttf",
        "src\\port_mapping\\profiles\\public\\generic_c9300_48p.json",
    ]
    missing = [frag for frag in required_fragments if frag not in names]
    if missing:
        _fail(f"Bundled assets missing from EXE archive: {missing}")
    print("OK: critical CustomTkinter/reportlab/profile assets present in EXE archive")


def main() -> None:
    verify_exe_exists()
    verify_bundle_markers()
    verify_headless_analysis_and_export()
    verify_exe_launch()
    print("All automated verification checks passed.")


if __name__ == "__main__":
    main()
