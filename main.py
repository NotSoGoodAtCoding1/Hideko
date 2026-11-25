from __future__ import annotations

import dataclasses
import gc
import logging
import sys
import threading
from pathlib import Path
from time import perf_counter

import numpy as np

from audio_manager import AudioError, Microphone, Speaker, list_devices
from cli import CliOptions, KeyListener, Status, parse_args
from config import AppConfig, ConfigError, load_config
from errors import HidekoError
from event_outputs import ConsoleSubscriber
from events import ALL, EventBus
from tools.registry import ToolRegistry
from tools.scheduler import Scheduler
from turn_state import TurnController, TurnState
from logging_setup import memory_rss_mb, setup_logging
from memory_store import MemoryStore
from response_handler import EchoResponder, ResponseHandler, Response, normalize
from stt_engine import STTEngine, STTError
from tts_engine import TTSEngine, TTSError
from vad import UtteranceRecorder

logger = logging.getLogger(__name__)


def _load_gui_launcher():
    """Return the GUI launcher if PySide6 is available, otherwise None.

    Qt is imported lazily, and only after ctranslate2. Importing PySide6 before
    ctranslate2 loads Qt's DLLs first, which makes Whisper model construction
    crash with a native access violation on Windows.
    """
    try:
        import ctranslate2  # noqa: F401  (DLL load-order guard for PySide6)
        from gui import launch_gui
    except ImportError as exc:
        logger.debug("GUI not available: %s", exc)
        return None
    return launch_gui


