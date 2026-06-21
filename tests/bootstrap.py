"""Ensure project root is on sys.path for src package imports in tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

path = str(ROOT)
if path not in sys.path:
    sys.path.insert(0, path)
