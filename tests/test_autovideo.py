from __future__ import annotations

import unittest

from app.autovideo import AutoVideoAutomation


class AutoVideoAutomationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AutoVideoAutomation()

    def test_normalize_story_text_merges_complete_sentences_into_15_to_30_char_lines(self) -> None:
        story_text = (
            "第一幕阳光洒在稻田上，农人弯腰查看稻穗。"
            "第二幕微风吹过田埂，镜头缓慢推近金黄稻浪。"
        )

        normalized = self.service._normalize_story_text(story_text)

        self.assertEqual(
            normalized,
            "第一幕阳光洒在稻田上，农人弯腰查看稻穗。\n第二幕微风吹过田埂，镜头缓慢推近金黄稻浪。",
        )
        for line in normalized.splitlines():
            self.assertGreaterEqual(len(line), 15)
            self.assertLessEqual(len(line), 30)

    def test_normalize_story_text_does_not_split_single_long_sentence_without_punctuation(self) -> None:
        story_text = "这是一个超过三十个字而且没有任何标点所以不能被错误拆成两行的完整句子内容展示"

        normalized = self.service._normalize_story_text(story_text)

        self.assertEqual(normalized, story_text)
        self.assertEqual(normalized.count("\n"), 0)

    def test_normalize_story_text_respects_existing_paragraphs_and_compacts_whitespace(self) -> None:
        story_text = "  第一幕  主持人走进展厅， 介绍新品亮点。 \n\n 第二幕 观众围上前来，纷纷拿起手机拍摄。 "

        normalized = self.service._normalize_story_text(story_text)

        self.assertEqual(
            normalized,
            "第一幕主持人走进展厅，介绍新品亮点。\n第二幕观众围上前来，纷纷拿起手机拍摄。",
        )


if __name__ == "__main__":
    unittest.main()