class HidekoApp:
    def __init__(
        self,
        config: AppConfig,
        opts: CliOptions,
        bus: EventBus | None = None,
        status: Status | None = None,
        turn: TurnController | None = None,
        registry: ToolRegistry | None = None,
        scheduler: Scheduler | None = None,
        gui_app: object | None = None,  # GUI app instance for Qt event processing
    ) -> None:
        self.config = config
        self.opts = opts
        self.keys = KeyListener()
        self.bus = bus if bus is not None else EventBus()
        self.status = status if status is not None else Status()
        self.turn = turn if turn is not None else TurnController(self.bus)
        self.registry = registry if registry is not None else ToolRegistry()
        self.scheduler = scheduler if scheduler is not None else Scheduler(self.bus)
        self._closed = False
        self._paused = False
        self._listening_shown = False
        self._wake_word_detected = False
        self._wake_word_timeout = 0.0
        self._pending_speech: list[str] = []
        self._speech_lock = threading.Lock()
        self.stt: STTEngine | None = None
        self.tts: TTSEngine | None = None
        self.speaker: Speaker | None = None
        self.mic: Microphone | None = None
        self.recorder: UtteranceRecorder | None = None
        self.responder: EchoResponder | None = None
        self.memory: MemoryStore | None = None
        self._gui_app = gui_app  # Store GUI app reference for Qt event processing

    def setup(self) -> None:
        # 1. logging setup at the very start
        self._consecutive_errors = 0
        self._start_rss = memory_rss_mb()
        setup_logging(self.config.logging, debug=self.opts.debug, log_file=self.opts.log_file)

        # 2. print/l logging "Hideko MVP — Ctrl+C to stop"
        logger.info("Hideko MVP — Ctrl+C to stop")
        self.bus.publish("startup")

        # 3. self.stt = STTEngine(config); log "STT ready in X.Xs" from warmup()
        self.stt = STTEngine(self.config)
        secs = self.stt.warmup()
        logger.info("STT ready in %.1fs", secs)

        # 4. self.tts = TTSEngine(config); if not available -> raise a fatal error mentioning download_models.py
        if not self.opts.no_tts:
            self.tts = TTSEngine(self.config)
            if not self.tts.is_available():
                raise TTSError("Piper binary or voice model not found. Run: python scripts/download_models.py --all")

        # 5. self.speaker = Speaker(config); self.mic = Microphone(config)
        self.speaker = Speaker(self.config)
        self.mic = Microphone(self.config)
        self.mic.__enter__()  # Opens the stream via __enter__

        # 6. self.recorder = UtteranceRecorder(config)
        self.recorder = UtteranceRecorder(self.config)

        # 7. if config.vad.calibrate: print "Stay quiet for 1 second — calibrating..." BEFORE calling recorder.calibrate(self.mic)
        if self.config.vad.calibrate:
            self.bus.publish("calibrating")
            self.recorder.calibrate(self.mic)

        # 8. Initialize memory store if enabled
        if self.config.memory.enabled:
            self.memory = MemoryStore(self.config)
            logger.info("memory: %d fact(s) loaded", len(self.memory.all()))

        # 9. Choose responder based on echo_mode
        if self.config.runtime.echo_mode:
            self.responder = EchoResponder(self.config)
            logger.info("responder: EchoResponder (echo_mode)")
        else:
            self.responder = ResponseHandler(self.config, memory=self.memory)
            logger.info("responder: ResponseHandler (%d triggers)", self.responder.trigger_count)
        
        # 10. Subscribe to mute_toggle events from GUI
        self.bus.subscribe("mute_toggle", self._on_mute_toggle)

        self.bus.publish(
            "ready",
            stt_s=secs,
            trigger_count=getattr(self.responder, "trigger_count", 0),
        )

        # Initialize turn state to IDLE
        self.turn.transition(TurnState.IDLE)
        
        # Start the background scheduler (idempotent; main() already started it)
        self.scheduler.start()

        # 9. if config.runtime.greet_on_start: synthesize+play greeting once
        if self.config.runtime.greet_on_start and not self.opts.no_greet and self.tts is not None:
            clip = self.tts.synthesize("Hello. I am Hideko. I am listening.")
            self.speaker.play(clip.samples, clip.sample_rate)

    def _process_qt_events(self) -> None:
        """Process Qt events if GUI is available.
        
        Called around blocking operations (mic reads, STT, TTS, playback)
        to keep the window responsive and prevent Windows from flagging
        it as "Not responding" during idle periods.
        """
        if self._gui_app is not None and hasattr(self._gui_app, 'process_events'):
            try:
                self._gui_app.process_events()
            except Exception:
                # Ignore Qt event processing errors to avoid breaking audio loop
                pass
    
    def _on_mute_toggle(self, event: object) -> None:
        """Handle mute toggle event from GUI.
        
        Args:
            event: The event object containing muted state.
        """
        muted = event.data.get("muted", True)
        self._paused = muted
        self._listening_shown = False
        if self._paused:
            self.bus.publish("paused")
            self.turn.transition(TurnState.PAUSED)
        else:
            self.bus.publish("listening")
            self._listening_shown = True
            self.turn.transition(TurnState.LISTENING)

    def run(self) -> int:
        try:
            turn = 0
            while True:
                if self.config.runtime.max_turns and turn >= self.config.runtime.max_turns:
                    break

                # Process Qt events if GUI is available (keeps window responsive,
                # prevents Windows "Not responding" during idle/blocking calls)
                self._process_qt_events()

                # Key handling at top of loop
                key = self.keys.poll()
                if key == "q":
                    break
                if key == self.opts.mute_key and self.opts.mute_key.lower() != "none":
                    self._paused = not self._paused
                    self._listening_shown = False
                    if self._paused:
                        self.bus.publish("paused")
                        self.turn.transition(TurnState.PAUSED)
                    else:
                        self.bus.publish("listening")
                        self._listening_shown = True
                        self.turn.transition(TurnState.LISTENING)
                if self._paused:
                    self.mic.flush(self.config.audio.block_ms)
                    continue

                # Process Qt events before blocking mic read
                self._process_qt_events()

                # Speak any pending tool results (e.g. timer finished) before listening.
                # NOTE: mic.read_block() blocks, so pending speech is delivered on
                # the next audio block. Timer speech may be delayed until the user
                # speaks again — acceptable for v1.
                with self._speech_lock:
                    pending = list(self._pending_speech)
                    self._pending_speech.clear()
                if pending and not self.turn.is_speaking():
                    self.turn.transition(TurnState.SPEAKING)
                    for text in pending:
                        self.bus.publish("speaking", text=text)
                        self._process_qt_events()
                        clip = self.tts.synthesize(text)
                        self._process_qt_events()
                        self.speaker.play(clip.samples, clip.sample_rate)
                        self._process_qt_events()
                    self.turn.transition(TurnState.IDLE)

                block = self.mic.read_block()
                
                # Process Qt events after blocking mic read
                self._process_qt_events()
                
                # Feed audio to GUI visualization
                if self._gui_app is not None:
                    try:
                        self._gui_app.update_audio_visualization(block)
                    except Exception:
                        # Don't let visualization errors break the audio loop
                        pass
                
                # Check for listen mode timeout (only when wake word mode is enabled)
                if self.config.wake_word.enabled and self._wake_word_detected:
                    if perf_counter() > self._wake_word_timeout:
                        self._wake_word_detected = False
                        logger.info("Listen mode timeout, returning to wake word detection")
                        self.bus.publish("listening")
                        self.turn.transition(TurnState.LISTENING)
                        self._listening_shown = True
                
                utterance = self.recorder.process_block(block)
                if utterance is None:
                    continue
                if len(utterance) < 0.30 * self.config.audio.sample_rate:
                    continue

                # First-time listening indicator (moved to TurnController)
                if not self._listening_shown:
                    self.bus.publish("listening")
                    self._listening_shown = True
                    self.turn.transition(TurnState.LISTENING)
                
                # Wake word detection mode
                if self.config.wake_word.enabled and not self._wake_word_detected:
                    self._process_qt_events()
                    t0 = perf_counter()
                    transcript = self.stt.transcribe(utterance, self.config.audio.sample_rate)
                    t1 = perf_counter()
                    self._process_qt_events()
                    
                    if transcript.text:
                        if self._check_wake_word(transcript.text):
                            self._wake_word_detected = True
                            self._wake_word_timeout = perf_counter() + self.config.wake_word.listen_mode_timeout_s
                            logger.info(f"Wake word detected: '{transcript.text}'")
                            self.bus.publish("wake_detected", text=transcript.text, latency_s=t1 - t0)
                            self.turn.transition(TurnState.LISTENING)  # Exit wake mode, go to listening
                            continue
                    # Not a wake word, loop back waiting for wake word
                    self.turn.transition(TurnState.WAITING_FOR_WAKE_WORD)
                    continue
                
                # Normal command processing (when not in wake word mode or after timeout)
                t0 = perf_counter()
                self.bus.publish("thinking")
                self.turn.transition(TurnState.THINKING)
                self._process_qt_events()
                transcript = self.stt.transcribe(utterance, self.config.audio.sample_rate)
                t1 = perf_counter()
                self._process_qt_events()
                if not transcript.text:
                    self.bus.publish("missed")
                    self.recorder.reset()
                    continue

                self.bus.publish("heard", text=transcript.text)
                if self.memory is not None and self.memory.observe(transcript.text):
                    self.memory.save()
                response = self.responder.respond(transcript.text)
                t2 = perf_counter()

                if self.opts.no_tts:
                    self.bus.publish("speaking", text=response.text)
                    t3 = t2
                    t4 = t2
                    self.turn.transition(TurnState.SPEAKING)
                else:
                    self.bus.publish("speaking", text=response.text)
                    self._process_qt_events()
                    clip = self.tts.synthesize(response.text)
                    t3 = perf_counter()
                    self._process_qt_events()
                    self.speaker.play(clip.samples, clip.sample_rate)
                    t4 = perf_counter()
                    self._process_qt_events()
                    self.turn.transition(TurnState.SPEAKING)

                self.bus.publish(
                    "turn_timing", 
                    stt=t1-t0, 
                    resp=t2-t1, 
                    tts=t3-t2, 
                    play=t4-t3, 
                    total=t4-t0
                )
                logger.info(
                    "timing stt=%.2f resp=%.3f tts=%.2f play=%.2f total=%.2f",
                    t1 - t0, t2 - t1, t3 - t2, t4 - t3, t4 - t0,
                )

                if response.should_exit:
                    self.bus.publish("goodbye")
                    self.turn.transition(TurnState.IDLE)
                    break

                # Execute tool action if the matched trigger requested one
                if response.tool_action:
                    result = self.registry.execute(
                        response.tool_action,
                        text=transcript.text,
                        response_text=response.text,
                    )
                    if result.ok and result.text:
                        with self._speech_lock:
                            self._pending_speech.append(result.text)
                    elif not result.ok:
                        logger.warning(
                            "tool %s failed: %s", response.tool_action, result.error
                        )

                turn += 1

                # Reset consecutive error counter after successful turn
                self._consecutive_errors = 0

                if self.config.runtime.half_duplex:
                    self.recorder.reset()
                    self.mic.flush(self.config.vad.post_playback_flush_ms)
                    self.turn.transition(TurnState.IDLE)

                # Process Qt events if GUI is available.
                self._process_qt_events()

                # Log memory every 20 turns
                if turn % 20 == 0:
                    rss = memory_rss_mb() or -1
                    logger.info("memory: %.0f MB RSS, %d objects", rss, len(gc.get_objects()))
                    gc.collect()
                    if self._start_rss is not None and rss != -1 and rss - self._start_rss > 300:
                        logger.warning("RSS grew >300 MB since start (%.0f -> %.0f MB)", self._start_rss, rss)

            return 0
        except HidekoError as exc:
            self.bus.publish("error", message=str(exc), exit_code=getattr(exc, "exit_code", 1))
            logger.exception("turn failed: %s", exc)
            self._consecutive_errors += 1
            self.turn.transition(TurnState.IDLE)
            sys.exit(getattr(exc, "exit_code", 1))

    def shutdown(self) -> None:
        # Idempotent via self._closed. Close speaker then mic.
        if self._closed:
            return
        self._closed = True
        self.bus.publish("shutdown")
        if self.speaker is not None:
            try:
                self.speaker.close()
            except Exception:
                pass
        if self.mic is not None:
            try:
                self.mic.close()
            except Exception:
                pass

        # Stop the background scheduler
        if self.scheduler is not None:
            self.scheduler.stop()

    def _queue_speech(self, text: str) -> None:
        """Thread-safe: queue text to be spoken at the start of the next loop."""
        with self._speech_lock:
            self._pending_speech.append(text)

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


