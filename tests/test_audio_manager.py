"""Offline unit tests for audio_manager.py: no real audio devices are touched."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pytest
import sounddevice as sd

import audio_manager
from audio_manager import (
    AudioDevice,
    AudioError,
    Speaker,
    find_input_device,
    find_output_device,
    list_devices,
)
from config import AppConfig


def test_list_devices_maps_default_flags(
    fake_devices: list[dict[str, Any]],
) -> None:
    """Dicts become AudioDevice objects with default input=1, output=0."""
    devices = list_devices()

    assert len(devices) == 3
    assert all(isinstance(dev, AudioDevice) for dev in devices)
    assert [dev.index for dev in devices] == [0, 1, 2]
    assert [dev.name for dev in devices] == [
        "Speakers (Realtek)",
        "Microphone (USB)",
        "Headset Mic",
    ]
    assert [dev.max_input_channels for dev in devices] == [0, 2, 1]
    assert [dev.max_output_channels for dev in devices] == [2, 0, 1]
    assert [dev.default_samplerate for dev in devices] == [48000.0, 44100.0, 16000.0]
    assert [dev.is_default_input for dev in devices] == [False, True, False]
    assert [dev.is_default_output for dev in devices] == [True, False, False]


def test_find_input_device_none_uses_default(
    fake_devices: list[dict[str, Any]],
) -> None:
    """A None spec resolves to the configured default input device (index 1)."""
    assert find_input_device(None) == 1


def test_find_input_device_by_index(
    fake_devices: list[dict[str, Any]],
) -> None:
    """An integer spec is returned when it has input channels."""
    assert find_input_device(1) == 1


def test_find_input_device_by_name_is_case_insensitive(
    fake_devices: list[dict[str, Any]],
) -> None:
    """A string spec matches a device name substring regardless of case."""
    assert find_input_device("usb") == 1


def test_find_input_device_no_match_lists_available(
    fake_devices: list[dict[str, Any]],
) -> None:
    """An unmatched name raises AudioError listing the available inputs."""
    with pytest.raises(AudioError) as exc_info:
        find_input_device("nope")

    message = str(exc_info.value)
    assert "nope" in message
    assert "Available input device indices" in message
    assert "1" in message and "2" in message


def test_find_input_device_ambiguous_name_raises(
    fake_devices: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two matching names are rejected as ambiguous."""
    devices = list(fake_devices) + [
        {
            "name": "USB Headset",
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 16000.0,
        }
    ]
    monkeypatch.setattr(sd, "query_devices", lambda *a, **k: devices)

    with pytest.raises(AudioError) as exc_info:
        find_input_device("headset")

    message = str(exc_info.value)
    assert "headset" in message.lower()
    assert "multiple" in message.lower() or "ambiguous" in message.lower()


def test_find_output_device_rejects_input_only_device(
    fake_devices: list[dict[str, Any]],
) -> None:
    """Device 1 has no output channels, so it is not a valid output device."""
    with pytest.raises(AudioError) as exc_info:
        find_output_device(1)

    assert "output" in str(exc_info.value).lower()


def test_speaker_applies_volume_and_clips(
    config: AppConfig,
    fake_devices: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Speaker.play scales by playback_volume and clips to [-1.0, 1.0]."""
    played: list[np.ndarray] = []

    def capture(data: np.ndarray, **kwargs: Any) -> None:
        played.append(np.asarray(data).copy())

    def no_wait(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(audio_manager.sd, "play", capture)
    monkeypatch.setattr(audio_manager.sd, "wait", no_wait)
    quiet_config = replace(
        config, audio=replace(config.audio, playback_volume=0.5)
    )
    speaker = Speaker(quiet_config)

    speaker.play(np.array([1.0, -1.0, 0.5], dtype=np.float32), 16000)
    np.testing.assert_allclose(played[0], [0.5, -0.5, 0.25], atol=1e-6)

    played.clear()
    speaker.play(np.array([2.0], dtype=np.float32), 16000)
    np.testing.assert_allclose(played[0], [1.0], atol=1e-6)
