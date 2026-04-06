from __future__ import annotations

import logging
import os
from pathlib import Path

import webview

from app.accounts import AccountService
from app.bridge import AppApi, DesktopBridge, build_menu
from app.config import resolve_db_path, resolve_resource_root
from app.database import close_database, init_database
from app.huasheng import HuaShengAutomation
from app.logging_utils import configure_application_logging
from app.microheadline import MicroHeadlineService


RESOURCE_ROOT = resolve_resource_root()
DEFAULT_WEB_DIR = RESOURCE_ROOT / "app" / "web_dist"
logger = logging.getLogger(__name__)


def resolve_web_dir() -> Path:
    override = os.environ.get("PYWEBVIEW_WEB_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_WEB_DIR


def resolve_index_file() -> Path:
    index_file = resolve_web_dir() / "index.html"
    if not index_file.exists():
        raise FileNotFoundError(
            "Vue build output not found. Run ./run.sh before launching the app."
        )
    return index_file


def configure_logging(db_path: Path) -> None:
    level_name = os.environ.get("HUASHENGAI_LOG_LEVEL", "INFO").upper()
    log_dir = configure_application_logging(db_path, level_name=level_name)
    logger.info("Application logging configured log_dir=%s level=%s", log_dir, level_name)


def main() -> None:
    db_path = resolve_db_path()
    configure_logging(db_path)
    index_file = resolve_index_file()
    debug = os.environ.get("PYWEBVIEW_DEBUG", "0") == "1"
    title = os.environ.get("PYWEBVIEW_TITLE", "HuaShengAI")
    logger.info("Launching HuaShengAI title=%s debug=%s index=%s", title, debug, index_file)
    db_path = init_database(db_path)
    huasheng = HuaShengAutomation()
    account_service = AccountService(db_path, huasheng=huasheng)
    account_service.bootstrap()
    microheadline_service = MicroHeadlineService(db_path)
    microheadline_service.bootstrap()
    account_service.start_task_processor()
    bridge = DesktopBridge(index_file=index_file, default_title=title)
    api = AppApi(bridge, account_service, huasheng, microheadline_service)

    window = webview.create_window(
        title=title,
        url=index_file.as_uri(),
        js_api=api,
        width=1280,
        height=800,
        min_size=(960, 640),
    )
    if window is None:
        raise RuntimeError("PyWebView window creation was cancelled.")

    bridge.attach_window(window)
    try:
        webview.start(debug=debug, menu=build_menu(bridge, account_service))
    finally:
        account_service.stop_task_processor()
        close_database()


if __name__ == "__main__":
    main()