def main(argv: list[str] | None = None) -> int:
    # Windows consoles often use cp1251/cp866; never crash on an unexpected
    # character in a transcript or generated reply.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")

    opts = parse_args(argv)

    # Set up event bus and console subscriber for all output
    bus = EventBus()
    console = ConsoleSubscriber(Status())
    bus.subscribe(ALL, console.handle)

    # Tool registry and background scheduler
    registry = ToolRegistry()
    scheduler = Scheduler(bus)
    scheduler.start()

    # Early-exit flags before config loading where possible
    if opts.list_devices:
        for d in list_devices():
            print(f"{d.index:3}  {d.name}  in={d.max_input_channels} out={d.max_output_channels} sr={d.default_samplerate}")
        return 0

    try:
        config = load_config(opts.config)
        if opts.turns is not None:
            config = dataclasses.replace(
                config,
                runtime=dataclasses.replace(config.runtime, max_turns=opts.turns),
            )
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code

    # --calibrate: open mic, calibrate, close mic, exit
    if opts.calibrate:
        cfg = load_config(opts.config)
        mic = Microphone(cfg)
        try:
            mic.__enter__()  # Open the stream
            threshold = UtteranceRecorder(cfg).calibrate(mic)
            print(f"VAD threshold: {threshold:.1f} dBFS")
        finally:
            mic.close()
        return 0

    # --facts: print remembered facts and exit
    if opts.facts:
        if not config.memory.enabled:
            print("(memory disabled)")
            return 0
        facts = MemoryStore(config).all()
        if facts:
            for key, value in sorted(facts.items()):
                print(f"{key}: {value}")
        else:
            print("(no facts)")
        return 0

    # --forget: delete all remembered facts and exit
    if opts.forget:
        if not config.memory.enabled:
            print("(memory disabled)")
            return 0
        MemoryStore(config).clear()
        print("memory cleared")
        return 0

    # --text branch: no mic, no VAD, no STT, no logging file required.
    if opts.text is not None:
        try:
            memory = MemoryStore(config) if config.memory.enabled else None
            if config.runtime.echo_mode:
                responder = EchoResponder(config)
            else:
                responder = ResponseHandler(config, memory=memory)
            
            # Wake word detection for text input (if enabled)
            if config.wake_word.enabled:
                normalized_text = normalize(opts.text)
                wake_word_found = False
                for phrase in config.wake_word.phrases:
                    if phrase.lower() in normalized_text:
                        print(f"  [wake word detected]")
                        wake_word_found = True
                        break
                
                if not wake_word_found:
                    # Wake word not found, ignore input
                    return 0
            
            if memory is not None and memory.observe(opts.text):
                memory.save()
            response = responder.respond(opts.text)
            
            # Handle tool action for text input (if any)
            if response.tool_action:
                result = registry.execute(
                    response.tool_action,
                    text=opts.text,
                    response_text=response.text,
                )
                if result.ok and result.text:
                    bus.publish("speaking", text=result.text)
                    if not opts.no_tts:
                        clip = TTSEngine(config).synthesize(result.text)
                        Speaker(config).play(clip.samples, clip.sample_rate)
            else:
                bus.publish("speaking", text=response.text)
                if not opts.no_tts:
                    clip = TTSEngine(config).synthesize(response.text)
                    Speaker(config).play(clip.samples, clip.sample_rate)
        except HidekoError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return exc.exit_code
        return 0

    # Launch GUI if requested
    gui_app = None
    if opts.gui:
        launch_gui = _load_gui_launcher()
        if launch_gui is None:
            logger.warning("GUI requested but PySide6 not available, continuing with CLI")
        else:
            try:
                gui_app = launch_gui(config, bus)
                if gui_app is None:
                    logger.warning("GUI failed to launch, continuing with CLI")
            except Exception as e:
                logger.error("GUI launch error: %s", e)
                logger.info("Continuing with CLI only")

    # Create app first, then register timer tool after scheduler starts
    app = HidekoApp(config, opts, bus=bus, registry=registry, scheduler=scheduler, gui_app=gui_app)
    
    # Register the timer tool after app is created (needs access to _queue_speech)
    from tools.timer_tool import TimerTool
    timer_tool = TimerTool(scheduler, bus, app._queue_speech)
    registry.register(timer_tool)
    
    try:
        app.setup()
        return app.run()
    except HidekoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print()
        return 0
    finally:
        # Clean up GUI if it exists
        if gui_app is not None:
            try:
                gui_app.close()
            except Exception:
                pass
        app.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
