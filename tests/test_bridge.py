from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.accounts import AccountService
from app.bridge import AppApi, DesktopBridge
from app.config import APP_VERSION
from app.database import close_database, init_database


class DummyMicroheadline:
    def get_microheadline_settings_payload(self):
        return {}


class AppApiModelActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.sqlite3"
        init_database(self.db_path)
        self.service = AccountService(self.db_path)
        self.service.bootstrap()
        self.bridge = DesktopBridge(index_file=self.db_path, default_title="Test")
        self.api = AppApi(
            self.bridge,
            self.service,
            huasheng=object(),
            microheadline=DummyMicroheadline(),
        )

    def tearDown(self) -> None:
        close_database()
        self.temp_dir.cleanup()

    def test_rewrite_article_returns_error_payload_instead_of_raising(self) -> None:
        with patch.object(
            self.service,
            "rewrite_article",
            side_effect=RuntimeError("文章改写失败: HTTP 502 Bad Gateway"),
        ):
            payload = self.api.rewrite_article(
                "https://api.example.com/v1",
                "secret-token",
                "gpt-5.4",
                1,
                "原始文章",
            )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["errorMessage"], "文章改写失败: HTTP 502 Bad Gateway")
        self.assertEqual(payload["promptId"], 1)
        self.assertEqual(payload["model"], "gpt-5.4")
        self.assertEqual(payload["requestUrl"], "https://api.example.com/v1")

    def test_test_model_connection_wraps_success_payload(self) -> None:
        with patch.object(
            self.service,
            "test_model_connection",
            return_value={
                "message": "模型连接测试成功",
                "responseText": "连接成功",
                "model": "gpt-5.4",
                "requestUrl": "https://api.example.com/v1/chat/completions",
                "databasePath": str(self.db_path),
            },
        ):
            payload = self.api.test_model_connection(
                "https://api.example.com/v1",
                "secret-token",
                "gpt-5.4",
            )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["errorMessage"], "")
        self.assertEqual(payload["responseText"], "连接成功")
        self.assertEqual(payload["requestUrl"], "https://api.example.com/v1/chat/completions")

    def test_download_task_video_delegates_to_service(self) -> None:
        with patch.object(
            self.service,
            "download_task_video",
            return_value={
                "taskId": 8,
                "downloadPath": "/tmp/demo.mp4",
                "deletedCount": 1,
            },
        ) as mocked_download:
            payload = self.api.download_task_video(8)

        mocked_download.assert_called_once_with(8)
        self.assertEqual(payload["taskId"], 8)
        self.assertEqual(payload["downloadPath"], "/tmp/demo.mp4")

    def test_get_app_state_includes_version(self) -> None:
        payload = self.api.get_app_state()

        self.assertEqual(payload["version"], APP_VERSION)
        self.assertEqual(payload["title"], "Test")


if __name__ == "__main__":
    unittest.main()
