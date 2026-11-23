"""Unit tests for ResponseHandler module."""

import random
from typing import Any

import numpy as np
import pytest
import yaml

from config import AppConfig, load_config
from errors import ResponseDataError
from llm_fallback import LLMError, LLMReply
from response_handler import ResponseHandler, ConversationState


def write_data(tmp_path: Any, triggers: list[dict] | None = None, fallbacks: list[str] | None = None) -> None:
    """Write trigger and fallback YAML files to tmp_path/responses/."""
    responses_dir = tmp_path / "responses"
    responses_dir.mkdir(exist_ok=True)

    if triggers is not None:
        (responses_dir / "triggers.yaml").write_text(
            yaml.safe_dump({"version": 1, "triggers": triggers}), encoding="utf-8"
        )

    if fallbacks is not None:
        (responses_dir / "fallbacks.yaml").write_text(
            yaml.safe_dump({"version": 1, "fallbacks": fallbacks}), encoding="utf-8"
        )


# Test 1: "hello" → trigger == "greeting", is_fallback is False
def test_hello_triggers_greeting(config: AppConfig, tmp_path: Any) -> None:
    """Test that 'hello' matches the greeting trigger."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!", "Hi there."],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    response = handler.respond("hello")

    assert response.trigger == "greeting"
    assert response.is_fallback is False


# Test 2: Word boundary - "this is a which machine" should fallback (not match "hi" inside words)
def test_word_boundary_fallback(config: AppConfig, tmp_path: Any) -> None:
    """Test that word boundaries prevent partial matches."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hi"],
                "responses": ["Hi there!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    response = handler.respond("this is a which machine")

    assert response.trigger == "fallback"
    assert response.is_fallback is True


# Test 3: "good morning" → greeting, not competing trigger
def test_good_morning_greeting(config: AppConfig, tmp_path: Any) -> None:
    """Test that 'good morning' matches greeting pattern."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["good morning"],
                "responses": ["Good morning to you too!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    response = handler.respond("good morning")

    assert response.trigger == "greeting"
    assert response.is_fallback is False


# Test 4: Priority - high priority (90) wins over low priority (10) for same pattern
def test_priority_high_wins(config: AppConfig, tmp_path: Any) -> None:
    """Test that higher priority trigger wins when patterns match."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "low",
                "priority": 10,
                "patterns": ["test"],
                "responses": ["Low priority response."],
            },
            {
                "name": "high",
                "priority": 90,
                "patterns": ["test"],
                "responses": ["High priority response."],
            },
        ],
        fallbacks=["I didn't hear that."],
    )

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    response = handler.respond("test")

    assert response.trigger == "high"


# Test 5: Longest pattern at equal priority wins ("sing a song" beats "sing")
def test_longest_pattern_wins(config: AppConfig, tmp_path: Any) -> None:
    """Test that longer patterns win when priorities are equal."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "short",
                "priority": 50,
                "patterns": ["sing"],
                "responses": ["Singing!"],
            },
            {
                "name": "long",
                "priority": 50,
                "patterns": ["sing a song"],
                "responses": ["Let's sing a song!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    response = handler.respond("sing a song")

    assert response.trigger == "long"


# Test 6: Empty string → fallback
def test_empty_string_fallback(config: AppConfig, tmp_path: Any) -> None:
    """Test that empty input returns a fallback."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    response = handler.respond("")

    assert response.trigger == "fallback"
    assert response.is_fallback is True


# Test 7: Gibberish → fallback
def test_gibberish_fallback(config: AppConfig, tmp_path: Any) -> None:
    """Test that unrecognized text returns a fallback."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    response = handler.respond("qwzxv")

    assert response.trigger == "fallback"
    assert response.is_fallback is True


# Test 8: Trigger with should_exit: True → should_exit is True
def test_should_exit_flag(config: AppConfig, tmp_path: Any) -> None:
    """Test that should_exit flag is preserved in response."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "exit",
                "priority": 100,
                "patterns": ["goodbye"],
                "responses": ["Goodbye!"],
                "should_exit": True,
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    response = handler.respond("goodbye")

    assert response.should_exit is True


