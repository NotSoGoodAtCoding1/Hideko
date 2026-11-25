"""LLM fallback module for Hideko.

This module provides an HTTP client that talks to a KoboldCpp server running locally.
No model is loaded in-process; a KoboldCpp server must be running at base_url.
Offline means loopback only (http://127.0.0.1 or http://localhost).
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass
from pathlib import Path
import sys
import typing
import urllib.error
import urllib.request

import yaml

from config import AppConfig
from errors import LLMError
from memory_store import MemoryStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMReply:
    """A reply from the LLM with timing information."""
    text: str
    latency_s: float


class LLMBackend:
    """Protocol-like base class for LLM backends.

    This exists so tests can inject a fake backend without importing network code.
    Subclasses must implement available() and generate().
    """
    
    def available(self) -> bool:
        """Return True if this backend can handle requests."""
        return False
    
    def generate(self, messages: list[dict[str, str]]) -> str:
        """Generate a response for the given chat messages.

        Args:
            messages: A list of message dicts with 'role' and 'content' keys.

        Returns:
            The generated response text.

        Raises:
            NotImplementedError: If this backend is not implemented.
        """
        raise NotImplementedError


class NullBackend(LLMBackend):
    """A no-op backend that always reports unavailable."""
    
    def available(self) -> bool:
        """Always return False."""
        return False
    
    def generate(self, messages: list[dict[str, str]]) -> str:
        """Raise LLMError since this backend is disabled."""
        raise LLMError("LLM backend is disabled")


class KoboldHttpBackend(LLMBackend):
    """A backend that sends requests to a KoboldCpp HTTP server."""
    
    def __init__(self, config: AppConfig) -> None:
        """Initialize with the given configuration.

        Args:
            config: AppConfig containing LLM settings.
        """
        self._config = config
    
    def available(self) -> bool:
        """Return True if the LLM is enabled (no model file check)."""
        return self._config.llm.enabled
    
    def generate(self, messages: list[dict[str, str]]) -> str:
        """Generate a response via KoboldCpp HTTP API.

        Args:
            messages: List of chat messages with 'role' and 'content'.

        Returns:
            The generated response text.

        Raises:
            LLMError: If the request fails or produces no reply.
        """
        cfg = self._config.llm
        url = cfg.base_url.rstrip("/") + cfg.endpoint
        
        body = {
            "model": cfg.model,
            "messages": messages,
            "max_tokens": min(cfg.max_tokens, 50),  # Cap at 50 tokens for smaller model
            "temperature": cfg.temperature,
            "stream": False,
            # Context size hint (Kobold.cpp may ignore this but it's helpful)
        }
        
        req_data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        
        try:
            with urllib.request.urlopen(req, timeout=cfg.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise LLMError(f"Cannot connect to KoboldCpp at {url}. Is KoboldCpp running?") from e
        except TimeoutError:
            raise LLMError(f"Request to KoboldCpp timed out after {cfg.timeout_s}s. Is KoboldCpp running?") from None
        except OSError as e:
            raise LLMError(f"Network error connecting to {url}: {e}. Is KoboldCpp running?") from e
        except json.JSONDecodeError:
            raise LLMError(f"Invalid JSON response from KoboldCpp at {url}") from e
        except KeyError as e:
            raise LLMError(f"Missing key in response from KoboldCpp: {e}") from e
        except IndexError as e:
            raise LLMError(f"Invalid response structure from KoboldCpp: {e}") from e
        
        # Extract text with fallback for older builds
        text = payload["choices"][0]["message"]["content"]
        if not isinstance(text, str) or not text.strip():
            # Fallback for older Kobold builds that return "text" instead of "message.content"
            alt_text = payload.get("choices", [{}])[0].get("text", "")
            if alt_text:
                text = alt_text
        
        text = text.strip()
        
        if not text:
            raise LLMError("LLM produced an empty reply")
        
        return text


class LLMFallback:
    """A fallback responder that uses the LLM when no YAML trigger matches.

    This wraps KoboldHttpBackend (or NullBackend if disabled) and handles prompting,
    memory injection, and error management. Importing this class never loads llama_cpp.
    """
    
    def __init__(
        self,
        config: AppConfig,
        memory: MemoryStore | None = None,
        backend: LLMBackend | None = None,
    ) -> None:
        """Initialize with config and optional dependencies.

        Args:
            config: AppConfig containing LLM settings.
            memory: Optional MemoryStore for user facts. If None, facts are omitted from prompts.
            backend: Optional LLMBackend to use. If None, creates KoboldHttpBackend if enabled,
                      otherwise NullBackend.
        """
        self._config = config
        self._memory = memory
        self._backend = backend if backend is not None else (
            KoboldHttpBackend(config) if config.llm.enabled else NullBackend()
        )
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm")
        self._persona_parts = self._load_persona_parts()
    
    def available(self) -> bool:
        """Return True if the backend can handle requests."""
        return self._backend.available()
    
    def _load_persona_parts(self) -> list[str] | None:
        """Load and cache persona text parts from the persona YAML file."""
        cfg = self._config.llm
        try:
            persona_data = yaml.safe_load(cfg.persona_file.read_text(encoding="utf-8"))
            if isinstance(persona_data, dict):
                system_parts: list[str] = []
                personality = persona_data.get("personality", "")
                description = persona_data.get("description", "")
                if personality and isinstance(personality, str):
                    system_parts.append(personality)
                if description and isinstance(description, str):
                    system_parts.append(description)
                return system_parts or None
            logger.warning("persona_file does not contain valid YAML with personality/description fields")
        except Exception as e:
            logger.warning(f"Cannot read persona file {cfg.persona_file}: {e}")
        return None

    def _build_messages(self, text: str, intent: str | None = None) -> list[dict[str, str]]:
        """Build the chat messages for the LLM.

        Args:
            text: The user input text.
            intent: Optional detected user intent.

        Returns:
            A list of message dicts with 'role' and 'content'.
        """
        cfg = self._config.llm

        if self._persona_parts:
            system_content = "\n".join(self._persona_parts) + "\n" + cfg.system_prompt
        else:
            system_content = cfg.system_prompt

        # Build system message
        lines = [system_content]

        # Add memory facts if available
        facts = self._memory.all() if self._memory is not None else {}
        if facts:
            lines.append("")
            lines.append("Known facts about the user:")
            for key, value in sorted(facts.items()):
                lines.append(f"- {key}: {value}")
            lines.append("")

        # Cap text at 500 characters
        capped_text = text[:500]

        # Add intent if present
        if intent is not None:
            lines.append(f"User intent: {intent}")

        user_content = "\n".join(lines) + f"\nUser: {capped_text}"

        return [{"role": "system", "content": user_content}, {"role": "user", "content": capped_text}]
    
    def respond(self, text: str, intent: str | None = None) -> LLMReply:
        """Generate a response to the given text.

        Args:
            text: The user input text.
            intent: Optional detected user intent.

        Returns:
            An LLMReply with the generated text and latency.

        Raises:
            LLMError: If the backend is unavailable or generation fails.
        """
        if not self.available():
            raise LLMError("LLM is not available")
        
        messages = self._build_messages(text, intent)
        t0 = time.perf_counter()
        
        # Use the long-lived executor; a timed-out thread cannot be killed and may
        # still occupy the single worker until it finishes.
        future = self._pool.submit(self._backend.generate, messages)

        try:
            reply = future.result(timeout=self._config.llm.timeout_s)
        except FuturesTimeout as exc:
            raise LLMError(
                f"LLM generation exceeded {self._config.llm.timeout_s:.0f}s"
            ) from exc
        except Exception as e:
            # Wrap any backend exceptions in LLMError for consistent error handling
            raise LLMError(f"LLM generation failed: {e}") from e
        
        # The TTS voice is English-only and Windows consoles are often cp1251;
        # drop emoji/non-ASCII (e.g. the 🌍✨ Qwen likes to append).
        reply_text = "".join(ch if ord(ch) < 128 else " " for ch in reply.strip())
        reply_text = __import__("re").sub(r"\s+", " ", reply_text).strip()
        if not reply_text:
            raise LLMError("LLM produced an empty reply")
        
        latency = time.perf_counter() - t0
        
        log_level = logging.DEBUG
        log_msg = f"llm: {latency:.2f}s -> {reply_text if self._config.runtime.log_transcripts else '***REDACTED***'}"
        logger.log(log_level, log_msg)
        
        return LLMReply(text=reply_text, latency_s=latency)


def main(argv=None) -> None:
    """CLI entry point for testing the LLM fallback."""
    parser = argparse.ArgumentParser(description="Test LLM fallback responder")
    parser.add_argument("--text", required=True, help="Input text to generate a response for")
    parser.add_argument("--config", default="config.yaml", help="Path to config file (default: config.yaml)")
    args = parser.parse_args(argv)
    
    from config import load_config
    
    config = load_config(args.config)
    
    fallback = LLMFallback(config)
    
    try:
        reply = fallback.respond(args.text)
        print(reply.text)
        print(f"Latency: {reply.latency_s:.2f}s")
    except LLMError as e:
        print(f"LLM error: {e}", file=sys.stderr)
        sys.exit(6)


if __name__ == "__main__":
    main()
