"""Unit tests for the svc-ai-litellm routing probe's verdict logic."""

from __future__ import annotations

import importlib.util
import unittest

from . import PROJECT_ROOT

MODULE_PATH = PROJECT_ROOT / "roles/svc-ai-litellm/files/test/probe.py"

spec = importlib.util.spec_from_file_location("litellm_probe", MODULE_PATH)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

ALIAS = "qwen2.5:0.5b"
LMSTUDIO_ONLY = "mistral:latest"


def verdict(**overrides) -> list[str]:
    kwargs = {
        "served": set(),
        "expected": [],
        "chat_model": "",
        "chat_model_served": False,
        "ollama_enabled": False,
        "lmstudio_enabled": False,
        "lmstudio_aliases": [LMSTUDIO_ONLY],
    }
    kwargs.update(overrides)
    return probe.evaluate(**kwargs)


class TestOllamaOnlyDeployment(unittest.TestCase):
    """svc-ai-ollama deployed, svc-ai-lmstudio not — variant 0."""

    def test_a_consistent_gateway_passes(self) -> None:
        self.assertEqual(
            verdict(
                served={ALIAS},
                expected=[ALIAS],
                chat_model=ALIAS,
                chat_model_served=True,
                ollama_enabled=True,
            ),
            [],
        )

    def test_an_lmstudio_alias_without_its_backend_fails(self) -> None:
        failures = verdict(
            served={ALIAS, LMSTUDIO_ONLY},
            expected=[ALIAS],
            chat_model=ALIAS,
            chat_model_served=True,
            ollama_enabled=True,
        )
        self.assertEqual(len(failures), 1)
        self.assertIn("svc-ai-lmstudio is not deployed", failures[0])

    def test_a_declared_model_the_gateway_dropped_fails(self) -> None:
        failures = verdict(
            served=set(),
            expected=[ALIAS],
            chat_model=ALIAS,
            chat_model_served=True,
            ollama_enabled=True,
        )
        self.assertTrue(
            any("does not serve" in failure for failure in failures), failures
        )

    def test_the_model_consumers_ask_for_must_be_routable(self) -> None:
        failures = verdict(
            served={ALIAS},
            expected=[ALIAS],
            chat_model="llama3:latest",
            chat_model_served=True,
            ollama_enabled=True,
        )
        self.assertEqual(len(failures), 1)
        self.assertIn("llama3:latest", failures[0])


class TestLmstudioOnlyDeployment(unittest.TestCase):
    """svc-ai-lmstudio deployed, svc-ai-ollama not — variant 2."""

    def test_the_same_alias_ollama_would_serve_passes(self) -> None:
        self.assertEqual(
            verdict(
                served={ALIAS},
                expected=[ALIAS],
                chat_model=ALIAS,
                chat_model_served=True,
                lmstudio_enabled=True,
                lmstudio_aliases=[ALIAS],
            ),
            [],
        )

    def test_a_declared_alias_the_gateway_never_routed_fails(self) -> None:
        failures = verdict(
            served=set(),
            expected=[ALIAS],
            chat_model=ALIAS,
            chat_model_served=True,
            lmstudio_enabled=True,
            lmstudio_aliases=[ALIAS],
        )
        self.assertTrue(
            any("declared and not routed" in failure for failure in failures), failures
        )

    def test_an_ollama_model_without_its_backend_fails(self) -> None:
        failures = verdict(
            served={ALIAS, "llama3:latest"},
            expected=[ALIAS],
            chat_model=ALIAS,
            chat_model_served=True,
            lmstudio_enabled=True,
            lmstudio_aliases=[ALIAS],
        )
        self.assertTrue(
            any("svc-ai-ollama is not deployed" in failure for failure in failures),
            failures,
        )


class TestBothBackendsDeployment(unittest.TestCase):
    """Variant 0 plus lmstudio: a shared alias proves nothing about lmstudio."""

    def test_only_the_exclusive_alias_is_demanded(self) -> None:
        self.assertEqual(
            verdict(
                served={ALIAS, LMSTUDIO_ONLY},
                expected=[ALIAS, LMSTUDIO_ONLY],
                chat_model=ALIAS,
                chat_model_served=True,
                ollama_enabled=True,
                lmstudio_enabled=True,
            ),
            [],
        )

    def test_a_missing_exclusive_alias_still_fails(self) -> None:
        failures = verdict(
            served={ALIAS},
            expected=[ALIAS],
            chat_model=ALIAS,
            chat_model_served=True,
            ollama_enabled=True,
            lmstudio_enabled=True,
        )
        self.assertTrue(
            any("declared and not routed" in failure for failure in failures), failures
        )


class TestNoBackendDeployment(unittest.TestCase):
    def test_an_empty_gateway_passes(self) -> None:
        self.assertEqual(verdict(), [])

    def test_any_published_model_fails(self) -> None:
        failures = verdict(served={probe.OPENROUTER_MODEL})
        self.assertTrue(
            any("no backend is deployed" in failure for failure in failures), failures
        )

    def test_the_chat_model_is_not_demanded_when_nothing_serves_it(self) -> None:
        self.assertEqual(verdict(chat_model=ALIAS), [])


if __name__ == "__main__":
    unittest.main()
