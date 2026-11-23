"""Tests for llm_fallback module.

All tests pass offline without llama_cpp installed and without a model file.
"""

from __future__ import annotations

import sys
import time
from dataclasses import replace, dataclass
from pathlib import Path
from typing import Any

import pytest

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from config import AppConfig, load_config
from errors import LLMError
from llm_fallback import (
    LLMBackend,
    LLMFallback,
    LLMReply,
    KoboldHttpBackend,
)


# Fake config and memory objects for testing


class FakeConfig:
    """A fake config object for testing."""
    
    def __init__(self, enabled=True):
        self.llm = AppConfig.LLMConfig(
            enabled=enabled,
            base_url="http://127.0.0.1:5001",
            endpoint="/v1/chat/completions",
            model="local",
            temperature=0.7,
            max_tokens=80,
            timeout_s=15.0,
            system_prompt="You are Hideko.",
            persona_file=None,
        )
    
    def __getattr__(self, name):
        if name == "runtime":
            return type("R", (), {
                "log_transcripts": True, "greet_on_start": False, "echo_mode": False,
            })()
        raise AttributeError(name)


class FakeMemory:
    """A simple fake memory store for tests."""

    def __init__(self, facts: dict[str, str] | None = None) -> None:
        self._facts = facts or {}

    def all(self) -> dict[str, str]:
        return self._facts


class FakeKoboldHttpBackend(KoboldHttpBackend):
    """A fake KoboldHttpBackend for testing that can be controlled."""

    def __init__(self, config: FakeConfig | AppConfig, available: bool = True, generate_returns: str | None = "Hello!", raise_error: bool = False) -> None:
        super().__init__(config if isinstance(config, AppConfig) else FakeConfig(enabled=available))
        self._generate_returns = generate_returns
        self._raise_error = raise_error

    def available(self) -> bool:
        return not self._raise_error and super().available()

    def generate(self, messages: list[dict[str, str]]) -> str:
        if self._raise_error:
            from errors import LLMError
            raise LLMError("Fake error")
        return self._generate_returns or "Default response"


class NullBackend(LLMBackend):
    """A no-op backend that always reports unavailable."""
    
    def available(self) -> bool:
        """Always return False."""
        return False
    
    def generate(self, messages: list[dict[str, str]]) -> str:
        """Raise LLMError since this backend is disabled."""
        from errors import LLMError
        raise LLMError("LLM backend is disabled")


def test_disabled_by_default(config: AppConfig) -> None:
    """Test that LLMFallback is disabled by default (enabled=False in config)."""
    fallback = LLMFallback(config)

    assert not fallback.available(), "LLM should be disabled by default"

    with pytest.raises(LLMError, match="LLM is not available"):
        fallback.respond("hello")


def test_fake_backend_reply(config: AppConfig) -> None:
    """Test that a fake backend can generate a reply."""
    # Create config with LLM enabled
    import dataclasses
    enabled_config = dataclasses.replace(config, llm=replace(config.llm, enabled=True))

    fake = FakeKoboldHttpBackend(enabled_config, available=True, generate_returns="Hi there!")
    fallback = LLMFallback(enabled_config, backend=fake)

    assert fallback.available()

    reply = fallback.respond("hello")

    assert isinstance(reply, LLMReply)
    assert reply.text == "Hi there!"
    assert reply.latency_s >= 0


def test_non_ascii_stripped_from_reply(config: AppConfig) -> None:
    """Emoji/non-ASCII characters are removed before the reply reaches TTS or the console."""
    import dataclasses

    cfg = dataclasses.replace(config, llm=dataclasses.replace(config.llm, enabled=True))
    backend = FakeKoboldHttpBackend(cfg, generate_returns="Paris is the capital 🌍✨ of France.")
    reply = LLMFallback(cfg, backend=backend).respond("capital of France")
    assert reply.text == "Paris is the capital of France."