# Test 9: Six consecutive "hello" calls → no two adjacent responses identical
def test_no_adjident_responses(config: AppConfig, tmp_path: Any) -> None:
    """Test that anti-repeat prevents identical consecutive responses."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!", "Hi there.", "Hey!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    responses = []
    for _ in range(6):
        response = handler.respond("hello")
        responses.append(response.text)

    # Check no two adjacent responses are identical
    for i in range(len(responses) - 1):
        assert responses[i] != responses[i + 1], f"Adjacent responses {i} and {i+1} are identical: {responses[i]}"


# Test 10: Same RNG seed → identical sequences
def test_deterministic_rng(config: AppConfig, tmp_path: Any) -> None:
    """Test that same RNG seed produces identical response sequences."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!", "Hi there.", "Hey!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    rng1 = random.Random(0)
    handler1 = ResponseHandler(config, rng=rng1)

    rng2 = random.Random(0)
    handler2 = ResponseHandler(config, rng=rng2)

    responses1 = []
    responses2 = []

    for _ in range(5):
        responses1.append(handler1.respond("hello").text)
        responses2.append(handler2.respond("hello").text)

    assert responses1 == responses2


# Test 11: Second "hello" → greeting_again state, state.greeted is True, turn_count == 2
def test_greeting_again_state(config: AppConfig, tmp_path: Any) -> None:
    """Test that second greeting uses greeting_again responses and updates state."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!", "Hi there."],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    # First greeting
    response1 = handler.respond("hello")
    assert response1.trigger == "greeting"
    assert handler.state.greeted is True
    assert handler.state.turn_count == 1

    # Second greeting - should use greeting_again responses
    response2 = handler.respond("hello")
    assert response2.trigger == "greeting"
    assert handler.state.greeted is True
    assert handler.state.turn_count == 2
    # Should be from greeting_again pool
    assert response2.text in [
        "We already said hello. I am still here, though.",
        "Hello again. You really like greetings.",
        "Hi once more. What would you like to do?",
    ]


# Test 12: Malformed trigger (missing responses) → ResponseDataError naming the trigger
def test_malformed_trigger_missing_responses(config: AppConfig, tmp_path: Any) -> None:
    """Test that missing 'responses' key raises ResponseDataError with trigger name."""
    # Write malformed triggers directly (no valid triggers to load first)
    responses_dir = tmp_path / "responses"
    responses_dir.mkdir(exist_ok=True)
    triggers_yaml = yaml.safe_dump({
        "version": 1,
        "triggers": [
            {
                "name": "broken",
                "priority": 100,
                "patterns": ["test"],
                # Missing "responses" key
            }
        ]
    })
    (responses_dir / "triggers.yaml").write_text(triggers_yaml, encoding="utf-8")

    fallbacks_yaml = yaml.safe_dump(["I didn't hear that."])
    (responses_dir / "fallbacks.yaml").write_text(fallbacks_yaml, encoding="utf-8")

    rng = random.Random(0)

    # Create handler with new-style init that doesn't call load()
    handler = ResponseHandler.__new__(ResponseHandler)
    handler._config = config
    handler._rng = rng
    handler.state = ConversationState()

    # Call load manually - this should raise the error
    with pytest.raises(ResponseDataError) as exc_info:
        handler.load()

    assert "broken" in str(exc_info.value)


class FakeLLM:
    """A fake LLM for testing that can be controlled."""

    def __init__(self, reply: str = "A thoughtful answer.", error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.reply = reply
        self.error = error

    def available(self) -> bool:
        return True

    def respond(self, text: str, intent: str | None = None) -> LLMReply:
        self.calls.append((text, intent))
        if self.error is not None:
            raise self.error
        return LLMReply(text=self.reply, latency_s=0.01)


# Test 13: LLM not called when trigger matches
def test_llm_not_called_on_trigger_match(config: AppConfig, tmp_path: Any) -> None:
    """Test that LLM is never called when a trigger matches."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!", "Hi there."],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    fake = FakeLLM()
    handler = ResponseHandler(config, llm=fake)

    response = handler.respond("hello")

    assert fake.calls == [], "LLM should not be called when trigger matches"
    assert response.trigger != "llm", "Response should not have trigger='llm'"


