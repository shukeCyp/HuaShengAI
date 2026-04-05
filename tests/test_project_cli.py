from __future__ import annotations

import unittest

from app.project_cli import detect_terminal_state


class ProjectCliTests(unittest.TestCase):
    def test_detect_terminal_state_ignores_bgm_download_url(self) -> None:
        payload = {
            "bgms": [
                {
                    "download_url": "http://example.com/bgm.m4a",
                }
            ],
            "project": {
                "progress": "9",
                "state_message": "项目处理中",
            },
        }

        state, reason = detect_terminal_state(payload)

        self.assertIsNone(state)
        self.assertIsNone(reason)

    def test_detect_terminal_state_uses_project_progress(self) -> None:
        payload = {
            "project": {
                "progress": "100",
                "state_message": "项目处理中",
            }
        }

        state, reason = detect_terminal_state(payload)

        self.assertEqual(state, "success")
        self.assertEqual(reason, "project.progress=100.0")


if __name__ == "__main__":
    unittest.main()
