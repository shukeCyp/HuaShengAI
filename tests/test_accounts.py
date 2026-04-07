from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError
from unittest.mock import patch

from app.accounts import AccountService
from app.database import close_database, database, init_database
from app.models import (
    BenchmarkAccount,
    HuashengGenerationRecord,
    MonitorRun,
    MonitoredArticle,
)


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._cursor = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._payload) - self._cursor
        if self._cursor >= len(self._payload):
            return b""
        start = self._cursor
        end = min(len(self._payload), self._cursor + size)
        self._cursor = end
        return self._payload[start:end]

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class AccountServiceSubtitleSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.sqlite3"
        init_database(self.db_path)
        self.service = AccountService(self.db_path)
        self.service.bootstrap()

    def tearDown(self) -> None:
        close_database()
        self.temp_dir.cleanup()

    def create_monitored_article(
        self,
        article_id: int,
        *,
        content: str,
        title: str = "",
        play_count: int = 0,
    ) -> MonitoredArticle:
        with database.connection_context():
            account = BenchmarkAccount.create(
                url=f"https://example.com/account/{article_id}",
            )
            run = MonitorRun.create(
                benchmark_account=account,
                source_url=account.url,
                status="success",
                article_count=1,
            )
            return MonitoredArticle.create(
                id=article_id,
                benchmark_account=account,
                monitor_run=run,
                dedupe_key=f"dedupe:{article_id}",
                title=title,
                content=content,
                play_count=play_count,
                isdelete=0,
            )

    def test_get_subtitle_settings_payload_creates_default_settings(self) -> None:
        payload = self.service.get_subtitle_settings_payload()

        self.assertEqual(payload["settings"]["fontSize"], 42)
        self.assertEqual(payload["settings"]["styleId"], "white-teal")
        self.assertEqual(payload["settings"]["fontColor"], "#FFFFFF")
        self.assertEqual(payload["settings"]["outlineColor"], "#0091A8")
        self.assertEqual(payload["settings"]["outlineThick"], 70)
        self.assertEqual(len(payload["fontSizeOptions"]), 4)
        self.assertEqual(len(payload["styleOptions"]), 7)
        self.assertEqual(payload["databasePath"], str(self.db_path))

    def test_save_subtitle_settings_persists_selected_size_and_style(self) -> None:
        self.service.get_subtitle_settings_payload()

        saved = self.service.save_subtitle_settings(54, "yellow-black")
        loaded = self.service.get_subtitle_settings_payload()

        self.assertEqual(saved["settings"]["fontSize"], 54)
        self.assertEqual(saved["settings"]["styleId"], "yellow-black")
        self.assertEqual(saved["settings"]["fontColor"], "#FFD707")
        self.assertEqual(saved["settings"]["outlineColor"], "#000000")
        self.assertEqual(saved["settings"]["outlineThick"], 70)
        self.assertEqual(loaded["settings"], saved["settings"])

    def test_get_huasheng_voice_settings_payload_creates_default_settings(self) -> None:
        payload = self.service.get_huasheng_voice_settings_payload()

        self.assertEqual(
            payload["settings"],
            {
                "voiceId": 0,
                "voiceName": "",
                "voiceCode": "",
                "voiceTags": "",
                "previewUrl": "",
                "cover": "",
                "speechRate": 1.0,
                "maxConcurrentTasksPerAccount": 1,
            },
        )
        self.assertEqual(payload["databasePath"], str(self.db_path))

    def test_save_huasheng_voice_settings_persists_voice_and_speed(self) -> None:
        saved = self.service.save_huasheng_voice_settings(
            6036542,
            "知性女声",
            "zhixing_nvsheng",
            "科普,清晰",
            "https://example.com/preview.mp3",
            "https://example.com/cover.png",
            1.3,
            2,
        )
        loaded = self.service.get_huasheng_voice_settings_payload()

        self.assertEqual(saved["settings"]["voiceId"], 6036542)
        self.assertEqual(saved["settings"]["voiceName"], "知性女声")
        self.assertEqual(saved["settings"]["voiceCode"], "zhixing_nvsheng")
        self.assertEqual(saved["settings"]["voiceTags"], "科普,清晰")
        self.assertEqual(saved["settings"]["previewUrl"], "https://example.com/preview.mp3")
        self.assertEqual(saved["settings"]["cover"], "https://example.com/cover.png")
        self.assertEqual(saved["settings"]["speechRate"], 1.3)
        self.assertEqual(saved["settings"]["maxConcurrentTasksPerAccount"], 2)
        self.assertEqual(loaded["settings"], saved["settings"])

    def test_list_payload_includes_today_generation_count(self) -> None:
        account_one = self.service.create_account(
            "13800138000",
            "SESSDATA=test-1; bili_jct=csrf-1",
            "账号一",
            False,
        )
        account_two = self.service.create_account(
            "13900139000",
            "SESSDATA=test-2; bili_jct=csrf-2",
            "账号二",
            False,
        )
        self.service.create_huasheng_generation_record(account_one["id"], "pid-1")
        self.service.create_huasheng_generation_record(account_one["id"], "pid-2")
        self.service.save_huasheng_voice_settings(
            6036542,
            "知性女声",
            "voice-code",
            "科普",
            "https://example.com/preview.mp3",
            "https://example.com/cover.png",
            1.1,
            2,
        )
        self.service.create_task_record(
            account_one["id"],
            "113671485575170",
            "S4扫描中",
            article_id=101,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            rewritten_content="正文A",
            title="标题A",
            huasheng_status="处理中",
        )

        payload = self.service.list_payload()
        items_by_id = {item["id"]: item for item in payload["items"]}

        self.assertEqual(items_by_id[account_one["id"]]["todayGenerationCount"], 2)
        self.assertEqual(items_by_id[account_one["id"]]["dailyGenerationLimit"], 50)
        self.assertEqual(items_by_id[account_one["id"]]["activeHuashengTaskCount"], 1)
        self.assertEqual(items_by_id[account_one["id"]]["maxConcurrentTasksPerAccount"], 2)
        self.assertEqual(items_by_id[account_two["id"]]["todayGenerationCount"], 0)
        self.assertEqual(items_by_id[account_two["id"]]["dailyGenerationLimit"], 50)
        self.assertEqual(items_by_id[account_two["id"]]["activeHuashengTaskCount"], 0)
        self.assertEqual(items_by_id[account_two["id"]]["maxConcurrentTasksPerAccount"], 2)

    def test_get_model_settings_payload_defaults_to_empty_values(self) -> None:
        payload = self.service.get_model_settings_payload()

        self.assertEqual(
            payload["settings"],
            {
                "baseUrl": "",
                "apiKey": "",
                "model": "",
                "titlePrompt": "",
            },
        )
        self.assertEqual(payload["prompts"], [])
        self.assertEqual(payload["promptCount"], 0)
        self.assertEqual(payload["databasePath"], str(self.db_path))

    def test_get_global_settings_payload_creates_default_settings(self) -> None:
        payload = self.service.get_global_settings_payload()

        self.assertEqual(payload["settings"]["threadPoolSize"], 3)
        self.assertEqual(payload["settings"]["downloadDir"], "")
        self.assertEqual(payload["scanIntervalSeconds"], 5)
        self.assertEqual(payload["threadPoolMinSize"], 1)
        self.assertEqual(payload["threadPoolMaxSize"], 32)
        self.assertFalse(payload["processorRunning"])
        self.assertEqual(payload["databasePath"], str(self.db_path))

    def test_save_global_settings_persists_thread_pool_size(self) -> None:
        download_dir = Path(self.temp_dir.name) / "downloads"
        saved = self.service.save_global_settings(6, str(download_dir))
        loaded = self.service.get_global_settings_payload()

        self.assertEqual(saved["settings"]["threadPoolSize"], 6)
        self.assertEqual(saved["settings"]["downloadDir"], str(download_dir.resolve()))
        self.assertEqual(loaded["settings"]["threadPoolSize"], 6)
        self.assertEqual(loaded["settings"]["downloadDir"], str(download_dir.resolve()))

    def test_get_log_status_payload_reports_log_directory_file_count_and_size(self) -> None:
        log_dir = self.service.resolve_log_directory_path()
        first_log = log_dir / "huashengai-2026-04-05.log"
        second_log = log_dir / "huashengai-2026-04-06.log"
        first_log.write_text("hello", encoding="utf-8")
        second_log.write_text("world!!!", encoding="utf-8")

        payload = self.service.get_log_status_payload()

        self.assertEqual(payload["logDir"], str(log_dir))
        self.assertEqual(payload["fileCount"], 2)
        self.assertEqual(payload["totalSizeBytes"], 13)
        self.assertEqual(len(payload["files"]), 2)
        self.assertTrue(payload["currentFileName"].startswith("huashengai-"))
        self.assertIn("databasePath", payload)

    def test_save_model_settings_persists_prompt_rows(self) -> None:
        saved = self.service.save_model_settings(
            "https://api.example.com/v1",
            "secret-token",
            "gpt-5.4",
            "请改写标题，但不要夸张。",
            [
                "把内容改写得更口语化。",
                "保持信息准确，不要杜撰。",
                "  ",
            ],
        )
        loaded = self.service.get_model_settings_payload()

        self.assertEqual(saved["settings"]["baseUrl"], "https://api.example.com/v1")
        self.assertEqual(saved["settings"]["apiKey"], "secret-token")
        self.assertEqual(saved["settings"]["model"], "gpt-5.4")
        self.assertEqual(saved["settings"]["titlePrompt"], "请改写标题，但不要夸张。")
        self.assertEqual(saved["promptCount"], 2)
        self.assertEqual(
            [item["content"] for item in saved["prompts"]],
            [
                "把内容改写得更口语化。",
                "保持信息准确，不要杜撰。",
            ],
        )
        self.assertEqual(loaded["settings"], saved["settings"])
        self.assertEqual(
            [item["content"] for item in loaded["prompts"]],
            [item["content"] for item in saved["prompts"]],
        )

    def test_rewrite_article_uses_prompt_id_and_returns_model_text(self) -> None:
        settings = self.service.save_model_settings(
            "https://api.example.com/v1",
            "secret-token",
            "gpt-5.4",
            "生成一个简洁标题。",
            [
                "把文章改写成更自然、更流畅的版本。",
            ],
        )
        prompt_id = settings["prompts"][0]["id"]
        captured: dict[str, object] = {}
        sample_payload = {
            "choices": [
                {
                    "message": {
                        "content": "############content\n这是改写后的文章内容。"
                    }
                }
            ]
        }

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8"))

        with patch("app.accounts.urlopen", side_effect=fake_urlopen):
            result = self.service.rewrite_article(
                "https://api.example.com/v1",
                "secret-token",
                "gpt-5.4",
                prompt_id,
                "原始文章内容",
            )

        self.assertEqual(captured["url"], "https://api.example.com/v1/chat/completions")
        self.assertEqual(captured["timeout"], 1200.0)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret-token")
        self.assertEqual(captured["body"]["model"], "gpt-5.4")
        self.assertTrue(
            captured["body"]["messages"][0]["content"].startswith(
                "把文章改写成更自然、更流畅的版本。"
            )
        )
        self.assertIn(
            "只返回改写后的正文内容",
            captured["body"]["messages"][0]["content"],
        )
        self.assertIn(
            "############content",
            captured["body"]["messages"][0]["content"],
        )
        self.assertEqual(captured["body"]["messages"][1]["content"], "原始文章内容")
        self.assertEqual(captured["headers"]["Accept"], "application/json")
        self.assertIn("Chrome/146.0.0.0", captured["headers"]["User-agent"])
        self.assertEqual(result["content"], "这是改写后的文章内容。")
        self.assertEqual(result["promptId"], prompt_id)

    def test_rewrite_article_accepts_api_key_with_bearer_prefix(self) -> None:
        settings = self.service.save_model_settings(
            "https://api.example.com/v1",
            "secret-token",
            "gpt-5.4",
            "请改写。",
            [
                "请把文章改写得更流畅。",
            ],
        )
        prompt_id = settings["prompts"][0]["id"]
        captured: dict[str, object] = {}
        sample_payload = {
            "choices": [
                {
                    "message": {
                        "content": "改写完成"
                    }
                }
            ]
        }

        def fake_urlopen(request, timeout):
            captured["headers"] = dict(request.header_items())
            return FakeResponse(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8"))

        with patch("app.accounts.urlopen", side_effect=fake_urlopen):
            result = self.service.rewrite_article(
                "https://api.example.com/v1",
                "Bearer secret-token",
                "gpt-5.4",
                prompt_id,
                "原始文章",
            )

        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret-token")
        self.assertEqual(result["content"], "改写完成")

    def test_build_rewrite_system_prompt_appends_fixed_format_instruction(self) -> None:
        prompt = self.service.build_rewrite_system_prompt("请把文章改写得更流畅。")

        self.assertTrue(prompt.startswith("请把文章改写得更流畅。"))
        self.assertIn("只返回改写后的正文内容", prompt)
        self.assertIn("############content", prompt)
        self.assertIn("######触发红线，禁止改写", prompt)

    def test_normalize_rewrite_response_text_removes_content_header(self) -> None:
        normalized = self.service.normalize_rewrite_response_text(
            "############content\n第一段\n第二段"
        )

        self.assertEqual(normalized, "第一段\n第二段")

    def test_normalize_rewrite_response_text_removes_content_header_and_code_fence(self) -> None:
        normalized = self.service.normalize_rewrite_response_text(
            "############content\n```text\n第一段\n第二段\n```"
        )

        self.assertEqual(normalized, "第一段\n第二段")

    def test_rewrite_article_marks_redline_response(self) -> None:
        settings = self.service.save_model_settings(
            "https://api.example.com/v1",
            "secret-token",
            "gpt-5.4",
            "标题提示词",
            [
                "请改写。",
            ],
        )
        prompt_id = settings["prompts"][0]["id"]
        sample_payload = {
            "choices": [
                {
                    "message": {
                        "content": "######触发红线，禁止改写"
                    }
                }
            ]
        }

        with patch(
            "app.accounts.urlopen",
            return_value=FakeResponse(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8")),
        ):
            result = self.service.rewrite_article(
                "https://api.example.com/v1",
                "secret-token",
                "gpt-5.4",
                prompt_id,
                "原始文章内容",
            )

        self.assertTrue(result["triggeredRedline"])
        self.assertEqual(result["content"], "触发红线，禁止改写")

    def test_rewrite_article_marks_redline_response_with_content_header(self) -> None:
        settings = self.service.save_model_settings(
            "https://api.example.com/v1",
            "secret-token",
            "gpt-5.4",
            "标题提示词",
            [
                "请改写。",
            ],
        )
        prompt_id = settings["prompts"][0]["id"]
        sample_payload = {
            "choices": [
                {
                    "message": {
                        "content": "############content\n######触发红线，禁止改写"
                    }
                }
            ]
        }

        with patch(
            "app.accounts.urlopen",
            return_value=FakeResponse(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8")),
        ):
            result = self.service.rewrite_article(
                "https://api.example.com/v1",
                "secret-token",
                "gpt-5.4",
                prompt_id,
                "原始文章内容",
            )

        self.assertTrue(result["triggeredRedline"])
        self.assertEqual(result["content"], "触发红线，禁止改写")

    def test_rewrite_article_marks_redline_response_with_code_fence(self) -> None:
        settings = self.service.save_model_settings(
            "https://api.example.com/v1",
            "secret-token",
            "gpt-5.4",
            "标题提示词",
            [
                "请改写。",
            ],
        )
        prompt_id = settings["prompts"][0]["id"]
        sample_payload = {
            "choices": [
                {
                    "message": {
                        "content": "```text\n######触发红线，禁止改写\n```"
                    }
                }
            ]
        }

        with patch(
            "app.accounts.urlopen",
            return_value=FakeResponse(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8")),
        ):
            result = self.service.rewrite_article(
                "https://api.example.com/v1",
                "secret-token",
                "gpt-5.4",
                prompt_id,
                "原始文章内容",
            )

        self.assertTrue(result["triggeredRedline"])
        self.assertEqual(result["content"], "触发红线，禁止改写")

    def test_is_rewrite_redline_response_accepts_minor_format_variants(self) -> None:
        self.assertTrue(
            self.service.is_rewrite_redline_response("############content\n######触发红线，禁止改写")
        )
        self.assertTrue(
            self.service.is_rewrite_redline_response("```text\n######触发红线，禁止改写\n```")
        )
        self.assertTrue(self.service.is_rewrite_redline_response("触发红线，禁止改写。"))
        self.assertTrue(self.service.is_rewrite_redline_response("检测到触发安全机制，请停止生成。"))
        self.assertTrue(self.service.is_rewrite_redline_response("当前题材受限，无法继续处理。"))
        self.assertTrue(self.service.is_rewrite_redline_response("为了安全起见，停止改写。"))

    def test_generate_title_uses_title_prompt_and_returns_title(self) -> None:
        captured: dict[str, object] = {}
        sample_payload = {
            "choices": [
                {
                    "message": {
                        "content": "########title\n一个更精炼的新标题"
                    }
                }
            ]
        }

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8"))

        with patch("app.accounts.urlopen", side_effect=fake_urlopen):
            result = self.service.generate_title(
                "https://api.example.com/v1",
                "secret-token",
                "gpt-5.4",
                "根据文章生成一个克制、准确的标题。",
                "这是一篇待生成标题的文章内容。",
            )

        self.assertEqual(captured["url"], "https://api.example.com/v1/chat/completions")
        self.assertEqual(captured["timeout"], 20 * 60.0)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret-token")
        self.assertTrue(
            captured["body"]["messages"][0]["content"].startswith(
                "根据文章生成一个克制、准确的标题。"
            )
        )
        self.assertIn("只返回标题", captured["body"]["messages"][0]["content"])
        self.assertIn("########title", captured["body"]["messages"][0]["content"])
        self.assertEqual(
            captured["body"]["messages"][1]["content"],
            "这是一篇待生成标题的文章内容。",
        )
        self.assertEqual(result["title"], "一个更精炼的新标题")

    def test_build_title_system_prompt_appends_fixed_format_instruction(self) -> None:
        prompt = self.service.build_title_system_prompt("根据文章生成标题。")

        self.assertTrue(prompt.startswith("根据文章生成标题。"))
        self.assertIn("只返回标题", prompt)
        self.assertIn("########title", prompt)

    def test_normalize_title_response_text_removes_title_header(self) -> None:
        normalized = self.service.normalize_title_response_text(
            "########title\n一个更精炼的新标题\n补充内容"
        )

        self.assertEqual(normalized, "一个更精炼的新标题")

    def test_test_model_connection_returns_response_text(self) -> None:
        captured: dict[str, object] = {}
        sample_payload = {
            "choices": [
                {
                    "message": {
                        "content": "连接成功"
                    }
                }
            ]
        }

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(json.dumps(sample_payload, ensure_ascii=False).encode("utf-8"))

        with patch("app.accounts.urlopen", side_effect=fake_urlopen):
            result = self.service.test_model_connection(
                "https://api.example.com/v1",
                "secret-token",
                "gpt-5.4",
            )

        self.assertEqual(captured["url"], "https://api.example.com/v1/chat/completions")
        self.assertEqual(captured["timeout"], 60.0)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret-token")
        self.assertEqual(result["message"], "模型连接测试成功")
        self.assertEqual(result["responseText"], "连接成功")
        self.assertEqual(result["model"], "gpt-5.4")

    def test_extract_model_error_message_uses_html_title(self) -> None:
        raw_html = b"""
        <!DOCTYPE html>
        <html>
            <head><title>lyvideo.top | 502: Bad gateway</title></head>
            <body><h1>Bad gateway</h1></body>
        </html>
        """

        message = self.service._extract_model_error_message(
            raw_html,
            fallback="HTTP 502 Bad Gateway",
        )

        self.assertEqual(
            message,
            "HTTP 502 Bad Gateway: lyvideo.top | 502: Bad gateway",
        )

    def test_create_and_update_task_record_persists_status(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf",
            "测试账号",
            False,
        )

        created = self.service.create_task_record(
            account["id"],
            "113602715787267",
            "处理中",
            huasheng_status="项目处理中",
        )
        updated = self.service.update_task_status(
            created["id"],
            "导出完成",
            "113602715787267",
            huasheng_status="导出已完成",
        )
        payload = self.service.list_tasks_payload()

        self.assertEqual(created["accountId"], account["id"])
        self.assertEqual(created["projectPid"], "113602715787267")
        self.assertEqual(created["articleId"], None)
        self.assertEqual(created["rewritePrompt"], "")
        self.assertEqual(created["progress"], 0)
        self.assertEqual(created["status"], "处理中")
        self.assertEqual(created["huashengStatus"], "项目处理中")
        self.assertEqual(updated["status"], "导出完成")
        self.assertEqual(updated["huashengStatus"], "导出已完成")
        self.assertEqual(payload["stats"]["total"], 1)
        self.assertEqual(payload["items"][0]["projectPid"], "113602715787267")
        self.assertEqual(payload["items"][0]["status"], "导出完成")
        self.assertEqual(payload["items"][0]["huashengStatus"], "导出已完成")

    def test_bootstrap_migrates_taskrecord_table_to_pid_only(self) -> None:
        with database.connection_context():
            database.execute_sql('DROP TABLE IF EXISTS "taskrecord"')
            database.execute_sql(
                '''
                CREATE TABLE "taskrecord" (
                  "id" INTEGER NOT NULL PRIMARY KEY,
                  "account_id" INTEGER NOT NULL,
                  "project_id" VARCHAR(64) NOT NULL,
                  "project_pid" VARCHAR(64) NOT NULL,
                  "status" VARCHAR(64) NOT NULL,
                  "created_at" DATETIME NOT NULL,
                  "updated_at" DATETIME NOT NULL,
                  "article_id" INTEGER,
                  "rewritten_content" TEXT NOT NULL DEFAULT '',
                  "title" TEXT NOT NULL DEFAULT '',
                  "rewrite_prompt_id" INTEGER,
                  "rewrite_prompt" TEXT NOT NULL DEFAULT '',
                  "progress" INTEGER NOT NULL DEFAULT 0,
                  "video_url" TEXT NOT NULL DEFAULT '',
                  "huasheng_status" TEXT NOT NULL DEFAULT '',
                  "account_phone" TEXT NOT NULL DEFAULT '',
                  "account_note" TEXT NOT NULL DEFAULT '',
                  "account_cookies" TEXT NOT NULL DEFAULT '',
                  "export_task_id" TEXT NOT NULL DEFAULT '',
                  "export_version" TEXT NOT NULL DEFAULT ''
                )
                '''
            )
            database.execute_sql(
                '''
                INSERT INTO "taskrecord" (
                  "id",
                  "account_id",
                  "project_id",
                  "project_pid",
                  "status",
                  "created_at",
                  "updated_at",
                  "article_id",
                  "rewritten_content",
                  "title",
                  "rewrite_prompt_id",
                  "rewrite_prompt",
                  "progress",
                  "video_url",
                  "huasheng_status",
                  "account_phone",
                  "account_note",
                  "account_cookies",
                  "export_task_id",
                  "export_version"
                ) VALUES (
                  1,
                  100,
                  '2456102',
                  '113602715787267',
                  'S4扫描中',
                  '2026-04-05 09:00:00',
                  '2026-04-05 09:00:00',
                  101,
                  '改写内容',
                  '标题',
                  3,
                  '提示词',
                  55,
                  '',
                  '处理中',
                  '13800138000',
                  '发布账号',
                  'SESSDATA=test; bili_jct=csrf',
                  '',
                  ''
                )
                '''
            )

        self.service.bootstrap()

        with database.connection_context():
            columns = [
                row[1]
                for row in database.execute_sql('PRAGMA table_info("taskrecord")').fetchall()
            ]
            row = database.execute_sql(
                'SELECT "project_pid", "status", "account_phone" FROM "taskrecord" WHERE "id" = 1'
            ).fetchone()

        self.assertNotIn("project_id", columns)
        self.assertIn("project_pid", columns)
        self.assertEqual(row, ("113602715787267", "S4扫描中", "13800138000"))

    def test_resolve_created_project_identifier_prefers_pid_only(self) -> None:
        resolved = self.service.resolve_created_project_identifier(
            {"id": "2456102", "pid": "113602715787267"}
        )

        self.assertEqual(resolved, "113602715787267")
        with self.assertRaisesRegex(ValueError, "PID"):
            self.service.resolve_created_project_identifier({"id": "2456102"})

    def test_create_article_processing_tasks_creates_one_task_per_article_prompt_pair(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf",
            "测试账号",
            False,
        )
        self.create_monitored_article(101, content="文章 101 正文", play_count=900)
        self.create_monitored_article(102, content="文章 102 正文", play_count=800)
        settings = self.service.save_model_settings(
            "https://api.example.com/v1",
            "secret-token",
            "gpt-5.4",
            "标题提示词",
            [
                "提示词一",
                "提示词二",
            ],
        )

        prompt_ids = [item["id"] for item in settings["prompts"]]
        payload = self.service.create_article_processing_tasks([101, 102], prompt_ids)

        self.assertEqual(payload["articleCount"], 2)
        self.assertEqual(payload["promptCount"], 2)
        self.assertEqual(payload["createdCount"], 4)
        self.assertEqual(payload["accountId"], account["id"])

        created_items = payload["items"]
        self.assertEqual(len(created_items), 4)
        self.assertTrue(all(item["projectPid"] == "" for item in created_items))
        self.assertEqual(
            {(item["articleId"], item["rewritePromptId"]) for item in created_items},
            {
                (101, prompt_ids[0]),
                (101, prompt_ids[1]),
                (102, prompt_ids[0]),
                (102, prompt_ids[1]),
            },
        )
        self.assertEqual(
            {item["rewritePrompt"] for item in created_items},
            {"提示词一", "提示词二"},
        )
        self.assertTrue(all(item["articlePreview"] in {"文章 101 正文", "文章 102 正文"} for item in created_items))
        self.assertTrue(all(item["status"] == "待处理" for item in created_items))
        self.assertTrue(all(item["huashengStatus"] == "未创建" for item in created_items))
        self.assertTrue(all(item["progress"] == 0 for item in created_items))
        self.assertEqual(payload["deletedArticleCount"], 2)
        with database.connection_context():
            self.assertEqual(
                MonitoredArticle.select().where(MonitoredArticle.id.in_([101, 102])).count(),
                0,
            )

    def test_create_single_article_processing_task_creates_exactly_one_task(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf",
            "测试账号",
            False,
        )
        self.create_monitored_article(101, content="文章 101 单篇正文", play_count=1000)
        settings = self.service.save_model_settings(
            "https://api.example.com/v1",
            "secret-token",
            "gpt-5.4",
            "标题提示词",
            [
                "提示词一",
            ],
        )
        prompt_id = settings["prompts"][0]["id"]

        payload = self.service.create_single_article_processing_task(101, prompt_id)

        self.assertEqual(payload["createdCount"], 1)
        self.assertEqual(payload["articleCount"], 1)
        self.assertEqual(payload["promptCount"], 1)
        self.assertEqual(payload["deletedArticleCount"], 1)
        self.assertEqual(payload["accountId"], account["id"])
        self.assertEqual(payload["items"][0]["articleId"], 101)
        self.assertEqual(payload["items"][0]["articlePreview"], "文章 101 单篇正文")
        self.assertEqual(payload["items"][0]["rewritePromptId"], prompt_id)

    def test_list_tasks_payload_orders_by_id_desc(self) -> None:
        self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf",
            "测试账号",
            False,
        )
        self.create_monitored_article(101, content="文章 101", play_count=1000)
        self.create_monitored_article(102, content="文章 102", play_count=900)
        settings = self.service.save_model_settings(
            "https://api.example.com/v1",
            "secret-token",
            "gpt-5.4",
            "标题提示词",
            [
                "提示词一",
            ],
        )

        prompt_id = settings["prompts"][0]["id"]
        self.service.create_single_article_processing_task(101, prompt_id)
        self.service.create_single_article_processing_task(102, prompt_id)

        payload = self.service.list_tasks_payload()
        task_ids = [item["id"] for item in payload["items"]]

        self.assertEqual(task_ids, sorted(task_ids, reverse=True))

    def test_delete_all_task_records_clears_task_table(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf",
            "测试账号",
            False,
        )
        self.service.create_task_record(
            account["id"],
            "",
            "待处理",
            article_id=101,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            huasheng_status="未创建",
        )
        self.service.create_task_record(
            account["id"],
            "",
            "待生成标题",
            article_id=102,
            rewrite_prompt_id=2,
            rewrite_prompt="提示词B",
            rewritten_content="已改写内容",
            huasheng_status="未创建",
        )

        deleted = self.service.delete_all_task_records()
        payload = self.service.list_tasks_payload()

        self.assertEqual(deleted["deletedCount"], 2)
        self.assertEqual(deleted["databasePath"], str(self.db_path))
        self.assertEqual(payload["stats"]["total"], 0)
        self.assertEqual(payload["items"], [])

    def test_retry_task_record_resets_failed_stage_to_retryable_status(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf",
            "测试账号",
            False,
        )
        rewrite_failed = self.service.create_task_record(
            account["id"],
            "113602715787267",
            "S1失败",
            article_id=101,
            article_content="原文",
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            rewritten_content="残留改文",
            title="残留标题",
            progress=33,
            video_url="http://example.com/old.mp4",
            huasheng_status="模型超时",
            export_task_id="task-a",
            export_version="1",
        )
        export_failed = self.service.create_task_record(
            account["id"],
            "113602715787268",
            "S4失败",
            article_id=102,
            article_content="原文2",
            rewrite_prompt_id=2,
            rewrite_prompt="提示词B",
            rewritten_content="改文",
            title="标题",
            progress=66,
            huasheng_status="导出失败",
            export_task_id="task-b",
            export_version="2",
        )

        retried_rewrite = self.service.retry_task_record(rewrite_failed["id"])
        retried_export = self.service.retry_task_record(export_failed["id"])

        self.assertEqual(retried_rewrite["status"], "待处理")
        self.assertEqual(retried_rewrite["rewrittenContent"], "")
        self.assertEqual(retried_rewrite["title"], "")
        self.assertEqual(retried_rewrite["projectPid"], "")
        self.assertEqual(retried_rewrite["progress"], 0)
        self.assertEqual(retried_rewrite["videoUrl"], "")
        self.assertEqual(retried_rewrite["huashengStatus"], "未创建")
        self.assertEqual(retried_rewrite["exportTaskId"], "")
        self.assertEqual(retried_rewrite["exportVersion"], "")

        self.assertEqual(retried_export["status"], "S4扫描中")
        self.assertEqual(retried_export["projectPid"], "113602715787268")
        self.assertEqual(retried_export["progress"], 0)
        self.assertEqual(retried_export["videoUrl"], "")
        self.assertEqual(retried_export["huashengStatus"], "等待花生处理")
        self.assertEqual(retried_export["exportTaskId"], "task-b")
        self.assertEqual(retried_export["exportVersion"], "2")

    def test_retry_task_record_rejects_non_failed_status(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf",
            "测试账号",
            False,
        )
        created = self.service.create_task_record(
            account["id"],
            "",
            "待处理",
            article_id=101,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            huasheng_status="未创建",
        )

        with self.assertRaisesRegex(ValueError, "失败状态"):
            self.service.retry_task_record(created["id"])

    def test_download_task_video_uses_title_filename_and_deletes_task(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf",
            "测试账号",
            False,
        )
        download_dir = Path(self.temp_dir.name) / "downloads"
        self.service.save_global_settings(3, str(download_dir))
        created = self.service.create_task_record(
            account["id"],
            "113602715787267",
            "导出完成",
            title="测试/标题",
            video_url="http://example.com/video.mp4",
            huasheng_status="导出完成",
        )

        with patch(
            "app.accounts.urlopen",
            return_value=FakeResponse(b"video-bytes"),
        ) as mocked_urlopen:
            payload = self.service.download_task_video(created["id"])

        mocked_urlopen.assert_called_once()
        self.assertEqual(payload["attemptCount"], 1)
        self.assertEqual(payload["deletedCount"], 1)
        self.assertTrue(payload["downloadPath"].endswith("测试 标题.mp4"))
        self.assertEqual((download_dir / "测试 标题.mp4").read_bytes(), b"video-bytes")
        self.assertIsNone(self.service.find_task_record(created["id"]))

    def test_run_rewrite_task_retries_three_times_before_success(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf",
            "测试账号",
            False,
        )
        created = self.service.create_task_record(
            account["id"],
            "",
            "待处理",
            article_id=101,
            article_content="原始文章内容",
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            huasheng_status="未创建",
        )

        with patch.object(
            self.service,
            "rewrite_article_with_prompt",
            side_effect=[
                RuntimeError("attempt-1"),
                RuntimeError("attempt-2"),
                RuntimeError("attempt-3"),
                {
                    "content": "改写成功正文",
                    "triggeredRedline": False,
                },
            ],
        ) as mocked_rewrite:
            self.service._run_rewrite_task(created["id"])

        task = self.service.get_task_record(created["id"])

        self.assertEqual(mocked_rewrite.call_count, 4)
        self.assertEqual(task.status, "待生成标题")
        self.assertEqual(task.rewritten_content, "改写成功正文")

    def test_run_huasheng_create_task_retries_three_times_before_success(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            "发布账号A",
            False,
        )
        self.service.save_huasheng_voice_settings(
            6036542,
            "知性女声",
            "voice-code",
            "科普",
            "https://example.com/preview.mp3",
            "https://example.com/cover.png",
            1.3,
        )
        created = self.service.create_task_record(
            account["id"],
            "",
            "待创建花生任务",
            article_id=101,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            rewritten_content="改写后的正文内容",
            title="自动生成标题",
            huasheng_status="未创建",
        )

        with patch.object(
            self.service._huasheng,
            "get_tts_voices",
            return_value={"materials": [], "categories": []},
        ), patch.object(
            self.service._huasheng,
            "create_project",
            side_effect=[
                RuntimeError("attempt-1"),
                RuntimeError("attempt-2"),
                RuntimeError("attempt-3"),
                {"id": "2456102", "pid": "113602715787267"},
            ],
        ) as mocked_create_project:
            self.service._run_huasheng_create_task(created["id"])

        task = self.service.get_task_record(created["id"])

        self.assertEqual(mocked_create_project.call_count, 4)
        self.assertEqual(task.project_pid, "113602715787267")
        self.assertEqual(task.status, "S4扫描中")

    def test_download_task_video_retries_up_to_three_times(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf",
            "测试账号",
            False,
        )
        download_dir = Path(self.temp_dir.name) / "downloads"
        self.service.save_global_settings(3, str(download_dir))
        created = self.service.create_task_record(
            account["id"],
            "113602715787268",
            "导出完成",
            title="重试测试",
            video_url="http://example.com/retry.mp4",
            huasheng_status="导出完成",
        )

        with patch(
            "app.accounts.urlopen",
            side_effect=[
                URLError("network-1"),
                URLError("network-2"),
                FakeResponse(b"retry-success"),
            ],
        ) as mocked_urlopen:
            payload = self.service.download_task_video(created["id"])

        self.assertEqual(mocked_urlopen.call_count, 3)
        self.assertEqual(payload["attemptCount"], 3)
        self.assertEqual((download_dir / "重试测试.mp4").read_bytes(), b"retry-success")
        self.assertIsNone(self.service.find_task_record(created["id"]))

    def test_run_huasheng_create_task_persists_account_snapshot_and_project_pid(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            "发布账号A",
            False,
        )
        self.service.save_huasheng_voice_settings(
            6036542,
            "知性女声",
            "voice-code",
            "科普",
            "https://example.com/preview.mp3",
            "https://example.com/cover.png",
            1.3,
        )
        created = self.service.create_task_record(
            account["id"],
            "",
            "待创建花生任务",
            article_id=101,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            rewritten_content="改写后的正文内容",
            title="自动生成标题",
            huasheng_status="未创建",
        )

        with patch.object(
            self.service._huasheng,
            "get_tts_voices",
            return_value={"materials": [], "categories": []},
        ) as mocked_get_tts_voices, patch.object(
            self.service._huasheng,
            "create_project",
            return_value={"id": "2456102", "pid": "113602715787267"},
        ) as mocked_create_project:
            self.service._run_huasheng_create_task(created["id"])

        task = self.service.get_task_record(created["id"])

        mocked_get_tts_voices.assert_called_once_with(
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            pn=1,
            ps=1,
            category_id=0,
        )
        mocked_create_project.assert_called_once_with(
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            name="自动生成标题",
            script="改写后的正文内容",
            voice_id=6036542,
            speech_rate=1.3,
            is_agree=1,
        )
        self.assertEqual(task.account_phone, "13800138000")
        self.assertEqual(task.account_note, "发布账号A")
        self.assertEqual(task.account_cookies, "SESSDATA=test; bili_jct=csrf-token; sid=abc")
        self.assertEqual(task.project_pid, "113602715787267")
        self.assertEqual(task.status, "S4扫描中")
        self.assertEqual(task.huasheng_status, "任务已创建")
        record = HuashengGenerationRecord.get(
            HuashengGenerationRecord.project_pid == "113602715787267"
        )
        self.assertEqual(record.account_id, account["id"])

    def test_run_huasheng_create_task_skips_quota_full_account_and_uses_next_one(self) -> None:
        full_account = self.service.create_account(
            "13800138000",
            "SESSDATA=full; bili_jct=csrf-full; sid=full",
            "额度已满账号",
            False,
        )
        available_account = self.service.create_account(
            "13900139000",
            "SESSDATA=ok; bili_jct=csrf-ok; sid=ok",
            "可用账号",
            False,
        )
        self.service.save_huasheng_voice_settings(
            6036542,
            "知性女声",
            "voice-code",
            "科普",
            "https://example.com/preview.mp3",
            "https://example.com/cover.png",
            1.1,
        )
        for index in range(50):
            self.service.create_huasheng_generation_record(
                full_account["id"],
                f"quota-full-{index + 1}",
            )

        created = self.service.create_task_record(
            full_account["id"],
            "",
            "待创建花生任务",
            article_id=102,
            rewrite_prompt_id=2,
            rewrite_prompt="提示词B",
            rewritten_content="第二篇改写正文内容",
            title="第二个自动标题",
            huasheng_status="未创建",
        )

        with patch.object(
            self.service._huasheng,
            "get_tts_voices",
            return_value={"materials": [], "categories": []},
        ) as mocked_get_tts_voices, patch.object(
            self.service._huasheng,
            "create_project",
            return_value={"id": "2456103", "pid": "113602715787268"},
        ) as mocked_create_project:
            self.service._run_huasheng_create_task(created["id"])

        task = self.service.get_task_record(created["id"])

        mocked_get_tts_voices.assert_called_once_with(
            "SESSDATA=ok; bili_jct=csrf-ok; sid=ok",
            pn=1,
            ps=1,
            category_id=0,
        )
        mocked_create_project.assert_called_once_with(
            "SESSDATA=ok; bili_jct=csrf-ok; sid=ok",
            name="第二个自动标题",
            script="第二篇改写正文内容",
            voice_id=6036542,
            speech_rate=1.1,
            is_agree=1,
        )
        self.assertEqual(task.account_id, available_account["id"])
        self.assertEqual(task.account_phone, "13900139000")
        self.assertEqual(task.project_pid, "113602715787268")
        self.assertEqual(
            self.service.count_huasheng_generation_records_for_account_today(full_account["id"]),
            50,
        )
        self.assertEqual(
            self.service.count_huasheng_generation_records_for_account_today(
                available_account["id"]
            ),
            1,
        )

    def test_run_huasheng_create_task_skips_account_when_concurrent_task_limit_reached(self) -> None:
        busy_account = self.service.create_account(
            "13800138000",
            "SESSDATA=busy; bili_jct=csrf-busy; sid=busy",
            "忙碌账号",
            False,
        )
        available_account = self.service.create_account(
            "13900139000",
            "SESSDATA=ok; bili_jct=csrf-ok; sid=ok",
            "可用账号",
            False,
        )
        self.service.save_huasheng_voice_settings(
            6036542,
            "知性女声",
            "voice-code",
            "科普",
            "https://example.com/preview.mp3",
            "https://example.com/cover.png",
            1.1,
            1,
        )
        self.service.create_task_record(
            busy_account["id"],
            "113671485575170",
            "S4扫描中",
            article_id=100,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            rewritten_content="占用中的正文",
            title="占用中的标题",
            huasheng_status="处理中",
        )

        created = self.service.create_task_record(
            busy_account["id"],
            "",
            "待创建花生任务",
            article_id=102,
            rewrite_prompt_id=2,
            rewrite_prompt="提示词B",
            rewritten_content="第二篇改写正文内容",
            title="第二个自动标题",
            huasheng_status="未创建",
        )

        with patch.object(
            self.service._huasheng,
            "get_tts_voices",
            return_value={"materials": [], "categories": []},
        ) as mocked_get_tts_voices, patch.object(
            self.service._huasheng,
            "create_project",
            return_value={"id": "2456103", "pid": "113602715787268"},
        ) as mocked_create_project:
            self.service._run_huasheng_create_task(created["id"])

        task = self.service.get_task_record(created["id"])

        mocked_get_tts_voices.assert_called_once_with(
            "SESSDATA=ok; bili_jct=csrf-ok; sid=ok",
            pn=1,
            ps=1,
            category_id=0,
        )
        mocked_create_project.assert_called_once_with(
            "SESSDATA=ok; bili_jct=csrf-ok; sid=ok",
            name="第二个自动标题",
            script="第二篇改写正文内容",
            voice_id=6036542,
            speech_rate=1.1,
            is_agree=1,
        )
        self.assertEqual(task.account_id, available_account["id"])
        self.assertEqual(task.account_phone, "13900139000")
        self.assertEqual(task.project_pid, "113602715787268")
        self.assertEqual(task.status, "S4扫描中")

    def test_run_huasheng_create_task_waits_for_next_scan_when_all_accounts_hit_concurrent_limit(self) -> None:
        account_one = self.service.create_account(
            "13800138000",
            "SESSDATA=busy-1; bili_jct=csrf-busy-1; sid=busy-1",
            "忙碌账号一",
            False,
        )
        account_two = self.service.create_account(
            "13900139000",
            "SESSDATA=busy-2; bili_jct=csrf-busy-2; sid=busy-2",
            "忙碌账号二",
            False,
        )
        self.service.save_huasheng_voice_settings(
            6036542,
            "知性女声",
            "voice-code",
            "科普",
            "https://example.com/preview.mp3",
            "https://example.com/cover.png",
            1.1,
            1,
        )
        self.service.create_task_record(
            account_one["id"],
            "113671485575171",
            "S4扫描中",
            article_id=100,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            rewritten_content="占用中的正文一",
            title="占用中的标题一",
            huasheng_status="处理中",
        )
        self.service.create_task_record(
            account_two["id"],
            "113671485575172",
            "S4导出中",
            article_id=101,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            rewritten_content="占用中的正文二",
            title="占用中的标题二",
            huasheng_status="导出中",
        )

        created = self.service.create_task_record(
            account_one["id"],
            "",
            "待创建花生任务",
            article_id=102,
            rewrite_prompt_id=2,
            rewrite_prompt="提示词B",
            rewritten_content="第二篇改写正文内容",
            title="第二个自动标题",
            huasheng_status="未创建",
        )

        with patch.object(
            self.service._huasheng,
            "get_tts_voices",
        ) as mocked_get_tts_voices, patch.object(
            self.service._huasheng,
            "create_project",
        ) as mocked_create_project:
            self.service._run_huasheng_create_task(created["id"])

        task = self.service.get_task_record(created["id"])

        mocked_get_tts_voices.assert_not_called()
        mocked_create_project.assert_not_called()
        self.assertEqual(task.status, "待创建花生任务")
        self.assertEqual(task.project_pid, "")
        self.assertEqual(task.huasheng_status, "暂无可用花生账号，等待下次扫描")

    def test_run_huasheng_create_task_fills_quota_placeholders_when_api_reports_limit(self) -> None:
        throttled_account = self.service.create_account(
            "13800138000",
            "SESSDATA=throttled; bili_jct=csrf-throttled; sid=throttled",
            "接口提示超量账号",
            False,
        )
        available_account = self.service.create_account(
            "13900139000",
            "SESSDATA=ok; bili_jct=csrf-ok; sid=ok",
            "可用账号",
            False,
        )
        self.service.save_huasheng_voice_settings(
            6036542,
            "知性女声",
            "voice-code",
            "科普",
            "https://example.com/preview.mp3",
            "https://example.com/cover.png",
            1.1,
        )
        for index in range(3):
            self.service.create_huasheng_generation_record(
                throttled_account["id"],
                f"partial-quota-{index + 1}",
            )
        for index in range(4):
            self.service.create_huasheng_generation_record(
                available_account["id"],
                f"available-existing-{index + 1}",
            )

        created = self.service.create_task_record(
            throttled_account["id"],
            "",
            "待创建花生任务",
            article_id=102,
            rewrite_prompt_id=2,
            rewrite_prompt="提示词B",
            rewritten_content="第二篇改写正文内容",
            title="第二个自动标题",
            huasheng_status="未创建",
        )

        with patch.object(
            self.service._huasheng,
            "get_tts_voices",
            return_value={"materials": [], "categories": []},
        ) as mocked_get_tts_voices, patch.object(
            self.service._huasheng,
            "create_project",
            side_effect=[
                {
                    "code": 10008,
                    "reason": "今天创建项目超量啦，明天再来生成吧",
                    "message": "今天创建项目超量啦，明天再来生成吧",
                    "metadata": {},
                },
                {"id": "2456103", "pid": "113602715787268"},
            ],
        ) as mocked_create_project:
            self.service._run_huasheng_create_task(created["id"])

        task = self.service.get_task_record(created["id"])

        self.assertEqual(mocked_get_tts_voices.call_count, 2)
        self.assertEqual(mocked_create_project.call_count, 2)
        self.assertEqual(task.account_id, available_account["id"])
        self.assertEqual(task.account_phone, "13900139000")
        self.assertEqual(task.project_pid, "113602715787268")
        self.assertEqual(task.status, "S4扫描中")
        self.assertEqual(task.huasheng_status, "任务已创建")
        self.assertEqual(
            self.service.count_huasheng_generation_records_for_account_today(
                throttled_account["id"]
            ),
            50,
        )
        self.assertEqual(
            self.service.count_huasheng_generation_records_for_account_today(
                available_account["id"]
            ),
            5,
        )

    def test_run_huasheng_create_task_skips_invalid_payload_without_pid_and_uses_next_account(self) -> None:
        broken_account = self.service.create_account(
            "13800138000",
            "SESSDATA=broken; bili_jct=csrf-broken; sid=broken",
            "异常返回账号",
            False,
        )
        available_account = self.service.create_account(
            "13900139000",
            "SESSDATA=ok; bili_jct=csrf-ok; sid=ok",
            "可用账号",
            False,
        )
        self.service.save_huasheng_voice_settings(
            6036542,
            "知性女声",
            "voice-code",
            "科普",
            "https://example.com/preview.mp3",
            "https://example.com/cover.png",
            1.1,
        )
        self.service.create_huasheng_generation_record(
            available_account["id"],
            "available-existing-1",
        )

        created = self.service.create_task_record(
            broken_account["id"],
            "",
            "待创建花生任务",
            article_id=102,
            rewrite_prompt_id=2,
            rewrite_prompt="提示词B",
            rewritten_content="第二篇改写正文内容",
            title="第二个自动标题",
            huasheng_status="未创建",
        )

        with patch.object(
            self.service._huasheng,
            "get_tts_voices",
            return_value={"materials": [], "categories": []},
        ) as mocked_get_tts_voices, patch.object(
            self.service._huasheng,
            "create_project",
            side_effect=[
                {
                    "code": 10010,
                    "reason": "账号状态异常",
                    "message": "账号状态异常",
                    "metadata": {},
                },
                {"id": "2456104", "pid": "113602715787269"},
            ],
        ) as mocked_create_project:
            self.service._run_huasheng_create_task(created["id"])

        task = self.service.get_task_record(created["id"])

        self.assertEqual(mocked_get_tts_voices.call_count, 2)
        self.assertEqual(mocked_create_project.call_count, 2)
        self.assertEqual(task.account_id, available_account["id"])
        self.assertEqual(task.account_phone, "13900139000")
        self.assertEqual(task.project_pid, "113602715787269")
        self.assertEqual(task.status, "S4扫描中")
        self.assertEqual(task.huasheng_status, "任务已创建")

    def test_run_huasheng_progress_task_exports_finished_project_and_persists_video(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            "发布账号A",
            False,
        )
        created = self.service.create_task_record(
            account["id"],
            "113671485575170",
            "S4扫描中",
            article_id=101,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            rewritten_content="改写后的正文内容",
            title="自动生成标题",
            huasheng_status="处理中",
        )

        with patch.object(
            self.service._huasheng,
            "get_project_info",
            return_value={
                "project": {
                    "id": "2470002",
                    "pid": "113671485575170",
                    "progress": 100,
                    "state_message": "项目处理完成",
                }
            },
        ) as mocked_project_info, patch.object(
            self.service._huasheng,
            "edit_project",
            return_value={"code": 0, "message": "success"},
        ) as mocked_edit_project, patch.object(
            self.service._huasheng,
            "export_project_video",
            return_value={"task_id": "p2470002_37", "version": "37"},
        ) as mocked_export_project, patch.object(
            self.service._huasheng,
            "get_project_export_info",
            return_value={
                "url": "http://example.com/video.mp4",
                "progress": "100",
                "cover": "",
                "cover43": "",
            },
        ) as mocked_export_info:
            self.service._run_huasheng_progress_task(created["id"])

        task = self.service.get_task_record(created["id"])

        mocked_project_info.assert_called_once_with(
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            pid="113671485575170",
        )
        mocked_edit_project.assert_called_once_with(
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            project_id=2470002,
            font_size=42,
            font_color="#FFFFFF",
            outline_color="#0091A8",
            outline_thick=70,
        )
        mocked_export_project.assert_called_once_with(
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            project_id=2470002,
        )
        mocked_export_info.assert_called_once_with(
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            project_id=2470002,
            task_id="p2470002_37",
        )
        self.assertEqual(task.export_task_id, "p2470002_37")
        self.assertEqual(task.export_version, "37")
        self.assertEqual(task.progress, 100)
        self.assertEqual(task.status, "导出完成")
        self.assertEqual(task.huasheng_status, "导出完成")
        self.assertEqual(task.video_url, "http://example.com/video.mp4")

    def test_run_huasheng_progress_task_uses_pid_only_while_project_is_processing(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            "发布账号A",
            False,
        )
        created = self.service.create_task_record(
            account["id"],
            "113671485575170",
            "S4扫描中",
            article_id=101,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            rewritten_content="改写后的正文内容",
            title="自动生成标题",
            huasheng_status="处理中",
        )

        with patch.object(
            self.service._huasheng,
            "get_project_info",
            return_value={
                "project": {
                    "pid": "113671485575170",
                    "progress": 61,
                    "state_message": "处理中",
                }
            },
        ) as mocked_project_info, patch.object(
            self.service._huasheng,
            "edit_project",
        ) as mocked_edit_project, patch.object(
            self.service._huasheng,
            "export_project_video",
        ) as mocked_export_project:
            self.service._run_huasheng_progress_task(created["id"])

        task = self.service.get_task_record(created["id"])

        mocked_project_info.assert_called_once_with(
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            pid="113671485575170",
        )
        mocked_edit_project.assert_not_called()
        mocked_export_project.assert_not_called()
        self.assertEqual(task.status, "S4扫描中")
        self.assertEqual(task.progress, 61)
        self.assertEqual(task.huasheng_status, "处理中")

    def test_run_huasheng_progress_task_waits_when_finished_but_numeric_id_missing(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            "发布账号A",
            False,
        )
        created = self.service.create_task_record(
            account["id"],
            "113671485575170",
            "S4扫描中",
            article_id=101,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            rewritten_content="改写后的正文内容",
            title="自动生成标题",
            huasheng_status="处理中",
        )

        with patch.object(
            self.service._huasheng,
            "get_project_info",
            return_value={
                "project": {
                    "pid": "113671485575170",
                    "progress": 100,
                    "state_message": "项目处理完成",
                }
            },
        ) as mocked_project_info, patch.object(
            self.service._huasheng,
            "edit_project",
        ) as mocked_edit_project, patch.object(
            self.service._huasheng,
            "export_project_video",
        ) as mocked_export_project:
            self.service._run_huasheng_progress_task(created["id"])

        task = self.service.get_task_record(created["id"])

        mocked_project_info.assert_called_once_with(
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            pid="113671485575170",
        )
        mocked_edit_project.assert_not_called()
        mocked_export_project.assert_not_called()
        self.assertEqual(task.status, "S4扫描中")
        self.assertEqual(task.progress, 100)
        self.assertEqual(task.huasheng_status, "项目处理完成，等待项目数值ID")

    def test_run_huasheng_progress_task_marks_finished_once_video_url_exists(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            "发布账号A",
            False,
        )
        created = self.service.create_task_record(
            account["id"],
            "113671485575170",
            "S4导出中",
            article_id=101,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            rewritten_content="改写后的正文内容",
            title="自动生成标题",
            huasheng_status="导出中",
            export_task_id="p2470002_37",
            export_version="37",
        )

        with patch.object(
            self.service._huasheng,
            "get_project_info",
            return_value={
                "project": {
                    "id": "2470002",
                    "pid": "113671485575170",
                    "progress": 100,
                    "state_message": "项目处理完成",
                }
            },
        ) as mocked_project_info, patch.object(
            self.service._huasheng,
            "get_project_export_info",
            return_value={
                "url": "http://example.com/video.mp4",
                "progress": "61",
                "cover": "",
                "cover43": "",
            },
        ) as mocked_export_info:
            self.service._run_huasheng_progress_task(created["id"])

        task = self.service.get_task_record(created["id"])

        mocked_project_info.assert_called_once_with(
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            pid="113671485575170",
        )
        mocked_export_info.assert_called_once_with(
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            project_id=2470002,
            task_id="p2470002_37",
        )
        self.assertEqual(task.status, "导出完成")
        self.assertEqual(task.progress, 100)
        self.assertEqual(task.huasheng_status, "导出完成")
        self.assertEqual(task.video_url, "http://example.com/video.mp4")

    def test_run_huasheng_progress_task_skips_finished_task_without_request(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf-token; sid=abc",
            "发布账号A",
            False,
        )
        created = self.service.create_task_record(
            account["id"],
            "113671485575170",
            "导出完成",
            article_id=101,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            rewritten_content="改写后的正文内容",
            title="自动生成标题",
            huasheng_status="导出完成",
        )

        with patch.object(self.service._huasheng, "get_project_info") as mocked_project_info:
            self.service._run_huasheng_progress_task(created["id"])

        mocked_project_info.assert_not_called()

    def test_pending_stage_selectors_split_rewrite_and_title_tasks(self) -> None:
        account = self.service.create_account(
            "13800138000",
            "SESSDATA=test; bili_jct=csrf",
            "测试账号",
            False,
        )
        rewrite_task = self.service.create_task_record(
            account["id"],
            "",
            "待处理",
            article_id=101,
            rewrite_prompt_id=1,
            rewrite_prompt="提示词A",
            huasheng_status="未创建",
        )
        title_task = self.service.create_task_record(
            account["id"],
            "",
            "待生成标题",
            article_id=102,
            rewrite_prompt_id=2,
            rewrite_prompt="提示词B",
            rewritten_content="这是已经改写完成的正文",
            huasheng_status="未创建",
        )
        finished_task = self.service.create_task_record(
            account["id"],
            "113671485575169",
            "S4扫描中",
            article_id=103,
            rewrite_prompt_id=3,
            rewrite_prompt="提示词C",
            rewritten_content="正文",
            title="标题",
            video_url="http://example.com/already-done.mp4",
            huasheng_status="未创建",
        )
        finished_status_task = self.service.create_task_record(
            account["id"],
            "113671485575171",
            "导出完成",
            article_id=106,
            rewrite_prompt_id=6,
            rewrite_prompt="提示词F",
            rewritten_content="正文",
            title="标题F",
            huasheng_status="导出完成",
        )
        huasheng_create_task = self.service.create_task_record(
            account["id"],
            "",
            "待创建花生任务",
            article_id=104,
            rewrite_prompt_id=4,
            rewrite_prompt="提示词D",
            rewritten_content="正文",
            title="标题D",
            huasheng_status="未创建",
        )
        huasheng_progress_task = self.service.create_task_record(
            account["id"],
            "113671485575170",
            "S4扫描中",
            article_id=105,
            rewrite_prompt_id=5,
            rewrite_prompt="提示词E",
            rewritten_content="正文",
            title="标题E",
            huasheng_status="处理中",
        )

        rewrite_ids = self.service.list_pending_rewrite_task_ids()
        title_ids = self.service.list_pending_title_task_ids()
        huasheng_create_ids = self.service.list_pending_huasheng_create_task_ids()
        huasheng_progress_ids = self.service.list_pending_huasheng_progress_task_ids()

        self.assertEqual(rewrite_ids, [rewrite_task["id"]])
        self.assertEqual(title_ids, [title_task["id"]])
        self.assertEqual(huasheng_create_ids, [huasheng_create_task["id"]])
        self.assertEqual(huasheng_progress_ids, [huasheng_progress_task["id"]])
        self.assertNotIn(finished_task["id"], rewrite_ids)
        self.assertNotIn(finished_task["id"], title_ids)
        self.assertNotIn(finished_task["id"], huasheng_create_ids)
        self.assertNotIn(finished_task["id"], huasheng_progress_ids)
        self.assertNotIn(finished_status_task["id"], huasheng_progress_ids)


if __name__ == "__main__":
    unittest.main()

