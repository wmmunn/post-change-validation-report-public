# Windows EXE Packaging

This document describes how to build a standalone Windows executable for the Post Change Validation Reviewer. It is intended for maintainers preparing a public release artifact.

## Approach

- **Tool:** [PyInstaller](https://pyinstaller.org/) 6.x
- **Layout:** One-file, windowed (`console=False`) executable
- **Entry point:** `post_change_validation_reviewer.py`
- **Bundled data:**
  - CustomTkinter theme/assets (`customtkinter/assets`)
  - ReportLab fonts (`reportlab/fonts`) so PDF export works in frozen builds
  - Public port-mapping JSON profiles under `src/port_mapping/profiles/public/`
  - Profile template under `src/port_mapping/profiles/templates/`

## Design assumptions

| Topic | Choice | Rationale |
| --- | --- | --- |
| One-file vs one-folder | One-file | Matches prior internal builds; single artifact is easier to distribute |
| Startup cost | Accept slower cold start | CustomTkinter + ReportLab inflate the bundle; one-file extracts to `%TEMP%` on launch |
| Auto port map | Runtime builder in `src/port_mapping/private/workplace_profile.py` | Same default behavior as source checkout; not a separate secrets bundle |
| Public JSON profiles | Bundled | Used when operators supply a profile path or future UI wiring references them |
| Tests / sample logs | Excluded | Not imported by the entry point; keeps artifact smaller |
| Historical monolith scripts | Excluded | Superseded by modular `post_change_validation_reviewer.py` |

## Prerequisites

- Windows 10/11
- Python 3.11+ (3.13 tested in development)
- Network access for first-time `pip install`

## Build steps

From the project root:

```powershell
.\scripts\build_exe.ps1
```

Fast rebuild after dependencies are installed:

```powershell
.\scripts\build_exe.ps1 -SkipInstall -SkipTests
```

Optional GUI smoke test (launches the EXE for five seconds):

```powershell
.\scripts\build_exe.ps1 -SkipInstall -SkipTests -SmokeTest
```

Manual equivalent:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean post_change_validation_reviewer.spec
```

Output:

```text
dist\post_change_validation_reviewer.exe
```

PyInstaller scratch directories `build/` and `dist/` are gitignored at the workspace tooling level.

## Known limitations

- **PDF export:** Requires ReportLab; the build script installs and bundles it. If you strip ReportLab from a custom build, PDF export fails with a clear runtime error while HTML export still works.
- **Private site profiles:** No separate private JSON bundle is shipped. Operators use manual CSV override or a local JSON profile path when generic auto-detection is insufficient.
- **Antivirus false positives:** Unsigned PyInstaller one-file executables are sometimes flagged. Sign the binary or distribute the one-folder build if your organization requires it.
- **Debug visibility:** The windowed build hides tracebacks. For troubleshooting, temporarily set `console=True` in `post_change_validation_reviewer.spec` and rebuild.

## Verification checklist

1. Import check passes (`post_change_validation_reviewer`, CustomTkinter, public profiles discoverable).
2. Unit tests pass (267+ tests at time of writing).
3. `dist\post_change_validation_reviewer.exe` launches and shows the main window.
4. Run analysis on sanitized sample logs from `sample_data/` (not bundled in the EXE).
5. Export HTML and PDF from the GUI when ReportLab is bundled.
