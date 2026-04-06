from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from app.database import close_database, database, init_database
from app.models import MonitoredArticle
from app.microheadline import (
    AutomationSettings,
    FeedCapture,
    MicroHeadlineAccountMonitor,
    MicroHeadlineService,
)


class MicroHeadlineServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.sqlite3"
        init_database(self.db_path)
        self.service = MicroHeadlineService(self.db_path)
        self.service.bootstrap()

    def tearDown(self) -> None:
        close_database()
        self.temp_dir.cleanup()

    def test_get_microheadline_settings_payload_returns_defaults(self) -> None:
        payload = self.service.get_microheadline_settings_payload()

        self.assertEqual(
            payload["settings"],
            {
                "headless": True,
                "workerCount": 1,
                "defaultMinPlayCount": 0,
                "defaultMinDiggCount": 0,
                "defaultMinForwardCount": 0,
            },
        )
        self.assertEqual(payload["workerCountMin"], 1)
        self.assertEqual(payload["workerCountMax"], 16)
        self.assertEqual(payload["databasePath"], str(self.db_path))

    def test_save_microheadline_settings_persists_values(self) -> None:
        saved = self.service.save_microheadline_settings("false", 4, 100, 10, 5)
        loaded = self.service.get_microheadline_settings_payload()

        self.assertEqual(
            saved["settings"],
            {
                "headless": False,
                "workerCount": 4,
                "defaultMinPlayCount": 100,
                "defaultMinDiggCount": 10,
                "defaultMinForwardCount": 5,
            },
        )
        self.assertEqual(loaded["settings"], saved["settings"])

    def test_create_update_delete_benchmark_account(self) -> None:
        created = self.service.create_benchmark_account("https://www.toutiao.com/c/user/token/example/")
        updated = self.service.update_benchmark_account(created["id"], "https://www.toutiao.com/c/user/token/changed/")
        payload = self.service.list_benchmark_accounts(1, 20)
        deleted = self.service.delete_benchmark_account(created["id"])
        payload_after_delete = self.service.list_benchmark_accounts(1, 20)

        self.assertEqual(created["url"], "https://www.toutiao.com/c/user/token/example/")
        self.assertEqual(updated["url"], "https://www.toutiao.com/c/user/token/changed/")
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["url"], "https://www.toutiao.com/c/user/token/changed/")
        self.assertTrue(deleted)
        self.assertEqual(payload_after_delete["total"], 0)

    def test_delete_all_monitored_articles_clears_article_library(self) -> None:
        created = self.service.create_benchmark_account("https://www.toutiao.com/c/user/token/example/")

        with database.connection_context():
            account = self.service._get_benchmark_account(created["id"])
            run = self.service._create_monitor_run(account, account.url)
            self.service._persist_monitored_articles(
                account,
                run,
                [
                    {
                        "itemId": "item-1",
                        "title": "标题 1",
                        "content": "正文 1",
                        "publishTime": "2026-04-04 10:00:00",
                        "playCount": 100,
                        "diggCount": 10,
                    },
                    {
                        "itemId": "item-2",
                        "title": "标题 2",
                        "content": "正文 2",
                        "publishTime": "2026-04-04 11:00:00",
                        "playCount": 200,
                        "diggCount": 20,
                    },
                ],
            )

        payload_before_delete = self.service.list_monitored_articles({}, 1, 20)
        deleted = self.service.delete_all_monitored_articles()
        payload_after_delete = self.service.list_monitored_articles({}, 1, 20)

        self.assertEqual(payload_before_delete["total"], 2)
        self.assertEqual(deleted["deletedCount"], 2)
        self.assertEqual(deleted["databasePath"], str(self.db_path))
        self.assertEqual(payload_after_delete["total"], 0)

    def test_persist_monitored_articles_skips_duplicate_content(self) -> None:
        created = self.service.create_benchmark_account("https://www.toutiao.com/c/user/token/example/")

        with database.connection_context():
            account = self.service._get_benchmark_account(created["id"])
            run = self.service._create_monitor_run(account, account.url)
            saved_count = self.service._persist_monitored_articles(
                account,
                run,
                [
                    {
                        "itemId": "item-1",
                        "title": "标题 1",
                        "content": "重复正文",
                        "publishTime": "2026-04-04 10:00:00",
                        "playCount": 100,
                    },
                    {
                        "itemId": "item-2",
                        "title": "标题 2",
                        "content": "重复正文",
                        "publishTime": "2026-04-04 11:00:00",
                        "playCount": 200,
                    },
                ],
            )

        payload = self.service.list_monitored_articles({}, 1, 20)

        self.assertEqual(saved_count, 1)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["content"], "重复正文")

    def test_list_monitored_article_ids_supports_play_count_desc_limit(self) -> None:
        created = self.service.create_benchmark_account("https://www.toutiao.com/c/user/token/example/")

        with database.connection_context():
            account = self.service._get_benchmark_account(created["id"])
            run = self.service._create_monitor_run(account, account.url)
            self.service._persist_monitored_articles(
                account,
                run,
                [
                    {
                        "itemId": "item-1",
                        "title": "标题 1",
                        "content": "正文 1",
                        "publishTime": "2026-04-04 10:00:00",
                        "playCount": 100,
                    },
                    {
                        "itemId": "item-2",
                        "title": "标题 2",
                        "content": "正文 2",
                        "publishTime": "2026-04-04 11:00:00",
                        "playCount": 500,
                    },
                    {
                        "itemId": "item-3",
                        "title": "标题 3",
                        "content": "正文 3",
                        "publishTime": "2026-04-04 12:00:00",
                        "playCount": 300,
                    },
                ],
            )
            title_to_id = {
                article.title: article.id
                for article in MonitoredArticle.select(
                    MonitoredArticle.id,
                    MonitoredArticle.title,
                )
            }

        article_ids = self.service.list_monitored_article_ids(
            {
                "sortBy": "playCountDesc",
                "limit": 2,
            }
        )

        self.assertEqual(
            article_ids,
            [title_to_id["标题 2"], title_to_id["标题 3"]],
        )


