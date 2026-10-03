"""Tests for the TLLMTranslator (local translation LLM) service."""

import unittest
from unittest import mock

import requests

from pdf2zh import cache
from pdf2zh.translator import TLLMTranslator, _tllm_lang_name


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def _envs(**overrides):
    envs = {
        "TLLM_BASE_URL": "http://127.0.0.1:8080",
        "TLLM_API_KEY": "local",
        "TLLM_MODEL": "hy-mt1.5-1.8b",
        "TLLM_PRESET": "hy-mt",
        "TLLM_GLOSSARY": "",
        "TLLM_TEMPLATE": "",
    }
    envs.update(overrides)
    return envs


class TestTLLMTranslator(unittest.TestCase):
    def setUp(self):
        self.test_db = cache.init_test_db()

    def tearDown(self):
        cache.clean_test_db(self.test_db)

    def _translator(self, **env_overrides):
        return TLLMTranslator(
            "en", "vi", "", envs=_envs(**env_overrides), ignore_cache=True
        )

    def test_hy_mt_prompt_openai_transport(self):
        translator = self._translator()
        response = FakeResponse(
            {"choices": [{"message": {"content": 'Translation: "Xin chào"'}}]}
        )
        with mock.patch.object(requests.Session, "post", return_value=response) as post:
            result = translator.do_translate("Hello world")

        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        self.assertEqual(url, "http://127.0.0.1:8080/v1/chat/completions")
        self.assertIn("messages", payload)
        prompt = payload["messages"][0]["content"]
        self.assertIn(
            "Translate the following segment into Vietnamese,"
            " without additional explanation.",
            prompt,
        )
        self.assertIn("Hello world", prompt)
        self.assertEqual(payload["temperature"], 0.7)
        self.assertEqual(payload["top_p"], 0.6)
        # Quotes and "Translation:" prefix are cleaned up.
        self.assertEqual(result, "Xin chào")

    def test_lmstudio_native_transport(self):
        translator = self._translator(TLLM_BASE_URL="http://localhost:8080/api/v1")
        response = FakeResponse(
            {
                "output": [
                    {"type": "message", "content": "Thuật toán"},
                    {"type": "message", "content": " gradient descent"},
                ]
            }
        )
        with mock.patch.object(requests.Session, "post", return_value=response) as post:
            result = translator.do_translate("The gradient descent")

        self.assertEqual(post.call_args.args[0], "http://localhost:8080/api/v1/chat")
        payload = post.call_args.kwargs["json"]
        self.assertIn("input", payload)
        self.assertNotIn("messages", payload)
        self.assertEqual(payload["top_k"], 20)
        self.assertEqual(payload["repeat_penalty"], 1.05)
        self.assertEqual(result, "Thuật toán gradient descent")

    def test_tag_clause_only_when_markers_present(self):
        translator = self._translator()
        prompt_both = translator._render_prompt("See {v0} and [[R0]]Hello[[/R0]]")
        self.assertIn("{v0}", prompt_both)
        self.assertIn("[[R0]]...[[/R0]]", prompt_both)

        prompt_runs = translator._render_prompt("[[R0]]Hello[[/R0]]")
        self.assertIn("[[R0]]...[[/R0]]", prompt_runs)
        self.assertNotIn("placeholder tokens", prompt_runs)

        prompt_no_markers = translator._render_prompt("Plain sentence")
        self.assertNotIn("unchanged", prompt_no_markers)

    def test_glossary_injection(self):
        translator = self._translator(
            TLLM_GLOSSARY="gradient=đạo hàm; tensor => ten-xơ\nloss -> mất mát"
        )
        prompt = translator._render_prompt("text")
        self.assertIn("gradient -> đạo hàm", prompt)
        self.assertIn("tensor -> ten-xơ", prompt)
        self.assertIn("loss -> mất mát", prompt)

    def test_glossary_skipped_for_marked_text(self):
        translator = self._translator(TLLM_GLOSSARY="gradient=đạo hàm")
        prompt = translator._render_prompt("[[R0]]gradient[[/R0]]")
        self.assertNotIn("term translations consistently", prompt)
        self.assertIn("[[R0]]gradient[[/R0]]", prompt)

    def test_translategemma_preset_uses_language_codes(self):
        translator = self._translator(TLLM_PRESET="translategemma")
        prompt = translator._render_prompt("Hello")
        self.assertEqual(prompt, "<<<source>>>en<<<target>>>vi<<<text>>>Hello")

    def test_seed_x_preset_appends_code(self):
        translator = self._translator(TLLM_PRESET="seed-x")
        prompt = translator._render_prompt("Hello")
        self.assertTrue(prompt.endswith("Hello<vi>"))

    def test_custom_preset_requires_template(self):
        with self.assertRaises(ValueError):
            self._translator(TLLM_PRESET="custom")
        translator = self._translator(
            TLLM_PRESET="custom", TLLM_TEMPLATE="Dịch sang {lang_out_name}: {text}"
        )
        self.assertEqual(translator._render_prompt("Hi"), "Dịch sang Vietnamese: Hi")

    def test_unknown_preset_raises(self):
        with self.assertRaises(ValueError):
            self._translator(TLLM_PRESET="does-not-exist")

    def test_language_name_normalization(self):
        self.assertEqual(_tllm_lang_name("vi"), "Vietnamese")
        self.assertEqual(_tllm_lang_name("zh"), "Chinese")
        self.assertEqual(_tllm_lang_name("zh-Hans"), "Chinese")
        self.assertEqual(_tllm_lang_name("zh-TW"), "Traditional Chinese")
        self.assertEqual(_tllm_lang_name("unknown-code"), "unknown-code")

    def test_clean_translation(self):
        self.assertEqual(
            TLLMTranslator._clean_translation('  "Xin chào"  '), "Xin chào"
        )
        self.assertEqual(
            TLLMTranslator._clean_translation("Translation: Xin chào"), "Xin chào"
        )
        self.assertEqual(TLLMTranslator._clean_translation("「Xin chào」"), "Xin chào")


if __name__ == "__main__":
    unittest.main()
