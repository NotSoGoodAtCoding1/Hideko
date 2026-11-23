"""Exception hierarchy for expected, user-actionable Hideko failures."""

class HidekoError(Exception):
    """Base class for all expected, user-actionable Hideko failures."""
    exit_code: int = 1

class ConfigError(HidekoError):
    """Bad configuration."""
    exit_code = 1

class AudioError(HidekoError):
    """No microphone/speaker, device busy, or PortAudio failure."""
    exit_code = 2

class ModelError(HidekoError):
    """A model binary or data file is missing."""
    exit_code = 3

class STTError(ModelError):
    """Speech-to-text failure."""

class TTSError(ModelError):
    """Text-to-speech failure."""

class ResponseDataError(HidekoError):
    """Broken responses/*.yaml."""
    exit_code = 4


class MemoryError(HidekoError):
    """Memory file could not be read/written."""
    exit_code = 5


class LLMError(HidekoError):
    """LLM-related failures (model loading, inference, etc.)."""
    exit_code = 6


class WakeWordError(HidekoError):
    """Wake word detection or timeout error."""
    exit_code = 7
