from __future__ import annotations

import json
import logging
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Callable

import webview
from webview.menu import Menu, MenuAction, MenuSeparator

from app.accounts import AccountService
from app.config import APP_VERSION
from app.huasheng import HuaShengAutomation
from app.microheadline import MicroHeadlineService

logger = logging.getLogger(__name__)

DESKTOP_EVENT_NAME = "huashengai:desktop-event"


class DesktopBridge:
    def __init__(self, *, index_file: Path, default_title: str) -> None:
        self.index_file = index_file
        self.default_title = default_title
        self.started_at = datetime.now(UTC)
        self.window: webview.Window | None = None
        self._lock = Lock()
        self._event_id = 0
        self._last_action = "app.boot"
        self._messages: list[dict[str, Any]] = []
        self._pending_events: list[dict[str, Any]] = []

    def attach_window(self, window: webview.Window) -> None:
        self.window = window
        window.events._pywebviewready += self._on_pywebview_ready

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "title": self.window.title if self.window else self.default_title,
                "version": APP_VERSION,
                "lastAction": self._last_action,
                "messageCount": len(self._messages),
                "startedAt": self.started_at.isoformat(),
                "python": platform.python_version(),
                "system": platform.platform(),
            }

    def post_message(self, source: str, message: str) -> dict[str, Any]:
        normalized = message.strip() or "Empty message"

        with self._lock:
            entry = {
                "id": len(self._messages) + 1,
                "source": source,
                "message": normalized,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self._messages.append(entry)
            self._last_action = f"{source}.message"

        self.publish_event("backend.message", {"entry": entry, "state": self.snapshot()})
        return entry

    def set_window_title(self, title: str, *, source: str) -> str:
        normalized = title.strip() or self.default_title

        if self.window:
            self.window.set_title(normalized)

        with self._lock:
            self._last_action = f"{source}.set-window-title"

        self.publish_event(
            "backend.title-changed",
            {"title": normalized, "source": source, "state": self.snapshot()},
        )
        return normalized

    def emit_demo_event(self, topic: str, *, source: str) -> dict[str, Any]:
        with self._lock:
            self._last_action = f"{source}.emit-demo-event"

        event = self.publish_event(
            "backend.demo-event",
            {
                "topic": topic,
                "source": source,
                "state": self.snapshot(),
            },
        )
        return event

    def emit_system_info(self, *, source: str) -> dict[str, Any]:
        with self._lock:
            self._last_action = f"{source}.system-info"

        event = self.publish_event(
            "backend.system-info",
            {
                "source": source,
                "python": platform.python_version(),
                "system": platform.platform(),
                "state": self.snapshot(),
            },
        )
        return event

    def reload_frontend(self) -> None:
        if not self.window:
            return

        with self._lock:
            self._last_action = "menu.reload-frontend"

        self.window.load_url(self.index_file.as_uri())

    def minimize(self) -> None:
        if not self.window:
            return

        with self._lock:
            self._last_action = "menu.minimize"

        self.window.minimize()

    def restore(self) -> None:
        if not self.window:
            return

        with self._lock:
            self._last_action = "menu.restore"

        self.window.restore()
        self.publish_event("backend.window-restored", {"state": self.snapshot()})

    def toggle_fullscreen(self) -> None:
        if not self.window:
            return

        with self._lock:
            self._last_action = "menu.toggle-fullscreen"

        self.window.toggle_fullscreen()
        self.publish_event("backend.window-updated", {"state": self.snapshot()})

    def close_window(self) -> None:
        if not self.window:
            return
        self.window.destroy()

    def choose_directory(self, directory: str = "") -> str:
        if not self.window:
            raise RuntimeError("窗口尚未初始化，无法选择文件夹。")

        dialog_enum = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
        if dialog_enum is None:
            dialog_enum = webview.FOLDER_DIALOG

        result = self.window.create_file_dialog(
            dialog_type=dialog_enum,
            directory=str(directory or ""),
            allow_multiple=False,
        )
        if not result:
            return ""

        if isinstance(result, (list, tuple)):
            return str(result[0] or "")
        return str(result or "")

    def open_directory_in_file_manager(self, directory: str) -> str:
        resolved_directory = Path(str(directory or "")).expanduser().resolve()
        resolved_directory.mkdir(parents=True, exist_ok=True)

        if sys.platform == "darwin":
            command = ["open", str(resolved_directory)]
        elif sys.platform.startswith("win"):
            command = ["explorer", str(resolved_directory)]
        else:
            command = ["xdg-open", str(resolved_directory)]

        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            raise RuntimeError(f"打开文件夹失败: {exc}") from exc

        return str(resolved_directory)

    def publish_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "id": self._next_event_id(),
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if not self._dispatch_event(event):
            with self._lock:
                self._pending_events.append(event)

        return event

    def _dispatch_event(self, event: dict[str, Any]) -> bool:
        if not self.window or not self.window.events._pywebviewready.is_set():
            return False

        script = f"""
            window.dispatchEvent(
              new CustomEvent({json.dumps(DESKTOP_EVENT_NAME)}, {{
                detail: {json.dumps(event, ensure_ascii=True)}
              }})
            );
        """

        try:
            self.window.evaluate_js(script)
            return True
        except Exception:
            logger.exception("Failed to dispatch desktop event %s", event["type"])
            return False

    def _flush_pending_events(self) -> None:
        with self._lock:
            pending_events = list(self._pending_events)
            self._pending_events.clear()

        for index, event in enumerate(pending_events):
            if not self._dispatch_event(event):
                with self._lock:
                    self._pending_events[:0] = pending_events[index:]
                return

    def _next_event_id(self) -> int:
        with self._lock:
            self._event_id += 1
            return self._event_id

    def _on_pywebview_ready(self, window: webview.Window) -> None:
        self._flush_pending_events()
        self.publish_event("backend.ready", {"state": self.snapshot()})


class AppApi:
    def __init__(
        self,
        bridge: DesktopBridge,
        account_service: AccountService,
        huasheng: HuaShengAutomation | None = None,
        microheadline: MicroHeadlineService | None = None,
    ) -> None:
        self._bridge = bridge
        self._account_service = account_service
        self._huasheng = huasheng or HuaShengAutomation()
        self._microheadline = microheadline or MicroHeadlineService(account_service.db_path)
        self._download_task_ids_lock = Lock()
        self._download_task_ids_inflight: set[int] = set()

    def ping(self) -> dict[str, Any]:
        response = {
            "message": "PyWebView API is connected.",
            "python": platform.python_version(),
            "system": platform.platform(),
            "state": self._bridge.snapshot(),
        }
        self._bridge.publish_event("backend.ping", response)
        return response

    def get_app_state(self) -> dict[str, Any]:
        return self._bridge.snapshot()

    def post_message(self, message: str) -> dict[str, Any]:
        entry = self._bridge.post_message("frontend", str(message))
        return {"ok": True, "entry": entry, "state": self._bridge.snapshot()}

    def emit_demo_event(self, topic: str = "manual") -> dict[str, Any]:
        event = self._bridge.emit_demo_event(str(topic), source="frontend")
        return {"ok": True, "event": event, "state": self._bridge.snapshot()}

    def set_window_title(self, title: str) -> dict[str, Any]:
        normalized = self._bridge.set_window_title(str(title), source="frontend")
        return {"ok": True, "title": normalized, "state": self._bridge.snapshot()}

    def list_accounts(self) -> dict[str, Any]:
        return self._account_service.list_payload()

    def list_tasks(self) -> dict[str, Any]:
        return self._account_service.list_tasks_payload()

    def delete_all_task_records(self) -> dict[str, Any]:
        logger.info("AppApi.delete_all_task_records called")
        return self._account_service.delete_all_task_records()

    def delete_task_record(self, task_id: int) -> dict[str, Any]:
        logger.info("AppApi.delete_task_record called task_id=%s", task_id)
        return self._account_service.delete_task_record(task_id)

    def retry_task_record(self, task_id: int) -> dict[str, Any]:
        logger.info("AppApi.retry_task_record called task_id=%s", task_id)
        return self._account_service.retry_task_record(task_id)

    def download_task_video(self, task_id: int) -> dict[str, Any]:
        logger.info("AppApi.download_task_video called task_id=%s", task_id)
        return self._account_service.download_task_video(task_id)

    def start_download_task_video(self, task_id: int) -> dict[str, Any]:
        normalized_task_id = self._account_service.normalize_positive_int(
            task_id,
            field_name="task_id",
        )
        logger.info("AppApi.start_download_task_video called task_id=%s", normalized_task_id)

        with self._download_task_ids_lock:
            if normalized_task_id in self._download_task_ids_inflight:
                return {
                    "taskId": normalized_task_id,
                    "started": False,
                    "alreadyRunning": True,
                    "databasePath": str(self._account_service.db_path),
                }
            self._download_task_ids_inflight.add(normalized_task_id)

        self._bridge.publish_event(
            "tasks.download.started",
            {
                "taskId": normalized_task_id,
                "databasePath": str(self._account_service.db_path),
            },
        )
        Thread(
            target=self._run_task_video_download_worker,
            args=(normalized_task_id,),
            name=f"task-video-download-{normalized_task_id}",
            daemon=True,
        ).start()
        return {
            "taskId": normalized_task_id,
            "started": True,
            "alreadyRunning": False,
            "databasePath": str(self._account_service.db_path),
        }

    def _run_task_video_download_worker(self, task_id: int) -> None:
        try:
            payload = self._account_service.download_task_video(task_id)
        except Exception as exc:
            logger.warning(
                "AppApi.start_download_task_video worker failed task_id=%s error=%s",
                task_id,
                exc,
            )
            self._bridge.publish_event(
                "tasks.download.failed",
                {
                    "taskId": task_id,
                    "errorMessage": str(exc),
                    "databasePath": str(self._account_service.db_path),
                },
            )
        else:
            self._bridge.publish_event("tasks.download.finished", payload)
        finally:
            with self._download_task_ids_lock:
                self._download_task_ids_inflight.discard(task_id)


    def create_task_record(
        self,
        account_id: int,
        project_pid: str = "",
        status: str = "处理中",
        huasheng_status: str | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "AppApi.create_task_record called account_id=%s project_pid=%s status=%s huasheng_status=%s",
            account_id,
            project_pid,
            status,
            huasheng_status,
        )
        return self._account_service.create_task_record(
            account_id,
            str(project_pid),
            str(status),
            huasheng_status=None if huasheng_status is None else str(huasheng_status),
        )

    def update_task_status(
        self,
        task_id: int,
        status: str,
        project_pid: str | None = None,
        progress: int | None = None,
        video_url: str | None = None,
        rewritten_content: str | None = None,
        title: str | None = None,
        huasheng_status: str | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "AppApi.update_task_status called task_id=%s status=%s project_pid=%s progress=%s huasheng_status=%s",
            task_id,
            status,
            project_pid,
            progress,
            huasheng_status,
        )
        return self._account_service.update_task_status(
            task_id,
            str(status),
            None if project_pid is None else str(project_pid),
            progress=progress,
            video_url=None if video_url is None else str(video_url),
            rewritten_content=(
                None if rewritten_content is None else str(rewritten_content)
            ),
            title=None if title is None else str(title),
            huasheng_status=None if huasheng_status is None else str(huasheng_status),
        )

    def get_subtitle_settings(self) -> dict[str, Any]:
        return self._account_service.get_subtitle_settings_payload()

    def get_global_settings(self) -> dict[str, Any]:
        return self._account_service.get_global_settings_payload()

    def save_global_settings(
        self,
        thread_pool_size: int,
        download_dir: str | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "AppApi.save_global_settings called thread_pool_size=%s download_dir_length=%s",
            thread_pool_size,
            len(str(download_dir or "")),
        )
        return self._account_service.save_global_settings(
            thread_pool_size,
            None if download_dir is None else str(download_dir),
        )

    def get_log_status(self) -> dict[str, Any]:
        logger.info("AppApi.get_log_status called")
        return self._account_service.get_log_status_payload()

    def open_logs_directory(self) -> dict[str, Any]:
        log_dir = self._account_service.resolve_log_directory_path()
        logger.info("AppApi.open_logs_directory called log_dir=%s", log_dir)
        opened_path = self._bridge.open_directory_in_file_manager(str(log_dir))
        return {
            "openedPath": opened_path,
            "databasePath": str(self._account_service.db_path),
        }

    def select_download_directory(self, current_directory: str = "") -> dict[str, Any]:
        logger.info(
            "AppApi.select_download_directory called current_directory_length=%s",
            len(str(current_directory or "")),
        )
        selected_path = self._bridge.choose_directory(str(current_directory or ""))
        return {
            "selectedPath": selected_path,
            "cancelled": not bool(selected_path),
        }

    def save_subtitle_settings(self, font_size: int, style_id: str) -> dict[str, Any]:
        logger.info(
            "AppApi.save_subtitle_settings called font_size=%s style_id=%s",
            font_size,
            style_id,
        )
        return self._account_service.save_subtitle_settings(font_size, str(style_id))

    def get_huasheng_voice_settings(self) -> dict[str, Any]:
        return self._account_service.get_huasheng_voice_settings_payload()

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
        logger.info(
            "AppApi.save_huasheng_voice_settings called voice_id=%s voice_name_length=%s voice_code_length=%s speech_rate=%s max_concurrent_tasks_per_account=%s",
            voice_id,
            len(str(voice_name or "")),
            len(str(voice_code or "")),
            speech_rate,
            max_concurrent_tasks_per_account,
        )
        return self._account_service.save_huasheng_voice_settings(
            voice_id,
            str(voice_name or ""),
            str(voice_code or ""),
            str(voice_tags or ""),
            str(preview_url or ""),
            str(cover or ""),
            speech_rate,
            max_concurrent_tasks_per_account,
        )

    def get_model_settings(self) -> dict[str, Any]:
        return self._account_service.get_model_settings_payload()

    def save_model_settings(
        self,
        base_url: str,
        api_key: str,
        model: str,
        title_prompt: str,
        rewrite_prompts: list[str] | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "AppApi.save_model_settings called base_url_length=%s api_key_length=%s model_length=%s title_prompt_length=%s prompt_count=%s",
            len(str(base_url or "")),
            len(str(api_key or "")),
            len(str(model or "")),
            len(str(title_prompt or "")),
            len(rewrite_prompts or []),
        )
        return self._account_service.save_model_settings(
            str(base_url or ""),
            str(api_key or ""),
            str(model or ""),
            str(title_prompt or ""),
            rewrite_prompts or [],
        )

    def _run_model_action(
        self,
        *,
        action_name: str,
        base_url: str,
        model: str,
        runner: Callable[[], dict[str, Any]],
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            payload = runner()
        except Exception as exc:
            message = str(exc).strip() or f"{action_name}失败"
            logger.warning(
                "AppApi.%s failed base_url=%s model=%s error=%s",
                action_name,
                str(base_url or ""),
                str(model or ""),
                message,
            )
            result = {
                "success": False,
                "errorMessage": message,
                "model": str(model or ""),
                "requestUrl": str(base_url or ""),
            }
            if extra:
                result.update(extra)
            return result

        payload["success"] = True
        payload.setdefault("errorMessage", "")
        return payload

    def rewrite_article(
        self,
        base_url: str,
        api_key: str,
        model: str,
        prompt_id: int,
        article: str,
    ) -> dict[str, Any]:
        logger.info(
            "AppApi.rewrite_article called base_url_length=%s api_key_length=%s model_length=%s prompt_id=%s article_length=%s",
            len(str(base_url or "")),
            len(str(api_key or "")),
            len(str(model or "")),
            prompt_id,
            len(str(article or "")),
        )
        normalized_base_url = str(base_url or "")
        normalized_model = str(model or "")
        return self._run_model_action(
            action_name="rewrite_article",
            base_url=normalized_base_url,
            model=normalized_model,
            extra={"promptId": prompt_id},
            runner=lambda: self._account_service.rewrite_article(
                normalized_base_url,
                str(api_key or ""),
                normalized_model,
                prompt_id,
                str(article or ""),
            ),
        )

    def generate_title(
        self,
        base_url: str,
        api_key: str,
        model: str,
        title_prompt: str,
        article: str,
    ) -> dict[str, Any]:
        logger.info(
            "AppApi.generate_title called base_url_length=%s api_key_length=%s model_length=%s title_prompt_length=%s article_length=%s",
            len(str(base_url or "")),
            len(str(api_key or "")),
            len(str(model or "")),
            len(str(title_prompt or "")),
            len(str(article or "")),
        )
        normalized_base_url = str(base_url or "")
        normalized_model = str(model or "")
        return self._run_model_action(
            action_name="generate_title",
            base_url=normalized_base_url,
            model=normalized_model,
            runner=lambda: self._account_service.generate_title(
                normalized_base_url,
                str(api_key or ""),
                normalized_model,
                str(title_prompt or ""),
                str(article or ""),
            ),
        )

    def test_model_connection(
        self,
        base_url: str,
        api_key: str,
        model: str,
    ) -> dict[str, Any]:
        normalized_base_url = str(base_url or "")
        normalized_model = str(model or "")
        logger.info(
            "AppApi.test_model_connection called base_url=%s base_url_length=%s api_key_length=%s model=%s model_length=%s",
            normalized_base_url,
            len(normalized_base_url),
            len(str(api_key or "")),
            normalized_model,
            len(normalized_model),
        )
        return self._run_model_action(
            action_name="test_model_connection",
            base_url=normalized_base_url,
            model=normalized_model,
            runner=lambda: self._account_service.test_model_connection(
                normalized_base_url,
                str(api_key or ""),
                normalized_model,
            ),
        )

    def get_microheadline_settings(self) -> dict[str, Any]:
        return self._microheadline.get_microheadline_settings_payload()

    def save_microheadline_settings(
        self,
        headless: bool | str,
        worker_count: int,
        default_min_play_count: int = 0,
        default_min_digg_count: int = 0,
        default_min_forward_count: int = 0,
    ) -> dict[str, Any]:
        logger.info(
            "AppApi.save_microheadline_settings called headless=%s worker_count=%s play=%s digg=%s forward=%s",
            headless,
            worker_count,
            default_min_play_count,
            default_min_digg_count,
            default_min_forward_count,
        )
        return self._microheadline.save_microheadline_settings(
            headless,
            worker_count,
            default_min_play_count,
            default_min_digg_count,
            default_min_forward_count,
        )

    def list_benchmark_accounts(self, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        return self._microheadline.list_benchmark_accounts(page, page_size)

    def list_benchmark_account_options(self) -> list[dict[str, Any]]:
        return self._microheadline.list_benchmark_account_options()

    def create_benchmark_account(self, url: str) -> dict[str, Any]:
        logger.info("AppApi.create_benchmark_account called url=%s", url)
        return self._microheadline.create_benchmark_account(str(url or ""))

    def update_benchmark_account(self, account_id: int, url: str) -> dict[str, Any]:
        logger.info("AppApi.update_benchmark_account called account_id=%s url=%s", account_id, url)
        return self._microheadline.update_benchmark_account(account_id, str(url or ""))

    def delete_benchmark_account(self, account_id: int) -> bool:
        logger.info("AppApi.delete_benchmark_account called account_id=%s", account_id)
        return self._microheadline.delete_benchmark_account(account_id)

    def list_monitored_articles(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        return self._microheadline.list_monitored_articles(filters or {}, page, page_size)

    def delete_all_monitored_articles(self) -> dict[str, Any]:
        logger.info("AppApi.delete_all_monitored_articles called")
        return self._microheadline.delete_all_monitored_articles()

    def create_article_processing_tasks(
        self,
        filters: dict[str, Any] | None = None,
        prompt_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        normalized_filters = filters or {}
        normalized_prompt_ids = prompt_ids or []
        logger.info(
            "AppApi.create_article_processing_tasks called article_keyword=%s prompt_count=%s",
            normalized_filters.get("keyword") if isinstance(normalized_filters, dict) else None,
            len(normalized_prompt_ids),
        )
        article_ids = self._microheadline.list_monitored_article_ids(normalized_filters)
        return self._account_service.create_article_processing_tasks(
            article_ids,
            normalized_prompt_ids,
        )

    def create_single_article_processing_task(
        self,
        article_id: int,
        prompt_id: int,
    ) -> dict[str, Any]:
        logger.info(
            "AppApi.create_single_article_processing_task called article_id=%s prompt_id=%s",
            article_id,
            prompt_id,
        )
        return self._account_service.create_single_article_processing_task(
            article_id,
            prompt_id,
        )

    def run_account_monitor(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info(
            "AppApi.run_account_monitor called benchmark_account_id=%s url=%s",
            payload.get("benchmarkAccountId") if isinstance(payload, dict) else None,
            payload.get("url") if isinstance(payload, dict) else None,
        )
        return self._microheadline.run_account_monitor(payload)

    def run_article_monitoring(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info(
            "AppApi.run_article_monitoring called account_count=%s",
            len(payload.get("benchmarkAccountIds") or []) if isinstance(payload, dict) else 0,
        )
        return self._microheadline.run_article_monitoring(payload)

    def create_account(
        self,
        phone: str,
        cookies: str,
        note: str = "",
        is_disabled: bool = False,
    ) -> dict[str, Any]:
        account = self._account_service.create_account(phone, cookies, note, is_disabled)
        payload = self._account_service.list_payload()
        self._bridge.publish_event(
            "accounts.created",
            {"account": account, "stats": payload["stats"]},
        )
        return payload

    def update_account(
        self,
        account_id: int,
        phone: str,
        cookies: str,
        note: str = "",
        is_disabled: bool = False,
    ) -> dict[str, Any]:
        account = self._account_service.update_account(
            account_id,
            phone,
            cookies,
            note,
            is_disabled,
        )
        payload = self._account_service.list_payload()
        self._bridge.publish_event(
            "accounts.updated",
            {"account": account, "stats": payload["stats"]},
        )
        return payload

    def set_account_disabled(self, account_id: int, is_disabled: bool) -> dict[str, Any]:
        account = self._account_service.set_account_disabled(account_id, is_disabled)
        payload = self._account_service.list_payload()
        self._bridge.publish_event(
            "accounts.status-changed",
            {"account": account, "stats": payload["stats"]},
        )
        return payload

    def list_tts_voices(
        self,
        cookies: str,
        pn: int = 1,
        ps: int = 50,
        category_id: int = 0,
    ) -> dict[str, Any]:
        logger.info(
            "AppApi.list_tts_voices called pn=%s ps=%s category_id=%s cookies_length=%s",
            pn,
            ps,
            category_id,
            len(str(cookies or "")),
        )
        return self._huasheng.get_tts_voices(
            str(cookies),
            pn=pn,
            ps=ps,
            category_id=category_id,
        )

    def create_project(
        self,
        cookies: str,
        name: str,
        script: str,
        voice_id: int,
        is_denoise: int = 0,
        voice_type: int = 0,
        audio_url: str = "",
        speech_rate: float = 1,
        speech_rate_change: int = 1,
        project_type: int = 0,
        is_agree: int = 1,
        is_multi: int = 0,
        audio_duration: int = 0,
    ) -> dict[str, Any]:
        logger.info(
            "AppApi.create_project called voice_id=%s name_length=%s script_length=%s speech_rate=%s cookies_length=%s",
            voice_id,
            len(str(name or "")),
            len(str(script or "")),
            speech_rate,
            len(str(cookies or "")),
        )
        return self._huasheng.create_project(
            str(cookies),
            name=str(name),
            script=str(script),
            voice_id=voice_id,
            is_denoise=is_denoise,
            voice_type=voice_type,
            audio_url=str(audio_url),
            speech_rate=speech_rate,
            speech_rate_change=speech_rate_change,
            project_type=project_type,
            is_agree=is_agree,
            is_multi=is_multi,
            audio_duration=audio_duration,
        )

    def get_project_info(self, cookies: str, pid: str) -> dict[str, Any]:
        logger.info(
            "AppApi.get_project_info called pid=%s cookies_length=%s",
            pid,
            len(str(cookies or "")),
        )
        return self._huasheng.get_project_info(str(cookies), pid=str(pid))

    def edit_project(
        self,
        cookies: str,
        project_id: int,
        font_size: int,
        font_color: str,
        outline_color: str,
        outline_thick: int,
    ) -> dict[str, Any]:
        logger.info(
            "AppApi.edit_project called project_id=%s font_size=%s font_color=%s outline_color=%s outline_thick=%s cookies_length=%s",
            project_id,
            font_size,
            font_color,
            outline_color,
            outline_thick,
            len(str(cookies or "")),
        )
        return self._huasheng.edit_project(
            str(cookies),
            project_id=project_id,
            font_size=font_size,
            font_color=str(font_color),
            outline_color=str(outline_color),
            outline_thick=outline_thick,
        )

    def export_project_video(self, cookies: str, project_id: int) -> dict[str, Any]:
        logger.info(
            "AppApi.export_project_video called project_id=%s cookies_length=%s",
            project_id,
            len(str(cookies or "")),
        )
        return self._huasheng.export_project_video(
            str(cookies),
            project_id=project_id,
        )

    def get_project_export_info(
        self,
        cookies: str,
        project_id: int,
        task_id: str,
    ) -> dict[str, Any]:
        logger.info(
            "AppApi.get_project_export_info called project_id=%s task_id=%s cookies_length=%s",
            project_id,
            task_id,
            len(str(cookies or "")),
        )
        return self._huasheng.get_project_export_info(
            str(cookies),
            project_id=project_id,
            task_id=str(task_id),
        )


def build_menu(bridge: DesktopBridge, account_service: AccountService) -> list[Menu]:
    return [
        Menu(
            "账号",
            [
                MenuAction(
                    "刷新账号列表",
                    lambda: bridge.publish_event(
                        "accounts.refresh-requested",
                        {"source": "menu"},
                    ),
                ),
                MenuAction(
                    "显示数据库路径",
                    lambda: bridge.publish_event(
                        "accounts.database-path",
                        {"path": str(account_service.db_path)},
                    ),
                ),
                MenuSeparator(),
                MenuAction("Reload Frontend", bridge.reload_frontend),
                MenuSeparator(),
                MenuAction("Quit", bridge.close_window),
            ],
        ),
        Menu(
            "Window",
            [
                MenuAction(
                    "Reset Title",
                    lambda: bridge.set_window_title(bridge.default_title, source="menu"),
                ),
                MenuAction("Minimize", bridge.minimize),
                MenuAction("Restore", bridge.restore),
                MenuAction("Toggle Fullscreen", bridge.toggle_fullscreen),
            ],
        ),
    ]
