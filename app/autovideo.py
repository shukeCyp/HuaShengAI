from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


class AutoVideoAutomation:
    BASE_URL = "https://autovideo.talkus.fun"
    API_PREFIX = "/gradio_api"
    GENERATE_VIDEO_PATH = f"{API_PREFIX}/call/generate_video"
    DEFAULT_TIMEOUT = 30.0
    DEFAULT_STREAM_TIMEOUT = 15 * 60.0
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )

    VOICE_OPTIONS = [
        {"label": "晓晓（中文主持，自然亲切）", "value": "zh-CN-YunxiNeural"},
        {"label": "晓晓（中文主持，情感丰富）", "value": "zh-CN-XiaoxiaoNeural"},
        {"label": "云扬（中文男声，新闻播报）", "value": "zh-CN-YunyangNeural"},
        {"label": "晓艺（中文女声，活泼可爱）", "value": "zh-CN-XiaoyiNeural"},
        {"label": "东北话（辽宁，幽默直爽）", "value": "zh-CN-liaoning-XiaobeiNeural"},
        {"label": "台湾话（温柔甜美）", "value": "zh-TW-HsiaoChenNeural"},
        {"label": "台湾男声（稳重沉稳）", "value": "zh-TW-YunJheNeural"},
        {"label": "粤语（女声，标准地道）", "value": "zh-HK-HiuMaanNeural"},
        {"label": "Jenny（美国女声，清晰专业）", "value": "en-US-JennyNeural"},
        {"label": "Guy（美国男声，稳重权威）", "value": "en-US-GuyNeural"},
        {"label": "Sonia（英国女声，优雅标准）", "value": "en-GB-SoniaNeural"},
        {"label": "七海（日本女声，温柔标准）", "value": "ja-JP-NanamiNeural"},
        {"label": "庆太（日本男声，年轻自然）", "value": "ja-JP-KeitaNeural"},
    ]
    RATE_OPTIONS = [
        {"label": "极慢（0.5x）", "value": "-50%"},
        {"label": "较慢（0.7x）", "value": "-30%"},
        {"label": "稍慢（0.9x）", "value": "-10%"},
        {"label": "正常（1.0x）", "value": "+0%"},
        {"label": "稍快（1.1x）", "value": "+10%"},
        {"label": "较快（1.2x）", "value": "+20%"},
        {"label": "快（1.3x）", "value": "+30%"},
        {"label": "极快（1.5x）", "value": "+50%"},
    ]
    DEFAULT_VOICE_CHOICE = "zh-CN-YunyangNeural"
    DEFAULT_RATE_CHOICE = "+20%"
    MIN_LINE_LENGTH = 15
    MAX_LINE_LENGTH = 30
    SENTENCE_BREAK_PATTERN = re.compile(r"[^，。！？；：,.!?;:\n]+[，。！？；：,.!?;:]*")

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        stream_timeout: float = DEFAULT_STREAM_TIMEOUT,
    ) -> None:
        self.base_url = str(base_url or self.BASE_URL).rstrip("/")
        self.timeout = float(timeout)
        self.stream_timeout = float(stream_timeout)

    def list_voice_options(self) -> list[dict[str, str]]:
        return [dict(item) for item in self.VOICE_OPTIONS]

    def list_rate_options(self) -> list[dict[str, str]]:
        return [dict(item) for item in self.RATE_OPTIONS]

    def generate_video(
        self,
        *,
        story_text: str,
        voice_choice: str = DEFAULT_VOICE_CHOICE,
        rate_choice: str = DEFAULT_RATE_CHOICE,
    ) -> dict[str, Any]:
        normalized_story_text = self._normalize_story_text(story_text)
        normalized_voice_choice = self.normalize_voice_choice(voice_choice)
        normalized_rate_choice = self.normalize_rate_choice(rate_choice)
        event_id = self._start_gradio_call(
            path=self.GENERATE_VIDEO_PATH,
            payload={
                "data": [
                    normalized_story_text,
                    normalized_voice_choice,
                    normalized_rate_choice,
                ]
            },
        )
        result = self._consume_event_stream(
            path=f"{self.GENERATE_VIDEO_PATH}/{event_id}",
        )
        video_file, status_message = self._parse_generate_video_result(result)
        return {
            "provider": "autovideo",
            "eventId": event_id,
            "storyText": normalized_story_text,
            "voiceChoice": normalized_voice_choice,
            "rateChoice": normalized_rate_choice,
            "video": video_file,
            "viewUrl": str(video_file.get("url") or "").strip(),
            "statusMessage": status_message,
            "requestUrl": f"{self.base_url}{self.GENERATE_VIDEO_PATH}",
        }

    def normalize_voice_choice(self, value: Any) -> str:
        normalized = str(value or "").strip()
        if any(item["value"] == normalized for item in self.VOICE_OPTIONS):
            return normalized
        return self.DEFAULT_VOICE_CHOICE

    def normalize_rate_choice(self, value: Any) -> str:
        normalized = str(value or "").strip()
        if any(item["value"] == normalized for item in self.RATE_OPTIONS):
            return normalized
        return self.DEFAULT_RATE_CHOICE

    def resolve_voice_label(self, value: Any) -> str:
        normalized = self.normalize_voice_choice(value)
        for item in self.VOICE_OPTIONS:
            if item["value"] == normalized:
                return item["label"]
        return normalized

    def resolve_rate_label(self, value: Any) -> str:
        normalized = self.normalize_rate_choice(value)
        for item in self.RATE_OPTIONS:
            if item["value"] == normalized:
                return item["label"]
        return normalized

    def _normalize_story_text(self, value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("分镜脚本不能为空。")
        if len(normalized) > 200000:
            raise ValueError("分镜脚本长度不能超过 200000 个字符。")
        return self._format_storyboard_lines(normalized)

    def _format_storyboard_lines(self, text: str) -> str:
        normalized = re.sub(r"\r\n?", "\n", str(text or "").strip())
        raw_lines = [line.strip() for line in normalized.split("\n") if line.strip()]
        if not raw_lines:
            raise ValueError("分镜脚本不能为空。")

        formatted_lines: list[str] = []
        for raw_line in raw_lines:
            formatted_lines.extend(self._format_storyboard_line(raw_line))
        return "\n".join(formatted_lines)

    def _format_storyboard_line(self, line: str) -> list[str]:
        sentences = self._split_storyboard_sentences(line)
        if not sentences:
            return []
        cache: dict[int, tuple[int, list[str]]] = {}
        best_cost, best_lines = self._choose_best_line_breaks(
            sentences,
            start_index=0,
            cache=cache,
        )
        del best_cost
        return best_lines

    def _choose_best_line_breaks(
        self,
        sentences: list[str],
        *,
        start_index: int,
        cache: dict[int, tuple[int, list[str]]],
    ) -> tuple[int, list[str]]:
        cached = cache.get(start_index)
        if cached is not None:
            return cached
        if start_index >= len(sentences):
            return 0, []

        best_cost: int | None = None
        best_lines: list[str] = []
        for end_index in range(start_index + 1, len(sentences) + 1):
            candidate_line = "".join(sentences[start_index:end_index])
            line_cost = self._line_length_penalty(len(candidate_line))
            remaining_cost, remaining_lines = self._choose_best_line_breaks(
                sentences,
                start_index=end_index,
                cache=cache,
            )
            total_cost = line_cost + remaining_cost
            candidate_lines = [candidate_line, *remaining_lines]
            if (
                best_cost is None
                or total_cost < best_cost
                or (total_cost == best_cost and len(candidate_lines) < len(best_lines))
            ):
                best_cost = total_cost
                best_lines = candidate_lines

        result = (int(best_cost or 0), best_lines)
        cache[start_index] = result
        return result

    def _line_length_penalty(self, length: int) -> int:
        if self.MIN_LINE_LENGTH <= length <= self.MAX_LINE_LENGTH:
            return 0
        if length < self.MIN_LINE_LENGTH:
            return (self.MIN_LINE_LENGTH - length) * 2 + 1
        return (length - self.MAX_LINE_LENGTH) * 3 + 10

    def _split_storyboard_sentences(self, line: str) -> list[str]:
        compact_line = re.sub(r"\s+", "", str(line or "").strip())
        if not compact_line:
            return []
        sentences = [
            match.group(0).strip()
            for match in self.SENTENCE_BREAK_PATTERN.finditer(compact_line)
            if match.group(0).strip()
        ]
        return sentences or [compact_line]

    def _build_headers(self, *, accept: str) -> dict[str, str]:
        return {
            "Accept": accept,
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/?view=api",
            "User-Agent": self.USER_AGENT,
        }

    def _start_gradio_call(self, *, path: str, payload: dict[str, Any]) -> str:
        request = Request(
            url=f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._build_headers(accept="application/json"),
            method="POST",
        )
        response = self._read_json_response(
            request,
            timeout=self.timeout,
            action_name="发起 AutoVideo 任务",
        )
        event_id = str(response.get("event_id") or "").strip()
        if not event_id:
            raise RuntimeError("发起 AutoVideo 任务失败: 接口未返回 event_id。")
        return event_id

    def _consume_event_stream(self, *, path: str) -> Any:
        request = Request(
            url=f"{self.base_url}{path}",
            headers={
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache",
                "Referer": f"{self.base_url}/?view=api",
                "User-Agent": self.USER_AGENT,
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.stream_timeout) as response:
                current_event = ""
                data_lines: list[str] = []
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                    if not line:
                        parsed = self._consume_sse_message(current_event, data_lines)
                        if parsed is not None:
                            return parsed
                        current_event = ""
                        data_lines = []
                        continue
                    if line.startswith(":"):
                        continue
                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                        continue
                    if line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                parsed = self._consume_sse_message(current_event, data_lines)
                if parsed is not None:
                    return parsed
        except HTTPError as exc:
            detail = self._read_error_body(exc)
            raise RuntimeError(f"获取 AutoVideo 结果失败: HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"获取 AutoVideo 结果失败: {exc.reason}") from exc
        raise RuntimeError("获取 AutoVideo 结果失败: 事件流提前结束。")

    def _consume_sse_message(self, event_name: str, data_lines: list[str]) -> Any | None:
        if not event_name and not data_lines:
            return None
        raw_data = "\n".join(data_lines).strip()
        if event_name == "complete":
            if not raw_data:
                raise RuntimeError("获取 AutoVideo 结果失败: complete 事件缺少数据。")
            try:
                return json.loads(raw_data)
            except json.JSONDecodeError as exc:
                raise RuntimeError("获取 AutoVideo 结果失败: complete 数据不是合法 JSON。") from exc
        if event_name == "error":
            message = raw_data or "未知错误"
            raise RuntimeError(f"AutoVideo 生成失败: {message}")
        return None

    def _parse_generate_video_result(
        self,
        payload: Any,
    ) -> tuple[dict[str, Any], str]:
        if not isinstance(payload, list) or len(payload) < 2:
            raise RuntimeError("AutoVideo 生成失败: 返回数据结构不符合预期。")
        video_file = payload[0]
        status_message = str(payload[1] or "").strip()
        if not isinstance(video_file, dict):
            raise RuntimeError("AutoVideo 生成失败: 未返回视频文件对象。")
        video_url = str(video_file.get("url") or "").strip()
        if not video_url:
            raise RuntimeError("AutoVideo 生成失败: 返回视频缺少可访问 URL。")
        normalized_video_file = {
            "path": str(video_file.get("path") or "").strip(),
            "url": video_url,
            "size": video_file.get("size"),
            "origName": str(video_file.get("orig_name") or "").strip(),
            "mimeType": str(video_file.get("mime_type") or "").strip(),
            "isStream": bool(video_file.get("is_stream")),
        }
        return normalized_video_file, status_message or "生成完成"

    def _read_json_response(
        self,
        request: Request,
        *,
        timeout: float,
        action_name: str,
    ) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            detail = self._read_error_body(exc)
            raise RuntimeError(f"{action_name}失败: HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"{action_name}失败: {exc.reason}") from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{action_name}失败: 接口返回不是合法 JSON。") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"{action_name}失败: 接口返回不是 JSON 对象。")
        return payload

    def _read_error_body(self, exc: HTTPError) -> str:
        try:
            body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            body = ""
        if not body:
            return ""
        if len(body) > 200:
            body = f"{body[:200]}..."
        return body