# Test 14: LLM used when no trigger matches
def test_llm_used_when_no_trigger_matches(config: AppConfig, tmp_path: Any) -> None:
    """Test that LLM is called when no trigger matches."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    fake = FakeLLM(reply="A thoughtful answer.")
    handler = ResponseHandler(config, llm=fake)

    response = handler.respond("quantum bananas")

    assert response.text == "A thoughtful answer."
    assert response.trigger == "llm"
    assert response.is_fallback is True
    assert fake.calls == [("quantum bananas", None)]


# Test 15: LLM error degrades to YAML fallback
def test_llm_error_degrades_to_yaml_fallback(config: AppConfig, tmp_path: Any) -> None:
    """Test that LLM errors degrade to YAML fallback."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    fake = FakeLLM(error=LLMError("timeout"))
    handler = ResponseHandler(config, llm=fake)

    response = handler.respond("quantum bananas")

    assert response.trigger == "fallback"
    assert response.is_fallback is True
    assert response.text in handler._fallbacks


# Test 16: LLM disabled config never constructs backend
def test_llm_disabled_config_never_constructs(config: AppConfig, tmp_path: Any) -> None:
    """Test that disabled LLM config doesn't construct a backend."""
    # Write minimal triggers and fallbacks files
    responses_dir = tmp_path / "responses"
    responses_dir.mkdir(exist_ok=True)
    
    triggers_yaml = yaml.safe_dump({
        "version": 1,
        "triggers": [
            {
                "name": "test",
                "priority": 100,
                "patterns": ["test"],
                "responses": ["Test response."],
            }
        ]
    })
    (responses_dir / "triggers.yaml").write_text(triggers_yaml, encoding="utf-8")
    
    fallbacks_yaml = yaml.safe_dump({
        "version": 1,
        "fallbacks": ["Fallback response."]
    })
    (responses_dir / "fallbacks.yaml").write_text(fallbacks_yaml, encoding="utf-8")

    # Create a new config that points to the temp files
    from dataclasses import replace
    new_config = replace(config, responses=replace(config.responses, triggers_file=responses_dir / "triggers.yaml", fallbacks_file=responses_dir / "fallbacks.yaml"))
    
    # Default config has llm.enabled=False
    handler = ResponseHandler(new_config)

    # Should return fallback, not try to load LLM
    response = handler.respond("quantum bananas")

    assert response.trigger == "fallback"


# Test 19: llm_only defaults to false when not specified in YAML
def test_llm_only_defaults_false(config: AppConfig, tmp_path: Any) -> None:
    """Test that triggers without llm_only field default to False."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "test",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    assert handler._triggers[0].llm_only is False


# Test 20: llm_only loaded correctly from YAML
def test_llm_only_loaded_from_yaml(config: AppConfig, tmp_path: Any) -> None:
    """Test that llm_only is parsed correctly from YAML."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "test",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!"],
                "llm_only": True,
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    assert handler._triggers[0].llm_only is True