class MicroHeadlineAccountMonitorBoundaryTests(unittest.TestCase):
    def test_has_reached_start_boundary_requires_older_article_than_start_time(self) -> None:
        start_time = datetime(2026, 4, 4, 12, 0, 0)
        monitor = MicroHeadlineAccountMonitor(
            url="https://www.toutiao.com/c/user/token/example/",
            start_time=start_time,
            settings=AutomationSettings(headless=True, worker_count=1),
        )
        captures = [
            FeedCapture(
                request_url="https://example.com/1",
                payload_text="",
                payload_json={
                    "data": [
                        {"publish_time": int((start_time + timedelta(hours=1)).timestamp())},
                        {"publish_time": int((start_time - timedelta(minutes=1)).timestamp())},
                    ]
                },
            )
        ]

        self.assertTrue(monitor._has_reached_start_boundary(captures))

    def test_has_reached_start_boundary_stays_false_when_only_reaches_start_time(self) -> None:
        start_time = datetime(2026, 4, 4, 12, 0, 0)
        monitor = MicroHeadlineAccountMonitor(
            url="https://www.toutiao.com/c/user/token/example/",
            start_time=start_time,
            settings=AutomationSettings(headless=True, worker_count=1),
        )
        captures = [
            FeedCapture(
                request_url="https://example.com/1",
                payload_text="",
                payload_json={
                    "data": [
                        {"publish_time": int((start_time + timedelta(hours=1)).timestamp())},
                        {"publish_time": int(start_time.timestamp())},
                    ]
                },
            )
        ]

        self.assertFalse(monitor._has_reached_start_boundary(captures))

    def test_resolve_max_scroll_rounds_expands_when_start_time_is_provided(self) -> None:
        with_start_time = MicroHeadlineAccountMonitor(
            url="https://www.toutiao.com/c/user/token/example/",
            start_time=datetime(2026, 4, 4, 12, 0, 0),
            settings=AutomationSettings(headless=True, worker_count=1),
        )
        without_start_time = MicroHeadlineAccountMonitor(
            url="https://www.toutiao.com/c/user/token/example/",
            settings=AutomationSettings(headless=True, worker_count=1),
        )

        self.assertGreater(
            with_start_time._resolve_max_scroll_rounds(),
            without_start_time._resolve_max_scroll_rounds(),
        )

    def test_resolve_max_no_progress_rounds_expands_when_start_time_is_provided(self) -> None:
        with_start_time = MicroHeadlineAccountMonitor(
            url="https://www.toutiao.com/c/user/token/example/",
            start_time=datetime(2026, 4, 4, 12, 0, 0),
            settings=AutomationSettings(headless=True, worker_count=1),
        )
        without_start_time = MicroHeadlineAccountMonitor(
            url="https://www.toutiao.com/c/user/token/example/",
            settings=AutomationSettings(headless=True, worker_count=1),
        )

        self.assertGreater(
            with_start_time._resolve_max_no_progress_rounds(),
            without_start_time._resolve_max_no_progress_rounds(),
        )

    def test_resolve_scroll_steps_per_round_expands_when_start_time_is_provided(self) -> None:
        with_start_time = MicroHeadlineAccountMonitor(
            url="https://www.toutiao.com/c/user/token/example/",
            start_time=datetime(2026, 4, 4, 12, 0, 0),
            settings=AutomationSettings(headless=True, worker_count=1),
        )
        without_start_time = MicroHeadlineAccountMonitor(
            url="https://www.toutiao.com/c/user/token/example/",
            settings=AutomationSettings(headless=True, worker_count=1),
        )

        self.assertGreater(
            with_start_time._resolve_scroll_steps_per_round(),
            without_start_time._resolve_scroll_steps_per_round(),
        )


if __name__ == "__main__":
    unittest.main()
