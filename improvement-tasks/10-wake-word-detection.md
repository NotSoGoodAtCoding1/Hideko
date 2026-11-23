# Task 10 — Wake Word / Hotword Detection

**Phase:** Post-improvement (UX). Depends on tasks 01-09. Touch at most 6 files.**

## Goal

Add wake word detection so Hideko can sleep/idle and only activate when the user says a trigger phrase (e.g., "Hideko" or "Hey Hideko"). This enables a hands-free, always-ready experience without continuous CPU usage or manual key presses.

**Core invariant:** When wake word mode is active and no wake word is detected, the main loop must skip full command processing and return immediately to listening for the wake word.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- Do not modify `vad.py`, `stt_engine.py`, or `tts_engine.py` core logic.
- Do not change existing trigger behavior — wake word is a pre-processing layer that runs before response matching.
- No network at runtime. No `print()` in library code outside `if __name__ == "__main__":`.
- Type hints + docstrings on all public classes/functions. No bare `except:`.
- Tests must pass offline with no mic: `python -m pytest -q`.
- When adding a config section, update **all four** places: `config.yaml`, `_DEFAULTS`, both known-key listings in `config.py`, and `tests/conftest.py`.
- Exit code for wake word errors: 7 (already defined in `errors.py` as `WakeWordError.exit_code = 7`).

## Current State (Exact)

`config.py` `AppConfig` dataclass:
```python
@dataclass(frozen=True)
class AppConfig:
    root: Path
    audio: AudioConfig
    vad: VADConfig
    stt: STTConfig
    tts: TTSConfig
    responses: ResponsesConfig
    runtime: RuntimeConfig
    logging: LoggingConfig
    memory: MemoryConfig
    llm: LLMConfig
    source: Path  # the config.yaml that produced this object
```

`errors.py` ends with:
```python
class LLMError(HidekoError):
    """LLM generation failed."""
    exit_code = 6
```

`main.py` `HidekoApp.__init__` stores:
```python
        self._closed = False
        self._paused = False
        self._listening_shown = False
        self.stt: STTEngine | None = None
        self.tts: TTSEngine | None = None
        self.speaker: Speaker | None = None
        self.mic: Microphone | None = None
        self.recorder: UtteranceRecorder | None = None
        self.responder: EchoResponder | ResponseHandler | None = None
        self.memory: MemoryStore | None = None
```

`main.py` `run()` loop begins with:
```python
            key = self.keys.poll()
            if key == "q":
                break
            if key == self.opts.mute_key and self.opts.mute_key.lower() != "none":
                self._paused = not self._paused
                ...
            if self._paused:
                self.mic.flush(self.config.audio.block_ms)
                continue

            block = self.mic.read_block()
            utterance = self.recorder.process_block(block)
            if utterance is None:
                continue
            if len(utterance) < 0.30 * self.config.audio.sample_rate:
                continue
```

`response_handler.py` exports:
```python
def normalize(text: str) -> str:
    """Normalize text for pattern matching."""
```

## Steps

### 1. `errors.py` — Add Wake Word Error

Append after `LLMError`:
```python
class WakeWordError(HidekoError):
    """Wake word detection or timeout error."""
    exit_code = 7
```

### 2. `config.py` — Add Wake Word Configuration

Add a new dataclass after `MemoryConfig`:
```python
@dataclass(frozen=True)
class WakeWordConfig:
    enabled: bool
    phrases: tuple[str, ...]
    threshold_db: float
    min_wake_duration_ms: int
    listen_mode_timeout_s: float
```

Add `wake_word: WakeWordConfig` to `AppConfig` immediately before `source`:
```python
@dataclass(frozen=True)
class AppConfig:
    root: Path
    audio: AudioConfig
    vad: VADConfig
    stt: STTConfig
    tts: TTSConfig
    responses: ResponsesConfig
    runtime: RuntimeConfig
    logging: LoggingConfig
    memory: MemoryConfig
    llm: LLMConfig
    wake_word: WakeWordConfig
    source: Path  # the config.yaml that produced this object
```

