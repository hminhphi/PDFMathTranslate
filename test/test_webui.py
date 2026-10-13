"""Tests for the web UI server helpers."""

import unittest

from pdf2zh.webui.server import _env_is_secret, _parse_pages


class TestWebUiHelpers(unittest.TestCase):
    def test_max_tokens_not_secret(self):
        self.assertFalse(_env_is_secret("OPENAI_MAX_TOKENS"))
        self.assertFalse(_env_is_secret("TLLM_MAX_TOKENS"))
        self.assertFalse(_env_is_secret("OPENAILIKED_STOP_TOKENS"))

    def test_keys_are_secret(self):
        self.assertTrue(_env_is_secret("OPENAI_API_KEY"))
        self.assertTrue(_env_is_secret("DEEPLX_ACCESS_TOKEN"))
        self.assertTrue(_env_is_secret("TENCENTCLOUD_SECRET_KEY"))

    def test_parse_pages(self):
        self.assertIsNone(_parse_pages("All", ""))
        self.assertEqual(_parse_pages("First", ""), [0])
        self.assertEqual(_parse_pages("First 5 pages", ""), [0, 1, 2, 3, 4])
        self.assertEqual(_parse_pages("Others", "2,4-5"), [1, 3, 4])


if __name__ == "__main__":
    unittest.main()
