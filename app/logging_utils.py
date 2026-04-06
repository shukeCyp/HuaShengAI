from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import TextIO

LOG_FILE_PREFIX = "huashengai"
LOG_MESSAGE_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def resolve_log_directory_from_db_path(db_path: Path) -> Path:
    return db_path.resolve().parent / "logs"


def build_daily_log_filename(value: date | datetime | None = None) -> str:
    current = value or datetime.now()
    if isinstance(current, datetime):
        current = current.date()
    return f"{LOG_FILE_PREFIX}-{current.strftime('%Y-%m-%d')}.log"


def resolve_daily_log_path(log_dir: Path, value: date | datetime | None = None) -> Path:
    return log_dir / build_daily_log_filename(value)


class DailyFileHandler(logging.Handler):
    terminator = "\n"

    def __init__(self, log_dir: Path, *, encoding: str = "utf-8") -> None:
        super().__init__()
        self.log_dir = Path(log_dir).expanduser().resolve()
        self.encoding = encoding
        self._current_date = ""
        self._stream: TextIO | None = None
        self._huasheng_daily_file_handler = True
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            self.acquire()
            self._ensure_stream(record.created)
            if self._stream is None:
                raise RuntimeError("日志文件流尚未初始化。")
            self._stream.write(message)
            self._stream.write(self.terminator)
            self._stream.flush()
        except Exception:
            self.handleError(record)
        finally:
            self.release()

    def close(self) -> None:
        self.acquire()
        try:
            self._close_stream()
            super().close()
        finally:
            self.release()

    def _ensure_stream(self, created: float) -> None:
        current_date = datetime.fromtimestamp(created).strftime("%Y-%m-%d")
        if self._stream is not None and self._current_date == current_date:
            return

        self._close_stream()
        log_path = self.log_dir / f"{LOG_FILE_PREFIX}-{current_date}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = log_path.open("a", encoding=self.encoding)
        self._current_date = current_date

    def _close_stream(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.flush()
        finally:
            self._stream.close()
            self._stream = None
            self._current_date = ""


def configure_application_logging(
    db_path: Path,
    *,
    level_name: str = "INFO",
) -> Path:
    log_dir = resolve_log_directory_from_db_path(db_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(LOG_MESSAGE_FORMAT)
    level = getattr(logging, str(level_name or "INFO").upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    has_console_handler = any(
        getattr(handler, "_huasheng_console_handler", False)
        for handler in root_logger.handlers
    )
    if not has_console_handler:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler._huasheng_console_handler = True
        root_logger.addHandler(console_handler)

    has_daily_file_handler = any(
        getattr(handler, "_huasheng_daily_file_handler", False)
        and getattr(handler, "log_dir", None) == log_dir
        for handler in root_logger.handlers
    )
    if not has_daily_file_handler:
        daily_file_handler = DailyFileHandler(log_dir)
        daily_file_handler.setFormatter(formatter)
        root_logger.addHandler(daily_file_handler)

    logging.captureWarnings(True)
    return log_dir
