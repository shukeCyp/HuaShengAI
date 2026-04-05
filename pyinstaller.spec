# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path(SPECPATH).resolve()
app_dist_name = os.environ.get("HUASHENGAI_DIST_NAME", "荷塘AI花生工具").strip() or "荷塘AI花生工具"
playwright_browser_dir = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
show_console = os.environ.get("HUASHENGAI_CONSOLE", "1" if sys.platform.startswith("win") else "0").strip().lower() not in {
    "",
    "0",
    "false",
    "no",
}

datas = collect_data_files("webview")
datas += collect_data_files("playwright")
datas += [
    (str(project_root / "app" / "web_dist"), "app/web_dist"),
]

if playwright_browser_dir:
    browser_root = Path(playwright_browser_dir)
    if not browser_root.is_absolute():
        browser_root = (project_root / browser_root).resolve()
    if browser_root.exists():
        datas.append((str(browser_root), "playwright-browsers"))

hiddenimports = collect_submodules("playwright")
try:
    datas += collect_data_files("paddleocr")
    hiddenimports += collect_submodules("paddleocr")
except Exception:
    pass
if sys.platform == "darwin":
    hiddenimports += [
        "webview.platforms.cocoa",
    ]
elif sys.platform.startswith("win"):
    hiddenimports += [
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "webview.platforms.mshtml",
    ]
else:
    hiddenimports += [
        "webview.platforms.gtk",
        "webview.platforms.qt",
    ]

a = Analysis(
    ["app/main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(project_root / "scripts" / "pyinstaller_runtime_playwright.py")],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=app_dist_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=show_console,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=app_dist_name,
)
