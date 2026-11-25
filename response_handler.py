from __future__ import annotations

import argparse
import logging
import random
import re
import sys
import unicodedata
from dataclasses import dataclass
from typing import Any

import yaml

from config import AppConfig
from errors import LLMError, ResponseDataError
from llm_fallback import LLMFallback
from memory_store import MemoryStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Response:
    """A line for Hideko to speak."""
    text: str
    trigger: str
    is_fallback: bool
    should_exit: bool = False
    tool_action: str | None = None


class EchoResponder:
    """Phase-1 stand-in: repeats what it heard. Replaced in task 11."""

    def __init__(self, config: AppConfig) -> None:
        self._count = 0

    def respond(self, text: str) -> Response:
        self._count += 1
        return Response(text=f"I heard you say: {text}", trigger="echo",
                        is_fallback=True, should_exit=False)

    def reset(self) -> None:
        self._count = 0


@dataclass(frozen=True)
class Trigger:
    """A trigger that matches user input and produces canned responses.
    
    When llm_only is true, matched turns are written by the LLM; canned responses are the fallback.
    """
    name: str
    priority: int
    patterns: tuple[str, ...]
    responses: tuple[str, ...]
    should_exit: bool = False
    llm_only: bool = False
    tool: str | None = None


@dataclass
class ConversationState:
    turn_count: int = 0
    greeted: bool = False
    goodbye_seen: bool = False
    last_trigger: str | None = None


_STATE_LINES = {
    "greeting_again": (
        "We already said hello. I am still here, though.",
        "Hello again. You really like greetings.",
        "Hi once more. What would you like to do?",
    ),
    "after_goodbye": (
        "I already said goodbye. I am still here if you need me.",
    ),
}