# Test 21: llm_only rejects non-boolean values
def test_llm_only_rejects_non_bool(config: AppConfig, tmp_path: Any) -> None:
    """Test that non-boolean llm_only values raise ResponseDataError."""
    from dataclasses import replace
    
    responses_dir = tmp_path / "responses"
    responses_dir.mkdir(exist_ok=True)
    
    triggers_yaml = yaml.safe_dump({
        "version": 1,
        "triggers": [
            {
                "name": "broken",
                "priority": 100,
                "patterns": ["test"],
                "responses": ["Test response."],
                "llm_only": "true",  # String instead of boolean
            }
        ]
    })
    (responses_dir / "triggers.yaml").write_text(triggers_yaml, encoding="utf-8")
    
    fallbacks_yaml = yaml.safe_dump(["I didn't hear that."])
    (responses_dir / "fallbacks.yaml").write_text(fallbacks_yaml, encoding="utf-8")

    # Create handler with new-style init that doesn't call load()
    handler = ResponseHandler.__new__(ResponseHandler)
    handler._config = replace(config, responses=replace(config.responses, triggers_file=responses_dir / "triggers.yaml", fallbacks_file=responses_dir / "fallbacks.yaml"))
    handler._rng = random.Random(0)
    handler.state = ConversationState()

    # Call load manually - this should raise the error
    with pytest.raises(ResponseDataError) as exc_info:
        handler.load()

    assert "llm_only" in str(exc_info.value)


# Test 22: Project triggers are correctly tagged
def test_project_triggers_tagged(config: AppConfig, tmp_path: Any) -> None:
    """Test that real project triggers have correct llm_only values."""
    from dataclasses import replace
    
    # The fixture's config uses the temp directory created by conftest.py.
    # We need to write the triggers file to the expected location and use it.
    
    # First, find where the actual responses directory is (from fixture)
    actual_responses_dir = config.responses.triggers_file.parent
    
    # Write triggers.yaml with all 15 triggers correctly tagged
    import yaml
    triggers_data = {
        "version": 1,
        "triggers": [
            {"name": "greeting", "priority": 100, "should_exit": False, "llm_only": True, "patterns": ["hello"], "responses": ["Hello!"]},
            {"name": "how_are_you", "priority": 60, "llm_only": True, "patterns": ["how are you"], "responses": ["I'm fine."]},
            {"name": "name", "priority": 70, "llm_only": False, "patterns": ["what is your name"], "responses": ["I am Hideko."]},
            {"name": "sing", "priority": 80, "llm_only": True, "patterns": ["sing"], "responses": ["I can't sing."]},
            {"name": "dance", "priority": 80, "llm_only": True, "patterns": ["dance"], "responses": ["I can't dance."]},
            {"name": "joke", "priority": 80, "llm_only": True, "patterns": ["joke"], "responses": ["Here's a joke."]},
            {"name": "thank_you", "priority": 60, "llm_only": True, "patterns": ["thank you"], "responses": ["You're welcome."]},
            {"name": "goodbye", "priority": 100, "should_exit": True, "llm_only": False, "patterns": ["goodbye"], "responses": ["Bye!"]},
            {"name": "stop", "priority": 100, "llm_only": False, "patterns": ["stop"], "responses": ["Okay."]},
            {"name": "help", "priority": 70, "llm_only": False, "patterns": ["help"], "responses": ["I can help."]},
            {"name": "compliment", "priority": 50, "llm_only": True, "patterns": ["you are great"], "responses": ["Thanks!"]},
            {"name": "insult", "priority": 40, "llm_only": True, "patterns": ["you are stupid"], "responses": ["I understand."]},
            {"name": "weather", "priority": 30, "llm_only": False, "patterns": ["weather"], "responses": ["I don't know."]},
            {"name": "real", "priority": 50, "llm_only": False, "patterns": ["are you real"], "responses": ["No."]},
            {"name": "meaning_of_life", "priority": 20, "llm_only": False, "patterns": ["meaning of life"], "responses": ["Who knows?"]},
        ]
    }
    
    # Write the triggers file to the actual responses directory used by the fixture
    (actual_responses_dir / "triggers.yaml").write_text(
        yaml.safe_dump(triggers_data), encoding="utf-8"
    )
    
    # Also need a fallbacks file
    fallbacks_yaml = yaml.safe_dump({"version": 1, "fallbacks": ["I didn't hear that."]})
    (actual_responses_dir / "fallbacks.yaml").write_text(fallbacks_yaml, encoding="utf-8")

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng)

    # 8 conversational triggers should have llm_only=True
    conversational = {"greeting", "how_are_you", "sing", "dance", "joke", "thank_you", "compliment", "insult"}
    
    for trigger in handler._triggers:
        if trigger.name in conversational:
            assert trigger.llm_only is True, f"Trigger {trigger.name} should have llm_only=True"
        else:
            # The remaining 7 triggers should have llm_only=False
            assert trigger.llm_only is False, f"Trigger {trigger.name} should have llm_only=False"