Add to `_DEFAULTS` after the `llm` section:
```python
    "wake_word": {
        "enabled": False,
        "phrases": ("hideko", "hey hideko"),
        "threshold_db": -35.0,
        "min_wake_duration_ms": 800,
        "listen_mode_timeout_s": 10.0,
    },
```

Add `"wake_word"` to `known_sections` in `_check_unknown_keys()`:
```python
    known_sections = {
        "audio", "vad", "stt", "tts", "responses", "runtime", "logging", "memory", "llm", "wake_word"
    }
```

Add to `section_keys` dict in `_check_unknown_keys()`:
```python
        "wake_word": {"enabled", "phrases", "threshold_db", "min_wake_duration_ms", "listen_mode_timeout_s"},
```

Add to `_get_known_keys()` function:
```python
    elif section_type == "wake_word":
        return {"enabled", "phrases", "threshold_db", "min_wake_duration_ms", "listen_mode_timeout_s"}
```

Add validation function after `_validate_llm`:
```python
def _validate_wake_word(config: dict[str, Any], path: str = "wake_word") -> None:
    """Validate the wake word section."""
    enabled = config.get("enabled", _DEFAULTS["wake_word"]["enabled"])
    if not isinstance(enabled, bool):
        raise ConfigError(f"{path}.enabled must be a boolean, got {type(enabled).__name__}")

    phrases = config.get("phrases", _DEFAULTS["wake_word"]["phrases"])
    if not isinstance(phrases, (list, tuple)):
        raise ConfigError(f"{path}.phrases must be a list or tuple, got {type(phrases).__name__}")
    if not phrases:
        raise ConfigError(f"{path}.phrases must not be empty")
    for i, p in enumerate(phrases):
        if not isinstance(p, str) or not p.strip():
            raise ConfigError(f"{path}.phrases[{i}] must be a non-empty string, got {p!r}")

    threshold_db = config.get("threshold_db", _DEFAULTS["wake_word"]["threshold_db"])
    if not isinstance(threshold_db, (int, float)) or isinstance(threshold_db, bool):
        raise ConfigError(f"{path}.threshold_db must be a number, got {type(threshold_db).__name__}")
    if not (-90.0 <= threshold_db <= 0.0):
        raise ConfigError(f"{path}.threshold_db must be between -90.0 and 0.0, got {threshold_db}")

    min_wake_duration_ms = config.get("min_wake_duration_ms", _DEFAULTS["wake_word"]["min_wake_duration_ms"])
    if not isinstance(min_wake_duration_ms, int) or isinstance(min_wake_duration_ms, bool):
        raise ConfigError(f"{path}.min_wake_duration_ms must be an int, got {type(min_wake_duration_ms).__name__}")
    if not (200 <= min_wake_duration_ms <= 5000):
        raise ConfigError(f"{path}.min_wake_duration_ms must be between 200 and 5000, got {min_wake_duration_ms}")

    listen_mode_timeout_s = config.get("listen_mode_timeout_s", _DEFAULTS["wake_word"]["listen_mode_timeout_s"])
    if not isinstance(listen_mode_timeout_s, (int, float)) or isinstance(listen_mode_timeout_s, bool):
        raise ConfigError(f"{path}.listen_mode_timeout_s must be a number, got {type(listen_mode_timeout_s).__name__}")
    if not (1.0 <= listen_mode_timeout_s <= 120.0):
        raise ConfigError(f"{path}.listen_mode_timeout_s must be between 1.0 and 120.0, got {listen_mode_timeout_s}")
```

