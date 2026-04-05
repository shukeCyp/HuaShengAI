from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from app.accounts import AccountService
from app.config import resolve_data_dir, resolve_db_path
from app.database import close_database, init_database
from app.huasheng import HuaShengAutomation

DEFAULT_SCRIPT = "这是一个命令行创建的测试项目，用于验证花生项目创建接口和进度轮询接口。"
DEFAULT_VOICE_ID = 6036542
DEFAULT_POLL_INTERVAL = 8.0
DEFAULT_MAX_POLLS = 60

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def mask_phone(value: str) -> str:
    normalized = str(value or "")
    if len(normalized) != 11:
        return normalized or "--"
    return f"{normalized[:3]}****{normalized[-4:]}"


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def format_timestamp(value: datetime | None = None) -> str:
    current = value or datetime.now()
    return current.strftime("%Y-%m-%d %H:%M:%S")


class MarkdownRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            "# 花生命令行项目日志\n\n"
            f"- 开始时间: {format_timestamp()}\n"
            f"- 输出文件: `{self.path}`\n\n",
            encoding="utf-8",
        )

    def append_overview(self, title: str, details: dict[str, Any]) -> None:
        lines = [f"## {title}", ""]
        for key, value in details.items():
            lines.append(f"- {key}: {value}")
        lines.append("")
        self._append("\n".join(lines))

    def append_request_result(
        self,
        *,
        title: str,
        method: str,
        url: str,
        request_params: dict[str, Any] | None = None,
        request_json: dict[str, Any] | None = None,
        response_json: Any = None,
        duration_ms: float | None = None,
        note: str | None = None,
        error: str | None = None,
    ) -> None:
        sections = [f"## {title}", "", f"- 时间: {format_timestamp()}"]
        sections.append(f"- 方法: `{method}`")
        sections.append(f"- URL: `{url}`")
        if duration_ms is not None:
            sections.append(f"- 耗时: `{duration_ms:.1f}ms`")
        if note:
            sections.append(f"- 备注: {note}")
        if error:
            sections.append(f"- 错误: {error}")
        sections.append("")

        if request_params is not None:
            sections.extend(
                [
                    "### Request Params",
                    "",
                    "```json",
                    dump_json(request_params),
                    "```",
                    "",
                ]
            )

        if request_json is not None:
            sections.extend(
                [
                    "### Request JSON",
                    "",
                    "```json",
                    dump_json(request_json),
                    "```",
                    "",
                ]
            )

        if response_json is not None:
            sections.extend(
                [
                    "### Response JSON",
                    "",
                    "```json",
                    dump_json(response_json),
                    "```",
                    "",
                ]
            )

        self._append("\n".join(sections))

    def _append(self, content: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(content)
            if not content.endswith("\n"):
                handle.write("\n")
            handle.write("\n")


def choose_account(account_service: AccountService, account_id: int | None) -> dict[str, Any]:
    payload = account_service.list_payload()
    accounts = payload.get("items", [])
    if not accounts:
        raise RuntimeError("本地账号库为空，请先在桌面端添加可用账号。")

    if account_id is not None:
        selected = next((item for item in accounts if int(item["id"]) == int(account_id)), None)
        if selected is None:
            raise RuntimeError(f"未找到账号 id={account_id}。")
        return selected

    enabled_accounts = [item for item in accounts if not item["isDisabled"]]
    if enabled_accounts:
        return enabled_accounts[0]
    return accounts[0]


def build_create_request_body(
    automation: HuaShengAutomation,
    *,
    cookies: str,
    name: str,
    script: str,
    voice_id: int,
    speech_rate: float,
) -> dict[str, Any]:
    return {
        "name": str(name or ""),
        "is_denoise": 0,
        "script": str(script),
        "voice_id": int(voice_id),
        "voice_type": 0,
        "audio_url": "",
        "speech_rate": float(speech_rate),
        "speech_rate_change": 1,
        "project_type": 0,
        "is_agree": 1,
        "is_multi": 0,
        "audio_duration": 0,
        "biliCSRF": automation._extract_cookie_value(cookies, "bili_jct"),
    }


def iter_nodes(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    nodes: list[tuple[tuple[str, ...], Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = path + (str(key),)
            nodes.append((next_path, item))
            nodes.extend(iter_nodes(item, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            next_path = path + (str(index),)
            nodes.extend(iter_nodes(item, next_path))
    return nodes


def detect_terminal_state(payload: Any) -> tuple[str | None, str | None]:
    success_texts = {
        "done",
        "finished",
        "complete",
        "completed",
        "success",
        "succeeded",
        "完成",
        "已完成",
        "成功",
    }
    failure_tokens = ("fail", "failed", "error", "cancel", "cancelled", "canceled", "异常", "失败")

    project = payload.get("project") if isinstance(payload, dict) else None
    if not isinstance(project, dict):
        return None, None

    progress_value = project.get("progress")
    try:
        progress = float(progress_value)
    except (TypeError, ValueError):
        progress = None
    if progress is not None and progress >= 100:
        return "success", f"project.progress={progress}"

    for key in ("state_message", "loading_msg"):
        normalized = str(project.get(key) or "").strip().lower()
        if normalized in success_texts or any(token in normalized for token in ("完成", "成功", "已生成")):
            return "success", f"project.{key}={project.get(key)}"
        if any(token in normalized for token in failure_tokens):
            return "failure", f"project.{key}={project.get(key)}"

    for key in ("video_url", "result_url", "output_url", "play_url"):
        value = project.get(key)
        if isinstance(value, str) and value.strip():
            return "success", f"project.{key} 已返回可用地址"

    return None, None


def build_default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return resolve_data_dir() / "project_runs" / f"project_run_{stamp}.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="创建花生项目并持续轮询进度，写入 Markdown 日志。")
    parser.add_argument("--account-id", type=int, default=None, help="指定账号 id；默认使用第一个启用账号。")
    parser.add_argument("--voice-id", type=int, default=DEFAULT_VOICE_ID, help="创建任务使用的 voice_id。")
    parser.add_argument("--speech-rate", type=float, default=1.0, help="创建任务使用的 speech_rate。")
    parser.add_argument("--name", default="", help="任务名称，可留空。")
    parser.add_argument("--script", default=DEFAULT_SCRIPT, help="创建任务的脚本文案。")
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL, help="轮询间隔秒数。")
    parser.add_argument("--max-polls", type=int, default=DEFAULT_MAX_POLLS, help="最大轮询次数。")
    parser.add_argument("--output", type=Path, default=None, help="Markdown 输出路径。")
    return parser


def main() -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args()

    db_path = init_database(resolve_db_path())
    automation = HuaShengAutomation()
    account_service = AccountService(db_path)
    account_service.bootstrap()
    selected_account = choose_account(account_service, args.account_id)
    output_path = (args.output or build_default_output_path()).expanduser().resolve()
    recorder = MarkdownRecorder(output_path)

    recorder.append_overview(
        "运行参数",
        {
            "账号 id": selected_account["id"],
            "账号手机号": mask_phone(selected_account["phone"]),
            "账号备注": selected_account["note"] or "未填写备注",
            "账号禁用状态": selected_account["isDisabled"],
            "voice_id": args.voice_id,
            "speech_rate": args.speech_rate,
            "poll_interval": args.poll_interval,
            "max_polls": args.max_polls,
        },
    )

    cookies = str(selected_account["cookies"])
    create_url = f"{automation.base_url}{automation.PROJECT_CREATE_PATH}"
    create_request = build_create_request_body(
        automation,
        cookies=cookies,
        name=args.name,
        script=args.script,
        voice_id=args.voice_id,
        speech_rate=args.speech_rate,
    )

    logger.info(
        "Starting CLI project flow account_id=%s phone=%s voice_id=%s output=%s",
        selected_account["id"],
        mask_phone(selected_account["phone"]),
        args.voice_id,
        output_path,
    )

    try:
        create_started = perf_counter()
        create_response = automation.create_project(
            cookies,
            name=args.name,
            script=args.script,
            voice_id=args.voice_id,
            speech_rate=args.speech_rate,
            is_agree=1,
        )
        create_duration_ms = (perf_counter() - create_started) * 1000
        recorder.append_request_result(
            title="创建任务",
            method="POST",
            url=create_url,
            request_json=create_request,
            response_json=create_response,
            duration_ms=create_duration_ms,
        )
    except Exception as exc:
        recorder.append_request_result(
            title="创建任务",
            method="POST",
            url=create_url,
            request_json=create_request,
            duration_ms=None,
            error=str(exc),
        )
        raise

    pid = str(create_response.get("pid") or "").strip()
    project_id = str(create_response.get("id") or "").strip()
    if not pid:
        raise RuntimeError("创建任务成功，但响应中没有 pid，无法轮询进度。")

    recorder.append_overview(
        "创建结果",
        {
            "project id": project_id or "--",
            "pid": pid,
        },
    )

    info_url = f"{automation.base_url}{automation.PROJECT_INFO_PATH}"
    terminal_state = None
    terminal_reason = None

    for poll_index in range(1, max(1, int(args.max_polls)) + 1):
        poll_started = perf_counter()
        try:
            info_response = automation.get_project_info(cookies, pid=pid)
            duration_ms = (perf_counter() - poll_started) * 1000
            terminal_state, terminal_reason = detect_terminal_state(info_response)
            note = terminal_reason or "继续轮询"
            recorder.append_request_result(
                title=f"轮询项目进度 #{poll_index}",
                method="GET",
                url=info_url,
                request_params={"pid": pid},
                response_json=info_response,
                duration_ms=duration_ms,
                note=note,
            )
        except Exception as exc:
            recorder.append_request_result(
                title=f"轮询项目进度 #{poll_index}",
                method="GET",
                url=info_url,
                request_params={"pid": pid},
                error=str(exc),
            )
            raise

        if terminal_state is not None:
            break

        if poll_index < int(args.max_polls):
            time.sleep(max(0.1, float(args.poll_interval)))

    if terminal_state is None:
        recorder.append_overview(
            "轮询结束",
            {
                "状态": "达到最大轮询次数，未识别到终态",
                "pid": pid,
            },
        )
    else:
        recorder.append_overview(
            "轮询结束",
            {
                "状态": terminal_state,
                "原因": terminal_reason or "--",
                "pid": pid,
            },
        )

    print(output_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        close_database()
