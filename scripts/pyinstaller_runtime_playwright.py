from __future__ import annotations

import os
import sys
from pathlib import Path


def _candidate_browser_roots() -> list[Path]:
    candidates: list[Path] = []
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        candidates.append(Path(bundled_root) / "playwright-browsers")

    executable_dir = Path(sys.executable).resolve().parent
    candidates.append(executable_dir / "playwright-browsers")
    candidates.append(executable_dir / "_internal" / "playwright-browsers")
    return candidates


for candidate in _candidate_browser_roots():
    if candidate.exists():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(candidate))
        break
