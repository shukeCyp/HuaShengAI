from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from peewee import IntegrityError, fn

from app.database import database
from app.models import AppSetting, BenchmarkAccount, MonitorRun, MonitoredArticle, now_local


logger = logging.getLogger(__name__)

MICROHEADLINE_HEADLESS_KEY = "microheadline.headless"
MICROHEADLINE_WORKER_COUNT_KEY = "microheadline.worker_count"
MICROHEADLINE_DEFAULT_MIN_PLAY_COUNT_KEY = "microheadline.default_min_play_count"
MICROHEADLINE_DEFAULT_MIN_DIGG_COUNT_KEY = "microheadline.default_min_digg_count"
MICROHEADLINE_DEFAULT_MIN_FORWARD_COUNT_KEY = "microheadline.default_min_forward_count"

DEFAULT_HEADLESS = True
DEFAULT_WORKER_COUNT = 1
DEFAULT_MIN_PLAY_COUNT = 0
DEFAULT_MIN_DIGG_COUNT = 0
DEFAULT_MIN_FORWARD_COUNT = 0
MAX_WORKER_COUNT = 16
MAX_PAGE_SIZE = 200

TARGET_FEED_PATH = "/api/pc/list/user/feed"
TARGET_FEED_CATEGORY = "pc_profile_ugc"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)
PAGE_BOOTSTRAP_TIMEOUT_MS = 60000
PAGE_IDLE_WAIT_MS = 4000
TAB_CLICK_WAIT_MS = 3000
SCROLL_WAIT_MS = 2500
NETWORK_SETTLE_TIMEOUT_MS = 4000
MAX_SCROLL_ROUNDS = 10
MAX_SCROLL_ROUNDS_WITH_START_TIME = 120
MAX_NO_PROGRESS_ROUNDS = 3
MAX_NO_PROGRESS_ROUNDS_WITH_START_TIME = 12
SCROLL_STEPS_PER_ROUND = 1
SCROLL_STEPS_PER_ROUND_WITH_START_TIME = 3


@dataclass(slots=True)
class AutomationSettings:
    headless: bool
    worker_count: int


@dataclass(slots=True)
class MonitoringThresholds:
    min_play_count: int = 0
    min_digg_count: int = 0
    min_forward_count: int = 0


@dataclass(slots=True)
class FeedCapture:
    request_url: str
    payload_text: str
    payload_json: dict[str, Any] | list[Any] | None


@dataclass(slots=True)
class BatchMonitorAccountResult:
    benchmark_account_id: int
    benchmark_account_url: str
    status: str
    saved_count: int
    article_count: int
    filtered_article_count: int
    capture_count: int
    warning: str | None
    error: str | None
    monitor_run_id: int | None
    articles: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmarkAccountId": self.benchmark_account_id,
            "benchmarkAccountUrl": self.benchmark_account_url,
            "status": self.status,
            "savedCount": self.saved_count,
            "articleCount": self.article_count,
            "filteredArticleCount": self.filtered_article_count,
            "captureCount": self.capture_count,
            "warning": self.warning,
            "error": self.error,
            "monitorRunId": self.monitor_run_id,
            "articles": self.articles,
        }


