# -*- mode: python ; coding: utf-8 -*-
"""
Reproducible PyInstaller spec for Post-Change Validation Reviewer.

Build:
  .venv\\Scripts\\pyinstaller.exe post_change_validation_reviewer.spec --noconfirm

Output:
  dist\\post_change_validation_reviewer.exe  (one-file, windowed GUI)
"""

from pathlib import Path

import customtkinter
import reportlab

# PyInstaller sets SPECPATH to the directory containing this .spec file.
PROJECT_ROOT = Path(SPECPATH)

CTK_PKG = Path(customtkinter.__file__).parent
RL_PKG = Path(reportlab.__file__).parent

PROFILE_PUBLIC = PROJECT_ROOT / "src" / "port_mapping" / "profiles" / "public"
PROFILE_TEMPLATES = PROJECT_ROOT / "src" / "port_mapping" / "profiles" / "templates"


def _json_datas(root: Path, dest_dir: str) -> list[tuple[str, str]]:
    """Collect JSON profile/template files with stable runtime paths."""
    if not root.is_dir():
        return []
    return [
        (str(path), dest_dir)
        for path in sorted(root.rglob("*.json"))
        if path.is_file()
    ]


# CustomTkinter: themes (blue.json, dark-blue.json, green.json) + icon fonts.
# reportlab: bundled fonts required for PDF export in frozen builds.
datas: list[tuple[str, str]] = [
    (str(CTK_PKG / "assets"), "customtkinter/assets"),
    (str(RL_PKG / "fonts"), "reportlab/fonts"),
]
datas.extend(_json_datas(PROFILE_PUBLIC, "src/port_mapping/profiles/public"))
datas.extend(_json_datas(PROFILE_TEMPLATES, "src/port_mapping/profiles/templates"))

hiddenimports = [
    # CustomTkinter widget/theme submodules (dynamic imports in CTk).
    "customtkinter",
    "customtkinter.windows",
    "customtkinter.windows.widgets",
    "customtkinter.windows.widgets.theme",
    "customtkinter.windows.widgets.theme.theme_manager",
    "customtkinter.windows.widgets.font",
    "customtkinter.windows.widgets.font.font_manager",
    "customtkinter.windows.widgets.font.ctk_font",
    "customtkinter.windows.widgets.scaling",
    "customtkinter.windows.widgets.scaling.scaling_tracker",
    "customtkinter.windows.widgets.appearance_mode",
    "customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker",
    # reportlab PDF stack (lazy / optional imports).
    "reportlab",
    "reportlab.lib",
    "reportlab.lib.colors",
    "reportlab.lib.styles",
    "reportlab.lib.units",
    "reportlab.lib.pagesizes",
    "reportlab.lib.enums",
    "reportlab.platypus",
    "reportlab.platypus.flowables",
    "reportlab.platypus.doctemplate",
    "reportlab.platypus.paragraph",
    "reportlab.platypus.tables",
    "reportlab.graphics",
    "reportlab.graphics.shapes",
    "reportlab.pdfbase",
    "reportlab.pdfbase.pdfmetrics",
    "reportlab.pdfbase.ttfonts",
    "reportlab.pdfbase._fontdata",
    "reportlab.rl_config",
    # Runtime port-map builder referenced by engine (Python module, not JSON).
    "src.port_mapping.private.workplace_profile",
]

excludes = [
    "tests",
    "pytest",
    "historical versions",
    "sample_data",
    "scripts",
]

a = Analysis(
    ["post_change_validation_reviewer.py"],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="post_change_validation_reviewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
