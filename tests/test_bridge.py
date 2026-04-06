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

    def test_ocr_image_text_returns_error_payload_instead_of_raising(self) -> None:
        with patch.object(
            self.service,
            "ocr_image_text",
            side_effect=RuntimeError("未安装 PaddleOCR 运行依赖"),
        ):
            payload = self.api.ocr_image_text("/tmp/demo.png")

        self.assertFalse(payload["success"])
        self.assertEqual(payload["errorMessage"], "未安装 PaddleOCR 运行依赖")
        self.assertEqual(payload["imagePath"], "/tmp/demo.png")
        self.assertEqual(payload["model"], "PaddleOCR")

    def test_ocr_image_text_wraps_success_payload(self) -> None:
        with patch.object(
            self.service,
            "ocr_image_text",
            return_value={
                "engine": "PaddleOCR",
                "imagePath": "/tmp/demo.png",
                "lineCount": 2,
                "text": "第一行\n第二行",
                "lines": [{"text": "第一行"}, {"text": "第二行"}],
            },
        ):
            payload = self.api.ocr_image_text("/tmp/demo.png")

        self.assertTrue(payload["success"])
        self.assertEqual(payload["errorMessage"], "")
        self.assertEqual(payload["lineCount"], 2)
        self.assertEqual(payload["text"], "第一行\n第二行")

    def test_get_ocr_model_status_wraps_success_payload(self) -> None:
        with patch.object(
            self.service,
            "get_ocr_model_status_payload",
            return_value={
                "engine": "PaddleOCR",
                "status": "ready",
                "ready": True,
                "message": "OCR 模型已就绪",
                "cacheDir": "/tmp/paddlex",
            },
        ) as mocked_status:
            payload = self.api.get_ocr_model_status()

        mocked_status.assert_called_once_with()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["ready"])

    def test_download_ocr_model_returns_error_payload_instead_of_raising(self) -> None:
        with patch.object(
            self.service,
            "download_ocr_models",
            side_effect=RuntimeError("OCR 模型正在下载或校验中，请稍后再试。"),
        ):
            payload = self.api.download_ocr_model()

        self.assertFalse(payload["success"])
        self.assertEqual(payload["errorMessage"], "OCR 模型正在下载或校验中，请稍后再试。")
        self.assertEqual(payload["model"], "PaddleOCR")

    def test_select_image_file_delegates_to_bridge(self) -> None:
        with patch.object(self.bridge, "choose_file", return_value="/tmp/image.png") as mocked_choose:
            payload = self.api.select_image_file("/tmp/current.jpg")

        mocked_choose.assert_called_once()
        self.assertEqual(payload["selectedPath"], "/tmp/image.png")
        self.assertFalse(payload["cancelled"])

    def test_get_log_status_delegates_to_service(self) -> None:
        with patch.object(
            self.service,
            "get_log_status_payload",
            return_value={
                "logDir": "/tmp/logs",
                "fileCount": 3,
                "totalSizeBytes": 1024,
            },
        ) as mocked_status:
            payload = self.api.get_log_status()

        mocked_status.assert_called_once_with()
        self.assertEqual(payload["logDir"], "/tmp/logs")
        self.assertEqual(payload["fileCount"], 3)

    def test_open_logs_directory_delegates_to_bridge(self) -> None:
        log_dir = self.service.resolve_log_directory_path()
        with patch.object(
            self.bridge,
            "open_directory_in_file_manager",
            return_value=str(log_dir),
        ) as mocked_open:
            payload = self.api.open_logs_directory()

        mocked_open.assert_called_once_with(str(log_dir))
        self.assertEqual(payload["openedPath"], str(log_dir))
        self.assertEqual(payload["databasePath"], str(self.db_path))

    def test_save_global_settings_delegates_to_service_with_website_check_flag(self) -> None:
        with patch.object(
            self.service,
            "save_global_settings",
            return_value={
                "settings": {
                    "threadPoolSize": 6,
                    "downloadDir": "/tmp/downloads",
                    "checkWebsiteLinks": True,
                }
            },
        ) as mocked_save:
            payload = self.api.save_global_settings(6, "/tmp/downloads", True)

        mocked_save.assert_called_once_with(6, "/tmp/downloads", True)
        self.assertTrue(payload["settings"]["checkWebsiteLinks"])

    def test_save_huasheng_voice_settings_delegates_to_service_with_concurrency_limit(self) -> None:
        with patch.object(
            self.service,
            "save_huasheng_voice_settings",
            return_value={
                "settings": {
                    "voiceId": 6036542,
                    "maxConcurrentTasksPerAccount": 2,
                }
            },
        ) as mocked_save:
            payload = self.api.save_huasheng_voice_settings(
                6036542,
                "知性女声",
                "voice-code",
                "科普",
                "https://example.com/preview.mp3",
                "https://example.com/cover.png",
                1.2,
                2,
            )

        mocked_save.assert_called_once_with(
            6036542,
            "知性女声",
            "voice-code",
            "科普",
            "https://example.com/preview.mp3",
            "https://example.com/cover.png",
            1.2,
            2,
        )
        self.assertEqual(payload["settings"]["maxConcurrentTasksPerAccount"], 2)

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

    def test_retry_task_record_delegates_to_service(self) -> None:
        with patch.object(
            self.service,
            "retry_task_record",
            return_value={
                "id": 9,
                "status": "待处理",
                "projectPid": "",
            },
        ) as mocked_retry:
            payload = self.api.retry_task_record(9)

        mocked_retry.assert_called_once_with(9)
        self.assertEqual(payload["id"], 9)
        self.assertEqual(payload["status"], "待处理")

    def test_get_app_state_includes_version(self) -> None:
        payload = self.api.get_app_state()

        self.assertEqual(payload["version"], APP_VERSION)
        self.assertEqual(payload["title"], "Test")


if __name__ == "__main__":
    unittest.main()
