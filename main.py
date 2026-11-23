from __future__ import annotations

import dataclasses
import gc
import logging
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

from audio_manager import AudioError, Microphone, Speaker, list_devices
from cli import CliOptions, KeyListener, Status, parse_args
from config import AppConfig, ConfigError, load_config
from errors import HidekoError
from logging_setup import memory_rss_mb, setup_logging
from memory_store import MemoryStore
from response_handler import EchoResponder, ResponseHandler, Response, normalize
from stt_engine import STTEngine, STTError
from tts_engine import TTSEngine, TTSError
from vad import UtteranceRecorder

logger = logging.getLogger(__name__)


class HidekoApp:
    def __init__(self, config: AppConfig, opts: CliOptions) -> None:
        self.config = config
        self.opts = opts
        self.keys = KeyListener()
        self.status = Status()
        self._closed = False
        self._paused = False
        self._listening_shown = False
        self._wake_word_detected = False
        self._wake_word_timeout = 0.0
        self.stt: STTEngine | None = None
        self.tts: TTSEngine | None = None
        self.speaker: Speaker | None = None
        self.mic: Microphone | None = None
        self.recorder: UtteranceRecorder | None = None
        self.responder: EchoResponder | None = None
        self.memory: MemoryStore | None = None

    def setup(self) -> None:
        # 1. logging setup at the very start
        self._consecutive_errors = 0
        self._start_rss = memory_rss_mb()
        setup_logging(self.config.logging, debug=self.opts.debug, log_file=self.opts.log_file)

        # 2. print/l logging "Hideko MVP — Ctrl+C to stop"
        logger.info("Hideko MVP — Ctrl+C to stop")

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
            print("Stay quiet for 1 second — calibrating...")
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

        # 9. if config.runtime.greet_on_start: synthesize+play greeting once
        if self.config.runtime.greet_on_start and not self.opts.no_greet and self.tts is not None:
            clip = self.tts.synthesize("Hello. I am Hideko. I am listening.")
            self.speaker.play(clip.samples, clip.sample_rate)

    def run(self) -> int:
        try:
            turn = 0
            while True:
                if self.config.runtime.max_turns and turn >= self.config.runtime.max_turns:
                    break

                # Key handling at top of loop
                key = self.keys.poll()
                if key == "q":
                    break
                if key == self.opts.mute_key and self.opts.mute_key.lower() != "none":
                    self._paused = not self._paused
                    self._listening_shown = False
                    if self._paused:
                        self.status.paused()
                    else:
                        self.status.listening()
                        self._listening_shown = True
                if self._paused:
                    self.mic.flush(self.config.audio.block_ms)
                    continue

                block = self.mic.read_block()
                
                # Check for listen mode timeout (only when wake word mode is enabled)
                if self.config.wake_word.enabled and self._wake_word_detected:
                    if perf_counter() > self._wake_word_timeout:
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
                            self._wake_word_timeout = perf_counter() + self.config.wake_word.listen_mode_timeout_s
                            logger.info(f"Wake word detected: '{transcript.text}'")
                            print(f"  [wake word detected in {t1-t0:.1f}s]")
                            continue
                    # Not a wake word, loop back to listen for wake word
                    continue
                
                # Normal command processing (when not in wake word mode or after timeout)
                t0 = perf_counter()
                self.status.thinking()
                transcript = self.stt.transcribe(utterance, self.config.audio.sample_rate)
                t1 = perf_counter()
                if not transcript.text:
                    print("  (didn't catch that)")
                    self.recorder.reset()
                    continue

                self.status.heard(transcript.text)
                if self.memory is not None and self.memory.observe(transcript.text):
                    self.memory.save()
                response = self.responder.respond(transcript.text)
                t2 = perf_counter()

                if self.opts.no_tts:
                    print(f"Hideko: {response.text}")
                    t3 = t2
                    t4 = t2
                else:
                    self.status.say(response.text)
                    clip = self.tts.synthesize(response.text)
                    t3 = perf_counter()
                    self.speaker.play(clip.samples, clip.sample_rate)
                    t4 = perf_counter()

                print(
                    f"  [stt {t1-t0:.1f}s | resp {t2-t1:.2f}s | tts {t3-t2:.2f}s "
                    f"| play {t4-t3:.2f}s | total {t4-t0:.1f}s]"
                )
                logger.info(
                    "timing stt=%.2f resp=%.3f tts=%.2f play=%.2f total=%.2f",
                    t1 - t0, t2 - t1, t3 - t2, t4 - t3, t4 - t0,
                )

                if response.should_exit:
                    print("\nGoodbye.")
                    break
                turn += 1

                # Reset consecutive error counter after successful turn
                self._consecutive_errors = 0

                if self.config.runtime.half_duplex:
                    self.recorder.reset()
                    self.mic.flush(self.config.vad.post_playback_flush_ms)

                # Log memory every 20 turns
                if turn % 20 == 0:
                    rss = memory_rss_mb() or -1
                    logger.info("memory: %.0f MB RSS, %d objects", rss, len(gc.get_objects()))
                    gc.collect()
                    if self._start_rss is not None and rss != -1 and rss - self._start_rss > 300:
                        logger.warning("RSS grew >300 MB since start (%.0f -> %.0f MB)", self._start_rss, rss)

            return 0
        except HidekoError as exc:
            print(f"  ({exc})")
            logger.exception("turn failed: %s", exc)
            self._consecutive_errors += 1
            sys.exit(getattr(exc, "exit_code", 1))

    def shutdown(self) -> None:
        # Idempotent via self._closed. Close speaker then mic.
        if self._closed:
            return
        self._closed = True
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
            print(f"Hideko: {response.text}")
            if not opts.no_tts:
                clip = TTSEngine(config).synthesize(response.text)
                Speaker(config).play(clip.samples, clip.sample_rate)
        except HidekoError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return exc.exit_code
        return 0

    app = HidekoApp(config, opts)
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
        app.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
