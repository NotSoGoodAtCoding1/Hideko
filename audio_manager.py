from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from math import ceil
from typing import Any

import numpy as np
import sounddevice as sd

from errors import AudioError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float
    is_default_input: bool
    is_default_output: bool


def _get_devices() -> list[dict[str, Any]]:
    """Query audio devices. Raises AudioError on PortAudio failure."""
    try:
        return sd.query_devices()
    except sd.PortAudioError as e:
        raise AudioError(
            f"No audio devices found. Is a microphone/speaker connected and enabled in Windows sound settings?\n"
            f"PortAudio error: {e}"
        ) from e


def list_devices() -> list[AudioDevice]:
    """Return a list of AudioDevice objects."""
    devices = _get_devices()
    
    # Get default device
    try:
        default_in, default_out = sd.default.device
    except AttributeError:
        # No default set, use first device
        default_in = -1
        default_out = -1
    
    result = []
    for i, dev in enumerate(devices):
        name = dev.get("name", f"Device {i}")
        max_input = dev.get("max_input_channels", 0)
        max_output = dev.get("max_output_channels", 0)
        samplerate = dev.get("default_samplerate", 44100.0)
        
        is_default_in = (default_in == -1 and i == 0) or (default_in >= 0 and default_in == i)
        is_default_out = (default_out == -1 and i == 0) or (default_out >= 0 and default_out == i)
        
        result.append(AudioDevice(
            index=i,
            name=name,
            max_input_channels=max_input,
            max_output_channels=max_output,
            default_samplerate=samplerate,
            is_default_input=is_default_in,
            is_default_output=is_default_out,
        ))
    
    return result


def _resolve_device_index(spec: int | str | None, devices: list[AudioDevice], direction: str) -> int:
    """Resolve a device spec to an index. Raises AudioError on failure."""
    if spec is None:
        # Get system default
        try:
            default_in, default_out = sd.default.device
        except AttributeError:
            # No default set, use first device
            return devices[0].index
        
        if direction == "input":
            if default_in >= 0:
                for dev in devices:
                    if dev.index == default_in:
                        return dev.index
            raise AudioError(
                f"No default input device found. Please set audio.input_device explicitly in config.yaml."
            )
        else:  # output
            if default_out >= 0:
                for dev in devices:
                    if dev.index == default_out:
                        return dev.index
            raise AudioError(
                f"No default output device found. Please set audio.output_device explicitly in config.yaml."
            )
    
    if isinstance(spec, int):
        # Validate integer index
        if spec < 0 or spec >= len(devices):
            valid = [d.index for d in devices]
            raise AudioError(
                f"Invalid device index {spec}. Valid input device indices: {valid}"
            )
        
        dev = devices[spec]
        if direction == "input" and dev.max_input_channels < 1:
            valid = [d.index for d in devices if d.max_input_channels >= 1]
            raise AudioError(
                f"Device {spec} ({dev.name}) has no input channels. Valid input device indices: {valid}"
            )
        elif direction == "output" and dev.max_output_channels < 1:
            valid = [d.index for d in devices if d.max_output_channels >= 1]
            raise AudioError(
                f"Device {spec} ({dev.name}) has no output channels. Valid output device indices: {valid}"
            )
        
        return spec
    
    if isinstance(spec, str):
        # Case-insensitive substring match
        matches = [d for d in devices if spec.lower() in d.name.lower()]
        
        if len(matches) == 0:
            available_in = [d.index for d in devices if d.max_input_channels >= 1]
            raise AudioError(
                f"No input device matches '{spec}'. Available input device indices: {available_in}"
            )
        
        if len(matches) > 1:
            match_names = ", ".join(f"{m.index}: {m.name}" for m in matches)
            raise AudioError(
                f"Multiple input devices match '{spec}': {match_names}. Please use a more specific string or an integer index."
            )
        
        return matches[0].index
    
    raise AudioError(f"Invalid device spec type: {type(spec).__name__}")


def find_input_device(spec: int | str | None) -> int:
    """Find input device by spec. Returns device index."""
    devices = list_devices()
    return _resolve_device_index(spec, devices, "input")


def find_output_device(spec: int | str | None) -> int:
    """Find output device by spec. Returns device index."""
    devices = list_devices()
    return _resolve_device_index(spec, devices, "output")


