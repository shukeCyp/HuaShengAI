from __future__ import annotations

import gzip
import json
import logging
from http.cookies import SimpleCookie
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


class HuaShengAutomation:
    BASE_URL = "https://www.huasheng.cn"
    TTS_LIST_PATH = "/api/innovideo/material/tts/list"
    PROJECT_CREATE_PATH = "/api/innovideo/project/create"
    PROJECT_INFO_PATH = "/api/innovideo/project/info"
    PROJECT_EDIT_PATH = "/api/innovideo/project/edit"
    PROJECT_EXPORT_VIDEO_TASK_PATH = "/api/innovideo/project/export/video/task"
    PROJECT_EXPORT_VIDEO_INFO_PATH = "/api/innovideo/project/export/video/info"
    DEFAULT_TIMEOUT = 15.0
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )

    def __init__(self, *, base_url: str = BASE_URL, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = str(base_url or self.BASE_URL).rstrip("/")
        self.timeout = float(timeout)

    def get_tts_voices(
        self,
        cookies: str,
        *,
        pn: int = 1,
        ps: int = 50,
        category_id: int = 0,
    ) -> dict[str, Any]:
        normalized_cookies = self._normalize_cookies(cookies)
        params = {
            "pn": self._normalize_int("pn", pn, minimum=1),
            "ps": self._normalize_int("ps", ps, minimum=1),
            "category_id": self._normalize_int("category_id", category_id, minimum=0),
        }
        payload = self._request_json(
            path=self.TTS_LIST_PATH,
            method="GET",
            cookies=normalized_cookies,
            params=params,
            action_name="获取音色",
        )

        if not isinstance(payload, dict):
            raise RuntimeError("获取音色失败: 接口返回不是 JSON 对象。")

        return self._normalize_tts_payload(payload)

    def 获取音色(
        self,
        cookies: str,
        *,
        pn: int = 1,
        ps: int = 50,
        category_id: int = 0,
    ) -> dict[str, Any]:
        return self.get_tts_voices(
            cookies,
            pn=pn,
            ps=ps,
            category_id=category_id,
        )

    def create_project(
        self,
        cookies: str,
        *,
        script: str,
        voice_id: int,
        name: str = "",
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
        normalized_cookies = self._normalize_cookies(cookies)
        payload = {
            "name": str(name or ""),
            "is_denoise": self._normalize_int("is_denoise", is_denoise, minimum=0),
            "script": self._normalize_script(script),
            "voice_id": self._normalize_int("voice_id", voice_id, minimum=1),
            "voice_type": self._normalize_int("voice_type", voice_type, minimum=0),
            "audio_url": str(audio_url or ""),
            "speech_rate": self._normalize_float("speech_rate", speech_rate, minimum=0),
            "speech_rate_change": self._normalize_int(
                "speech_rate_change", speech_rate_change, minimum=0
            ),
            "project_type": self._normalize_int("project_type", project_type, minimum=0),
            "is_agree": self._normalize_int("is_agree", is_agree, minimum=0),
            "is_multi": self._normalize_int("is_multi", is_multi, minimum=0),
            "audio_duration": self._normalize_int(
                "audio_duration", audio_duration, minimum=0
            ),
            "biliCSRF": self._extract_cookie_value(normalized_cookies, "bili_jct"),
        }

        response = self._request_json(
            path=self.PROJECT_CREATE_PATH,
            method="POST",
            cookies=normalized_cookies,
            json_body=payload,
            action_name="创建任务",
        )

        if not isinstance(response, dict):
            raise RuntimeError("创建任务失败: 接口返回不是 JSON 对象。")

        return response

    def 创建任务(
        self,
        cookies: str,
        *,
        script: str,
        voice_id: int,
        name: str = "",
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
        return self.create_project(
            cookies,
            script=script,
            voice_id=voice_id,
            name=name,
            is_denoise=is_denoise,
            voice_type=voice_type,
            audio_url=audio_url,
            speech_rate=speech_rate,
            speech_rate_change=speech_rate_change,
            project_type=project_type,
            is_agree=is_agree,
            is_multi=is_multi,
            audio_duration=audio_duration,
        )

    def get_project_info(self, cookies: str, *, pid: str) -> dict[str, Any]:
        normalized_cookies = self._normalize_cookies(cookies)
        normalized_pid = self._normalize_pid(pid)
        payload = self._request_json(
            path=self.PROJECT_INFO_PATH,
            method="GET",
            cookies=normalized_cookies,
            params={"pid": normalized_pid},
            action_name="获取项目进度",
        )

        if not isinstance(payload, dict):
            raise RuntimeError("获取项目进度失败: 接口返回不是 JSON 对象。")

        return payload

    def 获取项目进度(self, cookies: str, *, pid: str) -> dict[str, Any]:
        return self.get_project_info(cookies, pid=pid)

    def edit_project(
        self,
        cookies: str,
        *,
        project_id: int,
        font_size: int,
        font_color: str,
        outline_color: str,
        outline_thick: int,
    ) -> dict[str, Any]:
        normalized_cookies = self._normalize_cookies(cookies)
        payload = {
            "id": self._normalize_int("id", project_id, minimum=1),
            "font_size": self._normalize_int("font_size", font_size, minimum=1),
            "font_color": self._normalize_hex_color("font_color", font_color),
            "outline_color": self._normalize_hex_color("outline_color", outline_color),
            "outline_thick": self._normalize_int("outline_thick", outline_thick, minimum=0),
            "biliCSRF": self._extract_cookie_value(normalized_cookies, "bili_jct"),
        }
        response = self._request_json(
            path=self.PROJECT_EDIT_PATH,
            method="POST",
            cookies=normalized_cookies,
            json_body=payload,
            action_name="设置字幕",
        )

        if not isinstance(response, dict):
            raise RuntimeError("设置字幕失败: 接口返回不是 JSON 对象。")

        return response

    def 编辑项目(
        self,
        cookies: str,
        *,
        project_id: int,
        font_size: int,
        font_color: str,
        outline_color: str,
        outline_thick: int,
    ) -> dict[str, Any]:
        return self.edit_project(
            cookies,
            project_id=project_id,
            font_size=font_size,
            font_color=font_color,
            outline_color=outline_color,
            outline_thick=outline_thick,
        )

    def export_project_video(self, cookies: str, *, project_id: int) -> dict[str, Any]:
        normalized_cookies = self._normalize_cookies(cookies)
        payload = {
            "id": self._normalize_int("id", project_id, minimum=1),
            "biliCSRF": self._extract_cookie_value(normalized_cookies, "bili_jct"),
        }
        response = self._request_json(
            path=self.PROJECT_EXPORT_VIDEO_TASK_PATH,
            method="POST",
            cookies=normalized_cookies,
            json_body=payload,
            action_name="导出视频",
        )

        if not isinstance(response, dict):
            raise RuntimeError("导出视频失败: 接口返回不是 JSON 对象。")

        return response

    def 导出视频(self, cookies: str, *, project_id: int) -> dict[str, Any]:
        return self.export_project_video(cookies, project_id=project_id)

    def get_project_export_info(
        self,
        cookies: str,
        *,
        project_id: int,
        task_id: str,
    ) -> dict[str, Any]:
        normalized_cookies = self._normalize_cookies(cookies)
        params = {
            "id": self._normalize_int("id", project_id, minimum=1),
            "task_id": self._normalize_task_id(task_id),
        }
        payload = self._request_json(
            path=self.PROJECT_EXPORT_VIDEO_INFO_PATH,
            method="GET",
            cookies=normalized_cookies,
            params=params,
            action_name="获取导出进度",
        )

        if not isinstance(payload, dict):
            raise RuntimeError("获取导出进度失败: 接口返回不是 JSON 对象。")

        return payload

    def 获取导出进度(
        self,
        cookies: str,
        *,
        project_id: int,
        task_id: str,
    ) -> dict[str, Any]:
        return self.get_project_export_info(
            cookies,
            project_id=project_id,
            task_id=task_id,
        )

    def _build_headers(
        self,
        cookies: str,
        *,
        content_type: str | None = None,
        include_origin: bool = False,
    ) -> dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip",
            "Referer": f"{self.base_url}/",
            "User-Agent": self.USER_AGENT,
            "Cookie": cookies,
        }
        if content_type:
            headers["Content-Type"] = content_type
        if include_origin:
            headers["Origin"] = self.base_url
        return headers

    def _request_json(
        self,
        *,
        path: str,
        method: str,
        cookies: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        action_name: str,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"

        body = None
        content_type = None
        include_origin = False
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            content_type = "application/json"
            include_origin = True

        headers = self._build_headers(
            cookies,
            content_type=content_type,
            include_origin=include_origin,
        )
        request = Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )
        start_time = perf_counter()
        logger.info(
            "[%s] 请求开始 method=%s url=%s params=%s body=%s cookie_keys=%s",
            action_name,
            method,
            url,
            self._summarize_log_value(params),
            self._summarize_log_value(json_body),
            self._summarize_cookie_keys(cookies),
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                text, status_code, response_headers = self._read_text_response(response)
                payload = self._parse_json_text(text, action_name)
                duration_ms = (perf_counter() - start_time) * 1000
                logger.info(
                    "[%s] 请求完成 method=%s url=%s status=%s duration_ms=%.1f content_length=%s response=%s",
                    action_name,
                    method,
                    url,
                    status_code,
                    duration_ms,
                    response_headers.get("Content-Length", ""),
                    self._summarize_log_value(payload),
                )
                return payload
        except HTTPError as exc:
            text, status_code, response_headers = self._read_text_response(exc)
            duration_ms = (perf_counter() - start_time) * 1000
            detail = self._summarize_error_detail(text, exc.reason)
            logger.error(
                "[%s] 请求失败 method=%s url=%s status=%s duration_ms=%.1f content_length=%s detail=%s response=%s",
                action_name,
                method,
                url,
                status_code,
                duration_ms,
                response_headers.get("Content-Length", ""),
                detail,
                self._summarize_log_value(text),
            )
            raise RuntimeError(f"{action_name}失败，HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            duration_ms = (perf_counter() - start_time) * 1000
            logger.error(
                "[%s] 请求失败 method=%s url=%s reason=%s duration_ms=%.1f",
                action_name,
                method,
                url,
                exc.reason,
                duration_ms,
            )
            raise RuntimeError(f"{action_name}失败: {exc.reason}") from exc

    def _read_text_response(self, response: Any) -> tuple[str, int | None, dict[str, str]]:
        raw_body = response.read()
        content_encoding = response.headers.get("Content-Encoding", "")
        status_code = getattr(response, "status", None)
        headers = dict(response.headers.items())
        text = self._decode_body(raw_body, content_encoding)
        return text, status_code, headers

    def _parse_json_text(self, text: str, action_name: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("[%s] JSON 解析失败 response=%s", action_name, self._summarize_log_value(text))
            raise RuntimeError(f"{action_name}失败: 接口返回了无效 JSON。") from exc

    def _decode_body(self, body: bytes, content_encoding: str) -> str:
        encoding = str(content_encoding or "").lower()
        if "gzip" in encoding:
            body = gzip.decompress(body)
        return body.decode("utf-8")

    def _normalize_tts_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized["materials"] = [
            self._normalize_material(material)
            for material in payload.get("materials", [])
            if isinstance(material, dict)
        ]
        normalized["categories"] = [
            self._normalize_category(category)
            for category in payload.get("categories", [])
            if isinstance(category, dict)
        ]
        return normalized

    def _normalize_material(self, material: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(material)
        normalized["extra_json"] = self._parse_json_field(normalized.get("extra"))
        normalized["pool_extra_json"] = self._parse_json_field(normalized.get("pool_extra"))
        return normalized

    def _normalize_category(self, category: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(category)
        normalized["extra_json"] = self._parse_json_field(normalized.get("extra"))

        children = normalized.get("children")
        if isinstance(children, list):
            normalized["children"] = [
                self._normalize_category(child) if isinstance(child, dict) else child
                for child in children
            ]

        return normalized

    def _summarize_log_value(self, value: Any, *, limit: int = 500) -> str:
        if value is None:
            return "-"
        if isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            text = str(value)
        text = " ".join(text.split())
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

    def _summarize_cookie_keys(self, cookies: str) -> str:
        try:
            parsed = SimpleCookie()
            parsed.load(cookies)
            keys = sorted(parsed.keys())
        except Exception:
            return "-"
        if not keys:
            return "-"
        return ",".join(keys)

    def _parse_json_field(self, value: Any) -> dict[str, Any] | list[Any] | None:
        if not isinstance(value, str) or not value.strip():
            return None

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    def _normalize_cookies(self, cookies: str) -> str:
        normalized = str(cookies or "").strip()
        if not normalized:
            raise ValueError("cookies 不能为空。")
        return normalized

    def _normalize_script(self, script: str) -> str:
        normalized = str(script or "").strip()
        if not normalized:
            raise ValueError("script 不能为空。")
        return normalized

    def _normalize_pid(self, pid: str) -> str:
        normalized = str(pid or "").strip()
        if not normalized:
            raise ValueError("pid 不能为空。")
        return normalized

    def _normalize_task_id(self, task_id: str) -> str:
        normalized = str(task_id or "").strip()
        if not normalized:
            raise ValueError("task_id 不能为空。")
        return normalized

    def _normalize_int(self, name: str, value: Any, *, minimum: int) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} 必须是整数。") from exc

        if normalized < minimum:
            raise ValueError(f"{name} 不能小于 {minimum}。")

        return normalized

    def _normalize_float(self, name: str, value: Any, *, minimum: float) -> float:
        try:
            normalized = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} 必须是数字。") from exc

        if normalized < minimum:
            raise ValueError(f"{name} 不能小于 {minimum}。")

        return normalized

    def _normalize_hex_color(self, name: str, value: Any) -> str:
        normalized = str(value or "").strip().upper()
        if not normalized:
            raise ValueError(f"{name} 不能为空。")
        if len(normalized) != 7 or not normalized.startswith("#"):
            raise ValueError(f"{name} 必须是 #RRGGBB 格式。")
        try:
            int(normalized[1:], 16)
        except ValueError as exc:
            raise ValueError(f"{name} 必须是 #RRGGBB 格式。") from exc
        return normalized

    def _extract_cookie_value(self, cookies: str, key: str) -> str:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise ValueError("cookie key 不能为空。")

        cookie = SimpleCookie()
        cookie.load(cookies)
        morsel = cookie.get(normalized_key)
        if morsel is not None and morsel.value:
            return morsel.value

        for chunk in cookies.split(";"):
            name, separator, raw_value = chunk.strip().partition("=")
            if separator and name.strip() == normalized_key:
                value = raw_value.strip()
                if value:
                    return value

        raise ValueError(f"cookies 中缺少 {normalized_key}。")

    def _sanitize_headers_for_log(self, headers: dict[str, str]) -> dict[str, str]:
        sanitized: dict[str, str] = {}
        for key, value in headers.items():
            if key.lower() == "cookie":
                sanitized[key] = self._mask_cookie_string(value)
            else:
                sanitized[key] = value
        return sanitized

    def _mask_cookie_string(self, cookies: str) -> str:
        parts: list[str] = []
        for chunk in str(cookies or "").split(";"):
            name, separator, raw_value = chunk.strip().partition("=")
            if not separator:
                continue
            parts.append(f"{name}={self._mask_secret(raw_value.strip())}")
        return "; ".join(parts)

    def _mask_secret(self, value: str) -> str:
        normalized = str(value or "")
        if not normalized:
            return ""
        if len(normalized) <= 8:
            return "*" * len(normalized)
        return f"{normalized[:4]}...{normalized[-4:]}"

    def _summarize_error_detail(self, text: str, fallback: Any) -> str:
        detail = str(text or "").strip()
        if detail:
            return detail[:300]
        return str(fallback)


花生自动化 = HuaShengAutomation