Add a nested `build_wake_word()` function inside `load_config()`, right after `build_llm()`:
```python
    def build_wake_word() -> WakeWordConfig:
        wake_word_section = get_value(raw_config, "wake_word", {})
        if not isinstance(wake_word_section, dict):
            raise ConfigError(f"wake_word must be a mapping (dict), got {type(wake_word_section).__name__}")
        _validate_wake_word(wake_word_section)
        return WakeWordConfig(
            enabled=_validate_bool(
                get_value(wake_word_section, "enabled", _DEFAULTS["wake_word"]["enabled"]),
                "enabled", "wake_word",
            ),
            phrases=tuple(get_value(wake_word_section, "phrases", _DEFAULTS["wake_word"]["phrases"])),
            threshold_db=get_value(wake_word_section, "threshold_db", _DEFAULTS["wake_word"]["threshold_db"]),
            min_wake_duration_ms=get_value(wake_word_section, "min_wake_duration_ms", _DEFAULTS["wake_word"]["min_wake_duration_ms"]),
            listen_mode_timeout_s=get_value(wake_word_section, "listen_mode_timeout_s", _DEFAULTS["wake_word"]["listen_mode_timeout_s"]),
        )
```

In the final `load_config()` return statement, add `wake_word = build_wake_word()` and pass it to `AppConfig`:
```python
    audio = build_audio()
    vad = build_vad()
    stt = build_stt()
    tts = build_tts()
    responses = build_responses()
    runtime = build_runtime()
    logging_conf = build_logging()
    memory = build_memory()
    llm = build_llm()
    wake_word = build_wake_word()

    return AppConfig(
        root=PROJECT_ROOT,
        audio=audio,
        vad=vad,
        stt=stt,
        tts=tts,
        responses=responses,
        runtime=runtime,
        logging=logging_conf,
        memory=memory,
        llm=llm,
        wake_word=wake_word,
        source=config_path,
    )
```

### 3. `config.yaml` — Add Wake Word Section

Insert after the `llm:` section and before any other sections:
```yaml
wake_word:
  enabled: false              # enable wake word detection (disabled by default for backward compat)
  phrases:                    # phrases that wake up Hideko (case-insensitive matching)
    - hideko
    - hey hideko
  threshold_db: -35.0         # energy threshold for wake word detection
  min_wake_duration_ms: 800  # minimum duration of utterance to attempt wake word detection
  listen_mode_timeout_s: 10.0 # seconds of inactivity before returning to wake word mode
```

### 4. `main.py` — Add Wake Word State and Logic

Add import at the top (after existing imports):
```python
from response_handler import normalize
```

Add to `HidekoApp.__init__` after `_listening_shown`:
```python
        self._wake_word_detected = False
        self._wake_word_timeout = 0.0
```

Add a private method to `HidekoApp` class (place it near other private methods):
```python
    def _check_wake_word(self, transcript_text: str) -> bool:
        """Check if transcript contains a wake word phrase.
        
        Performs case-insensitive substring matching against configured wake word phrases.
        
        Args:
            transcript_text: The raw transcript text to check.
            
        Returns:
            True if any wake word phrase is found in the transcript, False otherwise.
        """
        if not self.config.wake_word.enabled:
            return False
        normalized = normalize(transcript_text)
        for phrase in self.config.wake_word.phrases:
            if phrase.lower() in normalized:
                logger.debug(f"Wake word detected: '{phrase}' in '{transcript_text}'")
                return True
        return False
```

Modify the `run()` method's main loop. Replace the existing block reading logic:

**OLD:**
```python
            block = self.mic.read_block()
            utterance = self.recorder.process_block(block)
            if utterance is None:
                continue
            if len(utterance) < 0.30 * self.config.audio.sample_rate:
                continue

            if not self._listening_shown:
                self.status.listening()
                self._listening_shown = True
```