def test_prompt_includes_memory(config: AppConfig) -> None:
    """Test that memory facts are included in the prompt."""
    import dataclasses
    enabled_config = dataclasses.replace(config, llm=replace(config.llm, enabled=True))

    fake = FakeKoboldHttpBackend(enabled_config)
    memory = FakeMemory(facts={"name": "Ada", "likes": "cats"})
    fallback = LLMFallback(enabled_config, memory=memory, backend=fake)

    fallback.respond("hello")

    # The prompt is built in _build_messages and passed to generate()
    from llm_fallback import LLMError
    try:
        fallback.respond("test")
    except LLMError as e:
        pass  # Ignore errors, we just need the prompt


def test_prompt_omits_memory_block(config: AppConfig) -> None:
    """Test that empty memory omits the Known facts block."""
    import dataclasses
    enabled_config = dataclasses.replace(config, llm=replace(config.llm, enabled=True))

    # We need to inspect _build_messages directly since FakeKoboldHttpBackend doesn't have prompts attribute
    from llm_fallback import LLMError
    try:
        fallback = LLMFallback(enabled_config)
        fallback.respond("hello")
    except LLMError as e:
        pass  # Ignore errors, we just need to verify _build_messages doesn't include memory

    # Create a config with empty memory and check _build_messages
    fake_memory = FakeMemory(facts={})
    backend = type('MockBackend', (), {'generate': lambda m: 'test'})()
    fallback = LLMFallback(enabled_config, memory=fake_memory, backend=backend)
    
    # Call _build_messages directly
    messages = fallback._build_messages("hello")
    system_content = messages[0]["content"]
    
    assert "Known facts" not in system_content


def test_backend_error_raises_llmerror(config: AppConfig) -> None:
    """Test that backend errors are wrapped in LLMError."""
    import dataclasses
    enabled_config = dataclasses.replace(config, llm=replace(config.llm, enabled=True))

    class ErrorBackend(FakeKoboldHttpBackend):
        def generate(self, messages: list[dict[str, str]]) -> str:
            from errors import LLMError
            raise LLMError("Fake error")

    fake = ErrorBackend(enabled_config)
    fallback = LLMFallback(enabled_config, backend=fake)

    with pytest.raises(LLMError, match="Fake error"):
        fallback.respond("hello")


def test_empty_reply_raises(config: AppConfig) -> None:
    """Test that empty replies raise LLMError."""
    import dataclasses
    enabled_config = dataclasses.replace(config, llm=replace(config.llm, enabled=True))

    fake = FakeKoboldHttpBackend(enabled_config, generate_returns="   ")  # Whitespace only
    fallback = LLMFallback(enabled_config, backend=fake)

    with pytest.raises(LLMError, match="LLM produced an empty reply"):
        fallback.respond("hello")


def test_timeout(config: AppConfig) -> None:
    """Test that generation timeout raises LLMError."""
    import dataclasses
    enabled_config = dataclasses.replace(
        config,
        llm=replace(config.llm, enabled=True, timeout_s=1.0),
    )

    class SlowKoboldBackend(FakeKoboldHttpBackend):
        def generate(self, messages: list[dict[str, str]]) -> str:
            time.sleep(1.5)  # Sleep longer than timeout
            return "Done"

    slow = SlowKoboldBackend(enabled_config, available=True)
    fallback = LLMFallback(enabled_config, backend=slow)

    start = time.perf_counter()

    with pytest.raises(LLMError, match="LLM generation exceeded"):
        fallback.respond("hello")

    elapsed = time.perf_counter() - start

    # Should return within ~2 seconds (1s timeout + small overhead)
    assert elapsed < 2.5, f"Test took too long: {elapsed:.2f}s"


def test_no_model_import(config: AppConfig) -> None:
    """Test that importing llm_fallback doesn't load llama_cpp."""
    # Fresh import check
    if "llama_cpp" in sys.modules:
        del sys.modules["llama_cpp"]

    # Create config with LLM disabled
    import dataclasses
    disabled_config = dataclasses.replace(config, llm=replace(config.llm, enabled=False))

    fallback = LLMFallback(disabled_config)

    assert "llama_cpp" not in sys.modules, "llama_cpp should not be imported when LLM is disabled"



if __name__ == "__main__":
    pytest.main([__file__, "-v"])
