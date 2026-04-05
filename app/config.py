from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "HuaShengAI"
DB_FILENAME = "huashengai.sqlite3"


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def resolve_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_resource_root() -> Path:
    if is_frozen_app():
        bundled_root = getattr(sys, "_MEIPASS", None)
        if bundled_root:
            return Path(bundled_root)
        return Path(sys.executable).resolve().parent
    return resolve_project_root()


def resolve_data_dir() -> Path:
    override = os.environ.get("HUASHENGAI_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    if not is_frozen_app():
        return resolve_project_root() / "app_data"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def resolve_db_path() -> Path:
    override = os.environ.get("HUASHENGAI_DB_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return resolve_data_dir() / DB_FILENAME