class MicroHeadlineAccountMonitor:
    def __init__(
        self,
        url: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        single_capture: bool = False,
        thresholds: MonitoringThresholds | None = None,
        settings: AutomationSettings | None = None,
    ) -> None:
        self.url = str(url or "").strip()
        self.start_time = start_time
        self.end_time = end_time
        self.single_capture = single_capture
        self.thresholds = thresholds or MonitoringThresholds()
        self.settings = settings or self.load_settings()
        self.reached_start_boundary = start_time is None
        self.scroll_stop_reason: str | None = None

    @staticmethod
    def load_settings() -> AutomationSettings:
        with database.connection_context():
            headless_raw = _get_setting_value(MICROHEADLINE_HEADLESS_KEY)
            worker_count_raw = _get_setting_value(MICROHEADLINE_WORKER_COUNT_KEY)
        headless = _parse_bool(headless_raw, DEFAULT_HEADLESS)
        worker_count = _parse_int(worker_count_raw, DEFAULT_WORKER_COUNT)
        worker_count = max(1, min(worker_count, MAX_WORKER_COUNT))
        return AutomationSettings(headless=headless, worker_count=worker_count)

    def _validate(self) -> None:
        if not self.url:
            raise ValueError("监控地址不能为空。")

        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("监控地址必须是有效的 http/https 链接。")

    def _serialize_datetime(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    def _extract_payload(self, payload_text: str) -> dict[str, Any] | list[Any] | None:
        if not payload_text:
            return None
        try:
            return json.loads(payload_text)
        except json.JSONDecodeError:
            return None

    def _is_target_feed_response(self, response_url: str) -> bool:
        parsed = urlparse(response_url)
        if parsed.path != TARGET_FEED_PATH:
            return False
        query = parse_qs(parsed.query)
        return query.get("category", [""])[0] == TARGET_FEED_CATEGORY

    def _extract_feed_items(
        self,
        payload: dict[str, Any] | list[Any] | None,
    ) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    def _extract_item_timestamp(self, item: dict[str, Any]) -> datetime | None:
        for key in ("publish_time", "behot_time", "create_time", "datetime", "time"):
            value = item.get(key)
            if isinstance(value, (int, float)):
                try:
                    return datetime.fromtimestamp(value)
                except (OSError, OverflowError, ValueError):
                    continue
            if isinstance(value, str) and value.strip():
                try:
                    return datetime.fromisoformat(value.strip())
                except ValueError:
                    continue
        return None

    def _extract_known_item_times(self, items: list[dict[str, Any]]) -> list[datetime]:
        return [
            item_time
            for item_time in (self._extract_item_timestamp(item) for item in items)
            if item_time is not None
        ]

    def _extract_oldest_item_time(self, items: list[dict[str, Any]]) -> datetime | None:
        known_times = self._extract_known_item_times(items)
        return min(known_times) if known_times else None

    def _extract_oldest_item_time_from_captures(
        self,
        captures: list[FeedCapture],
    ) -> datetime | None:
        oldest_time: datetime | None = None
        for capture in captures:
            capture_oldest = self._extract_oldest_item_time(
                self._extract_feed_items(capture.payload_json)
            )
            if capture_oldest is None:
                continue
            if oldest_time is None or capture_oldest < oldest_time:
                oldest_time = capture_oldest
        return oldest_time

    def _has_reached_start_boundary(self, captures: list[FeedCapture]) -> bool:
        if self.start_time is None:
            return True
        oldest_seen_time = self._extract_oldest_item_time_from_captures(captures)
        return oldest_seen_time is not None and oldest_seen_time < self.start_time

    def _resolve_max_scroll_rounds(self) -> int:
        if self.start_time is not None:
            return MAX_SCROLL_ROUNDS_WITH_START_TIME
        return MAX_SCROLL_ROUNDS

    def _resolve_max_no_progress_rounds(self) -> int:
        if self.start_time is not None:
            return MAX_NO_PROGRESS_ROUNDS_WITH_START_TIME
        return MAX_NO_PROGRESS_ROUNDS

    def _resolve_scroll_steps_per_round(self) -> int:
        if self.start_time is not None:
            return SCROLL_STEPS_PER_ROUND_WITH_START_TIME
        return SCROLL_STEPS_PER_ROUND

    def _perform_scroll_step(self, page: Any, round_index: int, step_index: int) -> None:
        wheel_delta = 1800 + round_index * 120 + step_index * 220
        page.mouse.wheel(0, wheel_delta)
        page.evaluate(
            """
            ([roundIndex, stepIndex]) => {
              const baseDistance = Math.max(window.innerHeight * 1.6, 1400)
              const extraDistance = stepIndex * 320 + roundIndex * 40
              window.scrollBy(0, baseDistance + extraDistance)
              const nodes = Array.from(document.querySelectorAll('*'))
              let best = null
              let bestScrollable = 0
              for (const node of nodes) {
                if (!(node instanceof HTMLElement)) {
                  continue
                }
                const scrollable = node.scrollHeight - node.clientHeight
                if (scrollable <= 200) {
                  continue
                }
                const style = window.getComputedStyle(node)
                if (!['auto', 'scroll', 'overlay'].includes(style.overflowY)) {
                  continue
                }
                if (scrollable > bestScrollable) {
                  bestScrollable = scrollable
                  best = node
                }
              }
              if (best) {
                const stepDistance = Math.max(best.clientHeight * 1.8, 1600) + stepIndex * 240
                best.scrollTop = Math.min(best.scrollTop + stepDistance, best.scrollHeight)
              }
            }
            """,
            [round_index, step_index],
        )
        page.wait_for_timeout(SCROLL_WAIT_MS)

    def _is_in_range(self, item_time: datetime | None) -> bool:
        if item_time is None:
            return self.start_time is None and self.end_time is None
        if self.start_time is not None and item_time < self.start_time:
            return False
        if self.end_time is not None and item_time > self.end_time:
            return False
        return True

    def _stringify(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _extract_text(self, item: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _extract_number(self, item: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                text = value.strip()
                if text.isdigit():
                    return int(text)
        return None

    def _normalize_article(
        self,
        item: dict[str, Any],
        item_time: datetime | None,
    ) -> dict[str, Any]:
        return {
            "id": self._stringify(item.get("id")),
            "groupId": self._stringify(item.get("group_id")),
            "itemId": self._stringify(item.get("item_id")),
            "cellType": self._stringify(item.get("cell_type")),
            "title": self._extract_text(item, "title"),
            "content": self._extract_text(item, "content", "abstract", "display_text"),
            "publishTime": item_time.isoformat() if item_time else None,
            "source": self._extract_text(item, "source"),
            "mediaName": self._extract_text(item, "media_name"),
            "displayUrl": self._extract_text(item, "display_url", "share_url", "source_url"),
            "playCount": self._extract_number(
                item,
                "play_count",
                "read_count",
                "view_count",
                "impression_count",
            ),
            "diggCount": self._extract_number(item, "digg_count", "like_count", "up_count"),
            "commentCount": self._extract_number(item, "comment_count"),
            "forwardCount": self._extract_number(
                item,
                "forward_count",
                "share_count",
                "repin_count",
            ),
            "buryCount": self._extract_number(item, "bury_count"),
            "raw": item,
        }

    def _passes_metric_threshold(self, value: int | None, threshold: int) -> bool:
        if threshold <= 0:
            return True
        if value is None:
            return False
        return value >= threshold

    def _passes_capture_thresholds(self, article: dict[str, Any]) -> bool:
        return (
            self._passes_metric_threshold(article.get("playCount"), self.thresholds.min_play_count)
            and self._passes_metric_threshold(article.get("diggCount"), self.thresholds.min_digg_count)
            and self._passes_metric_threshold(article.get("forwardCount"), self.thresholds.min_forward_count)
        )

    def _capture_response(self, response: Any) -> FeedCapture:
        payload_text = response.text()
        return FeedCapture(
            request_url=response.url,
            payload_text=payload_text,
            payload_json=self._extract_payload(payload_text),
        )

    def _get_microheadline_locator(self, page: Any) -> Any:
        locator_candidates = [
            page.get_by_role("tab", name="微头条"),
            page.get_by_role("button", name="微头条"),
            page.get_by_role("link", name="微头条"),
            page.get_by_text("微头条", exact=True),
            page.locator("text=微头条"),
        ]
        for locator in locator_candidates:
            try:
                candidate = locator.first
                if candidate.count() == 0:
                    continue
                if candidate.is_visible(timeout=1500):
                    return candidate
            except Exception:
                continue
        raise RuntimeError("未找到“微头条”标签，无法切换到微头条列表。")

    def _extract_item_identity(self, item: dict[str, Any]) -> str | None:
        for key in ("id", "group_id", "item_id", "thread_id", "thread_id_str"):
            value = self._stringify(item.get(key))
            if value:
                return value
        return None

    def _get_next_cursor(
        self,
        payload: dict[str, Any] | list[Any] | None,
        items: list[dict[str, Any]],
    ) -> int | None:
        if isinstance(payload, dict):
            for key in ("next", "next_max_behot_time", "max_behot_time"):
                value = payload.get(key)
                if isinstance(value, (int, float)):
                    return int(value)
                if isinstance(value, str) and value.strip().isdigit():
                    return int(value.strip())

        timestamps: list[int] = []
        for item in items:
            for key in ("behot_time", "publish_time", "create_time"):
                value = item.get(key)
                if isinstance(value, (int, float)):
                    timestamps.append(int(value))
                    break
                if isinstance(value, str) and value.strip().isdigit():
                    timestamps.append(int(value.strip()))
                    break
        return min(timestamps) if timestamps else None

    def _build_capture_signature(self, capture: FeedCapture) -> str:
        items = self._extract_feed_items(capture.payload_json)
        identities = [
            identity
            for identity in (self._extract_item_identity(item) for item in items[:5])
            if identity
        ]
        next_cursor = self._get_next_cursor(capture.payload_json, items)
        return f"{len(items)}|{next_cursor}|{'|'.join(identities)}"

    def _build_type_summary(
        self,
        payload: dict[str, Any] | list[Any] | None,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "topLevelType": type(payload).__name__ if payload is not None else None,
            "itemCount": len(items),
        }
        if isinstance(payload, dict):
            summary["topLevelKeys"] = sorted(payload.keys())
            summary["dataType"] = type(payload.get("data")).__name__ if "data" in payload else None
        if items:
            summary["sampleItemKeys"] = sorted(items[0].keys())
        return summary

    def _collect_feed_captures(self) -> list[FeedCapture]:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "当前 Python 环境未安装 playwright，请先安装依赖后再执行文章抓取。"
            ) from exc

        captures: list[FeedCapture] = []
        pending_captures: list[FeedCapture] = []
        seen_request_urls: set[str] = set()
        seen_capture_signatures: set[str] = set()

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.settings.headless)
            context = browser.new_context(user_agent=DEFAULT_USER_AGENT, locale="zh-CN")
            page = context.new_page()

            def handle_response(response: Any) -> None:
                if not self._is_target_feed_response(response.url):
                    return
                try:
                    pending_captures.append(self._capture_response(response))
                except Exception as exc:
                    logger.warning("读取微头条响应失败 url=%s error=%s", response.url, exc)

            try:
                logger.info(
                    "开始加载微头条账号页 url=%s headless=%s",
                    self.url,
                    self.settings.headless,
                )
                page.on("response", handle_response)
                page.goto(self.url, wait_until="domcontentloaded", timeout=PAGE_BOOTSTRAP_TIMEOUT_MS)
                page.wait_for_timeout(PAGE_IDLE_WAIT_MS)

                locator = self._get_microheadline_locator(page)
                with page.expect_response(
                    lambda response: self._is_target_feed_response(response.url),
                    timeout=PAGE_BOOTSTRAP_TIMEOUT_MS,
                ) as response_info:
                    locator.click(timeout=PAGE_BOOTSTRAP_TIMEOUT_MS)
                page.wait_for_timeout(TAB_CLICK_WAIT_MS)

                first_capture = self._capture_response(response_info.value)
                captures.append(first_capture)
                seen_request_urls.add(first_capture.request_url)
                seen_capture_signatures.add(self._build_capture_signature(first_capture))
                self.reached_start_boundary = self._has_reached_start_boundary(captures)

                if self.single_capture:
                    self.scroll_stop_reason = "single_capture_requested"
                    return captures

                if self.reached_start_boundary:
                    self.scroll_stop_reason = "reached_start_boundary_on_initial_capture"
                    logger.info(
                        "首屏已滚动到起始时间边界之前 oldest_seen_time=%s start_time=%s url=%s",
                        self._extract_oldest_item_time_from_captures(captures),
                        self.start_time,
                        self.url,
                    )
                    return captures

                pending_index = len(pending_captures)
                no_progress_rounds = 0
                max_scroll_rounds = self._resolve_max_scroll_rounds()
                max_no_progress_rounds = self._resolve_max_no_progress_rounds()
                scroll_steps_per_round = self._resolve_scroll_steps_per_round()
                for round_index in range(max_scroll_rounds):
                    logger.info(
                        "微头条滚动分页 round=%s/%s url=%s start_time=%s scroll_steps=%s",
                        round_index + 1,
                        max_scroll_rounds,
                        self.url,
                        self.start_time,
                        scroll_steps_per_round,
                    )
                    for step_index in range(scroll_steps_per_round):
                        self._perform_scroll_step(page, round_index, step_index)
                    try:
                        page.wait_for_load_state("networkidle", timeout=NETWORK_SETTLE_TIMEOUT_MS)
                    except PlaywrightTimeoutError:
                        logger.info("滚动后未进入 networkidle，继续处理已捕获响应。")

                    new_captures: list[FeedCapture] = []
                    for capture in pending_captures[pending_index:]:
                        if capture.request_url in seen_request_urls:
                            continue
                        items = self._extract_feed_items(capture.payload_json)
                        if not items:
                            continue
                        signature = self._build_capture_signature(capture)
                        if signature in seen_capture_signatures:
                            continue
                        seen_request_urls.add(capture.request_url)
                        seen_capture_signatures.add(signature)
                        new_captures.append(capture)

                    pending_index = len(pending_captures)
                    if not new_captures:
                        no_progress_rounds += 1
                        if no_progress_rounds >= max_no_progress_rounds:
                            self.scroll_stop_reason = "no_progress_before_start_boundary"
                            logger.info(
                                "停止滚动：连续无进展 round=%s url=%s reached_start_boundary=%s oldest_seen_time=%s start_time=%s",
                                round_index + 1,
                                self.url,
                                self.reached_start_boundary,
                                self._extract_oldest_item_time_from_captures(captures),
                                self.start_time,
                            )
                            break
                        continue

                    captures.extend(new_captures)
                    no_progress_rounds = 0
                    self.reached_start_boundary = self._has_reached_start_boundary(captures)

                    if self.reached_start_boundary:
                        self.scroll_stop_reason = "reached_start_boundary"
                        logger.info(
                            "停止滚动：已看到起始时间之前的文章 oldest_seen_time=%s start_time=%s url=%s",
                            self._extract_oldest_item_time_from_captures(captures),
                            self.start_time,
                            self.url,
                        )
                        break
                else:
                    self.scroll_stop_reason = "max_scroll_rounds_before_start_boundary"
                    logger.info(
                        "停止滚动：达到安全滚动上限 rounds=%s url=%s reached_start_boundary=%s oldest_seen_time=%s start_time=%s",
                        max_scroll_rounds,
                        self.url,
                        self.reached_start_boundary,
                        self._extract_oldest_item_time_from_captures(captures),
                        self.start_time,
                    )
            finally:
                try:
                    context.close()
                finally:
                    browser.close()

        return captures

    def _build_warning(
        self,
        captures: list[FeedCapture],
        latest_valid_capture: FeedCapture | None,
        filtered_count: int,
        saved_candidates: int,
    ) -> str | None:
        if not captures:
            return "未捕获到微头条列表响应。"
        if latest_valid_capture is None:
            return "已捕获响应，但没有解析出有效文章数据。"
        if self.start_time is not None and not self.reached_start_boundary:
            return "尚未滚动到起始时间之前的文章，抓取范围可能不完整。"
        if filtered_count <= 0 and saved_candidates > 0:
            return "已抓到文章，但没有内容满足当前筛选条件。"
        return None

    def _build_result(self, captures: list[FeedCapture]) -> dict[str, Any]:
        all_items: list[dict[str, Any]] = []
        for capture in captures:
            all_items.extend(self._extract_feed_items(capture.payload_json))

        deduped_items: list[dict[str, Any]] = []
        seen_article_keys: set[str] = set()
        for item in all_items:
            identity = self._extract_item_identity(item)
            if identity is None:
                identity = json.dumps(item, ensure_ascii=False, sort_keys=True)[:400]
            if identity in seen_article_keys:
                continue
            seen_article_keys.add(identity)
            deduped_items.append(item)

        prepared_articles: list[tuple[dict[str, Any], datetime | None]] = []
        for item in deduped_items:
            item_time = self._extract_item_timestamp(item)
            prepared_articles.append((self._normalize_article(item, item_time), item_time))

        time_filtered_articles = [
            article for article, item_time in prepared_articles if self._is_in_range(item_time)
        ]
        threshold_filtered_articles = [
            article for article in time_filtered_articles if self._passes_capture_thresholds(article)
        ]

        latest_valid_capture = next(
            (
                capture
                for capture in reversed(captures)
                if self._extract_feed_items(capture.payload_json)
            ),
            None,
        )
        latest_items = (
            self._extract_feed_items(latest_valid_capture.payload_json)
            if latest_valid_capture is not None
            else []
        )
        type_summary = self._build_type_summary(
            latest_valid_capture.payload_json if latest_valid_capture is not None else None,
            latest_items,
        )

        return {
            "url": self.url,
            "matchedRequestUrl": latest_valid_capture.request_url if latest_valid_capture else None,
            "rawText": latest_valid_capture.payload_text[:4000] if latest_valid_capture else None,
            "json": latest_valid_capture.payload_json if latest_valid_capture else None,
            "startTime": self._serialize_datetime(self.start_time),
            "endTime": self._serialize_datetime(self.end_time),
            "captureCount": len(captures),
            "typeSummary": type_summary,
            "articleCount": len(deduped_items),
            "filteredArticleCount": len(threshold_filtered_articles),
            "articles": threshold_filtered_articles,
            "warning": self._build_warning(
                captures,
                latest_valid_capture,
                len(threshold_filtered_articles),
                len(deduped_items),
            ),
        }

    def run(self) -> dict[str, Any]:
        self._validate()
        try:
            captures = self._collect_feed_captures()
        except Exception as exc:
            raise RuntimeError(f"账号监控执行失败：{exc}") from exc
        return self._build_result(captures)


class MicroHeadlineService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def bootstrap(self) -> None:
        with database.connection_context():
            database.create_tables(
                [AppSetting, BenchmarkAccount, MonitorRun, MonitoredArticle],
                safe=True,
            )

    def get_microheadline_settings_payload(self) -> dict[str, Any]:
        with database.connection_context():
            settings = self._load_settings()
            updated_at = self._latest_settings_timestamp()
        return self._build_settings_payload(settings, updated_at)

    def save_microheadline_settings(
        self,
        headless: bool | str,
        worker_count: int,
        default_min_play_count: int = 0,
        default_min_digg_count: int = 0,
        default_min_forward_count: int = 0,
    ) -> dict[str, Any]:
        settings = self._normalize_settings(
            {
                "headless": headless,
                "workerCount": worker_count,
                "defaultMinPlayCount": default_min_play_count,
                "defaultMinDiggCount": default_min_digg_count,
                "defaultMinForwardCount": default_min_forward_count,
            }
        )
        timestamp = now_local()
        with database.connection_context():
            self._set_setting_value(
                MICROHEADLINE_HEADLESS_KEY,
                "true" if settings["headless"] else "false",
                timestamp,
            )
            self._set_setting_value(
                MICROHEADLINE_WORKER_COUNT_KEY,
                str(settings["workerCount"]),
                timestamp,
            )
            self._set_setting_value(
                MICROHEADLINE_DEFAULT_MIN_PLAY_COUNT_KEY,
                str(settings["defaultMinPlayCount"]),
                timestamp,
            )
            self._set_setting_value(
                MICROHEADLINE_DEFAULT_MIN_DIGG_COUNT_KEY,
                str(settings["defaultMinDiggCount"]),
                timestamp,
            )
            self._set_setting_value(
                MICROHEADLINE_DEFAULT_MIN_FORWARD_COUNT_KEY,
                str(settings["defaultMinForwardCount"]),
                timestamp,
            )
        return self._build_settings_payload(settings, timestamp)

    def list_benchmark_account_options(self) -> list[dict[str, Any]]:
        with database.connection_context():
            query = (
                BenchmarkAccount.select()
                .order_by(BenchmarkAccount.updated_at.desc(), BenchmarkAccount.id.desc())
            )
            return [self._serialize_benchmark_account_option(account) for account in query]

    def list_benchmark_accounts(self, page: int, page_size: int) -> dict[str, Any]:
        safe_page = max(1, int(page or 1))
        safe_page_size = max(1, min(int(page_size or 20), MAX_PAGE_SIZE))
        with database.connection_context():
            total = BenchmarkAccount.select().count()
            query = (
                BenchmarkAccount.select()
                .order_by(BenchmarkAccount.updated_at.desc(), BenchmarkAccount.id.desc())
                .paginate(safe_page, safe_page_size)
            )
            items = [self._serialize_benchmark_account(account) for account in query]
        return {
            "items": items,
            "total": total,
            "page": safe_page,
            "pageSize": safe_page_size,
            "totalPages": ceil(total / safe_page_size) if total else 1,
            "databasePath": str(self.db_path),
        }

    def create_benchmark_account(self, url: str) -> dict[str, Any]:
        normalized_url = self._normalize_http_url(url)
        timestamp = now_local()
        with database.connection_context():
            try:
                account = BenchmarkAccount.create(
                    url=normalized_url,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            except IntegrityError as exc:
                raise ValueError("该对标账号已存在。") from exc
        return self._serialize_benchmark_account(account)

    def update_benchmark_account(self, account_id: int, url: str) -> dict[str, Any]:
        normalized_id = self._normalize_positive_int(account_id, field_name="account_id")
        normalized_url = self._normalize_http_url(url)
        timestamp = now_local()
        with database.connection_context():
            account = self._get_benchmark_account(normalized_id)
            account.url = normalized_url
            account.updated_at = timestamp
            try:
                account.save()
            except IntegrityError as exc:
                raise ValueError("该对标账号已存在。") from exc
        return self._serialize_benchmark_account(account)

    def delete_benchmark_account(self, account_id: int) -> bool:
        normalized_id = self._normalize_positive_int(account_id, field_name="account_id")
        with database.connection_context():
            deleted = (
                BenchmarkAccount.delete()
                .where(BenchmarkAccount.id == normalized_id)
                .execute()
            )
        return deleted > 0

    def delete_all_monitored_articles(self) -> dict[str, Any]:
        with database.connection_context():
            deleted_count = MonitoredArticle.delete().execute()
        return {
            "deletedCount": int(deleted_count or 0),
            "databasePath": str(self.db_path),
        }

    def list_monitored_articles(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        normalized_filters = filters or {}
        safe_page = max(1, int(page or 1))
        safe_page_size = max(1, min(int(page_size or 20), MAX_PAGE_SIZE))
        with database.connection_context():
            query = self._build_monitored_articles_query(normalized_filters)
            total = query.count()
            paged_query = (
                query.order_by(MonitoredArticle.publish_time.desc(), MonitoredArticle.updated_at.desc())
                .paginate(safe_page, safe_page_size)
            )
            items = [self._serialize_monitored_article(article) for article in paged_query]
        return {
            "items": items,
            "total": total,
            "page": safe_page,
            "pageSize": safe_page_size,
            "totalPages": ceil(total / safe_page_size) if total else 1,
            "databasePath": str(self.db_path),
        }

    def list_monitored_article_ids(
        self,
        filters: dict[str, Any] | None = None,
    ) -> list[int]:
        normalized_filters = filters or {}
        limit = self._normalize_non_negative_int(normalized_filters.get("limit"), default=0)
        sort_by = str(normalized_filters.get("sortBy") or "").strip()
        with database.connection_context():
            query = self._build_monitored_articles_query(normalized_filters)
            if sort_by == "playCountDesc":
                ordered_query = query.order_by(
                    fn.COALESCE(MonitoredArticle.play_count, 0).desc(),
                    MonitoredArticle.publish_time.desc(),
                    MonitoredArticle.updated_at.desc(),
                    MonitoredArticle.id.desc(),
                )
            else:
                ordered_query = query.order_by(
                    MonitoredArticle.publish_time.desc(),
                    MonitoredArticle.updated_at.desc(),
                    MonitoredArticle.id.desc(),
                )
            if limit > 0:
                ordered_query = ordered_query.limit(limit)
            return [article.id for article in ordered_query]

    def run_account_monitor(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._normalize_http_url(payload.get("url"))
        benchmark_account_id = payload.get("benchmarkAccountId")
        start_time = self._parse_datetime(payload.get("startTime"))
        end_time = self._parse_datetime(payload.get("endTime"))
        single_capture = bool(payload.get("singleCapture", False))

        with database.connection_context():
            benchmark_account = None
            if benchmark_account_id is not None:
                benchmark_account = self._get_benchmark_account(
                    self._normalize_positive_int(benchmark_account_id, field_name="benchmarkAccountId")
                )
            if benchmark_account is None:
                benchmark_account = BenchmarkAccount.get_or_none(BenchmarkAccount.url == url)
            if benchmark_account is None:
                benchmark_account = BenchmarkAccount.create(
                    url=url,
                    created_at=now_local(),
                    updated_at=now_local(),
                )
            monitor_run = self._create_monitor_run(benchmark_account, url)
            settings = self._automation_settings()

        try:
            logger.info(
                "开始执行单账号文章抓取 benchmark_account_id=%s url=%s start_time=%s end_time=%s single_capture=%s",
                benchmark_account.id,
                url,
                start_time,
                end_time,
                single_capture,
            )
            monitor = MicroHeadlineAccountMonitor(
                url=url,
                start_time=start_time,
                end_time=end_time,
                single_capture=single_capture,
                settings=settings,
            )
            result = monitor.run()
            with database.connection_context():
                benchmark_account = self._get_benchmark_account(benchmark_account.id)
                monitor_run = MonitorRun.get_by_id(monitor_run.id)
                saved_count = self._persist_monitored_articles(
                    benchmark_account,
                    monitor_run,
                    result.get("articles") or [],
                )
                status = "warning" if result.get("warning") else "success"
                self._finish_monitor_run(
                    monitor_run,
                    status=status,
                    warning=result.get("warning"),
                    article_count=saved_count,
                )
            result["savedCount"] = saved_count
            result["monitorRunId"] = monitor_run.id
            return result
        except Exception as exc:
            with database.connection_context():
                monitor_run = MonitorRun.get_by_id(monitor_run.id)
                self._finish_monitor_run(monitor_run, status="failed", warning=str(exc), article_count=0)
            raise

    def run_article_monitoring(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_account_ids = payload.get("benchmarkAccountIds") or []
        account_ids = list(dict.fromkeys(int(account_id) for account_id in raw_account_ids))
        if not account_ids:
            raise ValueError("请至少选择一个对标账号。")

        start_time = self._parse_datetime(payload.get("startTime"))
        end_time = self._parse_datetime(payload.get("endTime"))
        thresholds = MonitoringThresholds(
            min_play_count=self._normalize_non_negative_int(
                payload.get("minPlayCount"),
                default=DEFAULT_MIN_PLAY_COUNT,
            ),
            min_digg_count=self._normalize_non_negative_int(
                payload.get("minDiggCount"),
                default=DEFAULT_MIN_DIGG_COUNT,
            ),
            min_forward_count=self._normalize_non_negative_int(
                payload.get("minForwardCount"),
                default=DEFAULT_MIN_FORWARD_COUNT,
            ),
        )
        settings = self._automation_settings()

        logger.info(
            "开始执行批量文章抓取 account_ids=%s start_time=%s end_time=%s thresholds=%s/%s/%s headless=%s workers=%s",
            account_ids,
            start_time,
            end_time,
            thresholds.min_play_count,
            thresholds.min_digg_count,
            thresholds.min_forward_count,
            settings.headless,
            settings.worker_count,
        )

        def run_single(account_id: int) -> BatchMonitorAccountResult:
            with database.connection_context():
                benchmark_account = self._get_benchmark_account(account_id)
                benchmark_account_url = benchmark_account.url
                monitor_run = self._create_monitor_run(benchmark_account, benchmark_account_url)

            try:
                monitor = MicroHeadlineAccountMonitor(
                    url=benchmark_account_url,
                    start_time=start_time,
                    end_time=end_time,
                    thresholds=thresholds,
                    settings=settings,
                )
                result = monitor.run()
                with database.connection_context():
                    benchmark_account = self._get_benchmark_account(account_id)
                    monitor_run = MonitorRun.get_by_id(monitor_run.id)
                    saved_count = self._persist_monitored_articles(
                        benchmark_account,
                        monitor_run,
                        result.get("articles") or [],
                    )
                    status = "warning" if result.get("warning") else "success"
                    self._finish_monitor_run(
                        monitor_run,
                        status=status,
                        warning=result.get("warning"),
                        article_count=saved_count,
                    )
                return BatchMonitorAccountResult(
                    benchmark_account_id=account_id,
                    benchmark_account_url=benchmark_account_url,
                    status=status,
                    saved_count=saved_count,
                    article_count=int(result.get("articleCount") or 0),
                    filtered_article_count=int(result.get("filteredArticleCount") or 0),
                    capture_count=int(result.get("captureCount") or 0),
                    warning=result.get("warning"),
                    error=None,
                    monitor_run_id=monitor_run.id,
                    articles=result.get("articles") or [],
                )
            except Exception as exc:
                with database.connection_context():
                    monitor_run = MonitorRun.get_by_id(monitor_run.id)
                    self._finish_monitor_run(monitor_run, status="failed", warning=str(exc), article_count=0)
                return BatchMonitorAccountResult(
                    benchmark_account_id=account_id,
                    benchmark_account_url=benchmark_account_url,
                    status="failed",
                    saved_count=0,
                    article_count=0,
                    filtered_article_count=0,
                    capture_count=0,
                    warning=None,
                    error=str(exc),
                    monitor_run_id=monitor_run.id,
                    articles=[],
                )

        results: list[BatchMonitorAccountResult] = []
        with ThreadPoolExecutor(max_workers=settings.worker_count) as executor:
            future_map = {
                executor.submit(run_single, account_id): account_id for account_id in account_ids
            }
            for future in as_completed(future_map):
                results.append(future.result())

        results.sort(key=lambda item: account_ids.index(item.benchmark_account_id))
        succeeded_count = sum(1 for item in results if item.status == "success")
        failed_count = sum(1 for item in results if item.status == "failed")
        warning_count = sum(1 for item in results if item.status == "warning")
        return {
            "requestedCount": len(account_ids),
            "succeededCount": succeeded_count,
            "failedCount": failed_count,
            "warningCount": warning_count,
            "results": [item.to_dict() for item in results],
        }

    def _load_settings(self) -> dict[str, Any]:
        return self._normalize_settings(
            {
                "headless": _get_setting_value(MICROHEADLINE_HEADLESS_KEY),
                "workerCount": _get_setting_value(MICROHEADLINE_WORKER_COUNT_KEY),
                "defaultMinPlayCount": _get_setting_value(MICROHEADLINE_DEFAULT_MIN_PLAY_COUNT_KEY),
                "defaultMinDiggCount": _get_setting_value(MICROHEADLINE_DEFAULT_MIN_DIGG_COUNT_KEY),
                "defaultMinForwardCount": _get_setting_value(MICROHEADLINE_DEFAULT_MIN_FORWARD_COUNT_KEY),
            }
        )

    def _latest_settings_timestamp(self) -> datetime | None:
        rows = list(
            AppSetting.select()
            .where(
                AppSetting.key.in_(
                    [
                        MICROHEADLINE_HEADLESS_KEY,
                        MICROHEADLINE_WORKER_COUNT_KEY,
                        MICROHEADLINE_DEFAULT_MIN_PLAY_COUNT_KEY,
                        MICROHEADLINE_DEFAULT_MIN_DIGG_COUNT_KEY,
                        MICROHEADLINE_DEFAULT_MIN_FORWARD_COUNT_KEY,
                    ]
                )
            )
            .order_by(AppSetting.updated_at.desc())
            .limit(1)
        )
        return rows[0].updated_at if rows else None

    def _build_settings_payload(
        self,
        settings: dict[str, Any],
        updated_at: datetime | None,
    ) -> dict[str, Any]:
        return {
            "settings": settings,
            "workerCountMin": 1,
            "workerCountMax": MAX_WORKER_COUNT,
            "databasePath": str(self.db_path),
            "updatedAt": updated_at.isoformat(sep=" ", timespec="seconds") if updated_at else "",
        }

    def _normalize_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        return {
            "headless": _parse_bool(settings.get("headless"), DEFAULT_HEADLESS),
            "workerCount": max(
                1,
                min(
                    self._normalize_non_negative_int(
                        settings.get("workerCount"),
                        default=DEFAULT_WORKER_COUNT,
                    ) or DEFAULT_WORKER_COUNT,
                    MAX_WORKER_COUNT,
                ),
            ),
            "defaultMinPlayCount": self._normalize_non_negative_int(
                settings.get("defaultMinPlayCount"),
                default=DEFAULT_MIN_PLAY_COUNT,
            ),
            "defaultMinDiggCount": self._normalize_non_negative_int(
                settings.get("defaultMinDiggCount"),
                default=DEFAULT_MIN_DIGG_COUNT,
            ),
            "defaultMinForwardCount": self._normalize_non_negative_int(
                settings.get("defaultMinForwardCount"),
                default=DEFAULT_MIN_FORWARD_COUNT,
            ),
        }

    def _automation_settings(self) -> AutomationSettings:
        settings = self._load_settings()
        return AutomationSettings(
            headless=bool(settings["headless"]),
            worker_count=int(settings["workerCount"]),
        )

    def _get_benchmark_account(self, account_id: int) -> BenchmarkAccount:
        account = BenchmarkAccount.get_or_none(BenchmarkAccount.id == int(account_id))
        if account is None:
            raise ValueError("对标账号不存在，列表可能已经过期。")
        return account

    def _serialize_benchmark_account(self, account: BenchmarkAccount) -> dict[str, Any]:
        return {
            "id": account.id,
            "url": account.url,
            "createdAt": account.created_at.isoformat(sep=" ", timespec="seconds"),
            "updatedAt": account.updated_at.isoformat(sep=" ", timespec="seconds"),
            "lastMonitoredAt": (
                account.last_monitored_at.isoformat(sep=" ", timespec="seconds")
                if account.last_monitored_at
                else None
            ),
        }

    def _serialize_benchmark_account_option(self, account: BenchmarkAccount) -> dict[str, Any]:
        return {
            "id": account.id,
            "url": account.url,
        }

    def _serialize_monitored_article(self, article: MonitoredArticle) -> dict[str, Any]:
        account = article.benchmark_account
        return {
            "id": article.id,
            "benchmarkAccountId": account.id,
            "benchmarkAccountUrl": account.url,
            "itemId": article.item_id,
            "groupId": article.group_id,
            "cellType": article.cell_type,
            "title": article.title,
            "content": article.content,
            "publishTime": (
                article.publish_time.isoformat(sep=" ", timespec="seconds")
                if article.publish_time
                else None
            ),
            "source": article.source,
            "mediaName": article.media_name,
            "displayUrl": article.display_url,
            "playCount": article.play_count,
            "diggCount": article.digg_count,
            "commentCount": article.comment_count,
            "forwardCount": article.forward_count,
            "buryCount": article.bury_count,
            "updatedAt": article.updated_at.isoformat(sep=" ", timespec="seconds"),
            "raw": json.loads(article.raw_json) if article.raw_json else {},
        }

    def _create_monitor_run(self, benchmark_account: BenchmarkAccount, source_url: str) -> MonitorRun:
        timestamp = now_local()
        return MonitorRun.create(
            benchmark_account=benchmark_account,
            source_url=str(source_url or "").strip(),
            status="running",
            warning=None,
            article_count=0,
            started_at=timestamp,
            finished_at=None,
        )

    def _finish_monitor_run(
        self,
        run: MonitorRun,
        *,
        status: str,
        warning: str | None,
        article_count: int,
    ) -> None:
        run.status = str(status or "success")
        run.warning = str(warning or "").strip() or None
        run.article_count = max(0, int(article_count or 0))
        run.finished_at = now_local()
        run.save()

    def _touch_benchmark_account_monitor(
        self,
        account: BenchmarkAccount,
        monitored_at: datetime,
    ) -> None:
        account.last_monitored_at = monitored_at
        account.updated_at = monitored_at
        account.save()

    def _persist_monitored_articles(
        self,
        benchmark_account: BenchmarkAccount,
        run: MonitorRun,
        articles: list[dict[str, Any]],
    ) -> int:
        timestamp = now_local()
        saved_count = 0
        with database.atomic():
            for article in articles:
                dedupe_key = self._build_article_dedupe_key(benchmark_account.id, article)
                existing = MonitoredArticle.get_or_none(MonitoredArticle.dedupe_key == dedupe_key)
                if existing is not None and existing.isdelete:
                    continue
                article_content = _stringify(article.get("content"))
                if article_content:
                    existing_by_content = MonitoredArticle.get_or_none(
                        MonitoredArticle.content == article_content,
                        MonitoredArticle.isdelete == 0,
                    )
                    if existing_by_content is not None:
                        continue

                payload = {
                    "benchmark_account": benchmark_account,
                    "monitor_run": run,
                    "dedupe_key": dedupe_key,
                    "item_id": _stringify(article.get("itemId")),
                    "group_id": _stringify(article.get("groupId")),
                    "cell_type": _stringify(article.get("cellType")),
                    "title": _stringify(article.get("title")),
                    "content": article_content,
                    "publish_time": self._parse_datetime(article.get("publishTime")),
                    "source": _stringify(article.get("source")),
                    "media_name": _stringify(article.get("mediaName")),
                    "display_url": _stringify(article.get("displayUrl")),
                    "play_count": article.get("playCount"),
                    "digg_count": article.get("diggCount"),
                    "comment_count": article.get("commentCount"),
                    "forward_count": article.get("forwardCount"),
                    "bury_count": article.get("buryCount"),
                    "raw_json": json.dumps(article.get("raw") or {}, ensure_ascii=False),
                    "updated_at": timestamp,
                }

                if existing is None:
                    MonitoredArticle.create(**payload, created_at=timestamp, isdelete=0)
                else:
                    existing.benchmark_account = payload["benchmark_account"]
                    existing.monitor_run = payload["monitor_run"]
                    existing.item_id = payload["item_id"]
                    existing.group_id = payload["group_id"]
                    existing.cell_type = payload["cell_type"]
                    existing.title = payload["title"]
                    existing.content = payload["content"]
                    existing.publish_time = payload["publish_time"]
                    existing.source = payload["source"]
                    existing.media_name = payload["media_name"]
                    existing.display_url = payload["display_url"]
                    existing.play_count = payload["play_count"]
                    existing.digg_count = payload["digg_count"]
                    existing.comment_count = payload["comment_count"]
                    existing.forward_count = payload["forward_count"]
                    existing.bury_count = payload["bury_count"]
                    existing.raw_json = payload["raw_json"]
                    existing.updated_at = timestamp
                    existing.save()
                saved_count += 1

            self._touch_benchmark_account_monitor(benchmark_account, timestamp)

        return saved_count

    def _build_article_dedupe_key(self, account_id: int, article: dict[str, Any]) -> str:
        item_id = _stringify(article.get("itemId"))
        if item_id:
            return f"{account_id}:item:{item_id}"
        group_id = _stringify(article.get("groupId"))
        if group_id:
            return f"{account_id}:group:{group_id}"
        publish_time = _stringify(article.get("publishTime")) or "none"
        content = _stringify(article.get("content")) or "none"
        return f"{account_id}:fallback:{publish_time}:{content[:80]}"

    def _build_monitored_articles_query(self, filters: dict[str, Any]) -> Any:
        query = (
            MonitoredArticle.select(MonitoredArticle, BenchmarkAccount)
            .join(BenchmarkAccount)
            .where(MonitoredArticle.isdelete == 0)
        )

        account_id = filters.get("accountId")
        if account_id not in (None, ""):
            query = query.where(
                MonitoredArticle.benchmark_account == self._normalize_positive_int(
                    account_id,
                    field_name="accountId",
                )
            )

        keyword = str(filters.get("keyword") or "").strip()
        if keyword:
            query = query.where(
                MonitoredArticle.content.contains(keyword)
                | MonitoredArticle.title.contains(keyword)
            )

        start_time = self._parse_datetime(filters.get("startTime"))
        if start_time is not None:
            query = query.where(MonitoredArticle.publish_time >= start_time)

        end_time = self._parse_datetime(filters.get("endTime"))
        if end_time is not None:
            query = query.where(MonitoredArticle.publish_time <= end_time)

        for field_name, column in (
            ("minPlayCount", MonitoredArticle.play_count),
            ("minDiggCount", MonitoredArticle.digg_count),
            ("minForwardCount", MonitoredArticle.forward_count),
        ):
            raw_value = filters.get(field_name)
            if raw_value in (None, ""):
                continue
            query = query.where(column >= self._normalize_non_negative_int(raw_value, default=0))

        return query

    def _parse_datetime(self, value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("时间格式不正确，请使用 ISO 日期时间格式。") from exc

    def _normalize_positive_int(self, value: Any, *, field_name: str) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} 必须是正整数。") from exc
        if normalized <= 0:
            raise ValueError(f"{field_name} 必须大于 0。")
        return normalized

    def _normalize_non_negative_int(self, value: Any, *, default: int = 0) -> int:
        if value in (None, ""):
            return default
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("请输入大于等于 0 的整数。") from exc
        if normalized < 0:
            raise ValueError("请输入大于等于 0 的整数。")
        return normalized

    def _normalize_http_url(self, value: Any) -> str:
        text = str(value or "").strip()
        parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("请输入有效的 http/https 链接。")
        return text

    def _set_setting_value(self, key: str, value: str, timestamp: datetime) -> None:
        setting = AppSetting.get_or_none(AppSetting.key == key)
        if setting is None:
            AppSetting.create(
                key=key,
                value=value,
                created_at=timestamp,
                updated_at=timestamp,
            )
            return
        setting.value = value
        setting.updated_at = timestamp
        setting.save()


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_setting_value(key: str) -> str | None:
    setting = AppSetting.get_or_none(AppSetting.key == key)
    return setting.value if setting is not None else None
