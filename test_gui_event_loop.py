"""Test: GUI event loop runs in background, window stays responsive, UV meter gets data."""
import sys
import logging
import time
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

from PySide6.QtWidgets import QApplication

from gui import launch_gui
from events import EventBus

from config import AppConfig, AudioConfig, VADConfig, STTConfig, TTSConfig, \
    ResponsesConfig, RuntimeConfig, LoggingConfig, MemoryConfig, LLMConfig, WakeWordConfig
from pathlib import Path

config = AppConfig(
    root=Path("."),
    audio=AudioConfig(input_device=None, output_device=None, sample_rate=16000, channels=1, block_ms=32, playback_volume=1.0),
    vad=VADConfig(energy_threshold_db=-40.0, calibrate=False, calibration_ms=1000, silence_ms=450, min_speech_ms=200, max_utterance_s=15.0, pre_roll_ms=300, post_playback_flush_ms=150),
    stt=STTConfig(model_size="tiny.en", device="cpu", compute_type="int8", language="en", beam_size=1, cpu_threads=None, download_root=Path("models/whisper"), min_avg_logprob=-1.0, max_audio_s=30.0),
    tts=TTSConfig(backend="exe", piper_exe=Path("models/piper/piper/piper.exe"), voice_model=Path("models/piper/en_US-amy-medium.onnx"), length_scale=1.0, max_chars=300, timeout_s=30.0),
    responses=ResponsesConfig(triggers_file=Path("responses/triggers.yaml"), fallbacks_file=Path("responses/fallbacks.yaml")),
    runtime=RuntimeConfig(half_duplex=True, max_turns=0, log_transcripts=True, greet_on_start=False, echo_mode=True),
    logging=LoggingConfig(level="INFO", file=Path("logs/hideko.log"), max_bytes=1048576, backup_count=3),
    memory=MemoryConfig(enabled=True, file=Path("memory/facts.json"), max_facts=100, max_value_chars=120),
    llm=LLMConfig(enabled=False, base_url="http://127.0.0.1:5001", endpoint="/v1/chat/completions", model="local", temperature=0.7, max_tokens=80, timeout_s=15.0, system_prompt="test", persona_file=Path("persona/hideko.yaml")),
    wake_word=WakeWordConfig(enabled=False, phrases=("hideko",), threshold_db=-35.0, min_wake_duration_ms=800, listen_mode_timeout_s=10.0),
    source=Path("config.yaml"),
)

bus = EventBus()

# Launch GUI
gui_app = launch_gui(config, bus)
print("GUI app created:", gui_app is not None)

# Simulate app.setup() - publish startup then ready
bus.publish("startup")
bus.publish("ready", stt_s=1.5, trigger_count=3)

# Give the event loop thread a moment to start
time.sleep(0.5)

print("\n--- GUI state ---")
print("GUI visible:", gui_app.is_visible)
print("Event loop thread alive:", gui_app._event_loop_thread is not None and gui_app._event_loop_thread.is_alive())

mw = gui_app._main_window
if mw:
    print("MainWindow visible:", mw.isVisible())
    print("Audio viz:", mw._audio_viz is not None)
    
    # Simulate feeding audio to the visualizer (like main.py does)
    print("\n--- Feeding audio to visualizer ---")
    for i in range(5):
        # Simulate audio block: 32ms of 16kHz mono = 512 samples
        block = np.random.randn(512).astype(np.float32) * 0.1
        gui_app.update_audio_visualization(block)
        time.sleep(0.05)
    
    # Check VU meter level changed
    if mw._audio_viz:
        print("VU meter left level:", mw._audio_viz._left_meter._level)
        print("VU meter right level:", mw._audio_viz._right_meter._level)
        print("VU meter levels > 0:", mw._audio_viz._left_meter._level > 0 or mw._audio_viz._right_meter._level > 0)

# Simulate some events
print("\n--- Publishing events ---")
bus.publish("heard", text="hello hideko")
bus.publish("speaking", text="Hello! I am Hideko.")
bus.publish("turn_timing", stt=0.5, resp=0.3, tts=0.8, play=0.4, total=2.0)
time.sleep(0.3)

print("Conversation:", repr(mw._conversation_display.toPlainText()[:200]))
print("Status:", mw._status_bar._status_label.text())
print("Timing:", mw._status_bar._timing_label.text())

# Shutdown
print("\n--- Shutting down ---")
gui_app.close()
print("Event loop thread alive after close:", gui_app._event_loop_thread is not None and gui_app._event_loop_thread.is_alive())
print("Test complete")
