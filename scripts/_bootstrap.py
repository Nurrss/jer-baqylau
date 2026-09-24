"""Make ``apps/api`` importable from repository scripts (works on Windows and macOS)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "apps" / "api"
WEB_DIR = REPO_ROOT / "apps" / "web"

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))