**NEW:**
```python
            block = self.mic.read_block()
            
            # Check for listen mode timeout (only when wake word mode is enabled)
            if self.config.wake_word.enabled and self._wake_word_detected:
                import time as time_module
                if time_module.time() > self._wake_word_timeout:
                    self._wake_word_detected = False
                    logger.info("Listen mode timeout, returning to wake word detection")
                    self.status.listening()
                    self._listening_shown = True
            
            utterance = self.recorder.process_block(block)
            if utterance is None:
                continue
            if len(utterance) < 0.30 * self.config.audio.sample_rate:
                continue

            if not self._listening_shown:
                self.status.listening()
                self._listening_shown = True
            
            # Wake word detection mode
            if self.config.wake_word.enabled and not self._wake_word_detected:
                t0 = perf_counter()
                transcript = self.stt.transcribe(utterance, self.config.audio.sample_rate)
                t1 = perf_counter()
                
                if transcript.text:
                    if self._check_wake_word(transcript.text):
                        self._wake_word_detected = True
                        import time as time_module
                        self._wake_word_timeout = time_module.time() + self.config.wake_word.listen_mode_timeout_s
                        logger.info(f"Wake word detected: '{transcript.text}'")
                        print(f"  [wake word detected in {t1-t0:.1f}s]")
                        continue
                    # Not a wake word, loop back to listen for wake word
                    continue
```

### 5. `tests/conftest.py` — Add Wake Word to Config Fixture

Add to the `config` fixture's returned dictionary, after the `llm` section:
```python
        "wake_word": {
            "enabled": False,
            "phrases": ["hideko", "hey hideko"],
            "threshold_db": -35.0,
            "min_wake_duration_ms": 800,
            "listen_mode_timeout_s": 10.0,
        },
```

## Verification

Run all of these and paste the real output.

```powershell
python -m pytest -q
python config.py --check
python main.py --turns 1 --no-greet --no-tts --text "hello"
```

Expected with wake word **disabled** (default):

- `python -m pytest -q` — all tests pass.
- `python config.py --check` — prints JSON containing the `"wake_word"` object with all 5 keys and correct values.
- `python main.py --turns 1 --no-greet --no-tts --text "hello"` — behaves exactly as before, prints `Hideko: ...` response.

Expected with wake word **enabled** (using a temporary config):

```powershell
# Create a temp config that enables wake word
$temp_config_content = @'
wake_word:
  enabled: true
  phrases:
    - hideko
  threshold_db: -35.0
  min_wake_duration_ms: 800
  listen_mode_timeout_s: 5.0
'@
$temp_config_content | Out-File -Encoding utf8 temp_wake_config.yaml

# Test: wake word + command should work
python main.py --config temp_wake_config.yaml --turns 1 --no-greet --no-tts --text "hideko hello"
# Expected: Detects wake word, then processes "hello" -> prints wake word detected message + response

# Test: command without wake word should be ignored
python main.py --config temp_wake_config.yaml --turns 1 --no-greet --no-tts --text "hello"
# Expected: NO response (wake word not detected)

# Clean up
Remove-Item temp_wake_config.yaml -Force
```

## Stop and Ask the Human If

- The wake word detection fails to recognize legitimate wake phrases (e.g., "Hey Hideko" when configured), or
- The listen mode timeout causes the assistant to exit listen mode unexpectedly during a conversation, or
- Any existing test fails for a reason unrelated to the new config section, or
- You need to add additional wake word detection logic beyond simple substring matching.

## Notes

- Wake word mode is **disabled by default** (`enabled: false`) to maintain backward compatibility. Users must explicitly enable it in their config.
- When wake word mode is disabled, the behavior is identical to the current implementation.
- The `normalize()` function from `response_handler.py` is reused for consistent text normalization before wake word matching.
- Wake word detection runs STT on every utterance when in wake word mode, which has a CPU cost. This is acceptable because:
  1. The STT model is already loaded and warm
  2. Users can disable wake word mode if they prefer manual activation
  3. The tiny.en model is fast enough for this use case
- The `listen_mode_timeout_s` config allows users to control how long the assistant stays in listen mode after wake word detection before returning to wake word mode.
- The mute key (`m`) still works and takes precedence over wake word mode.
