from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import html
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Lock, RLock, Thread
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from peewee import IntegrityError

from app.autovideo import AutoVideoAutomation
from app.database import database
from app.huasheng import HuaShengAutomation
from app.logging_utils import resolve_daily_log_path, resolve_log_directory_from_db_path
from app.models import (
    Account,
    AppSetting,
    BenchmarkAccount,
    HuashengGenerationRecord,
    MonitoredArticle,
    MonitorRun,
    RewritePrompt,
    TaskRecord,
)

PHONE_PATTERN = re.compile(r"^1\d{10}$")
HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-F]{6}$")
HTML_TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
INVALID_FILENAME_CHARS_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1F]+')
LABELED_OUTPUT_PATTERN_TEMPLATE = r"^\s*#+\s*{label}\s*$"
SUBTITLE_SETTINGS_KEY = "subtitle_settings"
HUASHENG_VOICE_SETTINGS_KEY = "huasheng_voice_settings"
MODEL_SETTINGS_KEY = "model_settings"
GLOBAL_SETTINGS_KEY = "global_settings"
AUTOVIDEO_SETTINGS_KEY = "autovideo_settings"
SUBTITLE_FONT_SIZE_OPTIONS = [
    {"label": "超小号", "value": 22},
    {"label": "小号", "value": 32},
    {"label": "常规", "value": 42},
    {"label": "大号", "value": 54},
]
SUBTITLE_STYLE_OPTIONS = [
    {
        "id": "white-black",
        "label": "白字黑描边",
        "fontColor": "#FFFFFF",
        "outlineColor": "#000000",
        "outlineThick": 70,
    },
    {
        "id": "black-white",
        "label": "黑字白描边",
        "fontColor": "#000000",
        "outlineColor": "#FFFFFF",
        "outlineThick": 70,
    },
    {
        "id": "yellow-black",
        "label": "黄字黑描边",
        "fontColor": "#FFD707",
        "outlineColor": "#000000",
        "outlineThick": 70,
    },
    {
        "id": "white-red",
        "label": "白字红描边",
        "fontColor": "#FFFFFF",
        "outlineColor": "#FF1A1A",
        "outlineThick": 70,
    },
    {
        "id": "cyan-black",
        "label": "浅青黑描边",
        "fontColor": "#AFE6EF",
        "outlineColor": "#000000",
        "outlineThick": 70,
    },
    {
        "id": "white-pink",
        "label": "白字粉描边",
        "fontColor": "#FFFFFF",
        "outlineColor": "#FF6699",
        "outlineThick": 70,
    },
    {
        "id": "white-teal",
        "label": "白字青描边",
        "fontColor": "#FFFFFF",
        "outlineColor": "#0091A8",
        "outlineThick": 70,
    },
]
DEFAULT_SUBTITLE_STYLE_ID = "white-teal"
DEFAULT_SUBTITLE_FONT_SIZE = 42
DEFAULT_MODEL_SETTINGS = {
    "baseUrl": "",
    "apiKey": "",
    "model": "",
    "titlePrompt": "",
}
DEFAULT_GLOBAL_SETTINGS = {
    "threadPoolSize": 8,
    "downloadDir": "",
    "generationProvider": "huasheng",
    "autoDownloadVideos": False,
    "autoDeleteRedlineTasks": False,
    "rewriteThreadPoolSize": 3,
    "titleThreadPoolSize": 3,
    "createThreadPoolSize": 1,
    "progressThreadPoolSize": 1,
}
DEFAULT_HUASHENG_VOICE_SETTINGS = {
    "voiceId": 0,
    "voiceName": "",
    "voiceCode": "",
    "voiceTags": "",
    "previewUrl": "",
    "cover": "",
    "speechRate": 1,
    "maxConcurrentTasksPerAccount": 1,
}
DEFAULT_AUTOVIDEO_SETTINGS = {
    "voiceChoice": AutoVideoAutomation.DEFAULT_VOICE_CHOICE,
    "rateChoice": AutoVideoAutomation.DEFAULT_RATE_CHOICE,
}
MODEL_REQUEST_TIMEOUT = 60.0
REWRITE_MODEL_REQUEST_TIMEOUT = 20 * 60.0
TITLE_MODEL_REQUEST_TIMEOUT = 20 * 60.0
VIDEO_DOWNLOAD_TIMEOUT = 300.0
VIDEO_DOWNLOAD_MAX_RETRIES = 3
VIDEO_DOWNLOAD_CHUNK_SIZE = 1024 * 1024
MODEL_REQUEST_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)
REWRITE_OUTPUT_FORMAT_PROMPT = (
    "输出要求：\n"
    "1. 只返回改写后的正文内容，不要返回解释、标题、前言、总结或其他额外说明。\n"
    "2. 严格按照下面格式返回：\n"
    "############content\n"
    "这里填写改写后的正文内容\n"
    "3. 如果触发红线，只允许原样返回下面这一行，不要加标题、代码块、解释、引号、空行或其他任何字符：\n"
    "######触发红线，禁止改写"
)
TITLE_OUTPUT_FORMAT_PROMPT = (
    "输出要求：\n"
    "1. 只返回标题，不要返回解释、正文、序号或其他额外说明。\n"
    "2. 严格按照下面格式返回：\n"
    "########title\n"
    "这里填写生成后的标题"
)
TITLE_RESPONSE_MAX_LENGTH = 80
TITLE_RESPONSE_INVALID_PREFIXES = (
    "你的这篇文章",
    "这篇文章",
    "整体上",
    "核心优点",
    "优点是",
    "建议",
    "点评",
    "分析",
)
MODEL_CONNECTION_TEST_SYSTEM_PROMPT = "你是模型连接测试助手。请只返回“连接成功”四个字。"
MODEL_CONNECTION_TEST_USER_CONTENT = "请返回连接成功。"
TASK_QUEUE_SCAN_INTERVAL_SECONDS = 5
TASK_THREAD_POOL_MIN_SIZE = 1
TASK_THREAD_POOL_MAX_SIZE = 32
TASK_EXECUTOR_THREAD_POOL_MAX_SIZE = TASK_THREAD_POOL_MAX_SIZE * 4
TASK_STAGE_MAX_RETRIES = 3
HUASHENG_DAILY_PROJECT_LIMIT = 50
HUASHENG_DAILY_LIMIT_REACHED_CODE = 10008
HUASHENG_GENERATION_PLACEHOLDER_PREFIX = "quota-placeholder"
TASK_STATUS_PENDING = "待处理"
TASK_STATUS_REWRITE_RUNNING = "S1改写中"
TASK_STATUS_REWRITE_READY = "待生成标题"
TASK_STATUS_REWRITE_FAILED = "S1失败"
TASK_STATUS_REWRITE_REDLINE = "触发红线"
TASK_STATUS_TITLE_RUNNING = "S2标题中"
TASK_STATUS_READY_FOR_HUASHENG = "待创建花生任务"
TASK_STATUS_READY_FOR_VIDEO = "待生成视频"
TASK_STATUS_TITLE_FAILED = "S2失败"
TASK_STATUS_HUASHENG_CREATING = "S3创建花生中"
TASK_STATUS_VIDEO_CREATING = "S3生成视频中"
TASK_STATUS_HUASHENG_CREATE_FAILED = "S3失败"
TASK_STATUS_HUASHENG_POLLING = "S4扫描中"
TASK_STATUS_SUBTITLE_APPLYING = "设置字幕中"
TASK_STATUS_EXPORT_RUNNING = "S4导出中"
TASK_STATUS_EXPORT_FINISHED = "导出完成"
TASK_STATUS_EXPORT_FAILED = "S4失败"
TASK_HUASHENG_STATUS_NOT_CREATED = "未创建"
TASK_HUASHENG_STATUS_CREATED = "任务已创建"
TASK_HUASHENG_STATUS_EXPORT_READY = "准备导出"
TASK_HUASHENG_STATUS_EXPORT_FINISHED = "导出完成"
TASK_HUASHENG_STATUS_WAIT_FOR_AVAILABLE_ACCOUNT = "暂无可用花生账号，等待下次扫描"
TASK_STAGE_REWRITE = "rewrite"
TASK_STAGE_TITLE = "title"
TASK_STAGE_HUASHENG_CREATE = "huasheng_create"
TASK_STAGE_HUASHENG_PROGRESS = "huasheng_progress"
GENERATION_PROVIDER_HUASHENG = "huasheng"
GENERATION_PROVIDER_AUTOVIDEO = "autovideo"
REWRITE_REDLINE_RESPONSE_TEXT = "######触发红线，禁止改写"
REWRITE_REDLINE_DISPLAY_TEXT = "触发红线，禁止改写"
REWRITE_REDLINE_FUZZY_KEYWORDS = (
    "触发安全机制",
    "题材受限",
    "停止改写",
    "已停止重构",
)
TASK_HUASHENG_STATUS_ACCOUNT_RETRY = "账号限额，等待重新分配"
HUASHENG_ACCOUNT_MAX_CONCURRENT_TASKS_MIN = 1
HUASHENG_ACCOUNT_MAX_CONCURRENT_TASKS_MAX = 50
HUASHENG_PRE_EXPORT_EDIT_DELAY_SECONDS = 10.0
logger = logging.getLogger(__name__)


def now_local() -> datetime:
    return datetime.now().replace(microsecond=0)


class HuashengCreateRetryRequired(RuntimeError):
    pass


class NonRetryableTaskStageError(RuntimeError):
    pass


