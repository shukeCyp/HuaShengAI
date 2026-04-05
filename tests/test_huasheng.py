from __future__ import annotations

import gzip
import json
import unittest
from unittest.mock import patch

from app.huasheng import HuaShengAutomation


class FakeResponse:
    def __init__(self, payload: bytes, headers: dict[str, str] | None = None) -> None:
        self._payload = payload
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class HuaShengAutomationTests(unittest.TestCase):
    def test_get_tts_voices_parses_nested_json_fields(self) -> None:
        sample_payload = {
            "materials": [
                {
                    "id": "5866403",
                    "name": "生动解说",
                    "extra": json.dumps(
                        {
                            "voice_type": 2,
                            "voice": "male-qn-jingying",
                            "speech_rate": 10,
                        },
                        ensure_ascii=False,
                    ),
                    "pool_extra": json.dumps(
                        {
                            "tts_tags": "高昂有力",
                            "preview_url": "http://boss.hdslb.com/material/demo.wav",
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
            "categories": [
                {
                    "id": "1740252",
                    "title": "性别",
                    "extra": "{\"white_list\":0}",
                    "children": [
                        {
                            "id": "1740254",
                            "title": "男性",
                            "extra": "{\"white_list\":0}",
                            "children": [],
                        }
                    ],
                }
            ],
            "page": {"num": "1", "size": "40", "total": "40"},
            "last_used_voice_id": "6036554",
        }
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            payload = gzip.compress(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8"))
            return FakeResponse(payload, headers={"Content-Encoding": "gzip"})

        client = HuaShengAutomation(timeout=9.5)

        with patch("app.huasheng.urlopen", side_effect=fake_urlopen):
            result = client.获取音色("SESSDATA=test", pn=2, ps=20, category_id=1740254)

        self.assertEqual(
            captured["url"],
            "https://www.huasheng.cn/api/innovideo/material/tts/list?pn=2&ps=20&category_id=1740254",
        )
        self.assertEqual(captured["timeout"], 9.5)
        self.assertEqual(captured["headers"]["Cookie"], "SESSDATA=test")
        self.assertEqual(
            result["materials"][0]["extra_json"]["voice"],
            "male-qn-jingying",
        )
        self.assertEqual(
            result["materials"][0]["pool_extra_json"]["preview_url"],
            "http://boss.hdslb.com/material/demo.wav",
        )
        self.assertEqual(result["categories"][0]["extra_json"]["white_list"], 0)
        self.assertEqual(result["categories"][0]["children"][0]["extra_json"]["white_list"], 0)
        self.assertEqual(result["last_used_voice_id"], "6036554")

    def test_get_tts_voices_rejects_empty_cookies(self) -> None:
        client = HuaShengAutomation()

        with self.assertRaisesRegex(ValueError, "cookies 不能为空"):
            client.get_tts_voices("")

    def test_create_project_uses_bili_jct_from_cookies(self) -> None:
        sample_payload = {"id": "2456102", "pid": "113602715787267"}
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            payload = gzip.compress(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8"))
            return FakeResponse(payload, headers={"Content-Encoding": "gzip"})

        client = HuaShengAutomation(timeout=6)
        cookies = "SESSDATA=test; bili_jct=csrf-token-123; sid=abc"

        with patch("app.huasheng.urlopen", side_effect=fake_urlopen):
            result = client.create_project(
                cookies,
                name="",
                script="测试文案",
                voice_id=6036542,
                speech_rate=1,
            )

        self.assertEqual(
            captured["url"],
            "https://www.huasheng.cn/api/innovideo/project/create",
        )
        self.assertEqual(captured["timeout"], 6)
        self.assertEqual(captured["headers"]["Cookie"], cookies)
        self.assertEqual(captured["headers"]["Content-type"], "application/json")
        self.assertEqual(captured["headers"]["Origin"], "https://www.huasheng.cn")
        self.assertEqual(captured["body"]["voice_id"], 6036542)
        self.assertEqual(captured["body"]["script"], "测试文案")
        self.assertEqual(captured["body"]["biliCSRF"], "csrf-token-123")
        self.assertEqual(result, sample_payload)

    def test_create_project_requires_bili_jct_cookie(self) -> None:
        client = HuaShengAutomation()

        with self.assertRaisesRegex(ValueError, "cookies 中缺少 bili_jct"):
            client.create_project("SESSDATA=test", script="测试文案", voice_id=1)

    def test_get_project_info_uses_pid_query(self) -> None:
        sample_payload = {
            "pid": "113671485575170",
            "status": "processing",
            "progress": 42,
        }
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            payload = gzip.compress(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8"))
            return FakeResponse(payload, headers={"Content-Encoding": "gzip"})

        client = HuaShengAutomation(timeout=5)

        with patch("app.huasheng.urlopen", side_effect=fake_urlopen):
            result = client.get_project_info("SESSDATA=test", pid="113671485575170")

        self.assertEqual(
            captured["url"],
            "https://www.huasheng.cn/api/innovideo/project/info?pid=113671485575170",
        )
        self.assertEqual(captured["timeout"], 5)
        self.assertEqual(captured["headers"]["Cookie"], "SESSDATA=test")
        self.assertEqual(result, sample_payload)

    def test_export_project_video_uses_bili_jct_from_cookies(self) -> None:
        sample_payload = {"task_id": "p2470002_37", "version": "37"}
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            payload = gzip.compress(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8"))
            return FakeResponse(payload, headers={"Content-Encoding": "gzip"})

        client = HuaShengAutomation(timeout=4)
        cookies = "SESSDATA=test; bili_jct=csrf-token-123; sid=abc"

        with patch("app.huasheng.urlopen", side_effect=fake_urlopen):
            result = client.export_project_video(cookies, project_id=2470002)

        self.assertEqual(
            captured["url"],
            "https://www.huasheng.cn/api/innovideo/project/export/video/task",
        )
        self.assertEqual(captured["timeout"], 4)
        self.assertEqual(captured["headers"]["Cookie"], cookies)
        self.assertEqual(captured["body"]["id"], 2470002)
        self.assertEqual(captured["body"]["biliCSRF"], "csrf-token-123")
        self.assertEqual(result, sample_payload)

    def test_edit_project_uses_subtitle_payload_and_bili_jct(self) -> None:
        sample_payload = {"code": 0, "message": "success"}
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            payload = gzip.compress(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8"))
            return FakeResponse(payload, headers={"Content-Encoding": "gzip"})

        client = HuaShengAutomation(timeout=4)
        cookies = "SESSDATA=test; bili_jct=csrf-token-123; sid=abc"

        with patch("app.huasheng.urlopen", side_effect=fake_urlopen):
            result = client.edit_project(
                cookies,
                project_id=2470002,
                font_size=54,
                font_color="#ffffff",
                outline_color="#0091a8",
                outline_thick=70,
            )

        self.assertEqual(
            captured["url"],
            "https://www.huasheng.cn/api/innovideo/project/edit",
        )
        self.assertEqual(captured["timeout"], 4)
        self.assertEqual(captured["headers"]["Cookie"], cookies)
        self.assertEqual(captured["body"]["id"], 2470002)
        self.assertEqual(captured["body"]["font_size"], 54)
        self.assertEqual(captured["body"]["font_color"], "#FFFFFF")
        self.assertEqual(captured["body"]["outline_color"], "#0091A8")
        self.assertEqual(captured["body"]["outline_thick"], 70)
        self.assertEqual(captured["body"]["biliCSRF"], "csrf-token-123")
        self.assertEqual(result, sample_payload)

    def test_get_project_export_info_uses_id_and_task_id_query(self) -> None:
        sample_payload = {"url": "", "progress": "61", "cover": "", "cover43": ""}
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            payload = gzip.compress(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8"))
            return FakeResponse(payload, headers={"Content-Encoding": "gzip"})

        client = HuaShengAutomation(timeout=7)

        with patch("app.huasheng.urlopen", side_effect=fake_urlopen):
            result = client.get_project_export_info(
                "SESSDATA=test",
                project_id=2470002,
                task_id="p2470002_37",
            )

        self.assertEqual(
            captured["url"],
            "https://www.huasheng.cn/api/innovideo/project/export/video/info?id=2470002&task_id=p2470002_37",
        )
        self.assertEqual(captured["timeout"], 7)
        self.assertEqual(captured["headers"]["Cookie"], "SESSDATA=test")
        self.assertEqual(result, sample_payload)


if __name__ == "__main__":
    unittest.main()