def normalize(text: str) -> str:
    """Normalize text for pattern matching.
    
    Converts to NFKC normalized lowercase, replaces smart quotes with ASCII,
    removes punctuation (keeping letters/digits/underscore/apostrophe), and collapses whitespace.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class ResponseHandler:
    """Matches normalized transcripts against trigger patterns and returns a Response."""

    def __init__(
        self,
        config: AppConfig,
        rng: random.Random | None = None,
        memory: MemoryStore | None = None,
        llm: LLMFallback | None = None,
    ) -> None:
        self._config = config
        self._rng = rng if rng is not None else random.Random()
        self._memory = memory
        self._llm = (
            llm
            if llm is not None
            else (LLMFallback(config, memory=memory) if config.llm.enabled else None)
        )
        self._triggers: list[Trigger] = []
        self._compiled: list[tuple[Trigger, str, re.Pattern[str], int]] = []
        self._fallbacks: list[str] = []
        self._last_by_trigger: dict[str, str] = {}
        self._last_global: str | None = None
        self.load()

    def load(self) -> None:
        """Load and validate both YAML files, compile patterns once."""
        triggers_path = self._config.responses.triggers_file
        fallbacks_path = self._config.responses.fallbacks_file

        # Load triggers
        try:
            triggers_content = triggers_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ResponseDataError(f"Triggers file not found: {triggers_path}")
        except OSError as e:
            raise ResponseDataError(f"Cannot read triggers file {triggers_path}: {e}")

        try:
            triggers_data = yaml.safe_load(triggers_content)
        except yaml.YAMLError as e:
            raise ResponseDataError(f"Malformed triggers YAML: {e}")

        if not isinstance(triggers_data, dict):
            raise ResponseDataError(f"Triggers YAML root must be a mapping, got {type(triggers_data).__name__}")

        version = triggers_data.get("version")
        if version != 1:
            raise ResponseDataError(f"Triggers YAML version must be 1, got {version}")

        triggers_list = triggers_data.get("triggers")
        if not isinstance(triggers_list, list):
            raise ResponseDataError("Triggers YAML 'triggers' must be a list")

        for idx, trigger_raw in enumerate(triggers_list):
            if not isinstance(trigger_raw, dict):
                raise ResponseDataError(f"Trigger at index {idx} must be a mapping")

            name = trigger_raw.get("name")
            if name is None:
                name = f"<trigger-{idx}>"

            priority = trigger_raw.get("priority")
            if priority is None:
                raise ResponseDataError(f"Trigger '{name}' missing required key 'priority'")

            patterns_raw = trigger_raw.get("patterns")
            if not isinstance(patterns_raw, list) or len(patterns_raw) == 0:
                raise ResponseDataError(f"Trigger '{name}' missing or empty 'patterns'")

            responses_raw = trigger_raw.get("responses")
            if not isinstance(responses_raw, list) or len(responses_raw) == 0:
                raise ResponseDataError(f"Trigger '{name}' missing or empty 'responses'")

            should_exit = trigger_raw.get("should_exit", False)

            llm_only = trigger_raw.get("llm_only", False)
            if not isinstance(llm_only, bool):
                raise ResponseDataError(
                    f"Trigger '{name}' llm_only must be a boolean, got {type(llm_only).__name__}"
                )

            tool = trigger_raw.get("tool")
            if tool is not None and not isinstance(tool, str):
                raise ResponseDataError(
                    f"Trigger '{name}' tool must be a string, got {type(tool).__name__}"
                )

            # Compile patterns with word boundaries and escaping
            compiled_patterns = []
            for pattern_idx, pattern in enumerate(patterns_raw):
                if not isinstance(pattern, str):
                    raise ResponseDataError(f"Trigger '{name}' pattern at index {pattern_idx} must be a string")
                rx = re.compile(rf"\b{re.escape(pattern)}\b", re.IGNORECASE)
                word_count = len(pattern.split())
                compiled_patterns.append((pattern, rx, word_count))

            trigger = Trigger(
                name=name,
                priority=priority,
                patterns=tuple(patterns_raw),
                responses=tuple(responses_raw),
                should_exit=should_exit,
                llm_only=llm_only,
                tool=tool,
            )
            self._triggers.append(trigger)
            # Store: (trigger, pattern_text, compiled_regex, word_count)
            for pattern, rx, word_count in compiled_patterns:
                self._compiled.append((trigger, pattern, rx, word_count))

        # Load fallbacks
        try:
            fallbacks_content = fallbacks_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning(f"Fallbacks file not found: {fallbacks_path}, using default")
            self._fallbacks = ["I did not catch that."]
            return
        except OSError as e:
            logger.warning(f"Cannot read fallbacks file {fallbacks_path}: {e}")
            self._fallbacks = ["I did not catch that."]
            return

        try:
            fallbacks_data = yaml.safe_load(fallbacks_content)
        except yaml.YAMLError as e:
            raise ResponseDataError(f"Malformed fallbacks YAML: {e}")

        if not isinstance(fallbacks_data, dict):
            raise ResponseDataError(f"Fallbacks YAML root must be a mapping, got {type(fallbacks_data).__name__}")

        fallbacks_list = fallbacks_data.get("fallbacks")
        if fallbacks_list is None:
            self._fallbacks = ["I did not catch that."]
            return
        if not isinstance(fallbacks_list, list):
            raise ResponseDataError("Fallbacks YAML 'fallbacks' must be a list")

        # Filter out empty strings and keep as-is (do not lowercase)
        self._fallbacks = [f for f in fallbacks_list if isinstance(f, str) and f.strip()]
        if not self._fallbacks:
            logger.warning("Fallbacks file is empty, using default")
            self._fallbacks = ["I did not catch that."]

        self.state = ConversationState()

    def respond(self, text: str) -> Response:
        """Match text against triggers and return a Response.
        
        Never raises for ordinary input; always returns a Response.
        Truncates input to 500 characters before processing.
        """
        # Truncate input to prevent runaway regex subjects
        text = text[:500]

        # Normalize
        normalized = normalize(text)

        # Empty after normalization -> fallback
        if not normalized:
            return self._fallback_response()

        # Find all matching triggers with their patterns
        matches: list[tuple[Trigger, str, int]] = []  # (trigger, pattern_text, score_key)

        for trigger, pattern, rx, word_count in self._compiled:
            if rx.search(normalized):
                # Score key: (priority, word_count, -pattern_index)
                # We need to track pattern index within the trigger for tie-breaking
                # Re-scan to get pattern index
                patterns = trigger.patterns
                pattern_idx = patterns.index(pattern)
                score_key = (trigger.priority, word_count, -pattern_idx)
                matches.append((trigger, pattern, score_key))

        if not matches:
            llm_response = self._try_llm(text)
            if llm_response is not None:
                return llm_response
            return self._fallback_response()

        # Pick the best match by score key (max)
        best_match = max(matches, key=lambda x: x[2])
        trigger, pattern, _ = best_match
        tool_action = trigger.tool

        logger.debug(f"match: {normalized!r} -> {trigger.name} (priority {trigger.priority}, pattern {pattern!r})")

        # Hybrid persona: conversational intents are written by the LLM.
        # Commands/goodbye/help/facts (llm_only: false) stay canned below.
        if trigger.llm_only:
            llm_response = self._try_llm(text, intent=trigger.name)
            if llm_response is not None:
                return llm_response

        # Response selection with anti-repeat
        responses = list(trigger.responses)
        last_for_trigger = self._last_by_trigger.get(trigger.name)

        if last_for_trigger is not None and len(responses) > 1:
            # Exclude the previous response for this trigger
            responses = [r for r in responses if r != last_for_trigger]

        if not responses:
            # All responses were excluded (shouldn't happen with proper logic, but safety)
            responses = list(trigger.responses)

        chosen = self._rng.choice(responses)

        # Cross-trigger anti-repeat: avoid repeating the last global response if ≥2 options
        if len(responses) >= 2 and chosen == self._last_global:
            other_responses = [r for r in responses if r != self._last_global]
            if other_responses:
                chosen = self._rng.choice(other_responses)

        # State-dependent overrides — capture old values BEFORE updating state
        trigger_name = trigger.name
        was_greeted = self.state.greeted
        was_goodbye = self.state.goodbye_seen

        if trigger_name == "greeting" and self._memory is not None:
            name = self._memory.get("name")
            if name:
                chosen = (
                    f"Hello {name}. I am Hideko."
                    if not was_greeted
                    else f"Hello again, {name}."
                )
        elif trigger_name == "greeting" and was_greeted:
            chosen = self._rng.choice(_STATE_LINES["greeting_again"])
        elif trigger_name == "goodbye" and was_goodbye:
            chosen = _STATE_LINES["after_goodbye"][0]

        # Apply anti-repeat to state-dependent lines too
        if trigger_name in ("greeting", "goodbye"):
            last_for_trigger = self._last_by_trigger.get(trigger.name)
            if last_for_trigger is not None and chosen == last_for_trigger:
                # Pick a different response from the same pool
                pool = _STATE_LINES["greeting_again"] if trigger_name == "greeting" else _STATE_LINES["after_goodbye"]
                other_responses = [r for r in pool if r != last_for_trigger]
                if other_responses:
                    chosen = self._rng.choice(other_responses)

        # Update state — AFTER applying overrides
        self.state.turn_count += 1
        self.state.last_trigger = trigger_name if trigger_name != "fallback" else "fallback"
        if trigger_name == "greeting":
            self.state.greeted = True
        if trigger.should_exit:
            self.state.goodbye_seen = True

        # Update anti-repeat state
        self._last_by_trigger[trigger.name] = chosen
        self._last_global = chosen

        return Response(
            text=chosen,
            trigger=trigger.name,
            is_fallback=False,
            should_exit=trigger.should_exit,
            tool_action=tool_action,
        )

    def _try_llm(self, text: str, intent: str | None = None) -> Response | None:
        """Return an LLM-authored Response, or None if unavailable/failed.

        Returning None lets the caller fall back to canned responses.
        """
        if self._llm is None or not self._llm.available():
            return None
        try:
            reply = self._llm.respond(text, intent=intent)
        except LLMError as exc:
            logger.warning("LLM failed, using canned response: %s", exc)
            return None
        self.state.turn_count += 1
        self.state.last_trigger = intent or "llm"
        self._last_global = reply.text
        return Response(
            text=reply.text,
            trigger=intent or "llm",
            is_fallback=intent is None,
            should_exit=False,
        )

    def _fallback_response(self) -> Response:
        """Return a fallback response with anti-repeat logic."""
        fallbacks = list(self._fallbacks)
        last_global = self._last_global

        if len(fallbacks) > 1 and last_global is not None:
            # Exclude the last global response
            fallbacks = [f for f in fallbacks if f != last_global]

        if not fallbacks:
            fallbacks = list(self._fallbacks)

        chosen = self._rng.choice(fallbacks)
        self._last_global = chosen

        return Response(
            text=chosen,
            trigger="fallback",
            is_fallback=True,
            should_exit=False,
        )

    def reset(self) -> None:
        """Reset anti-repeat state and conversation state."""
        self._last_by_trigger.clear()
        self._last_global = None
        self.state = ConversationState()

    @property
    def trigger_count(self) -> int:
        return len(self._triggers)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hideko response handler CLI")
    parser.add_argument("--text", type=str, help="Text to respond to (single utterance)")
    parser.add_argument("--interactive", action="store_true", help="Read from stdin until EOF")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()

    if args.seed is not None:
        import random
        rng = random.Random(args.seed)
    else:
        rng = None

    try:
        from config import load_config
        config = load_config()
        handler = ResponseHandler(config, rng=rng)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.text is not None:
        response = handler.respond(args.text)
        print(response.text)
        print(f"     trigger={response.trigger} fallback={response.is_fallback} exit={response.should_exit}")
    elif args.interactive:
        import sys
        for line in sys.stdin:
            line = line.rstrip("\n")
            if not line:
                continue
            response = handler.respond(line)
            print(f"in:  {line}")
            print(f"out: {response.text}")
            print(f"     trigger={response.trigger} fallback={response.is_fallback} exit={response.should_exit}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