class AccountService:
    def __init__(
        self,
        db_path: Path,
        huasheng: HuaShengAutomation | None = None,
        autovideo: AutoVideoAutomation | None = None,
    ) -> None:
        self.db_path = db_path
        self._huasheng = huasheng or HuaShengAutomation()
        self._autovideo = autovideo or AutoVideoAutomation()
        self._task_processor_state_lock = RLock()
        self._task_processor_stop_event = Event()
        self._task_processor_thread: Thread | None = None
        self._task_executor: ThreadPoolExecutor | None = None
        self._task_executor_size = 0
        self._huasheng_account_selection_lock = Lock()
        self._rewrite_task_ids_inflight: set[int] = set()
        self._title_task_ids_inflight: set[int] = set()
        self._huasheng_create_task_ids_inflight: set[int] = set()
        self._huasheng_progress_task_ids_inflight: set[int] = set()

    def bootstrap(self) -> None:
        with database.connection_context():
            database.create_tables(
                [
                    Account,
                    AppSetting,
                    RewritePrompt,
                    TaskRecord,
                    HuashengGenerationRecord,
                    BenchmarkAccount,
                    MonitorRun,
                    MonitoredArticle,
                ],
                safe=True,
            )
            self._ensure_task_record_schema()

    def list_payload(self) -> dict[str, Any]:
        with database.connection_context():
            accounts = list(
                Account.select().order_by(Account.updated_at.desc(), Account.id.desc())
            )
        voice_settings = self.load_huasheng_voice_settings_snapshot()
        max_concurrent_tasks_per_account = int(
            voice_settings.get("maxConcurrentTasksPerAccount") or 1
        )
        generation_count_map = self.build_huasheng_generation_count_map(
            [int(account.id) for account in accounts]
        )
        active_task_count_map = self.list_huasheng_active_task_counts()
        items = [
            self.serialize_account(
                account,
                today_generation_count=generation_count_map.get(int(account.id), 0),
                active_huasheng_task_count=active_task_count_map.get(int(account.id), 0),
                max_concurrent_tasks_per_account=max_concurrent_tasks_per_account,
            )
            for account in accounts
        ]
        disabled_count = sum(1 for item in items if item["isDisabled"])
        total_count = len(items)

        return {
            "items": items,
            "stats": {
                "total": total_count,
                "active": total_count - disabled_count,
                "disabled": disabled_count,
            },
            "databasePath": str(self.db_path),
        }

    def create_account(
        self,
        phone: str,
        cookies: str,
        note: str = "",
        is_disabled: bool = False,
    ) -> dict[str, Any]:
        normalized_phone = self.normalize_phone(phone)
        normalized_cookies = self.normalize_cookies(cookies)
        normalized_note = self.normalize_note(note)
        timestamp = now_local()

        with database.connection_context():
            try:
                account = Account.create(
                    phone=normalized_phone,
                    cookies=normalized_cookies,
                    note=normalized_note,
                    is_disabled=bool(is_disabled),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            except IntegrityError as exc:
                raise ValueError("该手机号已存在，请直接编辑现有账号。") from exc

        return self.serialize_account(
            account,
            today_generation_count=self.count_huasheng_generation_records_for_account_today(
                account.id
            ),
        )

    def update_account(
        self,
        account_id: int,
        phone: str,
        cookies: str,
        note: str = "",
        is_disabled: bool = False,
    ) -> dict[str, Any]:
        normalized_phone = self.normalize_phone(phone)
        normalized_cookies = self.normalize_cookies(cookies)
        normalized_note = self.normalize_note(note)
        timestamp = now_local()

        with database.connection_context():
            account = self.get_account(account_id)
            account.phone = normalized_phone
            account.cookies = normalized_cookies
            account.note = normalized_note
            account.is_disabled = bool(is_disabled)
            account.updated_at = timestamp

            try:
                account.save()
            except IntegrityError as exc:
                raise ValueError("该手机号已存在，请使用其他手机号。") from exc

        return self.serialize_account(
            account,
            today_generation_count=self.count_huasheng_generation_records_for_account_today(
                account.id
            ),
        )

    def set_account_disabled(self, account_id: int, is_disabled: bool) -> dict[str, Any]:
        timestamp = now_local()

        with database.connection_context():
            account = self.get_account(account_id)
            account.is_disabled = bool(is_disabled)
            account.updated_at = timestamp
            account.save()

        return self.serialize_account(
            account,
            today_generation_count=self.count_huasheng_generation_records_for_account_today(
                account.id
            ),
        )

    def list_tasks_payload(self) -> dict[str, Any]:
        with database.connection_context():
            tasks = list(
                TaskRecord.select().order_by(TaskRecord.id.desc())
            )
            article_preview_map = self.build_task_article_preview_map(tasks)

        items = [
            self.serialize_task_record(
                task,
                article_preview=article_preview_map.get(int(task.article_id or 0), ""),
            )
            for task in tasks
        ]
        return {
            "items": items,
            "stats": {
                "total": len(items),
            },
            "databasePath": str(self.db_path),
        }

    def is_retryable_task_status(self, status: str) -> bool:
        normalized_status = str(status or "").strip()
        return normalized_status in {
            TASK_STATUS_REWRITE_FAILED,
            TASK_STATUS_TITLE_FAILED,
            TASK_STATUS_HUASHENG_CREATE_FAILED,
            TASK_STATUS_EXPORT_FAILED,
        }

    def retry_task_record(self, task_id: int) -> dict[str, Any]:
        normalized_task_id = self.normalize_positive_int(task_id, field_name="task_id")
        with database.connection_context():
            task = self.get_task_record(normalized_task_id)
            current_status = str(task.status or "").strip()
            if not self.is_retryable_task_status(current_status):
                raise ValueError("当前任务不是失败状态，无法重试。")

            if current_status == TASK_STATUS_REWRITE_FAILED:
                task.status = TASK_STATUS_PENDING
                task.rewritten_content = ""
                task.title = ""
                task.project_pid = ""
                task.progress = 0
                task.video_url = ""
                task.huasheng_status = TASK_HUASHENG_STATUS_NOT_CREATED
                task.export_task_id = ""
                task.export_version = ""
            elif current_status == TASK_STATUS_TITLE_FAILED:
                task.status = TASK_STATUS_REWRITE_READY
                task.title = ""
                task.project_pid = ""
                task.progress = 0
                task.video_url = ""
                task.huasheng_status = TASK_HUASHENG_STATUS_NOT_CREATED
                task.export_task_id = ""
                task.export_version = ""
            elif current_status == TASK_STATUS_HUASHENG_CREATE_FAILED:
                task.status = self.get_task_ready_for_generation_status(task)
                task.project_pid = ""
                task.progress = 0
                task.video_url = ""
                task.huasheng_status = TASK_HUASHENG_STATUS_NOT_CREATED
                task.export_task_id = ""
                task.export_version = ""
            else:
                task.status = (
                    TASK_STATUS_HUASHENG_POLLING
                    if str(task.project_pid or "").strip()
                    else self.get_task_ready_for_generation_status(task)
                )
                task.progress = 0
                task.video_url = ""
                task.huasheng_status = (
                    "等待花生处理"
                    if str(task.project_pid or "").strip()
                    else (
                        "等待 AutoVideo 生成"
                        if self.get_task_generation_provider(task)
                        == GENERATION_PROVIDER_AUTOVIDEO
                        else TASK_HUASHENG_STATUS_NOT_CREATED
                    )
                )
                if not str(task.project_pid or "").strip():
                    task.export_task_id = ""
                    task.export_version = ""

            task.updated_at = now_local()
            task.save()

        return self.serialize_task_record(task)

    def delete_all_task_records(self) -> dict[str, Any]:
        with self._task_processor_state_lock:
            inflight_rewrite = len(self._rewrite_task_ids_inflight)
            inflight_title = len(self._title_task_ids_inflight)
            inflight_huasheng_create = len(self._huasheng_create_task_ids_inflight)
            inflight_huasheng_progress = len(self._huasheng_progress_task_ids_inflight)
            self._rewrite_task_ids_inflight.clear()
            self._title_task_ids_inflight.clear()
            self._huasheng_create_task_ids_inflight.clear()
            self._huasheng_progress_task_ids_inflight.clear()

        with database.connection_context():
            deleted_count = TaskRecord.delete().execute()

        logger.info(
            "Deleted all task records deleted_count=%s cleared_inflight_rewrite=%s cleared_inflight_title=%s cleared_inflight_huasheng_create=%s cleared_inflight_huasheng_progress=%s",
            deleted_count,
            inflight_rewrite,
            inflight_title,
            inflight_huasheng_create,
            inflight_huasheng_progress,
        )
        return {
            "deletedCount": int(deleted_count or 0),
            "databasePath": str(self.db_path),
        }

    def delete_task_record(self, task_id: int) -> dict[str, Any]:
        normalized_task_id = self.normalize_positive_int(task_id, field_name="task_id")
        with self._task_processor_state_lock:
            self._rewrite_task_ids_inflight.discard(normalized_task_id)
            self._title_task_ids_inflight.discard(normalized_task_id)
            self._huasheng_create_task_ids_inflight.discard(normalized_task_id)
            self._huasheng_progress_task_ids_inflight.discard(normalized_task_id)

        with database.connection_context():
            deleted_count = (
                TaskRecord.delete().where(TaskRecord.id == normalized_task_id).execute()
            )

        return {
            "deletedCount": int(deleted_count or 0),
            "taskId": normalized_task_id,
            "databasePath": str(self.db_path),
        }

    def download_task_video(self, task_id: int) -> dict[str, Any]:
        return self.download_task_video_with_progress(task_id)

    def download_task_video_with_progress(
        self,
        task_id: int,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        normalized_task_id = self.normalize_positive_int(task_id, field_name="task_id")
        task = self.get_task_record(normalized_task_id)
        video_url = self.normalize_required_text_field(
            task.video_url,
            field_name="视频地址",
            max_length=4000,
        )
        download_directory = self.resolve_download_directory_path()
        filename = self.build_task_video_download_filename(task)
        final_path = self.resolve_unique_download_path(download_directory, filename)
        last_error: Exception | None = None

        for attempt in range(1, VIDEO_DOWNLOAD_MAX_RETRIES + 1):
            temp_path = final_path.with_name(f".{final_path.name}.part")
            try:
                if temp_path.exists():
                    temp_path.unlink()
                logger.info(
                    "Task video download started task_id=%s attempt=%s url=%s target=%s",
                    normalized_task_id,
                    attempt,
                    video_url,
                    final_path,
                )
                self._download_video_to_path(
                    video_url,
                    temp_path,
                    progress_callback=progress_callback,
                    task_id=normalized_task_id,
                )
                temp_path.replace(final_path)
                delete_payload = self.delete_task_record(normalized_task_id)
                logger.info(
                    "Task video download finished task_id=%s attempt=%s target=%s deleted_count=%s",
                    normalized_task_id,
                    attempt,
                    final_path,
                    delete_payload["deletedCount"],
                )
                return {
                    "taskId": normalized_task_id,
                    "title": str(task.title or "").strip(),
                    "downloadPath": str(final_path),
                    "fileName": final_path.name,
                    "attemptCount": attempt,
                    "deletedCount": delete_payload["deletedCount"],
                    "databasePath": str(self.db_path),
                }
            except Exception as exc:
                last_error = exc
                if temp_path.exists():
                    temp_path.unlink()
                logger.warning(
                    "Task video download failed task_id=%s attempt=%s error=%s",
                    normalized_task_id,
                    attempt,
                    exc,
                )

        message = str(last_error).strip() if last_error is not None else "未知错误"
        raise RuntimeError(
            f"下载失败，已重试 {VIDEO_DOWNLOAD_MAX_RETRIES} 次: {message}"
        )

    def create_task_record(
        self,
        account_id: int,
        project_pid: str = "",
        status: str = "处理中",
        article_id: int | None = None,
        article_content: str = "",
        rewrite_prompt_id: int | None = None,
        rewrite_prompt: str = "",
        rewritten_content: str = "",
        title: str = "",
        progress: int = 0,
        video_url: str = "",
        huasheng_status: str | None = None,
        account_phone: str = "",
        account_note: str = "",
        account_cookies: str = "",
        export_task_id: str = "",
        export_version: str = "",
    ) -> dict[str, Any]:
        normalized_account_id = self.normalize_positive_int(account_id, field_name="account_id")
        normalized_project_pid = self.normalize_short_text(
            project_pid,
            field_name="project_pid",
            max_length=64,
            allow_empty=True,
        )
        normalized_status = self.normalize_short_text(
            status,
            field_name="status",
            max_length=64,
        )
        normalized_article_id = self.normalize_optional_positive_int(article_id)
        normalized_article_content = self.normalize_text_field(
            article_content,
            field_name="文章内容快照",
            max_length=200000,
        )
        normalized_rewrite_prompt_id = self.normalize_optional_positive_int(rewrite_prompt_id)
        normalized_rewrite_prompt = self.normalize_text_field(
            rewrite_prompt,
            field_name="改文提示词",
            max_length=20000,
        )
        normalized_rewritten_content = self.normalize_text_field(
            rewritten_content,
            field_name="已改写文本",
            max_length=200000,
        )
        normalized_title = self.normalize_text_field(
            title,
            field_name="标题",
            max_length=2000,
        )
        normalized_progress = self.normalize_task_progress(progress)
        normalized_video_url = self.normalize_text_field(
            video_url,
            field_name="视频地址",
            max_length=4000,
        )
        normalized_account_phone = self.normalize_text_field(
            account_phone,
            field_name="账号手机号",
            max_length=32,
        )
        normalized_account_note = self.normalize_text_field(
            account_note,
            field_name="账号备注",
            max_length=255,
        )
        normalized_account_cookies = self.normalize_text_field(
            account_cookies,
            field_name="账号 Cookies",
            max_length=20000,
        )
        normalized_export_task_id = self.normalize_text_field(
            export_task_id,
            field_name="导出任务 ID",
            max_length=128,
        )
        normalized_export_version = self.normalize_text_field(
            export_version,
            field_name="导出版本",
            max_length=64,
        )
        normalized_huasheng_status = self.normalize_short_text(
            huasheng_status if huasheng_status is not None else normalized_status,
            field_name="huasheng_status",
            max_length=128,
            allow_empty=True,
        )
        timestamp = now_local()

        with database.connection_context():
            account = self.get_account(normalized_account_id)
            if not normalized_account_phone:
                normalized_account_phone = account.phone
            if not normalized_account_note:
                normalized_account_note = account.note
            if not normalized_account_cookies:
                normalized_account_cookies = account.cookies
            task = None
            if normalized_project_pid:
                task = TaskRecord.get_or_none(TaskRecord.project_pid == normalized_project_pid)
            if task is None:
                task = TaskRecord.create(
                    account_id=normalized_account_id,
                    account_phone=normalized_account_phone,
                    account_note=normalized_account_note,
                    account_cookies=normalized_account_cookies,
                    project_pid=normalized_project_pid,
                    article_id=normalized_article_id or None,
                    article_content=normalized_article_content,
                    rewritten_content=normalized_rewritten_content,
                    title=normalized_title,
                    rewrite_prompt_id=normalized_rewrite_prompt_id or None,
                    rewrite_prompt=normalized_rewrite_prompt,
                    progress=normalized_progress,
                    status=normalized_status,
                    huasheng_status=normalized_huasheng_status,
                    video_url=normalized_video_url,
                    export_task_id=normalized_export_task_id,
                    export_version=normalized_export_version,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            else:
                task.account_id = normalized_account_id
                task.account_phone = normalized_account_phone
                task.account_note = normalized_account_note
                task.account_cookies = normalized_account_cookies
                task.project_pid = normalized_project_pid
                task.article_id = normalized_article_id or None
                task.article_content = normalized_article_content
                task.rewritten_content = normalized_rewritten_content
                task.title = normalized_title
                task.rewrite_prompt_id = normalized_rewrite_prompt_id or None
                task.rewrite_prompt = normalized_rewrite_prompt
                task.progress = normalized_progress
                task.status = normalized_status
                task.huasheng_status = normalized_huasheng_status
                task.video_url = normalized_video_url
                task.export_task_id = normalized_export_task_id
                task.export_version = normalized_export_version
                task.updated_at = timestamp
                task.save()

        return self.serialize_task_record(task)

    def update_task_status(
        self,
        task_id: int,
        status: str,
        project_pid: str | None = None,
        *,
        progress: int | None = None,
        video_url: str | None = None,
        rewritten_content: str | None = None,
        title: str | None = None,
        huasheng_status: str | None = None,
        account_id: int | None = None,
        account_phone: str | None = None,
        account_note: str | None = None,
        account_cookies: str | None = None,
        export_task_id: str | None = None,
        export_version: str | None = None,
    ) -> dict[str, Any]:
        normalized_task_id = self.normalize_positive_int(task_id, field_name="task_id")
        normalized_status = self.normalize_short_text(
            status,
            field_name="status",
            max_length=64,
        )
        normalized_project_pid = None
        if project_pid is not None:
            normalized_project_pid = self.normalize_short_text(
                project_pid,
                field_name="project_pid",
                max_length=64,
                allow_empty=True,
            )
        normalized_progress = None
        if progress is not None:
            normalized_progress = self.normalize_task_progress(progress)
        normalized_video_url = None
        if video_url is not None:
            normalized_video_url = self.normalize_text_field(
                video_url,
                field_name="视频地址",
                max_length=4000,
            )
        normalized_rewritten_content = None
        if rewritten_content is not None:
            normalized_rewritten_content = self.normalize_text_field(
                rewritten_content,
                field_name="已改写文本",
                max_length=200000,
            )
        normalized_title = None
        if title is not None:
            normalized_title = self.normalize_text_field(
                title,
                field_name="标题",
                max_length=2000,
            )
        normalized_huasheng_status = None
        if huasheng_status is not None:
            normalized_huasheng_status = self.normalize_short_text(
                huasheng_status,
                field_name="huasheng_status",
                max_length=128,
                allow_empty=True,
            )
        normalized_account_id = None
        if account_id is not None:
            normalized_account_id = self.normalize_task_account_id(account_id)
        normalized_account_phone = None
        if account_phone is not None:
            normalized_account_phone = self.normalize_text_field(
                account_phone,
                field_name="账号手机号",
                max_length=32,
            )
        normalized_account_note = None
        if account_note is not None:
            normalized_account_note = self.normalize_text_field(
                account_note,
                field_name="账号备注",
                max_length=255,
            )
        normalized_account_cookies = None
        if account_cookies is not None:
            normalized_account_cookies = self.normalize_text_field(
                account_cookies,
                field_name="账号 Cookies",
                max_length=20000,
            )
        normalized_export_task_id = None
        if export_task_id is not None:
            normalized_export_task_id = self.normalize_text_field(
                export_task_id,
                field_name="导出任务 ID",
                max_length=128,
            )
        normalized_export_version = None
        if export_version is not None:
            normalized_export_version = self.normalize_text_field(
                export_version,
                field_name="导出版本",
                max_length=64,
            )

        with database.connection_context():
            task = self.get_task_record(normalized_task_id)
            task.status = normalized_status
            if normalized_account_id is not None:
                task.account_id = normalized_account_id
            if normalized_project_pid is not None:
                task.project_pid = normalized_project_pid
            if normalized_progress is not None:
                task.progress = normalized_progress
            if normalized_video_url is not None:
                task.video_url = normalized_video_url
            if normalized_rewritten_content is not None:
                task.rewritten_content = normalized_rewritten_content
            if normalized_title is not None:
                task.title = normalized_title
            if normalized_huasheng_status is not None:
                task.huasheng_status = normalized_huasheng_status
            if normalized_account_phone is not None:
                task.account_phone = normalized_account_phone
            if normalized_account_note is not None:
                task.account_note = normalized_account_note
            if normalized_account_cookies is not None:
                task.account_cookies = normalized_account_cookies
            if normalized_export_task_id is not None:
                task.export_task_id = normalized_export_task_id
            if normalized_export_version is not None:
                task.export_version = normalized_export_version
            task.updated_at = now_local()
            task.save()

        return self.serialize_task_record(task)

    def create_article_processing_tasks(
        self,
        article_ids: list[int] | tuple[int, ...],
        prompt_ids: list[int] | tuple[int, ...],
    ) -> dict[str, Any]:
        normalized_article_ids = self.normalize_positive_int_list(
            article_ids,
            field_name="article_ids",
        )
        normalized_prompt_ids = self.normalize_positive_int_list(
            prompt_ids,
            field_name="prompt_ids",
        )
        if not normalized_article_ids:
            raise ValueError("当前没有可处理的文章。")
        if not normalized_prompt_ids:
            raise ValueError("请至少选择一个改写提示词。")

        timestamp = now_local()
        generation_provider = self.get_current_generation_provider()

        with database.connection_context():
            if not database.table_exists(MonitoredArticle._meta.table_name):
                raise ValueError("文章表不存在，请先抓取文章后再处理。")
            account_snapshot = self.get_default_task_account_snapshot(
                generation_provider=generation_provider
            )
            articles = list(
                MonitoredArticle.select(
                    MonitoredArticle.id,
                    MonitoredArticle.content,
                    MonitoredArticle.title,
                ).where(
                    MonitoredArticle.id.in_(normalized_article_ids),
                    MonitoredArticle.isdelete == 0,
                )
            )
            article_map = {
                int(article.id): str(article.content or article.title or "").strip()
                for article in articles
            }
            available_article_ids = [
                article_id for article_id in normalized_article_ids if article_id in article_map
            ]
            if not available_article_ids:
                raise ValueError("当前没有可处理的文章。")
            prompts = list(
                RewritePrompt.select().where(RewritePrompt.id.in_(normalized_prompt_ids))
            )
            prompt_map = {prompt.id: prompt for prompt in prompts}
            missing_prompt_ids = [
                prompt_id
                for prompt_id in normalized_prompt_ids
                if prompt_id not in prompt_map
            ]
            if missing_prompt_ids:
                raise ValueError(
                    f"提示词不存在或已被删除: {', '.join(str(item) for item in missing_prompt_ids)}"
                )

            created_items: list[dict[str, Any]] = []
            with database.atomic():
                for article_id in available_article_ids:
                    article_content = article_map.get(article_id, "")
                    for prompt_id in normalized_prompt_ids:
                        prompt = prompt_map[prompt_id]
                        task = TaskRecord.create(
                            account_id=account_snapshot["accountId"],
                            account_phone=account_snapshot["phone"],
                            account_note=account_snapshot["note"],
                            account_cookies=account_snapshot["cookies"],
                            generation_provider=generation_provider,
                            project_pid="",
                            article_id=article_id,
                            article_content=article_content,
                            rewritten_content="",
                            title="",
                            rewrite_prompt_id=prompt.id,
                            rewrite_prompt=prompt.content,
                            progress=0,
                            status=TASK_STATUS_PENDING,
                            huasheng_status=TASK_HUASHENG_STATUS_NOT_CREATED,
                            video_url="",
                            export_task_id="",
                            export_version="",
                            created_at=timestamp,
                            updated_at=timestamp,
                        )
                        created_items.append(self.serialize_task_record(task))
                deleted_article_count = self.delete_monitored_articles_by_ids(
                    available_article_ids,
                    timestamp=timestamp,
                )

        return {
            "items": created_items,
            "createdCount": len(created_items),
            "articleCount": len(available_article_ids),
            "promptCount": len(normalized_prompt_ids),
            "deletedArticleCount": deleted_article_count,
            "accountId": account_snapshot["accountId"],
            "generationProvider": generation_provider,
            "databasePath": str(self.db_path),
        }

    def create_single_article_processing_task(
        self,
        article_id: int,
        prompt_id: int,
    ) -> dict[str, Any]:
        return self.create_article_processing_tasks([article_id], [prompt_id])

    def get_global_settings_payload(self) -> dict[str, Any]:
        with database.connection_context():
            setting = AppSetting.get_or_none(AppSetting.key == GLOBAL_SETTINGS_KEY)
            if setting is None:
                timestamp = now_local()
                settings = self.default_global_settings()
                setting = AppSetting.create(
                    key=GLOBAL_SETTINGS_KEY,
                    value=json.dumps(settings, ensure_ascii=False),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            else:
                settings = self.normalize_global_settings(
                    self.deserialize_setting_value(setting.value)
                )
                persisted_value = json.dumps(settings, ensure_ascii=False)
                if setting.value != persisted_value:
                    setting.value = persisted_value
                    setting.updated_at = now_local()
                    setting.save()

        return self.build_global_settings_payload(
            settings,
            updated_at=setting.updated_at,
        )

    def get_log_status_payload(self) -> dict[str, Any]:
        log_dir = self.resolve_log_directory_path()
        items: list[dict[str, Any]] = []
        total_size_bytes = 0

        for log_path in self.list_log_file_paths(log_dir):
            try:
                stat_result = log_path.stat()
            except OSError:
                continue

            size_bytes = int(stat_result.st_size or 0)
            total_size_bytes += size_bytes
            items.append(
                {
                    "name": log_path.name,
                    "path": str(log_path),
                    "sizeBytes": size_bytes,
                    "updatedAt": datetime.fromtimestamp(stat_result.st_mtime).replace(
                        microsecond=0
                    ).isoformat(sep=" ", timespec="seconds"),
                }
            )

        current_log_path = resolve_daily_log_path(log_dir)
        current_log_item = next(
            (item for item in items if item["path"] == str(current_log_path)),
            None,
        )
        latest_log_item = items[0] if items else None

        return {
            "logDir": str(log_dir),
            "fileCount": len(items),
            "totalSizeBytes": total_size_bytes,
            "currentFileName": current_log_path.name,
            "currentFilePath": str(current_log_path),
            "currentFileSizeBytes": (
                int(current_log_item["sizeBytes"]) if current_log_item is not None else 0
            ),
            "latestFileName": str(latest_log_item["name"]) if latest_log_item else "",
            "latestFileSizeBytes": (
                int(latest_log_item["sizeBytes"]) if latest_log_item is not None else 0
            ),
            "latestUpdatedAt": (
                str(latest_log_item["updatedAt"]) if latest_log_item is not None else ""
            ),
            "files": items[:20],
            "databasePath": str(self.db_path),
        }

    def save_global_settings(
        self,
        thread_pool_size: int,
        download_dir: str | None = None,
        generation_provider: str | None = None,
        auto_download_videos: bool | None = None,
        auto_delete_redline_tasks: bool | None = None,
        rewrite_thread_pool_size: int | None = None,
        title_thread_pool_size: int | None = None,
        create_thread_pool_size: int | None = None,
        progress_thread_pool_size: int | None = None,
    ) -> dict[str, Any]:
        settings_input: dict[str, Any] = {
            "threadPoolSize": thread_pool_size,
        }
        existing_settings = self.get_global_settings_payload()["settings"]
        if download_dir is None:
            settings_input["downloadDir"] = existing_settings.get("downloadDir", "")
        else:
            settings_input["downloadDir"] = download_dir
        if generation_provider is None:
            settings_input["generationProvider"] = existing_settings.get(
                "generationProvider",
                DEFAULT_GLOBAL_SETTINGS["generationProvider"],
            )
        else:
            settings_input["generationProvider"] = generation_provider
        if auto_download_videos is None:
            settings_input["autoDownloadVideos"] = existing_settings.get(
                "autoDownloadVideos",
                DEFAULT_GLOBAL_SETTINGS["autoDownloadVideos"],
            )
        else:
            settings_input["autoDownloadVideos"] = auto_download_videos
        if auto_delete_redline_tasks is None:
            settings_input["autoDeleteRedlineTasks"] = existing_settings.get(
                "autoDeleteRedlineTasks",
                DEFAULT_GLOBAL_SETTINGS["autoDeleteRedlineTasks"],
            )
        else:
            settings_input["autoDeleteRedlineTasks"] = auto_delete_redline_tasks
        if rewrite_thread_pool_size is None:
            settings_input["rewriteThreadPoolSize"] = existing_settings.get(
                "rewriteThreadPoolSize",
                existing_settings.get(
                    "threadPoolSize",
                    DEFAULT_GLOBAL_SETTINGS["rewriteThreadPoolSize"],
                ),
            )
        else:
            settings_input["rewriteThreadPoolSize"] = rewrite_thread_pool_size
        if title_thread_pool_size is None:
            settings_input["titleThreadPoolSize"] = existing_settings.get(
                "titleThreadPoolSize",
                existing_settings.get(
                    "threadPoolSize",
                    DEFAULT_GLOBAL_SETTINGS["titleThreadPoolSize"],
                ),
            )
        else:
            settings_input["titleThreadPoolSize"] = title_thread_pool_size
        if create_thread_pool_size is None:
            settings_input["createThreadPoolSize"] = existing_settings.get(
                "createThreadPoolSize",
                DEFAULT_GLOBAL_SETTINGS["createThreadPoolSize"],
            )
        else:
            settings_input["createThreadPoolSize"] = create_thread_pool_size
        if progress_thread_pool_size is None:
            settings_input["progressThreadPoolSize"] = existing_settings.get(
                "progressThreadPoolSize",
                DEFAULT_GLOBAL_SETTINGS["progressThreadPoolSize"],
            )
        else:
            settings_input["progressThreadPoolSize"] = progress_thread_pool_size

        settings = self.normalize_global_settings(settings_input)
        timestamp = now_local()

        with database.connection_context():
            setting = AppSetting.get_or_none(AppSetting.key == GLOBAL_SETTINGS_KEY)
            serialized = json.dumps(settings, ensure_ascii=False)
            if setting is None:
                setting = AppSetting.create(
                    key=GLOBAL_SETTINGS_KEY,
                    value=serialized,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            else:
                setting.value = serialized
                setting.updated_at = timestamp
                setting.save()

        if self.is_task_processor_running():
            self.configure_task_executor(settings["threadPoolSize"])

        return self.build_global_settings_payload(
            settings,
            updated_at=timestamp,
        )

    def get_subtitle_settings_payload(self) -> dict[str, Any]:
        with database.connection_context():
            setting = AppSetting.get_or_none(AppSetting.key == SUBTITLE_SETTINGS_KEY)
            if setting is None:
                timestamp = now_local()
                settings = self.default_subtitle_settings()
                setting = AppSetting.create(
                    key=SUBTITLE_SETTINGS_KEY,
                    value=json.dumps(settings, ensure_ascii=False),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            else:
                settings = self.normalize_subtitle_settings(
                    self.deserialize_setting_value(setting.value)
                )
                persisted_value = json.dumps(settings, ensure_ascii=False)
                if setting.value != persisted_value:
                    setting.value = persisted_value
                    setting.updated_at = now_local()
                    setting.save()

        return self.build_subtitle_settings_payload(
            settings,
            updated_at=setting.updated_at,
        )

    def save_subtitle_settings(self, font_size: int, style_id: str) -> dict[str, Any]:
        settings = self.normalize_subtitle_settings(
            {
                "fontSize": font_size,
                "styleId": style_id,
            }
        )
        timestamp = now_local()

        with database.connection_context():
            setting = AppSetting.get_or_none(AppSetting.key == SUBTITLE_SETTINGS_KEY)
            serialized = json.dumps(settings, ensure_ascii=False)
            if setting is None:
                setting = AppSetting.create(
                    key=SUBTITLE_SETTINGS_KEY,
                    value=serialized,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            else:
                setting.value = serialized
                setting.updated_at = timestamp
                setting.save()

        return self.build_subtitle_settings_payload(settings, updated_at=timestamp)

    def get_model_settings_payload(self) -> dict[str, Any]:
        with database.connection_context():
            setting = AppSetting.get_or_none(AppSetting.key == MODEL_SETTINGS_KEY)
            if setting is None:
                timestamp = now_local()
                settings = self.default_model_settings()
                setting = AppSetting.create(
                    key=MODEL_SETTINGS_KEY,
                    value=json.dumps(settings, ensure_ascii=False),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            else:
                settings = self.normalize_model_settings(
                    self.deserialize_setting_value(setting.value)
                )
                persisted_value = json.dumps(settings, ensure_ascii=False)
                if setting.value != persisted_value:
                    setting.value = persisted_value
                    setting.updated_at = now_local()
                    setting.save()

            prompts = list(
                RewritePrompt.select().order_by(
                    RewritePrompt.sort_order.asc(),
                    RewritePrompt.id.asc(),
                )
            )

        return self.build_model_settings_payload(
            settings,
            prompts,
            updated_at=setting.updated_at,
        )

    def get_huasheng_voice_settings_payload(self) -> dict[str, Any]:
        with database.connection_context():
            setting = AppSetting.get_or_none(
                AppSetting.key == HUASHENG_VOICE_SETTINGS_KEY
            )
            if setting is None:
                timestamp = now_local()
                settings = self.default_huasheng_voice_settings()
                setting = AppSetting.create(
                    key=HUASHENG_VOICE_SETTINGS_KEY,
                    value=json.dumps(settings, ensure_ascii=False),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            else:
                settings = self.normalize_huasheng_voice_settings(
                    self.deserialize_setting_value(setting.value)
                )
                persisted_value = json.dumps(settings, ensure_ascii=False)
                if setting.value != persisted_value:
                    setting.value = persisted_value
                    setting.updated_at = now_local()
                    setting.save()

        return self.build_huasheng_voice_settings_payload(
            settings,
            updated_at=setting.updated_at,
        )

    def save_huasheng_voice_settings(
        self,
        voice_id: int,
        voice_name: str,
        voice_code: str,
        voice_tags: str,
        preview_url: str,
        cover: str,
        speech_rate: float,
        max_concurrent_tasks_per_account: int | None = None,
    ) -> dict[str, Any]:
        settings = self.normalize_huasheng_voice_settings(
            {
                "voiceId": voice_id,
                "voiceName": voice_name,
                "voiceCode": voice_code,
                "voiceTags": voice_tags,
                "previewUrl": preview_url,
                "cover": cover,
                "speechRate": speech_rate,
                "maxConcurrentTasksPerAccount": max_concurrent_tasks_per_account,
            }
        )
        timestamp = now_local()

        with database.connection_context():
            setting = AppSetting.get_or_none(
                AppSetting.key == HUASHENG_VOICE_SETTINGS_KEY
            )
            serialized = json.dumps(settings, ensure_ascii=False)
            if setting is None:
                setting = AppSetting.create(
                    key=HUASHENG_VOICE_SETTINGS_KEY,
                    value=serialized,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            else:
                setting.value = serialized
                setting.updated_at = timestamp
                setting.save()

        return self.build_huasheng_voice_settings_payload(
            settings,
            updated_at=timestamp,
        )

    def get_autovideo_settings_payload(self) -> dict[str, Any]:
        with database.connection_context():
            setting = AppSetting.get_or_none(AppSetting.key == AUTOVIDEO_SETTINGS_KEY)
            if setting is None:
                timestamp = now_local()
                settings = self.default_autovideo_settings()
                setting = AppSetting.create(
                    key=AUTOVIDEO_SETTINGS_KEY,
                    value=json.dumps(settings, ensure_ascii=False),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            else:
                settings = self.normalize_autovideo_settings(
                    self.deserialize_setting_value(setting.value)
                )
                persisted_value = json.dumps(settings, ensure_ascii=False)
                if setting.value != persisted_value:
                    setting.value = persisted_value
                    setting.updated_at = now_local()
                    setting.save()

        return self.build_autovideo_settings_payload(
            settings,
            updated_at=setting.updated_at,
        )

    def save_autovideo_settings(
        self,
        voice_choice: str,
        rate_choice: str,
    ) -> dict[str, Any]:
        settings = self.normalize_autovideo_settings(
            {
                "voiceChoice": voice_choice,
                "rateChoice": rate_choice,
            }
        )
        timestamp = now_local()

        with database.connection_context():
            setting = AppSetting.get_or_none(AppSetting.key == AUTOVIDEO_SETTINGS_KEY)
            serialized = json.dumps(settings, ensure_ascii=False)
            if setting is None:
                setting = AppSetting.create(
                    key=AUTOVIDEO_SETTINGS_KEY,
                    value=serialized,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            else:
                setting.value = serialized
                setting.updated_at = timestamp
                setting.save()

        return self.build_autovideo_settings_payload(
            settings,
            updated_at=timestamp,
        )

    def save_model_settings(
        self,
        base_url: str,
        api_key: str,
        model: str,
        title_prompt: str,
        rewrite_prompts: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        settings = self.normalize_model_settings(
            {
                "baseUrl": base_url,
                "apiKey": api_key,
                "model": model,
                "titlePrompt": title_prompt,
            }
        )
        normalized_prompts = self.normalize_rewrite_prompt_list(rewrite_prompts)
        timestamp = now_local()

        with database.connection_context():
            with database.atomic():
                setting = AppSetting.get_or_none(AppSetting.key == MODEL_SETTINGS_KEY)
                serialized = json.dumps(settings, ensure_ascii=False)
                if setting is None:
                    setting = AppSetting.create(
                        key=MODEL_SETTINGS_KEY,
                        value=serialized,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                else:
                    setting.value = serialized
                    setting.updated_at = timestamp
                    setting.save()

                RewritePrompt.delete().execute()
                prompts: list[RewritePrompt] = []
                for index, content in enumerate(normalized_prompts):
                    prompts.append(
                        RewritePrompt.create(
                            content=content,
                            sort_order=index,
                            created_at=timestamp,
                            updated_at=timestamp,
                        )
                    )

        return self.build_model_settings_payload(
            settings,
            prompts,
            updated_at=timestamp,
        )

    def rewrite_article(
        self,
        base_url: str,
        api_key: str,
        model: str,
        prompt_id: int,
        article: str,
    ) -> dict[str, Any]:
        normalized_base_url = self.normalize_model_base_url(base_url)
        normalized_api_key = self.normalize_required_text_field(
            api_key,
            field_name="API Key",
            max_length=4000,
        )
        normalized_model = self.normalize_required_text_field(
            model,
            field_name="Model",
            max_length=255,
        )
        normalized_prompt_id = self.normalize_positive_int(prompt_id, field_name="prompt_id")
        normalized_article = self.normalize_required_text_field(
            article,
            field_name="文章",
            max_length=100000,
        )

        with database.connection_context():
            prompt = RewritePrompt.get_or_none(RewritePrompt.id == normalized_prompt_id)
            if prompt is None:
                raise ValueError("改写提示词不存在，可能已经被删除。")

        return self.rewrite_article_with_prompt(
            normalized_base_url,
            normalized_api_key,
            normalized_model,
            prompt.content,
            normalized_article,
            prompt_id=prompt.id,
        )

    def rewrite_article_with_prompt(
        self,
        base_url: str,
        api_key: str,
        model: str,
        prompt_content: str,
        article: str,
        *,
        prompt_id: int | None = None,
        task_id: int | None = None,
    ) -> dict[str, Any]:
        normalized_base_url = self.normalize_model_base_url(base_url)
        normalized_api_key = self.normalize_required_text_field(
            api_key,
            field_name="API Key",
            max_length=4000,
        )
        normalized_model = self.normalize_required_text_field(
            model,
            field_name="Model",
            max_length=255,
        )
        normalized_prompt_content = self.normalize_required_text_field(
            prompt_content,
            field_name="改写提示词",
            max_length=20000,
        )
        normalized_article = self.normalize_required_text_field(
            article,
            field_name="文章",
            max_length=100000,
        )
        rewrite_system_prompt = self.build_rewrite_system_prompt(normalized_prompt_content)
        rewrite_user_content = self.build_rewrite_user_content(normalized_article)
        content = self._request_model_text(
            base_url=normalized_base_url,
            api_key=normalized_api_key,
            model=normalized_model,
            system_prompt=rewrite_system_prompt,
            user_content=rewrite_user_content,
            action_name="文章改写",
            timeout=REWRITE_MODEL_REQUEST_TIMEOUT,
            task_id=task_id,
        )
        normalized_content = self.normalize_rewrite_response_text(content)
        if self.is_rewrite_redline_response(normalized_content or content):
            return {
                "content": REWRITE_REDLINE_DISPLAY_TEXT,
                "promptId": prompt_id or 0,
                "promptContent": normalized_prompt_content,
                "model": normalized_model,
                "requestUrl": normalized_base_url,
                "databasePath": str(self.db_path),
                "triggeredRedline": True,
            }
        if not normalized_content:
            raise RuntimeError("文章改写失败: 模型接口返回为空。")

        return {
            "content": normalized_content,
            "promptId": prompt_id or 0,
            "promptContent": normalized_prompt_content,
            "model": normalized_model,
            "requestUrl": normalized_base_url,
            "databasePath": str(self.db_path),
            "triggeredRedline": False,
        }

    def build_rewrite_system_prompt(self, prompt_content: str) -> str:
        return str(prompt_content or "").strip()

    def build_rewrite_user_content(self, article: str) -> str:
        normalized_article = str(article or "").strip()
        if not normalized_article:
            return REWRITE_OUTPUT_FORMAT_PROMPT
        return f"{normalized_article}\n\n{REWRITE_OUTPUT_FORMAT_PROMPT}"

    def normalize_rewrite_response_text(self, text: str) -> str:
        normalized = self._strip_labeled_output(text, label="content")
        normalized = self._strip_markdown_code_fence(normalized)
        return self._strip_rewrite_markdown_chars(normalized)

    def is_rewrite_redline_response(self, text: str) -> bool:
        normalized = self._strip_markdown_code_fence(str(text or "").strip())
        if not normalized:
            return False

        candidates = [
            normalized,
            self._strip_labeled_output(normalized, label="content"),
        ]
        expected = "触发红线禁止改写"
        for candidate in candidates:
            compact = re.sub(r"[#`\s:：,，.。!！?？\"'“”‘’]+", "", str(candidate or ""))
            if compact == expected:
                return True
            if any(keyword in compact for keyword in REWRITE_REDLINE_FUZZY_KEYWORDS):
                return True
        return False

    def generate_title(
        self,
        base_url: str,
        api_key: str,
        model: str,
        title_prompt: str,
        article: str,
    ) -> dict[str, Any]:
        normalized_base_url = self.normalize_model_base_url(base_url)
        normalized_api_key = self.normalize_required_text_field(
            api_key,
            field_name="API Key",
            max_length=4000,
        )
        normalized_model = self.normalize_required_text_field(
            model,
            field_name="Model",
            max_length=255,
        )
        normalized_title_prompt = self.normalize_required_text_field(
            title_prompt,
            field_name="标题提示词",
            max_length=20000,
        )
        normalized_article = self.normalize_required_text_field(
            article,
            field_name="文章",
            max_length=100000,
        )
        title_system_prompt = self.build_title_system_prompt(normalized_title_prompt)
        title_user_content = self.build_title_user_content(normalized_article)

        title = self._request_model_text(
            base_url=normalized_base_url,
            api_key=normalized_api_key,
            model=normalized_model,
            system_prompt=title_system_prompt,
            user_content=title_user_content,
            action_name="标题生成",
            timeout=TITLE_MODEL_REQUEST_TIMEOUT,
        )
        title = self.normalize_title_response_text(title)
        if not title:
            raise RuntimeError("标题生成失败: 模型接口返回为空。")

        return {
            "title": title,
            "titlePrompt": normalized_title_prompt,
            "model": normalized_model,
            "requestUrl": normalized_base_url,
            "databasePath": str(self.db_path),
        }

    def start_task_processor(self) -> None:
        with self._task_processor_state_lock:
            if self._task_processor_thread and self._task_processor_thread.is_alive():
                return
            settings = self.get_global_settings_payload()["settings"]
            self._task_processor_stop_event.clear()
            self._ensure_task_executor_locked(settings["threadPoolSize"])
            self._task_processor_thread = Thread(
                target=self._task_processor_loop,
                name="huasheng-task-scanner",
                daemon=True,
            )
            thread = self._task_processor_thread

        logger.info(
            "Task processor starting executor_thread_pool_size=%s rewrite_limit=%s title_limit=%s create_limit=%s progress_limit=%s scan_interval=%ss",
            settings["threadPoolSize"],
            settings["rewriteThreadPoolSize"],
            settings["titleThreadPoolSize"],
            settings["createThreadPoolSize"],
            settings["progressThreadPoolSize"],
            TASK_QUEUE_SCAN_INTERVAL_SECONDS,
        )
        thread.start()

    def stop_task_processor(self) -> None:
        with self._task_processor_state_lock:
            self._task_processor_stop_event.set()
            thread = self._task_processor_thread
            self._task_processor_thread = None
            executor = self._task_executor
            self._task_executor = None
            self._task_executor_size = 0
            self._rewrite_task_ids_inflight.clear()
            self._title_task_ids_inflight.clear()
            self._huasheng_create_task_ids_inflight.clear()
            self._huasheng_progress_task_ids_inflight.clear()

        if thread and thread.is_alive():
            thread.join(timeout=TASK_QUEUE_SCAN_INTERVAL_SECONDS + 1)
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    def is_task_processor_running(self) -> bool:
        with self._task_processor_state_lock:
            return bool(self._task_processor_thread and self._task_processor_thread.is_alive())

    def configure_task_executor(self, thread_pool_size: int) -> None:
        previous_executor: ThreadPoolExecutor | None = None
        with self._task_processor_state_lock:
            normalized_size = self.normalize_executor_thread_pool_size(thread_pool_size)
            if (
                self._task_executor is not None
                and self._task_executor_size == normalized_size
            ):
                return
            previous_executor = self._task_executor
            self._ensure_task_executor_locked(normalized_size)

        if previous_executor is not None:
            previous_executor.shutdown(wait=False, cancel_futures=False)

    def process_task_queue_once(self) -> dict[str, int]:
        global_settings = self.get_global_settings_payload()["settings"]
        model_settings = self.get_model_settings_payload()["settings"]
        has_model_connection = self.has_model_connection_settings(model_settings)
        rewrite_task_ids = (
            self.list_pending_rewrite_task_ids() if has_model_connection else []
        )
        title_task_ids = (
            self.list_pending_title_task_ids() if has_model_connection else []
        )
        huasheng_create_task_ids = self.list_pending_huasheng_create_task_ids()
        huasheng_progress_task_ids = self.list_pending_huasheng_progress_task_ids()
        with self._task_processor_state_lock:
            inflight_rewrite = len(self._rewrite_task_ids_inflight)
            inflight_title = len(self._title_task_ids_inflight)
            inflight_huasheng_create = len(self._huasheng_create_task_ids_inflight)
            inflight_huasheng_progress = len(self._huasheng_progress_task_ids_inflight)
            executor_size = self._task_executor_size

        rewrite_slots = max(0, int(global_settings["rewriteThreadPoolSize"]) - inflight_rewrite)
        title_slots = max(0, int(global_settings["titleThreadPoolSize"]) - inflight_title)
        huasheng_create_slots = max(
            0,
            int(global_settings["createThreadPoolSize"]) - inflight_huasheng_create,
        )
        huasheng_progress_slots = max(
            0,
            int(global_settings["progressThreadPoolSize"]) - inflight_huasheng_progress,
        )

        if (
            rewrite_task_ids
            or title_task_ids
            or huasheng_create_task_ids
            or huasheng_progress_task_ids
            or inflight_rewrite
            or inflight_title
            or inflight_huasheng_create
            or inflight_huasheng_progress
        ):
            logger.debug(
                "Task processor scan pending_rewrite=%s pending_title=%s pending_huasheng_create=%s pending_huasheng_progress=%s inflight_rewrite=%s inflight_title=%s inflight_huasheng_create=%s inflight_huasheng_progress=%s rewrite_slots=%s title_slots=%s huasheng_create_slots=%s huasheng_progress_slots=%s executor_size=%s",
                len(rewrite_task_ids),
                len(title_task_ids),
                len(huasheng_create_task_ids),
                len(huasheng_progress_task_ids),
                inflight_rewrite,
                inflight_title,
                inflight_huasheng_create,
                inflight_huasheng_progress,
                rewrite_slots,
                title_slots,
                huasheng_create_slots,
                huasheng_progress_slots,
                executor_size,
            )

        rewrite_submitted = 0
        title_submitted = 0
        huasheng_create_submitted = 0
        huasheng_progress_submitted = 0

        if has_model_connection:
            for task_id in rewrite_task_ids[:rewrite_slots]:
                if self.submit_rewrite_task(task_id):
                    rewrite_submitted += 1
        elif self.list_pending_rewrite_task_ids():
            logger.debug("Task processor skipped rewrite because model connection settings are incomplete")

        if has_model_connection and str(model_settings.get("titlePrompt") or "").strip():
            for task_id in title_task_ids[:title_slots]:
                if self.submit_title_task(task_id):
                    title_submitted += 1
        elif has_model_connection and title_task_ids:
            logger.debug(
                "Task processor skipped title generation because title prompt is empty pending_title=%s",
                len(title_task_ids),
            )
        elif not has_model_connection and self.list_pending_title_task_ids():
            logger.debug("Task processor skipped title generation because model connection settings are incomplete")

        for task_id in huasheng_create_task_ids[:huasheng_create_slots]:
            if self.submit_huasheng_create_task(task_id):
                huasheng_create_submitted += 1

        for task_id in huasheng_progress_task_ids[:huasheng_progress_slots]:
            if self.submit_huasheng_progress_task(task_id):
                huasheng_progress_submitted += 1

        if (
            rewrite_submitted
            or title_submitted
            or huasheng_create_submitted
            or huasheng_progress_submitted
        ):
            logger.info(
                "Task processor submitted rewrite=%s title=%s huasheng_create=%s huasheng_progress=%s",
                rewrite_submitted,
                title_submitted,
                huasheng_create_submitted,
                huasheng_progress_submitted,
            )

        return {
            "rewriteSubmitted": rewrite_submitted,
            "titleSubmitted": title_submitted,
            "huashengCreateSubmitted": huasheng_create_submitted,
            "huashengProgressSubmitted": huasheng_progress_submitted,
        }

    def list_pending_rewrite_task_ids(self) -> list[int]:
        with database.connection_context():
            query = (
                TaskRecord.select(TaskRecord.id)
                .where(
                    TaskRecord.status == TASK_STATUS_PENDING,
                    TaskRecord.article_id.is_null(False),
                    TaskRecord.rewritten_content == "",
                )
                .order_by(TaskRecord.created_at.asc(), TaskRecord.id.asc())
            )
            return [task.id for task in query]

    def list_pending_title_task_ids(self) -> list[int]:
        with database.connection_context():
            query = (
                TaskRecord.select(TaskRecord.id)
                .where(
                    TaskRecord.status == TASK_STATUS_REWRITE_READY,
                    TaskRecord.article_id.is_null(False),
                    TaskRecord.rewritten_content != "",
                    TaskRecord.title == "",
                )
                .order_by(TaskRecord.created_at.asc(), TaskRecord.id.asc())
            )
            return [task.id for task in query]

    def list_pending_huasheng_create_task_ids(self) -> list[int]:
        with database.connection_context():
            query = (
                TaskRecord.select(TaskRecord.id)
                .where(
                    TaskRecord.status.in_(
                        [TASK_STATUS_READY_FOR_HUASHENG, TASK_STATUS_READY_FOR_VIDEO]
                    ),
                    TaskRecord.article_id.is_null(False),
                    TaskRecord.rewritten_content != "",
                    TaskRecord.title != "",
                    TaskRecord.project_pid == "",
                    TaskRecord.video_url == "",
                )
                .order_by(TaskRecord.created_at.asc(), TaskRecord.id.asc())
            )
            return [task.id for task in query]

    def list_pending_huasheng_progress_task_ids(self) -> list[int]:
        with database.connection_context():
            query = (
                TaskRecord.select(TaskRecord.id)
                .where(
                    TaskRecord.project_pid != "",
                    TaskRecord.video_url == "",
                    TaskRecord.status != TASK_STATUS_EXPORT_FINISHED,
                )
                .order_by(TaskRecord.updated_at.asc(), TaskRecord.id.asc())
            )
            return [task.id for task in query]

    def submit_rewrite_task(self, task_id: int) -> bool:
        normalized_task_id = self.normalize_positive_int(task_id, field_name="task_id")
        if not self._mark_task_inflight(normalized_task_id, stage=TASK_STAGE_REWRITE):
            logger.debug(
                "Task processor skipped duplicate rewrite submission task_id=%s",
                normalized_task_id,
            )
            return False

        try:
            self.update_task_status(normalized_task_id, TASK_STATUS_REWRITE_RUNNING)
            future = self.get_task_executor().submit(
                self._run_rewrite_task,
                normalized_task_id,
            )
            logger.debug("Task processor submitted rewrite task_id=%s", normalized_task_id)
            future.add_done_callback(
                lambda done_future, submitted_task_id=normalized_task_id: self._finalize_submitted_task(
                    submitted_task_id,
                    stage=TASK_STAGE_REWRITE,
                    future=done_future,
                )
            )
            return True
        except Exception:
            self._unmark_task_inflight(normalized_task_id, stage=TASK_STAGE_REWRITE)
            raise

    def submit_title_task(self, task_id: int) -> bool:
        normalized_task_id = self.normalize_positive_int(task_id, field_name="task_id")
        if not self._mark_task_inflight(normalized_task_id, stage=TASK_STAGE_TITLE):
            logger.debug(
                "Task processor skipped duplicate title submission task_id=%s",
                normalized_task_id,
            )
            return False

        try:
            self.update_task_status(normalized_task_id, TASK_STATUS_TITLE_RUNNING)
            future = self.get_task_executor().submit(
                self._run_title_task,
                normalized_task_id,
            )
            logger.debug("Task processor submitted title task_id=%s", normalized_task_id)
            future.add_done_callback(
                lambda done_future, submitted_task_id=normalized_task_id: self._finalize_submitted_task(
                    submitted_task_id,
                    stage=TASK_STAGE_TITLE,
                    future=done_future,
                )
            )
            return True
        except Exception:
            self._unmark_task_inflight(normalized_task_id, stage=TASK_STAGE_TITLE)
            raise

    def submit_huasheng_create_task(self, task_id: int) -> bool:
        normalized_task_id = self.normalize_positive_int(task_id, field_name="task_id")
        if not self._mark_task_inflight(normalized_task_id, stage=TASK_STAGE_HUASHENG_CREATE):
            logger.debug(
                "Task processor skipped duplicate huasheng-create submission task_id=%s",
                normalized_task_id,
            )
            return False

        try:
            task = self.find_task_record(normalized_task_id)
            if task is None:
                self._unmark_task_inflight(normalized_task_id, stage=TASK_STAGE_HUASHENG_CREATE)
                return False
            self.update_task_status(
                normalized_task_id,
                self.get_task_create_running_status(task),
            )
            future = self.get_task_executor().submit(
                self._run_huasheng_create_task,
                normalized_task_id,
            )
            logger.debug("Task processor submitted huasheng-create task_id=%s", normalized_task_id)
            future.add_done_callback(
                lambda done_future, submitted_task_id=normalized_task_id: self._finalize_submitted_task(
                    submitted_task_id,
                    stage=TASK_STAGE_HUASHENG_CREATE,
                    future=done_future,
                )
            )
            return True
        except Exception:
            self._unmark_task_inflight(normalized_task_id, stage=TASK_STAGE_HUASHENG_CREATE)
            raise

    def submit_huasheng_progress_task(self, task_id: int) -> bool:
        normalized_task_id = self.normalize_positive_int(task_id, field_name="task_id")
        if not self._mark_task_inflight(normalized_task_id, stage=TASK_STAGE_HUASHENG_PROGRESS):
            logger.debug(
                "Task processor skipped duplicate huasheng-progress submission task_id=%s",
                normalized_task_id,
            )
            return False

        try:
            future = self.get_task_executor().submit(
                self._run_huasheng_progress_task,
                normalized_task_id,
            )
            logger.debug(
                "Task processor submitted huasheng-progress task_id=%s",
                normalized_task_id,
            )
            future.add_done_callback(
                lambda done_future, submitted_task_id=normalized_task_id: self._finalize_submitted_task(
                    submitted_task_id,
                    stage=TASK_STAGE_HUASHENG_PROGRESS,
                    future=done_future,
                )
            )
            return True
        except Exception:
            self._unmark_task_inflight(normalized_task_id, stage=TASK_STAGE_HUASHENG_PROGRESS)
            raise

    def get_task_executor(self) -> ThreadPoolExecutor:
        with self._task_processor_state_lock:
            self._ensure_task_executor_locked(
                self.get_global_settings_payload()["settings"]["threadPoolSize"]
            )
            if self._task_executor is None:
                raise RuntimeError("任务线程池未初始化。")
            return self._task_executor

    def load_source_article_text(self, article_id: int) -> str:
        normalized_article_id = self.normalize_positive_int(article_id, field_name="article_id")
        with database.connection_context():
            article = MonitoredArticle.get_or_none(MonitoredArticle.id == normalized_article_id)
            if article is None:
                raise ValueError("文章不存在，可能已经被删除。")
            content = str(article.content or article.title or "").strip()
            if not content:
                raise ValueError("文章内容为空，无法执行改写。")
            return content

    def load_task_source_article_text(self, task: TaskRecord) -> str:
        snapshot_content = str(task.article_content or "").strip()
        if snapshot_content:
            return snapshot_content
        if not task.article_id:
            raise ValueError("任务没有文章 ID，无法读取原文。")
        return self.load_source_article_text(int(task.article_id))

    def load_model_settings_snapshot(self) -> dict[str, str]:
        payload = self.get_model_settings_payload()
        settings = payload.get("settings") or {}
        return self.normalize_model_settings(settings)

    def load_huasheng_voice_settings_snapshot(self) -> dict[str, Any]:
        payload = self.get_huasheng_voice_settings_payload()
        settings = payload.get("settings") or {}
        return self.normalize_huasheng_voice_settings(settings)

    def load_subtitle_settings_snapshot(self) -> dict[str, Any]:
        payload = self.get_subtitle_settings_payload()
        settings = payload.get("settings") or {}
        return self.normalize_subtitle_settings(settings)

    def has_model_connection_settings(self, settings: dict[str, Any]) -> bool:
        return all(
            str(settings.get(field) or "").strip()
            for field in ("baseUrl", "apiKey", "model")
        )

    def build_title_system_prompt(self, title_prompt: str) -> str:
        return str(title_prompt or "").strip()

    def build_title_user_content(self, article: str) -> str:
        normalized_article = str(article or "").strip()
        if not normalized_article:
            return TITLE_OUTPUT_FORMAT_PROMPT
        return f"{normalized_article}\n\n{TITLE_OUTPUT_FORMAT_PROMPT}"

    def normalize_title_response_text(self, text: str) -> str:
        normalized = self._strip_markdown_code_fence(
            self._strip_labeled_output(text, label="title")
        )
        for line in normalized.splitlines():
            stripped = line.strip()
            if stripped:
                if len(stripped) > TITLE_RESPONSE_MAX_LENGTH:
                    raise RuntimeError(
                        "标题生成失败: 模型返回内容不符合格式，只接受单行短标题。"
                    )
                if any(stripped.startswith(prefix) for prefix in TITLE_RESPONSE_INVALID_PREFIXES):
                    raise RuntimeError(
                        "标题生成失败: 模型返回内容不符合格式，只接受单行短标题。"
                    )
                return stripped
        return ""

    def test_model_connection(
        self,
        base_url: str,
        api_key: str,
        model: str,
    ) -> dict[str, Any]:
        normalized_base_url = self.normalize_model_base_url(base_url)
        normalized_api_key = self.normalize_required_text_field(
            api_key,
            field_name="API Key",
            max_length=4000,
        )
        normalized_model = self.normalize_required_text_field(
            model,
            field_name="Model",
            max_length=255,
        )

        response_text = self._request_model_text(
            base_url=normalized_base_url,
            api_key=normalized_api_key,
            model=normalized_model,
            system_prompt=MODEL_CONNECTION_TEST_SYSTEM_PROMPT,
            user_content=MODEL_CONNECTION_TEST_USER_CONTENT,
            action_name="模型连接测试",
        )

        return {
            "message": "模型连接测试成功",
            "responseText": response_text,
            "model": normalized_model,
            "requestUrl": normalized_base_url,
            "databasePath": str(self.db_path),
        }

    def get_account(self, account_id: int) -> Account:
        account = Account.get_or_none(Account.id == int(account_id))
        if account is None:
            raise ValueError("账号不存在，列表可能已经过期。")
        return account

    def find_task_record(self, task_id: int) -> TaskRecord | None:
        with database.connection_context():
            return TaskRecord.get_or_none(TaskRecord.id == int(task_id))

    def get_task_record(self, task_id: int) -> TaskRecord:
        task = self.find_task_record(task_id)
        if task is None:
            raise ValueError("任务不存在，列表可能已经过期。")
        return task

    def ensure_task_account_snapshot(self, task: TaskRecord) -> dict[str, Any]:
        account_phone = str(task.account_phone or "").strip()
        account_note = str(task.account_note or "").strip()
        account_cookies = str(task.account_cookies or "").strip()
        if account_phone and account_cookies:
            return {
                "accountId": int(task.account_id),
                "phone": account_phone,
                "note": account_note,
                "cookies": account_cookies,
            }

        with database.connection_context():
            account = self.get_account(task.account_id)
            refreshed_task = self.get_task_record(task.id)
            refreshed_task.account_phone = account.phone
            refreshed_task.account_note = account.note
            refreshed_task.account_cookies = account.cookies
            refreshed_task.updated_at = now_local()
            refreshed_task.save()

        logger.info(
            "Task account snapshot synced task_id=%s account_id=%s phone=%s",
            task.id,
            account.id,
            account.phone,
        )
        return {
            "accountId": account.id,
            "phone": account.phone,
            "note": account.note,
            "cookies": account.cookies,
        }

    def parse_project_progress(self, payload: dict[str, Any] | None) -> int:
        project = self.extract_project_payload(payload)
        return self.normalize_task_progress(project.get("progress"))

    def extract_project_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(payload, dict) and isinstance(payload.get("project"), dict):
            return payload["project"]
        if isinstance(payload, dict):
            return payload
        return {}

    def build_project_state_text(self, payload: dict[str, Any] | None) -> str:
        project = self.extract_project_payload(payload)
        for field in ("state_message", "loading_msg", "status", "message"):
            value = str(project.get(field) or "").strip()
            if value:
                return value
        progress = self.parse_project_progress(payload)
        if progress > 0:
            return f"项目进度 {progress}%"
        return "等待花生处理"

    def is_project_finished(self, payload: dict[str, Any] | None) -> bool:
        progress = self.parse_project_progress(payload)
        if progress >= 100:
            return True
        return "项目处理完成" in self.build_project_state_text(payload)

    def is_project_failed(self, payload: dict[str, Any] | None) -> bool:
        return bool(re.search(r"失败|异常|取消", self.build_project_state_text(payload)))

    def parse_export_progress(self, payload: dict[str, Any] | None) -> int:
        source = payload if isinstance(payload, dict) else {}
        return self.normalize_task_progress(source.get("progress"))

    def extract_export_url(self, payload: dict[str, Any] | None) -> str:
        source = payload if isinstance(payload, dict) else {}
        return str(source.get("url") or "").strip()

    def build_export_state_text(self, payload: dict[str, Any] | None) -> str:
        progress = self.parse_export_progress(payload)
        url = self.extract_export_url(payload)
        if url:
            return TASK_HUASHENG_STATUS_EXPORT_FINISHED
        if progress > 0:
            return f"导出进度 {progress}%"
        return "导出中"

    def is_export_finished(self, payload: dict[str, Any] | None) -> bool:
        url = self.extract_export_url(payload)
        return bool(url)

    def extract_numeric_identifier(self, value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            return ""
        try:
            parsed = int(normalized)
        except (TypeError, ValueError):
            return ""
        if parsed <= 0:
            return ""
        return str(parsed)

    def resolve_created_project_identifier(self, payload: dict[str, Any] | None) -> str:
        project = self.extract_project_payload(payload)
        for candidate in (
            project.get("pid"),
            (payload or {}).get("pid") if isinstance(payload, dict) else None,
        ):
            normalized = self.extract_numeric_identifier(candidate)
            if normalized:
                return normalized
        raise ValueError("创建花生任务失败: 接口未返回有效的项目 PID。")

    def resolve_progress_query_identifier(self, task: TaskRecord) -> str:
        normalized = self.extract_numeric_identifier(task.project_pid)
        if normalized:
            return normalized
        raise ValueError("任务没有有效的花生项目 ID，无法扫描项目状态。")

    def resolve_project_identifier_from_progress_payload(
        self,
        payload: dict[str, Any] | None,
        *,
        fallback: Any = "",
    ) -> str:
        project = self.extract_project_payload(payload)
        for candidate in (
            project.get("pid"),
            (payload or {}).get("pid") if isinstance(payload, dict) else None,
            fallback,
        ):
            normalized = self.extract_numeric_identifier(candidate)
            if normalized:
                return normalized
        raise ValueError("项目 ID 无效，无法继续处理。")

    def resolve_project_numeric_id_from_progress_payload(
        self,
        payload: dict[str, Any] | None,
    ) -> int:
        project = self.extract_project_payload(payload)
        for candidate in (
            project.get("id"),
            (payload or {}).get("id") if isinstance(payload, dict) else None,
        ):
            normalized = self.extract_numeric_identifier(candidate)
            if normalized:
                return self.parse_project_numeric_id(normalized)
        raise ValueError("项目数值 ID 无效，无法继续处理。")

    def parse_project_numeric_id(self, value: Any) -> int:
        try:
            normalized = int(str(value or "").strip())
        except (TypeError, ValueError):
            raise ValueError("项目 ID 无效，无法继续处理。") from None
        if normalized <= 0:
            raise ValueError("项目 ID 无效，无法继续处理。")
        return normalized

    def normalize_phone(self, phone: str) -> str:
        normalized = re.sub(r"[\s-]+", "", str(phone or ""))
        if not PHONE_PATTERN.fullmatch(normalized):
            raise ValueError("请输入 11 位中国大陆手机号。")
        return normalized

    def normalize_cookies(self, cookies: str) -> str:
        normalized = str(cookies or "").strip()
        if not normalized:
            raise ValueError("Cookies 不能为空。")
        return normalized

    def normalize_note(self, note: str) -> str:
        normalized = str(note or "").strip()
        if len(normalized) > 255:
            raise ValueError("备注长度不能超过 255 个字符。")
        return normalized

    def normalize_positive_int(self, value: Any, *, field_name: str) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} 必须是正整数。") from exc
        if normalized <= 0:
            raise ValueError(f"{field_name} 必须大于 0。")
        return normalized

    def normalize_short_text(
        self,
        value: Any,
        *,
        field_name: str,
        max_length: int,
        allow_empty: bool = False,
    ) -> str:
        normalized = str(value or "").strip()
        if not normalized and not allow_empty:
            raise ValueError(f"{field_name} 不能为空。")
        if len(normalized) > max_length:
            raise ValueError(f"{field_name} 长度不能超过 {max_length} 个字符。")
        return normalized

    def serialize_account(
        self,
        account: Account,
        *,
        today_generation_count: int | None = None,
        active_huasheng_task_count: int | None = None,
        max_concurrent_tasks_per_account: int | None = None,
    ) -> dict[str, Any]:
        if today_generation_count is None:
            today_generation_count = self.count_huasheng_generation_records_for_account_today(
                account.id
            )
        if active_huasheng_task_count is None:
            active_huasheng_task_count = self.list_huasheng_active_task_counts().get(
                int(account.id),
                0,
            )
        if max_concurrent_tasks_per_account is None:
            max_concurrent_tasks_per_account = int(
                self.load_huasheng_voice_settings_snapshot().get(
                    "maxConcurrentTasksPerAccount"
                )
                or 1
            )
        return {
            "id": account.id,
            "phone": account.phone,
            "cookies": account.cookies,
            "note": account.note,
            "isDisabled": account.is_disabled,
            "todayGenerationCount": int(today_generation_count or 0),
            "dailyGenerationLimit": HUASHENG_DAILY_PROJECT_LIMIT,
            "activeHuashengTaskCount": int(active_huasheng_task_count or 0),
            "maxConcurrentTasksPerAccount": int(max_concurrent_tasks_per_account or 1),
            "createdAt": account.created_at.isoformat(sep=" ", timespec="seconds"),
            "updatedAt": account.updated_at.isoformat(sep=" ", timespec="seconds"),
        }

    def serialize_task_record(
        self,
        task: TaskRecord,
        *,
        article_preview: str = "",
    ) -> dict[str, Any]:
        return {
            "id": task.id,
            "accountId": task.account_id,
            "accountPhone": task.account_phone,
            "accountNote": task.account_note,
            "generationProvider": self.normalize_generation_provider(
                getattr(task, "generation_provider", GENERATION_PROVIDER_HUASHENG)
            ),
            "projectPid": task.project_pid,
            "articleId": task.article_id,
            "articlePreview": article_preview or str(task.article_content or "").strip(),
            "rewrittenContent": task.rewritten_content,
            "title": task.title,
            "rewritePromptId": task.rewrite_prompt_id,
            "rewritePrompt": task.rewrite_prompt,
            "progress": task.progress,
            "status": task.status,
            "huashengStatus": task.huasheng_status,
            "videoUrl": task.video_url,
            "exportTaskId": task.export_task_id,
            "exportVersion": task.export_version,
            "createdAt": task.created_at.isoformat(sep=" ", timespec="seconds"),
            "updatedAt": task.updated_at.isoformat(sep=" ", timespec="seconds"),
        }

    def get_default_task_account(self) -> Account:
        account = (
            Account.select()
            .where(Account.is_disabled == False)
            .order_by(Account.updated_at.desc(), Account.id.desc())
            .first()
        )
        if account is None:
            account = Account.select().order_by(Account.updated_at.desc(), Account.id.desc()).first()
        if account is None:
            raise ValueError("请先至少添加一个花生账号。")
        return account

    def get_default_task_account_snapshot(self, *, generation_provider: str) -> dict[str, Any]:
        normalized_provider = self.normalize_generation_provider(generation_provider)
        if normalized_provider == GENERATION_PROVIDER_AUTOVIDEO:
            return {
                "accountId": 0,
                "phone": "",
                "note": "AutoVideo",
                "cookies": "",
            }
        account = self.get_default_task_account()
        return self.build_account_snapshot(account)

    def get_task_generation_provider(self, task: TaskRecord) -> str:
        return self.normalize_generation_provider(
            getattr(task, "generation_provider", GENERATION_PROVIDER_HUASHENG)
        )

    def get_task_ready_for_generation_status(self, task: TaskRecord) -> str:
        if self.get_task_generation_provider(task) == GENERATION_PROVIDER_AUTOVIDEO:
            return TASK_STATUS_READY_FOR_VIDEO
        return TASK_STATUS_READY_FOR_HUASHENG

    def get_task_create_running_status(self, task: TaskRecord) -> str:
        if self.get_task_generation_provider(task) == GENERATION_PROVIDER_AUTOVIDEO:
            return TASK_STATUS_VIDEO_CREATING
        return TASK_STATUS_HUASHENG_CREATING

    def build_account_snapshot(self, account: Account) -> dict[str, Any]:
        return {
            "accountId": int(account.id),
            "phone": str(account.phone or "").strip(),
            "note": str(account.note or "").strip(),
            "cookies": str(account.cookies or "").strip(),
        }

    def resolve_day_time_range(
        self,
        reference_time: datetime | None = None,
    ) -> tuple[datetime, datetime]:
        current_time = reference_time or now_local()
        start_time = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        return start_time, start_time + timedelta(days=1)

    def list_huasheng_generation_counts_for_day(
        self,
        reference_time: datetime | None = None,
    ) -> dict[int, int]:
        start_time, end_time = self.resolve_day_time_range(reference_time)
        counts: dict[int, int] = {}
        with database.connection_context():
            query = HuashengGenerationRecord.select(HuashengGenerationRecord.account_id).where(
                HuashengGenerationRecord.generated_at >= start_time,
                HuashengGenerationRecord.generated_at < end_time,
            )
            for record in query:
                counts[int(record.account_id)] = counts.get(int(record.account_id), 0) + 1
        return counts

    def count_huasheng_generation_records_for_account_today(self, account_id: int) -> int:
        normalized_account_id = self.normalize_positive_int(account_id, field_name="account_id")
        return self.list_huasheng_generation_counts_for_day().get(normalized_account_id, 0)

    def list_huasheng_active_task_counts(self) -> dict[int, int]:
        active_statuses = (
            TASK_STATUS_HUASHENG_POLLING,
            TASK_STATUS_SUBTITLE_APPLYING,
            TASK_STATUS_EXPORT_RUNNING,
        )
        counts: dict[int, int] = {}
        with database.connection_context():
            query = TaskRecord.select(TaskRecord.account_id).where(
                TaskRecord.status.in_(active_statuses),
                TaskRecord.video_url == "",
            )
            for task in query:
                account_id = int(task.account_id or 0)
                if account_id <= 0:
                    continue
                counts[account_id] = counts.get(account_id, 0) + 1
        return counts

    def build_huasheng_generation_count_map(
        self,
        account_ids: list[int] | tuple[int, ...] | set[int],
        reference_time: datetime | None = None,
    ) -> dict[int, int]:
        normalized_account_ids = {
            self.normalize_positive_int(account_id, field_name="account_id")
            for account_id in account_ids
            if account_id
        }
        if not normalized_account_ids:
            return {}

        daily_counts = self.list_huasheng_generation_counts_for_day(reference_time)
        return {
            account_id: daily_counts.get(account_id, 0)
            for account_id in normalized_account_ids
        }

    def create_huasheng_generation_record(
        self,
        account_id: int,
        project_pid: str,
        *,
        generated_at: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_account_id = self.normalize_positive_int(account_id, field_name="account_id")
        normalized_project_pid = self.normalize_short_text(
            project_pid,
            field_name="project_pid",
            max_length=64,
        )
        timestamp = generated_at or now_local()
        with database.connection_context():
            record, created = HuashengGenerationRecord.get_or_create(
                project_pid=normalized_project_pid,
                defaults={
                    "account_id": normalized_account_id,
                    "generated_at": timestamp,
                },
            )
            if not created:
                record.account_id = normalized_account_id
                record.generated_at = timestamp
                record.save()
        return {
            "accountId": normalized_account_id,
            "projectPid": normalized_project_pid,
            "generatedAt": timestamp.isoformat(sep=" ", timespec="seconds"),
            "databasePath": str(self.db_path),
        }

    def extract_huasheng_response_code(self, payload: dict[str, Any] | None) -> int | None:
        if not isinstance(payload, dict):
            return None
        raw_code = payload.get("code")
        if raw_code in (None, ""):
            return None
        try:
            return int(raw_code)
        except (TypeError, ValueError):
            return None

    def build_huasheng_response_text(self, payload: dict[str, Any] | None) -> str:
        if not isinstance(payload, dict):
            return ""
        project = self.extract_project_payload(payload)
        parts: list[str] = []
        for field in ("reason", "message", "status", "loading_msg", "state_message"):
            for source in (payload, project):
                value = str(source.get(field) or "").strip()
                if value and value not in parts:
                    parts.append(value)
        return " ".join(parts).strip()

    def is_huasheng_daily_limit_reached_payload(
        self,
        payload: dict[str, Any] | None,
    ) -> bool:
        if self.extract_huasheng_response_code(payload) == HUASHENG_DAILY_LIMIT_REACHED_CODE:
            return True
        response_text = self.build_huasheng_response_text(payload)
        return bool(re.search(r"超量|上限|限额", response_text))

    def build_huasheng_create_error_detail(self, payload: dict[str, Any] | None) -> str:
        response_text = self.build_huasheng_response_text(payload)
        response_code = self.extract_huasheng_response_code(payload)
        if response_code is not None and response_text:
            return f"code={response_code} {response_text}"
        if response_code is not None:
            return f"code={response_code}"
        if response_text:
            return response_text
        if isinstance(payload, dict) and payload:
            return f"返回结构异常: {json.dumps(payload, ensure_ascii=False)[:200]}"
        return "接口返回了无效结果"

    def build_huasheng_generation_placeholder_project_pid(
        self,
        account_id: int,
        slot_index: int,
        *,
        reference_time: datetime | None = None,
    ) -> str:
        normalized_account_id = self.normalize_positive_int(account_id, field_name="account_id")
        normalized_slot_index = self.normalize_positive_int(slot_index, field_name="slot_index")
        timestamp = reference_time or now_local()
        return (
            f"{HUASHENG_GENERATION_PLACEHOLDER_PREFIX}-"
            f"{timestamp.strftime('%Y%m%d')}-"
            f"{normalized_account_id}-"
            f"{normalized_slot_index}"
        )

    def fill_huasheng_generation_placeholders_to_limit(
        self,
        account_id: int,
        *,
        current_count: int | None = None,
        reference_time: datetime | None = None,
    ) -> int:
        normalized_account_id = self.normalize_positive_int(account_id, field_name="account_id")
        if current_count is None:
            existing_count = self.count_huasheng_generation_records_for_account_today(
                normalized_account_id
            )
        else:
            existing_count = max(0, int(current_count))
        if existing_count >= HUASHENG_DAILY_PROJECT_LIMIT:
            return 0

        timestamp = reference_time or now_local()
        created_count = 0
        for slot_index in range(existing_count + 1, HUASHENG_DAILY_PROJECT_LIMIT + 1):
            placeholder_pid = self.build_huasheng_generation_placeholder_project_pid(
                normalized_account_id,
                slot_index,
                reference_time=timestamp,
            )
            self.create_huasheng_generation_record(
                normalized_account_id,
                placeholder_pid,
                generated_at=timestamp,
            )
            created_count += 1
        return created_count

    def list_huasheng_generation_candidate_accounts(self) -> list[tuple[Account, int, int]]:
        with database.connection_context():
            accounts = list(
                Account.select()
                .where(Account.is_disabled == False)
                .order_by(Account.id.asc())
            )
        if not accounts:
            raise ValueError("请先至少启用一个花生账号。")

        generation_counts = self.list_huasheng_generation_counts_for_day()
        active_task_counts = self.list_huasheng_active_task_counts()
        ranked_accounts = sorted(
            accounts,
            key=lambda account: (
                active_task_counts.get(int(account.id), 0),
                generation_counts.get(int(account.id), 0),
                int(account.id),
            ),
        )
        return [
            (
                account,
                generation_counts.get(int(account.id), 0),
                active_task_counts.get(int(account.id), 0),
            )
            for account in ranked_accounts
        ]

    def create_huasheng_project_with_available_account(
        self,
        *,
        name: str,
        script: str,
        voice_id: int,
        speech_rate: float,
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        normalized_name = self.normalize_text_field(
            name,
            field_name="项目名称",
            max_length=120,
        )
        normalized_script = self.normalize_required_text_field(
            script,
            field_name="项目文案",
            max_length=200000,
        )
        normalized_voice_id = self.normalize_positive_int(voice_id, field_name="voice_id")
        normalized_speech_rate = self.normalize_speech_rate(speech_rate)
        max_concurrent_tasks = int(
            self.load_huasheng_voice_settings_snapshot().get("maxConcurrentTasksPerAccount") or 1
        )

        with self._huasheng_account_selection_lock:
            candidate_accounts = self.list_huasheng_generation_candidate_accounts()
            errors: list[str] = []
            limit_reached_count = 0
            concurrency_reached_count = 0
            skipped_by_capacity_count = 0
            for account, used_count, active_task_count in candidate_accounts:
                if used_count >= HUASHENG_DAILY_PROJECT_LIMIT:
                    logger.debug(
                        "Huasheng account skipped because daily limit reached account_id=%s used=%s limit=%s",
                        account.id,
                        used_count,
                        HUASHENG_DAILY_PROJECT_LIMIT,
                    )
                    errors.append(
                        f"{account.phone} 今日已生成 {used_count}/{HUASHENG_DAILY_PROJECT_LIMIT} 条"
                    )
                    skipped_by_capacity_count += 1
                    continue

                if active_task_count >= max_concurrent_tasks:
                    logger.debug(
                        "Huasheng account skipped because concurrent task limit reached account_id=%s active=%s limit=%s",
                        account.id,
                        active_task_count,
                        max_concurrent_tasks,
                    )
                    concurrency_reached_count += 1
                    skipped_by_capacity_count += 1
                    continue

                account_snapshot = self.build_account_snapshot(account)
                cookies = str(account_snapshot["cookies"] or "").strip()
                if not cookies:
                    logger.warning(
                        "Huasheng account skipped because cookies are empty account_id=%s phone=%s",
                        account.id,
                        account.phone,
                    )
                    errors.append(f"{account.phone} cookies 为空")
                    continue

                try:
                    self._huasheng.get_tts_voices(
                        cookies,
                        pn=1,
                        ps=1,
                        category_id=0,
                    )
                except Exception as exc:
                    logger.warning(
                        "Huasheng account unavailable account_id=%s phone=%s error=%s",
                        account.id,
                        account.phone,
                        exc,
                    )
                    errors.append(f"{account.phone} 不可用: {exc}")
                    continue

                try:
                    payload = self._huasheng.create_project(
                        cookies,
                        name=normalized_name,
                        script=normalized_script,
                        voice_id=normalized_voice_id,
                        speech_rate=normalized_speech_rate,
                        is_agree=1,
                    )
                except Exception as exc:
                    logger.warning(
                        "Huasheng account create-project failed account_id=%s phone=%s error=%s",
                        account.id,
                        account.phone,
                        exc,
                    )
                    errors.append(f"{account.phone} 创建失败: {exc}")
                    continue

                if self.is_huasheng_daily_limit_reached_payload(payload):
                    placeholders_added = self.fill_huasheng_generation_placeholders_to_limit(
                        int(account.id),
                        current_count=used_count,
                    )
                    logger.warning(
                        "Huasheng account quota reached during create-project account_id=%s phone=%s used_before=%s placeholders_added=%s",
                        account.id,
                        account.phone,
                        used_count,
                        placeholders_added,
                    )
                    errors.append(
                        f"{account.phone} 今日已生成 {HUASHENG_DAILY_PROJECT_LIMIT}/{HUASHENG_DAILY_PROJECT_LIMIT} 条"
                    )
                    limit_reached_count += 1
                    continue

                try:
                    project_identifier = self.resolve_created_project_identifier(payload)
                except ValueError:
                    error_detail = self.build_huasheng_create_error_detail(payload)
                    logger.warning(
                        "Huasheng account create-project returned invalid payload account_id=%s phone=%s detail=%s",
                        account.id,
                        account.phone,
                        error_detail,
                    )
                    errors.append(f"{account.phone} 创建失败: {error_detail}")
                    continue
                self.create_huasheng_generation_record(
                    int(account.id),
                    project_identifier,
                )
                account_snapshot["usedTodayCount"] = used_count + 1
                account_snapshot["remainingTodayCount"] = max(
                    0,
                    HUASHENG_DAILY_PROJECT_LIMIT - (used_count + 1),
                )
                return account_snapshot, payload, project_identifier

        if candidate_accounts and skipped_by_capacity_count == len(candidate_accounts):
            if concurrency_reached_count:
                raise HuashengCreateRetryRequired(
                    TASK_HUASHENG_STATUS_WAIT_FOR_AVAILABLE_ACCOUNT
                )
            if limit_reached_count:
                raise HuashengCreateRetryRequired(TASK_HUASHENG_STATUS_ACCOUNT_RETRY)

        error_message = "；".join(errors[:5]).strip()
        if error_message:
            raise RuntimeError(f"没有可用的花生账号: {error_message}")
        raise RuntimeError("没有可用的花生账号。")

    def build_task_article_preview_map(
        self,
        tasks: list[TaskRecord],
    ) -> dict[int, str]:
        preview_map: dict[int, str] = {
            int(task.article_id): str(task.article_content or "").strip()
            for task in tasks
            if task.article_id and str(task.article_content or "").strip()
        }
        article_ids = sorted(
            {
                int(task.article_id)
                for task in tasks
                if task.article_id and int(task.article_id) not in preview_map
            }
        )
        if not article_ids:
            return preview_map
        if not database.table_exists(MonitoredArticle._meta.table_name):
            return preview_map

        query = MonitoredArticle.select(
            MonitoredArticle.id,
            MonitoredArticle.content,
            MonitoredArticle.title,
        ).where(MonitoredArticle.id.in_(article_ids))
        for article in query:
            preview_map[article.id] = str(article.content or article.title or "").strip()
        return preview_map

    def delete_monitored_articles_by_ids(
        self,
        article_ids: list[int] | tuple[int, ...],
        *,
        timestamp: datetime | None = None,
    ) -> int:
        del timestamp
        normalized_article_ids = self.normalize_positive_int_list(
            article_ids,
            field_name="article_ids",
        )
        if not normalized_article_ids:
            return 0
        if not database.table_exists(MonitoredArticle._meta.table_name):
            return 0
        delete_query = MonitoredArticle.delete().where(
            MonitoredArticle.id.in_(normalized_article_ids)
        )
        if database.is_closed():
            with database.connection_context():
                return int(delete_query.execute() or 0)
        return int(delete_query.execute() or 0)

    def _ensure_task_record_schema(self) -> None:
        table_name = TaskRecord._meta.table_name
        existing_columns = {
            row[1]
            for row in database.execute_sql(f'PRAGMA table_info("{table_name}")').fetchall()
        }
        if "project_id" in existing_columns:
            self._migrate_task_record_table_remove_project_id()
            existing_columns = {
                row[1]
                for row in database.execute_sql(f'PRAGMA table_info("{table_name}")').fetchall()
            }

        column_definitions = {
            "account_phone": '"account_phone" TEXT NOT NULL DEFAULT \'\'',
            "account_note": '"account_note" TEXT NOT NULL DEFAULT \'\'',
            "account_cookies": '"account_cookies" TEXT NOT NULL DEFAULT \'\'',
            "generation_provider": '"generation_provider" TEXT NOT NULL DEFAULT \'huasheng\'',
            "article_id": '"article_id" INTEGER',
            "article_content": '"article_content" TEXT NOT NULL DEFAULT \'\'',
            "rewritten_content": '"rewritten_content" TEXT NOT NULL DEFAULT \'\'',
            "title": '"title" TEXT NOT NULL DEFAULT \'\'',
            "rewrite_prompt_id": '"rewrite_prompt_id" INTEGER',
            "rewrite_prompt": '"rewrite_prompt" TEXT NOT NULL DEFAULT \'\'',
            "progress": '"progress" INTEGER NOT NULL DEFAULT 0',
            "huasheng_status": '"huasheng_status" TEXT NOT NULL DEFAULT \'\'',
            "video_url": '"video_url" TEXT NOT NULL DEFAULT \'\'',
            "export_task_id": '"export_task_id" TEXT NOT NULL DEFAULT \'\'',
            "export_version": '"export_version" TEXT NOT NULL DEFAULT \'\'',
        }
        for column_name, column_sql in column_definitions.items():
            if column_name in existing_columns:
                continue
            database.execute_sql(f'ALTER TABLE "{table_name}" ADD COLUMN {column_sql}')

        database.execute_sql(
            f'CREATE INDEX IF NOT EXISTS "{table_name}_article_id_idx" ON "{table_name}" ("article_id")'
        )
        database.execute_sql(
            f'CREATE INDEX IF NOT EXISTS "{table_name}_project_pid_idx" ON "{table_name}" ("project_pid")'
        )

    def _migrate_task_record_table_remove_project_id(self) -> None:
        table_name = TaskRecord._meta.table_name
        temp_table_name = f"{table_name}__migrated"
        logger.info('Migrating "%s" table to remove project_id column', table_name)
        database.execute_sql(f'DROP TABLE IF EXISTS "{temp_table_name}"')
        database.execute_sql(
            f'''
            CREATE TABLE "{temp_table_name}" (
              "id" INTEGER NOT NULL PRIMARY KEY,
              "account_id" INTEGER NOT NULL,
              "account_phone" TEXT NOT NULL DEFAULT '',
              "account_note" TEXT NOT NULL DEFAULT '',
              "account_cookies" TEXT NOT NULL DEFAULT '',
              "generation_provider" TEXT NOT NULL DEFAULT 'huasheng',
              "project_pid" VARCHAR(64) NOT NULL DEFAULT '',
              "article_id" INTEGER,
              "article_content" TEXT NOT NULL DEFAULT '',
              "rewritten_content" TEXT NOT NULL DEFAULT '',
              "title" TEXT NOT NULL DEFAULT '',
              "rewrite_prompt_id" INTEGER,
              "rewrite_prompt" TEXT NOT NULL DEFAULT '',
              "progress" INTEGER NOT NULL DEFAULT 0,
              "status" VARCHAR(64) NOT NULL,
              "huasheng_status" TEXT NOT NULL DEFAULT '',
              "video_url" TEXT NOT NULL DEFAULT '',
              "export_task_id" TEXT NOT NULL DEFAULT '',
              "export_version" TEXT NOT NULL DEFAULT '',
              "created_at" DATETIME NOT NULL,
              "updated_at" DATETIME NOT NULL
            )
            '''
        )
        database.execute_sql(
            f'''
            INSERT INTO "{temp_table_name}" (
              "id",
              "account_id",
              "account_phone",
              "account_note",
              "account_cookies",
              "generation_provider",
              "project_pid",
              "article_id",
              "article_content",
              "rewritten_content",
              "title",
              "rewrite_prompt_id",
              "rewrite_prompt",
              "progress",
              "status",
              "huasheng_status",
              "video_url",
              "export_task_id",
              "export_version",
              "created_at",
              "updated_at"
            )
            SELECT
              "id",
              "account_id",
              COALESCE("account_phone", ''),
              COALESCE("account_note", ''),
              COALESCE("account_cookies", ''),
              'huasheng',
              CASE
                WHEN TRIM(COALESCE("project_pid", '')) IN ('', '0') THEN ''
                ELSE TRIM("project_pid")
              END,
              "article_id",
              '',
              COALESCE("rewritten_content", ''),
              COALESCE("title", ''),
              "rewrite_prompt_id",
              COALESCE("rewrite_prompt", ''),
              COALESCE("progress", 0),
              COALESCE("status", '待处理'),
              COALESCE("huasheng_status", ''),
              COALESCE("video_url", ''),
              COALESCE("export_task_id", ''),
              COALESCE("export_version", ''),
              "created_at",
              "updated_at"
            FROM "{table_name}"
            '''
        )
        database.execute_sql(f'DROP TABLE "{table_name}"')
        database.execute_sql(f'ALTER TABLE "{temp_table_name}" RENAME TO "{table_name}"')
        database.execute_sql(
            f'CREATE INDEX IF NOT EXISTS "{table_name}_account_id" ON "{table_name}" ("account_id")'
        )
        database.execute_sql(
            f'CREATE INDEX IF NOT EXISTS "{table_name}_article_id" ON "{table_name}" ("article_id")'
        )
        database.execute_sql(
            f'CREATE INDEX IF NOT EXISTS "{table_name}_project_pid_idx" ON "{table_name}" ("project_pid")'
        )

    def build_subtitle_settings_payload(
        self,
        settings: dict[str, Any],
        *,
        updated_at: datetime | None,
    ) -> dict[str, Any]:
        return {
            "settings": settings,
            "fontSizeOptions": list(SUBTITLE_FONT_SIZE_OPTIONS),
            "styleOptions": list(SUBTITLE_STYLE_OPTIONS),
            "databasePath": str(self.db_path),
            "updatedAt": (
                updated_at.isoformat(sep=" ", timespec="seconds") if updated_at else ""
            ),
        }

    def build_model_settings_payload(
        self,
        settings: dict[str, Any],
        prompts: list[RewritePrompt],
        *,
        updated_at: datetime | None,
    ) -> dict[str, Any]:
        return {
            "settings": settings,
            "prompts": [self.serialize_rewrite_prompt(prompt) for prompt in prompts],
            "promptCount": len(prompts),
            "databasePath": str(self.db_path),
            "updatedAt": (
                updated_at.isoformat(sep=" ", timespec="seconds") if updated_at else ""
            ),
        }

    def build_huasheng_voice_settings_payload(
        self,
        settings: dict[str, Any],
        *,
        updated_at: datetime | None,
    ) -> dict[str, Any]:
        return {
            "settings": settings,
            "databasePath": str(self.db_path),
            "updatedAt": (
                updated_at.isoformat(sep=" ", timespec="seconds") if updated_at else ""
            ),
        }

    def build_global_settings_payload(
        self,
        settings: dict[str, Any],
        *,
        updated_at: datetime | None,
    ) -> dict[str, Any]:
        return {
            "settings": settings,
            "scanIntervalSeconds": TASK_QUEUE_SCAN_INTERVAL_SECONDS,
            "threadPoolMinSize": TASK_THREAD_POOL_MIN_SIZE,
            "threadPoolMaxSize": TASK_THREAD_POOL_MAX_SIZE,
            "executorThreadPoolMaxSize": TASK_EXECUTOR_THREAD_POOL_MAX_SIZE,
            "processorRunning": self.is_task_processor_running(),
            "databasePath": str(self.db_path),
            "updatedAt": (
                updated_at.isoformat(sep=" ", timespec="seconds") if updated_at else ""
            ),
        }

    def build_autovideo_settings_payload(
        self,
        settings: dict[str, Any],
        *,
        updated_at: datetime | None,
    ) -> dict[str, Any]:
        return {
            "settings": settings,
            "voiceOptions": self._autovideo.list_voice_options(),
            "rateOptions": self._autovideo.list_rate_options(),
            "databasePath": str(self.db_path),
            "updatedAt": (
                updated_at.isoformat(sep=" ", timespec="seconds") if updated_at else ""
            ),
        }

    def default_subtitle_settings(self) -> dict[str, Any]:
        return self.normalize_subtitle_settings(
            {
                "fontSize": DEFAULT_SUBTITLE_FONT_SIZE,
                "styleId": DEFAULT_SUBTITLE_STYLE_ID,
            }
        )

    def default_model_settings(self) -> dict[str, Any]:
        return self.normalize_model_settings(DEFAULT_MODEL_SETTINGS)

    def default_global_settings(self) -> dict[str, Any]:
        return self.normalize_global_settings(DEFAULT_GLOBAL_SETTINGS)

    def default_huasheng_voice_settings(self) -> dict[str, Any]:
        return self.normalize_huasheng_voice_settings(DEFAULT_HUASHENG_VOICE_SETTINGS)

    def default_autovideo_settings(self) -> dict[str, Any]:
        return self.normalize_autovideo_settings(DEFAULT_AUTOVIDEO_SETTINGS)

    def deserialize_setting_value(self, raw_value: str) -> dict[str, Any]:
        normalized = str(raw_value or "").strip()
        if not normalized:
            return {}
        try:
            value = json.loads(normalized)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def normalize_subtitle_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        font_size = self.normalize_subtitle_font_size(settings.get("fontSize"))
        style = self.resolve_subtitle_style(
            settings.get("styleId"),
            font_color=settings.get("fontColor"),
            outline_color=settings.get("outlineColor"),
            outline_thick=settings.get("outlineThick"),
        )
        return {
            "fontSize": font_size,
            "styleId": style["id"],
            "fontColor": style["fontColor"],
            "outlineColor": style["outlineColor"],
            "outlineThick": style["outlineThick"],
        }

    def normalize_subtitle_font_size(self, value: Any) -> int:
        allowed_values = {item["value"] for item in SUBTITLE_FONT_SIZE_OPTIONS}
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = DEFAULT_SUBTITLE_FONT_SIZE

        if normalized not in allowed_values:
            return DEFAULT_SUBTITLE_FONT_SIZE
        return normalized

    def normalize_model_settings(self, settings: dict[str, Any]) -> dict[str, str]:
        return {
            "baseUrl": self.normalize_text_field(
                settings.get("baseUrl"),
                field_name="Base URL",
                max_length=1000,
            ),
            "apiKey": self.normalize_text_field(
                settings.get("apiKey"),
                field_name="API Key",
                max_length=4000,
            ),
            "model": self.normalize_text_field(
                settings.get("model"),
                field_name="Model",
                max_length=255,
            ),
            "titlePrompt": self.normalize_text_field(
                settings.get("titlePrompt"),
                field_name="标题提示词",
                max_length=20000,
            ),
        }

    def normalize_global_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        has_legacy_thread_pool_size = settings.get("threadPoolSize") is not None
        legacy_thread_pool_size = self.normalize_thread_pool_size(
            settings.get(
                "threadPoolSize",
                DEFAULT_GLOBAL_SETTINGS["rewriteThreadPoolSize"],
            )
        )
        rewrite_thread_pool_size = self.normalize_thread_pool_size(
            settings.get(
                "rewriteThreadPoolSize",
                legacy_thread_pool_size
                if has_legacy_thread_pool_size
                else DEFAULT_GLOBAL_SETTINGS["rewriteThreadPoolSize"],
            )
        )
        title_thread_pool_size = self.normalize_thread_pool_size(
            settings.get(
                "titleThreadPoolSize",
                legacy_thread_pool_size
                if has_legacy_thread_pool_size
                else DEFAULT_GLOBAL_SETTINGS["titleThreadPoolSize"],
            )
        )
        create_thread_pool_size = self.normalize_thread_pool_size(
            settings.get(
                "createThreadPoolSize",
                DEFAULT_GLOBAL_SETTINGS["createThreadPoolSize"],
            )
        )
        progress_thread_pool_size = self.normalize_thread_pool_size(
            settings.get(
                "progressThreadPoolSize",
                DEFAULT_GLOBAL_SETTINGS["progressThreadPoolSize"],
            )
        )
        return {
            "threadPoolSize": self.normalize_executor_thread_pool_size(
                rewrite_thread_pool_size
                + title_thread_pool_size
                + create_thread_pool_size
                + progress_thread_pool_size
            ),
            "downloadDir": self.normalize_download_directory(
                settings.get("downloadDir")
            ),
            "generationProvider": self.normalize_generation_provider(
                settings.get("generationProvider")
            ),
            "autoDownloadVideos": self.normalize_boolean_flag(
                settings.get("autoDownloadVideos"),
                default=bool(DEFAULT_GLOBAL_SETTINGS["autoDownloadVideos"]),
            ),
            "autoDeleteRedlineTasks": self.normalize_boolean_flag(
                settings.get("autoDeleteRedlineTasks"),
                default=bool(DEFAULT_GLOBAL_SETTINGS["autoDeleteRedlineTasks"]),
            ),
            "rewriteThreadPoolSize": rewrite_thread_pool_size,
            "titleThreadPoolSize": title_thread_pool_size,
            "createThreadPoolSize": create_thread_pool_size,
            "progressThreadPoolSize": progress_thread_pool_size,
        }

    def normalize_generation_provider(self, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == GENERATION_PROVIDER_AUTOVIDEO:
            return GENERATION_PROVIDER_AUTOVIDEO
        return GENERATION_PROVIDER_HUASHENG

    def get_current_generation_provider(self) -> str:
        return self.normalize_generation_provider(
            self.get_global_settings_payload()["settings"].get("generationProvider")
        )

    def normalize_thread_pool_size(self, value: Any) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = DEFAULT_GLOBAL_SETTINGS["threadPoolSize"]

        if normalized < TASK_THREAD_POOL_MIN_SIZE:
            return TASK_THREAD_POOL_MIN_SIZE
        if normalized > TASK_THREAD_POOL_MAX_SIZE:
            return TASK_THREAD_POOL_MAX_SIZE
        return normalized

    def normalize_executor_thread_pool_size(self, value: Any) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = DEFAULT_GLOBAL_SETTINGS["threadPoolSize"]

        if normalized < TASK_THREAD_POOL_MIN_SIZE:
            return TASK_THREAD_POOL_MIN_SIZE
        if normalized > TASK_EXECUTOR_THREAD_POOL_MAX_SIZE:
            return TASK_EXECUTOR_THREAD_POOL_MAX_SIZE
        return normalized

    def normalize_download_directory(self, value: Any) -> str:
        normalized = self.normalize_text_field(
            value,
            field_name="默认下载路径",
            max_length=4000,
        )
        if not normalized:
            return ""

        path = Path(normalized).expanduser()
        try:
            resolved_path = path.resolve()
        except OSError as exc:
            raise ValueError(f"默认下载路径无效: {exc}") from exc

        if resolved_path.exists() and not resolved_path.is_dir():
            raise ValueError("默认下载路径必须是文件夹。")
        return str(resolved_path)

    def normalize_boolean_flag(self, value: Any, *, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)

        normalized = str(value).strip().lower()
        if not normalized:
            return default
        if normalized in {"1", "true", "yes", "y", "on", "是", "开", "开启"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "否", "关", "关闭"}:
            return False
        return default

    def normalize_huasheng_voice_settings(
        self,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "voiceId": self.normalize_optional_positive_int(settings.get("voiceId")),
            "voiceName": self.normalize_text_field(
                settings.get("voiceName"),
                field_name="音色名称",
                max_length=255,
            ),
            "voiceCode": self.normalize_text_field(
                settings.get("voiceCode"),
                field_name="音色编码",
                max_length=255,
            ),
            "voiceTags": self.normalize_text_field(
                settings.get("voiceTags"),
                field_name="音色标签",
                max_length=1000,
            ),
            "previewUrl": self.normalize_text_field(
                settings.get("previewUrl"),
                field_name="试听地址",
                max_length=4000,
            ),
            "cover": self.normalize_text_field(
                settings.get("cover"),
                field_name="封面地址",
                max_length=4000,
            ),
            "speechRate": self.normalize_speech_rate(settings.get("speechRate")),
            "maxConcurrentTasksPerAccount": self.normalize_huasheng_max_concurrent_tasks(
                settings.get("maxConcurrentTasksPerAccount")
            ),
        }

    def normalize_autovideo_settings(
        self,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        voice_choice = self._autovideo.normalize_voice_choice(settings.get("voiceChoice"))
        rate_choice = self._autovideo.normalize_rate_choice(settings.get("rateChoice"))
        return {
            "voiceChoice": voice_choice,
            "voiceLabel": self._autovideo.resolve_voice_label(voice_choice),
            "rateChoice": rate_choice,
            "rateLabel": self._autovideo.resolve_rate_label(rate_choice),
        }

    def normalize_huasheng_max_concurrent_tasks(self, value: Any) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = int(DEFAULT_HUASHENG_VOICE_SETTINGS["maxConcurrentTasksPerAccount"])

        if normalized < HUASHENG_ACCOUNT_MAX_CONCURRENT_TASKS_MIN:
            return HUASHENG_ACCOUNT_MAX_CONCURRENT_TASKS_MIN
        if normalized > HUASHENG_ACCOUNT_MAX_CONCURRENT_TASKS_MAX:
            return HUASHENG_ACCOUNT_MAX_CONCURRENT_TASKS_MAX
        return normalized

    def normalize_text_field(
        self,
        value: Any,
        *,
        field_name: str,
        max_length: int,
    ) -> str:
        normalized = str(value or "").strip()
        if len(normalized) > max_length:
            raise ValueError(f"{field_name} 长度不能超过 {max_length} 个字符。")
        return normalized

    def normalize_optional_positive_int(self, value: Any) -> int:
        if value is None or value == "" or value == 0 or value == "0":
            return 0
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return 0
        return normalized if normalized > 0 else 0

    def normalize_task_account_id(self, value: Any) -> int:
        if value is None or value == "" or value == 0 or value == "0":
            return 0
        return self.normalize_positive_int(value, field_name="account_id")

    def normalize_positive_int_list(
        self,
        values: list[Any] | tuple[Any, ...],
        *,
        field_name: str,
    ) -> list[int]:
        if not isinstance(values, (list, tuple)):
            raise ValueError(f"{field_name} 必须是列表。")

        normalized_values: list[int] = []
        seen: set[int] = set()
        for value in values:
            normalized = self.normalize_positive_int(value, field_name=field_name)
            if normalized in seen:
                continue
            seen.add(normalized)
            normalized_values.append(normalized)
        return normalized_values

    def normalize_task_progress(self, value: Any) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = 0

        if normalized < 0:
            return 0
        if normalized > 100:
            return 100
        return normalized

    def normalize_speech_rate(self, value: Any) -> float:
        try:
            normalized = float(value)
        except (TypeError, ValueError):
            normalized = 1.0

        if normalized < 0.5 or normalized > 2:
            normalized = 1.0

        return round(normalized, 1)

    def normalize_required_text_field(
        self,
        value: Any,
        *,
        field_name: str,
        max_length: int,
    ) -> str:
        normalized = self.normalize_text_field(
            value,
            field_name=field_name,
            max_length=max_length,
        )
        if not normalized:
            raise ValueError(f"{field_name} 不能为空。")
        return normalized

    def resolve_log_directory_path(self) -> Path:
        log_directory = resolve_log_directory_from_db_path(self.db_path)
        log_directory.mkdir(parents=True, exist_ok=True)
        return log_directory.resolve()

    def list_log_file_paths(self, log_dir: Path | None = None) -> list[Path]:
        target_dir = (log_dir or self.resolve_log_directory_path()).resolve()
        if not target_dir.exists():
            return []

        def sort_key(path: Path) -> float:
            try:
                return float(path.stat().st_mtime)
            except OSError:
                return 0.0

        return sorted(
            (
                path
                for path in target_dir.glob("*.log")
                if path.is_file()
            ),
            key=sort_key,
            reverse=True,
        )

    def resolve_download_directory_path(self) -> Path:
        settings = self.get_global_settings_payload()["settings"]
        normalized = str(settings.get("downloadDir") or "").strip()
        if not normalized:
            raise ValueError("请先在全局设置中选择默认下载路径。")

        directory = Path(normalized).expanduser()
        try:
            resolved_directory = directory.resolve()
        except OSError as exc:
            raise ValueError(f"默认下载路径无效: {exc}") from exc

        if resolved_directory.exists() and not resolved_directory.is_dir():
            raise ValueError("默认下载路径必须是文件夹。")
        resolved_directory.mkdir(parents=True, exist_ok=True)
        return resolved_directory

    def resolve_video_download_suffix(self, video_url: str) -> str:
        parsed = urlparse(str(video_url or "").strip())
        suffix = Path(parsed.path).suffix.strip()
        if not suffix:
            return ".mp4"
        if len(suffix) > 10 or not re.fullmatch(r"\.[A-Za-z0-9]+", suffix):
            return ".mp4"
        return suffix.lower()

    def sanitize_download_filename_stem(self, value: Any, *, fallback: str) -> str:
        normalized = str(value or "").strip()
        normalized = INVALID_FILENAME_CHARS_PATTERN.sub(" ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip(" ._-")
        if not normalized:
            normalized = fallback
        return normalized[:120].rstrip(" ._-") or fallback

    def build_task_video_download_filename(self, task: TaskRecord) -> str:
        suffix = self.resolve_video_download_suffix(task.video_url)
        fallback = f"task-{task.id}"
        stem = self.sanitize_download_filename_stem(task.title, fallback=fallback)
        max_stem_length = max(1, 180 - len(suffix))
        stem = stem[:max_stem_length].rstrip(" ._-") or fallback
        return f"{stem}{suffix}"

    def resolve_unique_download_path(self, directory: Path, filename: str) -> Path:
        candidate = directory / filename
        if not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix
        index = 2
        while True:
            next_candidate = directory / f"{stem}-{index}{suffix}"
            if not next_candidate.exists():
                return next_candidate
            index += 1

    def _download_video_to_path(
        self,
        video_url: str,
        target_path: Path,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        task_id: int | None = None,
    ) -> None:
        request = Request(
            str(video_url),
            headers={
                "Accept": "*/*",
                "User-Agent": MODEL_REQUEST_USER_AGENT,
            },
            method="GET",
        )
        with urlopen(request, timeout=VIDEO_DOWNLOAD_TIMEOUT) as response:
            total_bytes = self._parse_download_content_length(
                getattr(response, "headers", None)
            )
            downloaded_bytes = 0
            last_reported_progress = -1
            if progress_callback is not None:
                progress_callback(
                    {
                        "taskId": int(task_id or 0),
                        "downloadedBytes": 0,
                        "totalBytes": total_bytes,
                        "progressPercent": 0 if total_bytes else None,
                    }
                )
            with target_path.open("wb") as output_file:
                while True:
                    chunk = response.read(VIDEO_DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    output_file.write(chunk)
                    downloaded_bytes += len(chunk)
                    if progress_callback is None:
                        continue
                    progress_percent = None
                    if total_bytes and total_bytes > 0:
                        progress_percent = min(
                            99,
                            max(0, int(downloaded_bytes * 100 / total_bytes)),
                        )
                    if progress_percent is not None and progress_percent == last_reported_progress:
                        continue
                    last_reported_progress = (
                        progress_percent
                        if progress_percent is not None
                        else last_reported_progress
                    )
                    progress_callback(
                        {
                            "taskId": int(task_id or 0),
                            "downloadedBytes": downloaded_bytes,
                            "totalBytes": total_bytes,
                            "progressPercent": progress_percent,
                        }
                    )

        if not target_path.exists() or target_path.stat().st_size <= 0:
            raise RuntimeError("下载结果为空文件。")

    def _parse_download_content_length(self, headers: Any) -> int | None:
        if headers is None:
            return None
        raw_value = None
        try:
            raw_value = headers.get("Content-Length")
        except Exception:
            raw_value = None
        if raw_value in (None, ""):
            return None
        try:
            total_bytes = int(raw_value)
        except (TypeError, ValueError):
            return None
        return total_bytes if total_bytes > 0 else None

    def normalize_model_base_url(self, value: Any) -> str:
        normalized = self.normalize_required_text_field(
            value,
            field_name="Base URL",
            max_length=1000,
        ).rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Base URL 必须是有效的 http/https 地址。")
        if parsed.path.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"

    def normalize_rewrite_prompt_list(
        self,
        prompts: list[str] | tuple[str, ...] | None,
    ) -> list[str]:
        if prompts is None:
            return []
        if not isinstance(prompts, (list, tuple)):
            raise ValueError("改写提示词必须是列表。")

        normalized_items: list[str] = []
        for item in prompts:
            normalized = self.normalize_text_field(
                item,
                field_name="改写提示词",
                max_length=20000,
            )
            if normalized:
                normalized_items.append(normalized)
        return normalized_items

    def resolve_subtitle_style(
        self,
        style_id: Any,
        *,
        font_color: Any = None,
        outline_color: Any = None,
        outline_thick: Any = None,
    ) -> dict[str, Any]:
        normalized_style_id = str(style_id or "").strip()
        if normalized_style_id:
            for item in SUBTITLE_STYLE_OPTIONS:
                if item["id"] == normalized_style_id:
                    return dict(item)

        normalized_font_color = self.normalize_hex_color(font_color)
        normalized_outline_color = self.normalize_hex_color(outline_color)

        try:
            normalized_outline_thick = int(outline_thick)
        except (TypeError, ValueError):
            normalized_outline_thick = None

        if (
            normalized_font_color
            and normalized_outline_color
            and normalized_outline_thick is not None
        ):
            for item in SUBTITLE_STYLE_OPTIONS:
                if (
                    item["fontColor"] == normalized_font_color
                    and item["outlineColor"] == normalized_outline_color
                    and int(item["outlineThick"]) == normalized_outline_thick
                ):
                    return dict(item)

        for item in SUBTITLE_STYLE_OPTIONS:
            if item["id"] == DEFAULT_SUBTITLE_STYLE_ID:
                return dict(item)
        return dict(SUBTITLE_STYLE_OPTIONS[0])

    def normalize_hex_color(self, value: Any) -> str | None:
        normalized = str(value or "").strip().upper()
        if not normalized:
            return None
        if not HEX_COLOR_PATTERN.fullmatch(normalized):
            return None
        return normalized

    def serialize_rewrite_prompt(self, prompt: RewritePrompt) -> dict[str, Any]:
        return {
            "id": prompt.id,
            "content": prompt.content,
            "sortOrder": prompt.sort_order,
            "createdAt": prompt.created_at.isoformat(sep=" ", timespec="seconds"),
            "updatedAt": prompt.updated_at.isoformat(sep=" ", timespec="seconds"),
        }

    def _task_processor_loop(self) -> None:
        logger.info("Task processor scanner started")
        while not self._task_processor_stop_event.is_set():
            try:
                self.process_task_queue_once()
            except Exception:
                logger.exception("Task processor scan failed")
            if self._task_processor_stop_event.wait(TASK_QUEUE_SCAN_INTERVAL_SECONDS):
                break
        logger.info("Task processor scanner stopped")

    def _ensure_task_executor_locked(self, thread_pool_size: int) -> None:
        normalized_size = self.normalize_executor_thread_pool_size(thread_pool_size)
        if self._task_executor is not None and self._task_executor_size == normalized_size:
            return
        self._task_executor = ThreadPoolExecutor(
            max_workers=normalized_size,
            thread_name_prefix="huasheng-task",
        )
        self._task_executor_size = normalized_size
        logger.info("Task processor executor ready thread_pool_size=%s", normalized_size)

    def _get_inflight_set(self, stage: str) -> set[int]:
        if stage == TASK_STAGE_REWRITE:
            return self._rewrite_task_ids_inflight
        if stage == TASK_STAGE_TITLE:
            return self._title_task_ids_inflight
        if stage == TASK_STAGE_HUASHENG_CREATE:
            return self._huasheng_create_task_ids_inflight
        if stage == TASK_STAGE_HUASHENG_PROGRESS:
            return self._huasheng_progress_task_ids_inflight
        raise ValueError(f"未知任务阶段: {stage}")

    def _mark_task_inflight(self, task_id: int, *, stage: str) -> bool:
        with self._task_processor_state_lock:
            inflight = self._get_inflight_set(stage)
            if task_id in inflight:
                return False
            inflight.add(task_id)
            return True

    def _unmark_task_inflight(self, task_id: int, *, stage: str) -> None:
        with self._task_processor_state_lock:
            inflight = self._get_inflight_set(stage)
            inflight.discard(task_id)

    def _finalize_submitted_task(
        self,
        task_id: int,
        *,
        stage: str,
        future: Future[None],
    ) -> None:
        self._unmark_task_inflight(task_id, stage=stage)
        exception = future.exception()
        if exception is not None:
            if self._should_suppress_worker_failure_warning(stage=stage, error=exception):
                logger.debug(
                    "Task processor worker failure already logged task_id=%s stage=%s",
                    task_id,
                    stage,
                )
                return
            logger.warning(
                "Task processor worker failed task_id=%s stage=%s error=%s",
                task_id,
                stage,
                exception,
            )
            return

        logger.debug(
            "Task processor worker finished task_id=%s stage=%s",
            task_id,
            stage,
        )

    def _is_missing_task_error(self, error: Exception) -> bool:
        return isinstance(error, ValueError) and "任务不存在" in str(error)

    def _should_suppress_worker_failure_warning(self, *, stage: str, error: BaseException) -> bool:
        handled_stages = {
            TASK_STAGE_REWRITE,
            TASK_STAGE_TITLE,
            TASK_STAGE_HUASHENG_CREATE,
            TASK_STAGE_HUASHENG_PROGRESS,
        }
        return (
            stage in handled_stages
            and isinstance(error, RuntimeError)
            and getattr(error, "__cause__", None) is not None
        )

    def _run_stage_with_auto_retries(
        self,
        task_id: int,
        *,
        stage_label: str,
        runner: Callable[[], None],
    ) -> None:
        total_attempts = TASK_STAGE_MAX_RETRIES + 1
        for attempt in range(1, total_attempts + 1):
            try:
                runner()
                return
            except HuashengCreateRetryRequired:
                raise
            except NonRetryableTaskStageError:
                raise
            except Exception as exc:
                if self._is_missing_task_error(exc) or attempt >= total_attempts:
                    raise
                logger.warning(
                    "Task %s retry scheduled task_id=%s attempt=%s/%s error=%s",
                    stage_label,
                    task_id,
                    attempt,
                    total_attempts,
                    exc,
                )

    def _run_rewrite_task(self, task_id: int) -> None:
        def run_once() -> None:
            task = self.find_task_record(task_id)
            if task is None:
                logger.info("Task rewrite skipped because task was deleted task_id=%s", task_id)
                return
            if not task.article_id:
                raise ValueError("任务没有文章 ID，无法执行改写。")
            prompt_content = str(task.rewrite_prompt or "").strip()
            if not prompt_content:
                raise ValueError("任务没有改写提示词，无法执行改写。")

            model_settings = self.load_model_settings_snapshot()
            article_text = self.load_task_source_article_text(task)
            logger.info(
                "Task rewrite started task_id=%s article_id=%s prompt_id=%s prompt_length=%s article_length=%s",
                task_id,
                task.article_id,
                task.rewrite_prompt_id,
                len(prompt_content),
                len(article_text),
            )
            payload = self.rewrite_article_with_prompt(
                model_settings["baseUrl"],
                model_settings["apiKey"],
                model_settings["model"],
                prompt_content,
                article_text,
                prompt_id=task.rewrite_prompt_id,
                task_id=task_id,
            )
            if payload.get("triggeredRedline"):
                global_settings = self.get_global_settings_payload()["settings"]
                if bool(global_settings.get("autoDeleteRedlineTasks")):
                    self.delete_task_record(task_id)
                    logger.info(
                        "Task rewrite blocked by redline and deleted automatically task_id=%s",
                        task_id,
                    )
                    return
                try:
                    self.update_task_status(
                        task_id,
                        TASK_STATUS_REWRITE_REDLINE,
                        rewritten_content=str(payload.get("content") or ""),
                        huasheng_status=REWRITE_REDLINE_DISPLAY_TEXT,
                    )
                except Exception as status_error:
                    if self._is_missing_task_error(status_error):
                        logger.info(
                            "Task rewrite redline result discarded because task was deleted task_id=%s",
                            task_id,
                        )
                        return
                    raise
                logger.info("Task rewrite blocked by redline task_id=%s", task_id)
                return
            try:
                self.update_task_status(
                    task_id,
                    TASK_STATUS_REWRITE_READY,
                    rewritten_content=payload["content"],
                )
            except Exception as status_error:
                if self._is_missing_task_error(status_error):
                    logger.info(
                        "Task rewrite result discarded because task was deleted task_id=%s",
                        task_id,
                    )
                    return
                raise
            logger.info(
                "Task rewrite completed task_id=%s rewritten_length=%s next_status=%s",
                task_id,
                len(str(payload.get("content") or "")),
                TASK_STATUS_REWRITE_READY,
            )

        try:
            self._run_stage_with_auto_retries(
                task_id,
                stage_label="rewrite",
                runner=run_once,
            )
        except Exception as exc:
            if self._is_missing_task_error(exc):
                logger.info("Task rewrite stopped because task was deleted task_id=%s", task_id)
                return

            if isinstance(exc, NonRetryableTaskStageError):
                logger.warning("Task rewrite failed task_id=%s error=%s", task_id, exc)
            else:
                logger.exception("Task rewrite failed task_id=%s error=%s", task_id, exc)
            try:
                self.update_task_status(
                    task_id,
                    TASK_STATUS_REWRITE_FAILED,
                    huasheng_status=self._build_task_failure_detail(exc),
                )
            except Exception as status_error:
                if self._is_missing_task_error(status_error):
                    logger.info(
                        "Task rewrite failure status skipped because task was deleted task_id=%s",
                        task_id,
                    )
                    return
                raise
            raise RuntimeError(str(exc)) from exc

    def _run_title_task(self, task_id: int) -> None:
        def run_once() -> None:
            task = self.find_task_record(task_id)
            if task is None:
                logger.info("Task title skipped because task was deleted task_id=%s", task_id)
                return
            rewritten_content = str(task.rewritten_content or "").strip()
            if not rewritten_content:
                raise ValueError("任务还没有改写内容，无法生成标题。")

            model_settings = self.load_model_settings_snapshot()
            title_prompt = str(model_settings["titlePrompt"] or "").strip()
            if not title_prompt:
                raise ValueError("标题提示词为空，无法生成标题。")

            logger.info(
                "Task title started task_id=%s rewritten_length=%s title_prompt_length=%s",
                task_id,
                len(rewritten_content),
                len(title_prompt),
            )
            payload = self.generate_title(
                model_settings["baseUrl"],
                model_settings["apiKey"],
                model_settings["model"],
                title_prompt,
                rewritten_content,
            )
            next_status = self.get_task_ready_for_generation_status(task)
            try:
                self.update_task_status(
                    task_id,
                    next_status,
                    title=payload["title"],
                )
            except Exception as status_error:
                if self._is_missing_task_error(status_error):
                    logger.info(
                        "Task title result discarded because task was deleted task_id=%s",
                        task_id,
                    )
                    return
                raise
            logger.info(
                "Task title completed task_id=%s title_length=%s next_status=%s",
                task_id,
                len(str(payload.get("title") or "")),
                next_status,
            )

        try:
            self._run_stage_with_auto_retries(
                task_id,
                stage_label="title",
                runner=run_once,
            )
        except Exception as exc:
            if self._is_missing_task_error(exc):
                logger.info("Task title stopped because task was deleted task_id=%s", task_id)
                return

            if isinstance(exc, NonRetryableTaskStageError):
                logger.warning("Task title generation failed task_id=%s error=%s", task_id, exc)
            else:
                logger.exception("Task title generation failed task_id=%s error=%s", task_id, exc)
            try:
                self.update_task_status(
                    task_id,
                    TASK_STATUS_TITLE_FAILED,
                    huasheng_status=self._build_task_failure_detail(exc),
                )
            except Exception as status_error:
                if self._is_missing_task_error(status_error):
                    logger.info(
                        "Task title failure status skipped because task was deleted task_id=%s",
                        task_id,
                    )
                    return
                raise
            raise RuntimeError(str(exc)) from exc

    def _run_huasheng_create_task(self, task_id: int) -> None:
        def run_once() -> None:
            task = self.find_task_record(task_id)
            if task is None:
                logger.info("Task huasheng-create skipped because task was deleted task_id=%s", task_id)
                return
            if self.get_task_generation_provider(task) == GENERATION_PROVIDER_AUTOVIDEO:
                self._run_autovideo_create_task(task)
                return

            rewritten_content = str(task.rewritten_content or "").strip()
            title = str(task.title or "").strip()
            if not rewritten_content:
                raise ValueError("任务还没有改写内容，无法创建花生任务。")
            if not title:
                raise ValueError("任务还没有标题，无法创建花生任务。")

            voice_settings = self.load_huasheng_voice_settings_snapshot()
            voice_id = int(voice_settings.get("voiceId") or 0)
            if voice_id <= 0:
                raise ValueError("请先在设置中保存默认音色。")

            project_name = self.normalize_text_field(
                title[:120],
                field_name="项目名称",
                max_length=120,
            )
            logger.info(
                "Task huasheng-create started task_id=%s voice_id=%s speech_rate=%s title_length=%s content_length=%s",
                task_id,
                voice_id,
                voice_settings["speechRate"],
                len(title),
                len(rewritten_content),
            )
            account_snapshot, payload, project_identifier = (
                self.create_huasheng_project_with_available_account(
                    name=project_name,
                    script=rewritten_content,
                    voice_id=voice_id,
                    speech_rate=voice_settings["speechRate"],
                )
            )

            try:
                self.update_task_status(
                    task_id,
                    TASK_STATUS_HUASHENG_POLLING,
                    project_identifier,
                    progress=0,
                    huasheng_status=TASK_HUASHENG_STATUS_CREATED,
                    account_id=account_snapshot["accountId"],
                    account_phone=account_snapshot["phone"],
                    account_note=account_snapshot["note"],
                    account_cookies=account_snapshot["cookies"],
                    export_task_id="",
                    export_version="",
                )
            except Exception as status_error:
                if self._is_missing_task_error(status_error):
                    logger.info(
                        "Task huasheng-create result discarded because task was deleted task_id=%s",
                        task_id,
                    )
                    return
                raise
            logger.info(
                "Task huasheng-create completed task_id=%s account_id=%s phone=%s project_identifier=%s used_today=%s remaining_today=%s",
                task_id,
                account_snapshot["accountId"],
                account_snapshot["phone"],
                project_identifier,
                account_snapshot.get("usedTodayCount", 0),
                account_snapshot.get("remainingTodayCount", HUASHENG_DAILY_PROJECT_LIMIT),
            )

        try:
            self._run_stage_with_auto_retries(
                task_id,
                stage_label="huasheng-create",
                runner=run_once,
            )
        except HuashengCreateRetryRequired as exc:
            logger.info(
                "Task huasheng-create requeued task_id=%s reason=%s",
                task_id,
                exc,
            )
            try:
                self.update_task_status(
                    task_id,
                    TASK_STATUS_READY_FOR_HUASHENG,
                    huasheng_status=(
                        str(exc)[:128] if str(exc).strip() else TASK_HUASHENG_STATUS_ACCOUNT_RETRY
                    ),
                )
            except Exception as status_error:
                if self._is_missing_task_error(status_error):
                    logger.info(
                        "Task huasheng-create requeue skipped because task was deleted task_id=%s",
                        task_id,
                    )
                    return
                raise
        except Exception as exc:
            if self._is_missing_task_error(exc):
                logger.info("Task huasheng-create stopped because task was deleted task_id=%s", task_id)
                return

            logger.exception("Task huasheng-create failed task_id=%s error=%s", task_id, exc)
            try:
                self.update_task_status(
                    task_id,
                    TASK_STATUS_HUASHENG_CREATE_FAILED,
                    huasheng_status=str(exc)[:128] if str(exc).strip() else "创建花生失败",
                )
            except Exception as status_error:
                if self._is_missing_task_error(status_error):
                    logger.info(
                        "Task huasheng-create failure status skipped because task was deleted task_id=%s",
                        task_id,
                    )
                    return
                raise
            raise RuntimeError(str(exc)) from exc

    def _run_autovideo_create_task(self, task: TaskRecord) -> None:
        rewritten_content = str(task.rewritten_content or "").strip()
        title = str(task.title or "").strip()
        if not rewritten_content:
            raise ValueError("任务还没有改写内容，无法生成视频。")
        if not title:
            raise ValueError("任务还没有标题，无法生成视频。")

        autovideo_settings = self.get_autovideo_settings_payload()["settings"]
        logger.info(
            "Task autovideo-create started task_id=%s voice_choice=%s rate_choice=%s title_length=%s content_length=%s",
            task.id,
            autovideo_settings["voiceChoice"],
            autovideo_settings["rateChoice"],
            len(title),
            len(rewritten_content),
        )
        payload = self._autovideo.generate_video(
            story_text=rewritten_content,
            voice_choice=autovideo_settings["voiceChoice"],
            rate_choice=autovideo_settings["rateChoice"],
        )
        try:
            self.update_task_status(
                int(task.id),
                TASK_STATUS_EXPORT_FINISHED,
                str(payload.get("eventId") or ""),
                progress=100,
                video_url=str(payload.get("viewUrl") or ""),
                huasheng_status=str(payload.get("statusMessage") or "AutoVideo 生成完成"),
                account_id=0,
                account_phone="",
                account_note="AutoVideo",
                account_cookies="",
                export_task_id="",
                export_version="",
            )
        except Exception as status_error:
            if self._is_missing_task_error(status_error):
                logger.info(
                    "Task autovideo-create result discarded because task was deleted task_id=%s",
                    task.id,
                )
                return
            raise
        logger.info(
            "Task autovideo-create completed task_id=%s event_id=%s has_video_url=%s",
            task.id,
            str(payload.get("eventId") or ""),
            bool(str(payload.get("viewUrl") or "").strip()),
        )

    def _run_huasheng_progress_task(self, task_id: int) -> None:
        def run_once() -> None:
            task = self.find_task_record(task_id)
            if task is None:
                logger.info("Task huasheng-progress skipped because task was deleted task_id=%s", task_id)
                return
            if str(task.video_url or "").strip():
                logger.debug(
                    "Task huasheng-progress skipped because task already has video url task_id=%s",
                    task_id,
                )
                return
            if str(task.status or "").strip() == TASK_STATUS_EXPORT_FINISHED:
                logger.debug(
                    "Task huasheng-progress skipped because task is already finished task_id=%s",
                    task_id,
                )
                return

            account_snapshot = self.ensure_task_account_snapshot(task)
            project_identifier = self.resolve_progress_query_identifier(task)
            project_payload = self._huasheng.get_project_info(
                account_snapshot["cookies"],
                pid=project_identifier,
            )
            project_identifier = self.resolve_project_identifier_from_progress_payload(
                project_payload,
                fallback=project_identifier,
            )

            if str(task.export_task_id or "").strip():
                export_task_id = str(task.export_task_id or "").strip()
                try:
                    project_numeric_id = self.resolve_project_numeric_id_from_progress_payload(
                        project_payload
                    )
                except ValueError:
                    wait_message = "导出已创建，等待项目数值ID"
                    self.update_task_status(
                        task_id,
                        TASK_STATUS_EXPORT_RUNNING,
                        project_identifier,
                        huasheng_status=wait_message,
                    )
                    logger.warning(
                        "Task huasheng-export waiting numeric project id task_id=%s project_identifier=%s export_task_id=%s",
                        task_id,
                        project_identifier,
                        export_task_id,
                    )
                    return
                logger.debug(
                    "Task huasheng-export polling task_id=%s project_identifier=%s export_task_id=%s",
                    task_id,
                    project_identifier,
                    export_task_id,
                )
                export_payload = self._huasheng.get_project_export_info(
                    account_snapshot["cookies"],
                    project_id=project_numeric_id,
                    task_id=export_task_id,
                )
                export_progress = self.parse_export_progress(export_payload)
                export_state_text = self.build_export_state_text(export_payload)
                export_url = self.extract_export_url(export_payload)
                effective_export_progress = 100 if export_url else export_progress
                next_status = (
                    TASK_STATUS_EXPORT_FINISHED
                    if self.is_export_finished(export_payload)
                    else TASK_STATUS_EXPORT_RUNNING
                )
                export_changed = (
                    int(task.progress or 0) != effective_export_progress
                    or str(task.status or "").strip() != next_status
                    or str(task.huasheng_status or "").strip() != export_state_text
                    or str(task.video_url or "").strip() != export_url
                )
                try:
                    self.update_task_status(
                        task_id,
                        next_status,
                        project_identifier,
                        progress=effective_export_progress,
                        video_url=export_url,
                        huasheng_status=export_state_text,
                    )
                except Exception as status_error:
                    if self._is_missing_task_error(status_error):
                        logger.info(
                            "Task huasheng-export result discarded because task was deleted task_id=%s",
                            task_id,
                        )
                        return
                    raise
                if export_changed:
                    logger.info(
                        "Task huasheng-export updated task_id=%s progress=%s status=%s has_video_url=%s",
                        task_id,
                        effective_export_progress,
                        next_status,
                        bool(export_url),
                    )
                return

            project_numeric_id: int | None = None
            logger.debug(
                "Task huasheng-project polling task_id=%s project_query_identifier=%s",
                task_id,
                project_identifier,
            )
            project_progress = self.parse_project_progress(project_payload)
            project_state_text = self.build_project_state_text(project_payload)
            if self.is_project_failed(project_payload):
                self.update_task_status(
                    task_id,
                    TASK_STATUS_EXPORT_FAILED,
                    project_identifier,
                    progress=project_progress,
                    huasheng_status=project_state_text,
                )
                logger.warning(
                    "Task huasheng-project failed task_id=%s state=%s",
                    task_id,
                    project_state_text,
                )
                return

            if not self.is_project_finished(project_payload):
                project_changed = (
                    int(task.progress or 0) != project_progress
                    or str(task.status or "").strip() != TASK_STATUS_HUASHENG_POLLING
                    or str(task.huasheng_status or "").strip() != project_state_text
                    or str(task.project_pid or "").strip() != project_identifier
                )
                self.update_task_status(
                    task_id,
                    TASK_STATUS_HUASHENG_POLLING,
                    project_identifier,
                    progress=project_progress,
                    huasheng_status=project_state_text,
                )
                if project_changed:
                    logger.info(
                        "Task huasheng-project pending task_id=%s progress=%s state=%s",
                        task_id,
                        project_progress,
                        project_state_text,
                    )
                return

            try:
                project_numeric_id = self.resolve_project_numeric_id_from_progress_payload(
                    project_payload
                )
            except ValueError:
                wait_message = "项目处理完成，等待项目数值ID"
                self.update_task_status(
                    task_id,
                    TASK_STATUS_HUASHENG_POLLING,
                    project_identifier,
                    progress=100,
                    huasheng_status=wait_message,
                )
                logger.warning(
                    "Task huasheng-project waiting numeric project id task_id=%s project_identifier=%s",
                    task_id,
                    project_identifier,
                )
                return

            subtitle_settings = self.load_subtitle_settings_snapshot()
            voice_settings = self.load_huasheng_voice_settings_snapshot()
            self.update_task_status(
                task_id,
                TASK_STATUS_SUBTITLE_APPLYING,
                project_identifier,
                progress=100,
                huasheng_status=project_state_text,
            )
            logger.info(
                "Task huasheng-project finished task_id=%s applying subtitle font_size=%s style_id=%s voice_id=%s speech_rate=%s",
                task_id,
                subtitle_settings["fontSize"],
                subtitle_settings["styleId"],
                voice_settings["voiceId"],
                voice_settings["speechRate"],
            )
            self._huasheng.edit_project(
                account_snapshot["cookies"],
                project_id=project_numeric_id,
                font_size=subtitle_settings["fontSize"],
                font_color=subtitle_settings["fontColor"],
                outline_color=subtitle_settings["outlineColor"],
                outline_thick=subtitle_settings["outlineThick"],
            )
            self._huasheng.edit_project_tts_settings(
                account_snapshot["cookies"],
                project_id=project_numeric_id,
                voice_id=int(voice_settings["voiceId"]),
                speech_rate=float(voice_settings["speechRate"]),
            )
            time.sleep(HUASHENG_PRE_EXPORT_EDIT_DELAY_SECONDS)
            export_payload = self._huasheng.export_project_video(
                account_snapshot["cookies"],
                project_id=project_numeric_id,
            )
            export_task_id = str(export_payload.get("task_id") or "").strip()
            export_version = str(export_payload.get("version") or "").strip()
            if not export_task_id:
                raise RuntimeError("导出任务创建失败: 接口未返回 task_id。")

            self.update_task_status(
                task_id,
                TASK_STATUS_EXPORT_RUNNING,
                project_identifier,
                progress=0,
                huasheng_status=TASK_HUASHENG_STATUS_EXPORT_READY,
                export_task_id=export_task_id,
                export_version=export_version,
            )
            export_info_payload = self._huasheng.get_project_export_info(
                account_snapshot["cookies"],
                project_id=project_numeric_id,
                task_id=export_task_id,
            )
            export_progress = self.parse_export_progress(export_info_payload)
            export_state_text = self.build_export_state_text(export_info_payload)
            export_url = self.extract_export_url(export_info_payload)
            effective_export_progress = 100 if export_url else export_progress
            next_status = (
                TASK_STATUS_EXPORT_FINISHED
                if self.is_export_finished(export_info_payload)
                else TASK_STATUS_EXPORT_RUNNING
            )
            self.update_task_status(
                task_id,
                next_status,
                project_identifier,
                progress=effective_export_progress,
                video_url=export_url,
                huasheng_status=export_state_text,
                export_task_id=export_task_id,
                export_version=export_version,
            )
            logger.info(
                "Task huasheng-export created task_id=%s export_task_id=%s export_version=%s progress=%s status=%s",
                task_id,
                export_task_id,
                export_version,
                effective_export_progress,
                next_status,
            )

        try:
            self._run_stage_with_auto_retries(
                task_id,
                stage_label="huasheng-progress",
                runner=run_once,
            )
        except Exception as exc:
            if self._is_missing_task_error(exc):
                logger.info("Task huasheng-progress stopped because task was deleted task_id=%s", task_id)
                return

            logger.exception("Task huasheng-progress failed task_id=%s error=%s", task_id, exc)
            try:
                task = self.find_task_record(task_id)
                project_identifier = None
                if task is not None:
                    project_identifier = (
                        self.extract_numeric_identifier(task.project_pid)
                        or str(task.project_pid or "").strip()
                    )
                self.update_task_status(
                    task_id,
                    TASK_STATUS_EXPORT_FAILED,
                    project_identifier,
                    huasheng_status=str(exc)[:128] if str(exc).strip() else "花生处理失败",
                )
            except Exception as status_error:
                if self._is_missing_task_error(status_error):
                    logger.info(
                        "Task huasheng-progress failure status skipped because task was deleted task_id=%s",
                        task_id,
                    )
                    return
                raise
            raise RuntimeError(str(exc)) from exc

    def _request_model_text(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str,
        user_content: str,
        action_name: str,
        timeout: float = MODEL_REQUEST_TIMEOUT,
        task_id: int | None = None,
    ) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        request = Request(
            base_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": self._build_model_authorization_header(api_key),
                "User-Agent": MODEL_REQUEST_USER_AGENT,
            },
            method="POST",
        )
        task_log_value = int(task_id) if int(task_id or 0) > 0 else "-"
        logger.info(
            "%s request task_id=%s url=%s model=%s timeout_seconds=%.1f system_prompt_length=%s article_length=%s",
            action_name,
            task_log_value,
            base_url,
            model,
            timeout,
            len(system_prompt),
            len(user_content),
        )
        if self._should_log_model_request_payload(action_name):
            logger.info(
                "%s request payload task_id=%s url=%s system_prompt=%s user_content=%s",
                action_name,
                task_log_value,
                base_url,
                self._summarize_model_text(system_prompt, limit=5000),
                self._summarize_model_text(user_content, limit=5000),
            )
        start_time = time.perf_counter()
        response_status: int | None = None
        try:
            with urlopen(request, timeout=timeout) as response:
                response_status = getattr(response, "status", None)
                raw_body = response.read()
        except HTTPError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            error_body = exc.read()
            error_message = self._extract_model_error_message(
                error_body,
                fallback=f"HTTP {exc.code} {exc.reason}",
            )
            logger.warning(
                "%s request failed task_id=%s url=%s status=%s reason=%s duration_ms=%.1f body_bytes=%s message=%s response_preview=%s",
                action_name,
                task_log_value,
                base_url,
                exc.code,
                exc.reason,
                duration_ms,
                len(error_body),
                error_message,
                self._summarize_model_raw_text(error_body),
            )
            raise RuntimeError(
                f"{action_name}失败: {error_message}"
            ) from exc
        except URLError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(
                "%s request failed task_id=%s url=%s reason=%s duration_ms=%.1f",
                action_name,
                task_log_value,
                base_url,
                exc.reason,
                duration_ms,
            )
            raise RuntimeError(f"{action_name}失败: {exc.reason}") from exc
        except OSError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(
                "%s request failed task_id=%s url=%s reason=%s duration_ms=%.1f",
                action_name,
                task_log_value,
                base_url,
                exc,
                duration_ms,
            )
            raise RuntimeError(f"{action_name}失败: {exc}") from exc

        duration_ms = (time.perf_counter() - start_time) * 1000
        try:
            response_payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning(
                "%s response decode failed task_id=%s url=%s status=%s duration_ms=%.1f body_bytes=%s response_preview=%s",
                action_name,
                task_log_value,
                base_url,
                response_status,
                duration_ms,
                len(raw_body),
                self._summarize_model_raw_text(raw_body),
            )
            raise RuntimeError(f"{action_name}失败: 模型接口返回不是有效 JSON。") from exc

        response_summary = self._describe_model_response_payload(response_payload)
        logger.info(
            "%s response received task_id=%s url=%s status=%s duration_ms=%.1f body_bytes=%s summary=%s",
            action_name,
            task_log_value,
            base_url,
            response_status,
            duration_ms,
            len(raw_body),
            response_summary,
        )
        if self._should_log_model_response_payload(action_name):
            logger.info(
                "%s response payload task_id=%s url=%s payload=%s",
                action_name,
                task_log_value,
                base_url,
                self._summarize_model_payload(response_payload, limit=5000),
            )

        try:
            text = self._extract_model_response_text(response_payload)
        except RuntimeError as exc:
            nonretryable_error = self._detect_nonretryable_model_response_error(
                response_payload,
                action_name=action_name,
            )
            translated_error: RuntimeError = nonretryable_error or exc
            logger.warning(
                "%s response parse failed task_id=%s url=%s status=%s duration_ms=%.1f reason=%s summary=%s payload=%s",
                action_name,
                task_log_value,
                base_url,
                response_status,
                duration_ms,
                translated_error,
                response_summary,
                self._summarize_model_payload(response_payload, limit=5000),
            )
            if nonretryable_error is not None:
                raise nonretryable_error from exc
            raise RuntimeError(f"{action_name}失败: {exc} ({response_summary})") from exc
        if not text:
            logger.warning(
                "%s response empty task_id=%s url=%s status=%s duration_ms=%.1f summary=%s payload=%s",
                action_name,
                task_log_value,
                base_url,
                response_status,
                duration_ms,
                response_summary,
                self._summarize_model_payload(response_payload, limit=5000),
            )
            raise RuntimeError(f"{action_name}失败: 模型接口返回为空。({response_summary})")
        if self._should_log_model_response_payload(action_name):
            logger.info(
                "%s response text task_id=%s url=%s text_length=%s text_preview=%s",
                action_name,
                task_log_value,
                base_url,
                len(text),
                self._summarize_model_text(text, limit=3000),
            )
        return text

    def _extract_model_response_text(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            raise RuntimeError("模型接口返回不是 JSON 对象。")

        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            if message:
                raise RuntimeError(message)

        output_text = self._normalize_model_text_content(payload.get("output_text"))
        if output_text:
            return output_text

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("模型接口返回中缺少 choices。")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise RuntimeError("模型接口返回的 choices[0] 结构不正确。")

        message = first_choice.get("message")
        if isinstance(message, dict):
            content = self._normalize_model_text_content(message.get("content"))
            if content:
                return content

        text = self._normalize_model_text_content(first_choice.get("text"))
        if text:
            return text

        raise RuntimeError("模型接口返回中缺少文本内容。")

    def _normalize_model_text_content(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()

        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    normalized = item.strip()
                    if normalized:
                        parts.append(normalized)
                    continue
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").strip()
                if item_type in {"text", "output_text"}:
                    normalized = str(item.get("text") or "").strip()
                    if normalized:
                        parts.append(normalized)
            return "\n".join(parts).strip()

        return ""

    def _describe_model_response_payload(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return f"type={type(payload).__name__}"

        parts: list[str] = []
        keys = sorted(str(key) for key in payload.keys())
        parts.append(f"keys={','.join(keys[:10]) or '-'}")

        response_id = str(payload.get("id") or "").strip()
        if response_id:
            parts.append(f"id={response_id[:80]}")

        model_name = str(payload.get("model") or "").strip()
        if model_name:
            parts.append(f"model={model_name[:80]}")

        if "output_text" in payload:
            parts.append(
                f"output_text={self._describe_model_value_shape(payload.get('output_text'))}"
            )

        usage = payload.get("usage")
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")
            if prompt_tokens is not None:
                parts.append(f"prompt_tokens={prompt_tokens}")
            if completion_tokens is not None:
                parts.append(f"completion_tokens={completion_tokens}")
            if total_tokens is not None:
                parts.append(f"total_tokens={total_tokens}")

        choices = payload.get("choices")
        if isinstance(choices, list):
            parts.append(f"choices={len(choices)}")
            if choices:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    choice_keys = sorted(str(key) for key in first_choice.keys())
                    parts.append(f"choice_keys={','.join(choice_keys[:10]) or '-'}")

                    finish_reason = str(first_choice.get("finish_reason") or "").strip()
                    if finish_reason:
                        parts.append(f"finish_reason={finish_reason}")

                    message = first_choice.get("message")
                    if isinstance(message, dict):
                        message_keys = sorted(str(key) for key in message.keys())
                        parts.append(f"message_keys={','.join(message_keys[:10]) or '-'}")
                        parts.append(
                            f"message_content={self._describe_model_value_shape(message.get('content'))}"
                        )
                    elif message is not None:
                        parts.append(f"message_type={type(message).__name__}")

                    if "text" in first_choice:
                        parts.append(
                            f"text={self._describe_model_value_shape(first_choice.get('text'))}"
                        )
                else:
                    parts.append(f"choice0_type={type(first_choice).__name__}")
        elif choices is not None:
            parts.append(f"choices_type={type(choices).__name__}")

        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            parts.append(f"message_length={len(message.strip())}")

        return " ".join(parts)

    def _describe_model_value_shape(self, value: Any) -> str:
        if value is None:
            return "none"
        if isinstance(value, str):
            return f"str[{len(value.strip())}]"
        if isinstance(value, list):
            text_items = sum(1 for item in value if isinstance(item, str) and item.strip())
            dict_items = sum(1 for item in value if isinstance(item, dict))
            return f"list[{len(value)}] text_items={text_items} dict_items={dict_items}"
        if isinstance(value, dict):
            keys = sorted(str(key) for key in value.keys())
            return f"dict[{','.join(keys[:6]) or '-'}]"
        return type(value).__name__

    def _summarize_model_payload(self, payload: Any, *, limit: int = 1500) -> str:
        try:
            if isinstance(payload, (dict, list)):
                text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            else:
                text = str(payload)
        except (TypeError, ValueError):
            text = repr(payload)
        text = " ".join(text.split())
        if not text:
            return "-"
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

    def _summarize_model_raw_text(self, raw_body: bytes, *, limit: int = 1200) -> str:
        text = raw_body.decode("utf-8", errors="replace")
        text = " ".join(text.split())
        if not text:
            return "-"
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

    def _summarize_model_text(self, text: str, *, limit: int = 3000) -> str:
        normalized = " ".join(str(text or "").split()).strip()
        if not normalized:
            return "-"
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[:limit]}..."

    def _should_log_model_request_payload(self, action_name: str) -> bool:
        return str(action_name or "").strip() == "模型连接测试"

    def _should_log_model_response_payload(self, action_name: str) -> bool:
        return str(action_name or "").strip() in {"文章改写", "模型连接测试"}

    def _detect_nonretryable_model_response_error(
        self,
        payload: Any,
        *,
        action_name: str,
    ) -> NonRetryableTaskStageError | None:
        if not isinstance(payload, dict):
            return None

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return None

        finish_reason = str(first_choice.get("finish_reason") or "").strip().lower()
        if finish_reason != "stop":
            return None

        message = first_choice.get("message")
        if not isinstance(message, dict):
            return None

        if self._normalize_model_text_content(message.get("content")):
            return None
        if self._normalize_model_text_content(first_choice.get("text")):
            return None
        if self._normalize_model_text_content(payload.get("output_text")):
            return None

        if action_name == "文章改写":
            return NonRetryableTaskStageError(
                "模型网关兼容异常：finish_reason=stop，但未返回正文内容。"
            )
        return NonRetryableTaskStageError(
            "模型网关兼容异常：finish_reason=stop，但未返回文本内容。"
        )

    def _build_task_failure_detail(self, error: Exception, *, limit: int = 120) -> str:
        text = str(error or "").strip()
        if not text:
            return "任务失败"

        for prefix in ("文章改写失败:", "标题生成失败:"):
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
                break

        summary_marker = " (keys="
        if summary_marker in text:
            text = text.split(summary_marker, 1)[0].strip()

        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

    def _extract_model_error_message(self, raw_body: bytes, *, fallback: str) -> str:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            text = raw_body.decode("utf-8", errors="ignore").strip()
            html_title = self._extract_html_error_title(text)
            if html_title:
                return f"{fallback}: {html_title}"
            compact = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()
            if compact:
                return f"{fallback}: {compact[:200]}"
            if text:
                return f"{fallback}: {text[:500]}"
            return fallback

        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, str):
                message = error.strip()
                if message:
                    return message
            if isinstance(error, dict):
                message = str(error.get("message") or "").strip()
                if message:
                    return message
            message = str(payload.get("message") or "").strip()
            if message:
                return message
        return fallback

    def _extract_html_error_title(self, text: str) -> str:
        match = HTML_TITLE_PATTERN.search(text)
        if not match:
            return ""
        title = html.unescape(match.group(1))
        return re.sub(r"\s+", " ", title).strip()

    def _strip_labeled_output(self, text: str, *, label: str) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""

        pattern = re.compile(
            LABELED_OUTPUT_PATTERN_TEMPLATE.format(label=re.escape(label)),
            re.IGNORECASE,
        )
        lines = normalized.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and pattern.fullmatch(lines[0].strip()):
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines.pop(0)
        return "\n".join(lines).strip()

    def _strip_markdown_code_fence(self, text: str) -> str:
        normalized = str(text or "").strip()
        if not normalized.startswith("```"):
            return normalized

        lines = normalized.splitlines()
        if not lines:
            return normalized

        first_line = lines[0].strip()
        if not first_line.startswith("```"):
            return normalized

        lines = lines[1:]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def _strip_rewrite_markdown_chars(self, text: str) -> str:
        normalized = str(text or "")
        normalized = normalized.replace("*", "").replace("#", "")
        normalized = "\n".join(line.strip() for line in normalized.splitlines())
        normalized = re.sub(r"[ \t]+\n", "\n", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    def _build_model_authorization_header(self, api_key: str) -> str:
        normalized = str(api_key or "").strip()
        if not normalized:
            raise ValueError("API Key 不能为空。")

        if normalized.lower().startswith("authorization:"):
            normalized = normalized.split(":", 1)[1].strip()

        if normalized.lower().startswith("bearer "):
            return normalized

        return f"Bearer {normalized}"