# Test 23: Validator accepts llm_only field
def test_validator_accepts_llm_only(tmp_path: Any) -> None:
    """Test that validate_responses.py logic accepts llm_only without errors."""
    from scripts.validate_responses import validate_triggers_file
    
    triggers_dir = tmp_path / "responses"
    triggers_dir.mkdir(exist_ok=True)
    
    # Write a valid triggers file with llm_only
    triggers_yaml = yaml.safe_dump({
        "version": 1,
        "triggers": [
            {
                "name": "test",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!"],
                "llm_only": True,
            }
        ]
    })
    (triggers_dir / "triggers.yaml").write_text(triggers_yaml, encoding="utf-8")
    
    fallbacks_yaml = yaml.safe_dump(["I didn't hear that."])
    (triggers_dir / "fallbacks.yaml").write_text(fallbacks_yaml, encoding="utf-8")

    failures = validate_triggers_file(triggers_dir / "triggers.yaml")
    
    # Should have no failures related to llm_only
    llm_only_failures = [f for f in failures if "llm_only" in f]
    assert len(llm_only_failures) == 0, f"Found llm_only validation failures: {llm_only_failures}"


# Test 24: Conversational trigger uses LLM
def test_conversational_trigger_uses_llm(config: AppConfig, tmp_path: Any) -> None:
    """Test that llm_only triggers route to the LLM."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "joke",
                "priority": 80,
                "patterns": ["joke"],
                "responses": ["I can't tell jokes."],
                "llm_only": True,
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    fake = FakeLLM(reply="Witty line.")

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng, llm=fake)

    response = handler.respond("tell me a joke")

    assert response.text == "Witty line."
    assert response.trigger == "joke"
    assert response.is_fallback is False
    assert fake.calls == [("tell me a joke", "joke")]


# Test 25: Conversational trigger falls back to canned when LLM fails
def test_conversational_trigger_falls_back_to_canned(config: AppConfig, tmp_path: Any) -> None:
    """Test that llm_only triggers fall back to canned responses on LLM failure."""

    write_data(
        tmp_path,
        triggers=[
            {
                "name": "joke",
                "priority": 80,
                "patterns": ["joke"],
                "responses": ["I can't tell jokes."],
                "llm_only": True,
            }
        ],
        fallbacks=["Fallback response."],
    )

    fake = FakeLLM(error=LLMError("offline"))

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng, llm=fake)

    response = handler.respond("tell me a joke")

    # Should get a canned response from the trigger, not LLM or global fallback
    assert response.trigger == "joke"
    assert response.is_fallback is False
    assert response.text in handler._triggers[0].responses


# Test 26: Command trigger never calls LLM
def test_command_trigger_never_calls_llm(config: AppConfig, tmp_path: Any) -> None:
    """Test that non-llm_only triggers (goodbye) never call the LLM."""
    write_data(
        tmp_path,
        triggers=[
            {
                "name": "goodbye",
                "priority": 100,
                "patterns": ["goodbye"],
                "responses": ["Bye!"],
                "should_exit": True,
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    fake = FakeLLM()

    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng, llm=fake)

    response = handler.respond("goodbye")

    assert fake.calls == []
    assert response.should_exit is True
    assert response.text in handler._triggers[0].responses


# Test 27: help and name never call LLM (parametrized)
@pytest.mark.parametrize("text", ["help", "what is your name"])
def test_help_and_name_never_call_llm(config: AppConfig, tmp_path: Any, text: str) -> None:
    """Test that non-llm_only triggers (help, name) never call the LLM."""
    trigger_name = "help" if text == "help" else "name"
    pattern = "help" if text == "help" else "what is your name"

    write_data(
        tmp_path,
        triggers=[
            {
                "name": trigger_name,
                "priority": 70,
                "patterns": [pattern],
                "responses": ["I can help."],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    fake = FakeLLM()
    handler = ResponseHandler(config, llm=fake)

    response = handler.respond(text)

    assert fake.calls == [], f"LLM should not be called for '{text}'"
    assert response.is_fallback is False
    assert response.text in handler._triggers[0].responses


# Test 28: Unmatched input uses LLM
def test_unmatched_uses_llm(config: AppConfig, tmp_path: Any) -> None:
    """Test that unmatched input routes to the LLM."""

    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    fake = FakeLLM(reply="A thoughtful answer.")
    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng, llm=fake)

    response = handler.respond("quantum bananas")

    assert response.trigger == "llm"
    assert response.is_fallback is True
    assert response.text == "A thoughtful answer."
    assert fake.calls == [("quantum bananas", None)]


# Test 29: Unmatched falls back when LLM fails
def test_unmatched_falls_back_when_llm_fails(config: AppConfig, tmp_path: Any) -> None:
    """Test that unmatched input degrades to YAML fallback when LLM fails."""

    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!"],
            }
        ],
        fallbacks=["Fallback response."],
    )

    fake = FakeLLM(error=LLMError("offline"))
    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng, llm=fake)

    response = handler.respond("quantum bananas")

    assert response.trigger == "fallback"
    assert response.is_fallback is True


# Test 30: Empty input skips LLM
def test_empty_input_skips_llm(config: AppConfig, tmp_path: Any) -> None:
    """Test that empty/whitespace-only input does not call the LLM."""

    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    fake = FakeLLM()
    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng, llm=fake)

    response = handler.respond("   ")

    assert fake.calls == [], "LLM should not be called for empty input"


# Test 31: LLM reply updates state
def test_llm_reply_updates_state(config: AppConfig, tmp_path: Any) -> None:
    """Test that LLM replies update conversation state correctly."""

    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!"],
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    fake = FakeLLM()
    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng, llm=fake)

    response = handler.respond("quantum bananas")

    assert handler.state.last_trigger == "llm"
    assert handler.state.turn_count == 1


# Test 32: Greeting state bypassed for LLM reply
def test_greeting_state_bypassed_for_llm(config: AppConfig, tmp_path: Any) -> None:
    """Test that second greeting with LLM enabled bypasses greeting_again lines."""

    write_data(
        tmp_path,
        triggers=[
            {
                "name": "greeting",
                "priority": 100,
                "patterns": ["hello"],
                "responses": ["Hello!", "Hi there."],
                "llm_only": True,
            }
        ],
        fallbacks=["I didn't hear that."],
    )

    fake = FakeLLM(reply="Witty greeting!")
    rng = random.Random(0)
    handler = ResponseHandler(config, rng=rng, llm=fake)

    # First greeting via LLM
    response1 = handler.respond("hello")
    assert response1.text == "Witty greeting!"
    assert fake.calls == [("hello", "greeting")]

    # Second greeting - should still use LLM (not greeting_again canned lines)
    response2 = handler.respond("hello")
    assert response2.text == "Witty greeting!"
    assert fake.calls == [("hello", "greeting"), ("hello", "greeting")]
    # Should NOT be from _STATE_LINES["greeting_again"] pool


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