class Microphone:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._stream: sd.InputStream | None = None
        self._device_index: int | None = None
    
    def __enter__(self) -> Microphone:
        device_index = find_input_device(self.config.audio.input_device)
        self._device_index = device_index
        
        self._stream = sd.InputStream(
            samplerate=self.config.audio.sample_rate,
            channels=self.config.audio.channels,
            dtype="float32",
            blocksize=self.config.audio.blocksize,
            device=device_index,
        )
        self._stream.start()
        return self
    
    def __exit__(self, *exc: object) -> None:
        self.close()
    
    def read_block(self) -> np.ndarray:
        """Read one block of audio. Returns float32 mono array."""
        if self._stream is None:
            raise AudioError("Microphone stream not open")
        
        try:
            data, _ = self._stream.read(self.config.audio.blocksize)
            
            # Downmix stereo to mono if needed
            if data.ndim == 2 and data.shape[1] > 1:
                data = data.mean(axis=1)
            
            return np.asarray(data, dtype=np.float32).reshape(-1)
        except sd.PortAudioError as e:
            raise AudioError(f"PortAudio error during read: {e}") from e
    
    def flush(self, ms: int) -> None:
        """Read and discard `ms` milliseconds of audio."""
        if self._stream is None:
            return
        
        num_blocks = ceil(ms / self.config.audio.block_ms)
        for _ in range(num_blocks):
            try:
                self._stream.read(self.config.audio.blocksize)
            except sd.PortAudioError:
                # Stream may be closed
                break
    
    def close(self) -> None:
        """Close the microphone stream. Idempotent."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except (sd.PortAudioError, OSError):
                pass
            finally:
                self._stream = None


class Speaker:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._device_index: int | None = None
        self._playing = False
    
    def __enter__(self) -> Speaker:
        device_index = find_output_device(self.config.audio.output_device)
        self._device_index = device_index
        return self
    
    def __exit__(self, *exc: object) -> None:
        self.stop()
    
    def play(self, samples: np.ndarray, sample_rate: int) -> None:
        """Play audio samples. Blocking."""
        if len(samples) == 0:
            return
        
        # Convert to float32 1-D
        data = np.asarray(samples, dtype=np.float32).reshape(-1)
        
        # Apply volume and clip
        data = data * self.config.audio.playback_volume
        data = np.clip(data, -1.0, 1.0)
        
        if self._device_index is None:
            self._device_index = find_output_device(self.config.audio.output_device)
        
        self._playing = True
        try:
            sd.play(data, samplerate=sample_rate, device=self._device_index, blocking=False)
            sd.wait()
        except sd.PortAudioError as e:
            raise AudioError(f"PortAudio error during playback: {e}") from e
        finally:
            self._playing = False
    
    def stop(self) -> None:
        """Stop playback."""
        if self._playing:
            try:
                sd.stop()
            except (sd.PortAudioError, OSError):
                pass
            finally:
                self._playing = False
    
    @property
    def is_playing(self) -> bool:
        return self._playing
    
    def close(self) -> None:
        """Close the speaker. Idempotent."""
        if self._device_index is not None:
            try:
                sd.stop()
            except (sd.PortAudioError, OSError):
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Audio manager CLI")
    parser.add_argument("--list", action="store_true", help="List audio devices")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Record and play back audio"
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=3.0,
        help="Recording duration for --test (default: 3)"
    )
    args = parser.parse_args()
    
    if args.list:
        devices = list_devices()
        print(f"{'idx':<6} {'in':<4} {'out':<4} {'rate':<8} {'default':<10} {'name'}")
        print("-" * 55)
        for dev in devices:
            default_marker = "Y" if dev.is_default_input or dev.is_default_output else ""
            print(
                f"{dev.index:<6} "
                f"{('yes' if dev.max_input_channels > 0 else 'no'):<4} "
                f"{('yes' if dev.max_output_channels > 0 else 'no'):<4} "
                f"{dev.default_samplerate:<8.0f} "
                f"{default_marker:<10} "
                f"{dev.name}"
            )
        sys.exit(0)
    
    if args.test:
        try:
            from config import load_config, AppConfig
            
            config = load_config()
            
            # Record audio
            print(f"Recording for {args.seconds} seconds...")
            with Microphone(config) as mic:
                sample_rate = config.audio.sample_rate
                blocksize = config.audio.blocksize
                
                # Calculate number of blocks needed
                total_samples = int(args.seconds * sample_rate)
                num_blocks = (total_samples + blocksize - 1) // blocksize
                
                all_samples = []
                for _ in range(num_blocks):
                    block = mic.read_block()
                    all_samples.append(block)
                
                recorded = np.concatenate(all_samples)
                duration = len(recorded) / sample_rate
                
                peak = float(np.max(np.abs(recorded)))
                rms = float(np.sqrt(np.mean(recorded ** 2)))
                
                print(f"recorded {duration:.1f} s, peak {peak:.2f}, rms {rms:.3f}")
                
                if peak < 0.001:
                    print("Captured silence — check the Windows input device and microphone level.")
                
                # Play back
                print("Playing back...")
                with Speaker(config) as speaker:
                    speaker.play(recorded, sample_rate)
            
            sys.exit(0)
            
        except AudioError as e:
            print(f"Audio Error: {e}", file=sys.stderr)
            sys.exit(2)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
