# Task 08 — CLI-GUI Integration

**Phase:** Integration · **Depends on:** task 07 · **Blocks:** task 09 · **Effort:** 45-60 min

---

## Goal

Integrate the GUI with the CLI by adding a `--gui` flag to enable the GUI, and wiring the GUI into the main application loop. The GUI should work alongside the CLI, not replace it.

**You only need this file.** Everything is inlined. Do not open other task files or READMEs.

| | |
|---|---|
| Files you touch | `cli.py`, `main.py` — **modify only these** |
| Depends on | task 07 (tray icon exists) |
| Blocks | task 09 |
| Time budget | ~50 min |

---

## Step 1 — Verify dependencies

```powershell
# Verify GUI modules
python -c "from gui import launch_gui; from gui.app import GUIApp; from gui.tray import SystemTray; print('GUI imports OK')"

# Verify CLI module
python -c "from cli import CliOptions, parse_args; print('CLI imports OK')"

# Verify main module
python -c "from main import HidekoApp; print('main module OK')"

# Verify event bus
python -c "from events import EventBus; print('events module OK')"
```

All must succeed. If any fail, stop and report.

---

## Step 2 — Add GUI flag to CLI

First, let's add the `--gui` flag to the CLI options.

**Modify `cli.py`**:

**Update the CliOptions dataclass** (add one more field):

```python
@dataclasses.dataclass(frozen=True)
class CliOptions:
    """Command-line options for the application."""
    config: Path
    text: str | None
    turns: int | None
    debug: bool
    no_tts: bool
    no_greet: bool
    list_devices: bool
    calibrate: bool
    log_file: Path | None
    mute_key: str
    facts: bool
    forget: bool
    gui: bool = False  # Add this line
```

**Add the --gui argument to build_parser()**:

Find the `build_parser()` function and add this after the `--forget` argument:

```python
parser.add_argument(
    "--gui",
    action="store_true",
    default=False,
    help="Enable GUI interface",
)
```

**Update parse_args() to include gui**:

Find the `parse_args()` function and add `gui=args.gui` to the CliOptions constructor:

```python
return CliOptions(
    config=config_path,
    text=args.text,
    turns=turns,
    debug=args.debug,
    no_tts=args.no_tts,
    no_greet=args.no_greet,
    list_devices=args.list_devices,
    calibrate=args.calibrate,
    log_file=log_file_path,
    mute_key=args.mute_key,
    facts=args.facts,
    forget=args.forget,
    gui=args.gui,  # Add this line
)
```

---

## Step 3 — Modify main.py to support GUI

Now we need to integrate the GUI into the main application.

**Modify `main.py`**:

First, add the GUI import at the top (after other imports):

```python
# Add this after the other imports
try:
    from gui import launch_gui
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
    logger.warning("GUI not available: PySide6 not installed")
```

**Modify the main() function**:

Find the `main()` function and modify it to support GUI:

```python
def main() -> None:
    """Entry point for Hideko."""
    opts = parse_args()
    
    # Load config
    try:
        config = load_config(opts.config)
    except ConfigError as e:
        logger.error("Config error: %s", e)
        sys.exit(1)
    
    # Check if we need to list devices or calibrate and exit
    if opts.list_devices:
        from audio_manager import list_devices
        for device in list_devices():
            print(f"{device.get('index', '?')}: {device.get('name', 'Unknown')} "
                  f"({device.get('max_input_channels', 0)} in, "
                  f"{device.get('max_output_channels', 0)} out)")
        sys.exit(0)
    
    if opts.calibrate:
        from audio_manager import Microphone, AudioError
        try:
            mic = Microphone(config)
            with mic:
                # This will trigger calibration in the recorder
                print("Stay quiet for 1 second — calibrating...")
        except AudioError as e:
            print(f"Calibration failed: {e}")
            sys.exit(1)
        sys.exit(0)
    
    # Create event bus
    bus = EventBus()
    
    # Launch GUI if requested
    gui_app = None
    if opts.gui and GUI_AVAILABLE:
        try:
            gui_app = launch_gui(config, bus)
            if gui_app is None:
                logger.warning("GUI failed to launch, continuing with CLI")
        except Exception as e:
            logger.error("GUI launch error: %s", e)
            logger.info("Continuing with CLI only")
    elif opts.gui and not GUI_AVAILABLE:
        logger.warning("GUI requested but not available, continuing with CLI")
    
    # Create and run the application
    app = HidekoApp(config, opts, bus=bus)
    
    # Connect GUI to app if available
    if gui_app is not None:
        # Pass app to GUI for potential future connections
        # The GUI already subscribes to the event bus
        pass
    
    # Run the main loop
    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        app.shutdown()
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        app.shutdown()
        sys.exit(1)
    finally:
        # Clean up GUI
        if gui_app is not None:
            gui_app.close()
    
    # Exit with appropriate code
    sys.exit(app.exit_code)
```

**Wait, we need to check what the current main() function looks like and how HidekoApp.run() works.**

Let me check the current main.py structure more carefully.

Actually, let's take a different approach. We need to modify the main() function to process Qt events while the audio loop is running.

**Find and modify the main() function**:

The current main.py likely has a main() function that creates HidekoApp and calls run(). We need to process Qt events periodically.

**Replace the main() function with this**:

```python
def main() -> None:
    """Entry point for Hideko."""
    opts = parse_args()
    
    # Load config
    try:
        config = load_config(opts.config)
    except ConfigError as e:
        logger.error("Config error: %s", e)
        sys.exit(1)
    
    # Handle special CLI flags that exit early
    if opts.list_devices:
        from audio_manager import list_devices
        for device in list_devices():
            print(f"{device.get('index', '?')}: {device.get('name', 'Unknown')} "
                  f"({device.get('max_input_channels', 0)} in, "
                  f"{device.get('max_output_channels', 0)} out)")
        sys.exit(0)
    
    if opts.calibrate:
        from audio_manager import Microphone
        try:
            mic = Microphone(config)
            with mic:
                print("Stay quiet for 1 second — calibrating...")
        except Exception as e:
            print(f"Calibration failed: {e}")
            sys.exit(1)
        sys.exit(0)
    
    if opts.facts:
        from memory_store import MemoryStore
        store = MemoryStore()
        facts = store.get_all_facts()
        if facts:
            print("Remembered facts:")
            for fact in facts:
                print(f"  - {fact}")
        else:
            print("No facts remembered yet.")
        sys.exit(0)
    
    if opts.forget:
        from memory_store import MemoryStore
        store = MemoryStore()
        store.clear()
        print("All facts forgotten.")
        sys.exit(0)
    
    # Create event bus
    bus = EventBus()
    
    # Launch GUI if requested
    gui_app = None
    if opts.gui and GUI_AVAILABLE:
        try:
            gui_app = launch_gui(config, bus)
            if gui_app is None:
                logger.warning("GUI failed to launch, continuing with CLI")
        except Exception as e:
            logger.error("GUI launch error: %s", e)
            logger.info("Continuing with CLI only")
    elif opts.gui and not GUI_AVAILABLE:
        logger.warning("GUI requested but not available, continuing with CLI")
    
    # Create application
    app = HidekoApp(config, opts, bus=bus)
    
    # If GUI is available and requested, process Qt events in main loop
    if gui_app is not None and gui_app.qapp is not None:
        # Set up timer to process Qt events
        from PySide6.QtCore import QTimer
        qt_timer = QTimer()
        qt_timer.setInterval(16)  # ~60 FPS
        qt_timer.timeout.connect(lambda: gui_app.qapp.processEvents())
        qt_timer.start()
        
        # Store timer reference to keep it alive
        app._qt_timer = qt_timer
    
    # Run the application
    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
    finally:
        # Clean up GUI
        if gui_app is not None:
            gui_app.close()
        
        # Shutdown application
        app.shutdown()
    
    sys.exit(app.exit_code)
```

**Wait, we need to check if HidekoApp.run() is a blocking call. If it is, we need to integrate Qt event processing into it.**

Let me think about this differently. The HidekoApp.run() method likely contains the main audio loop. We need to process Qt events within that loop.

**Find the run() method in HidekoApp and modify it**:

Actually, let's modify the approach. Instead of changing the core run() method, we'll modify main() to handle both the audio loop and Qt events.

But first, let's see what the current structure is. Looking at the code we've seen, HidekoApp has a run() method that does the audio loop.

**Alternative approach: Modify HidekoApp to be aware of GUI**:

Actually, a better approach is to have the GUI process events itself. Since the event bus is already publishing events, and the GUI subscribes to them, we just need to ensure the Qt event loop runs.

Let's modify the approach:

**Modify `main.py`**:

Add at the top:

```python
# GUI availability
try:
    from gui import launch_gui
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
    logger.debug("GUI not available")
```

**Modify the main() function**:

We need to handle the case where GUI is enabled. The simplest approach is to run the Qt event loop in a separate thread, but that's complex. Instead, we'll process Qt events in the main loop.

Actually, looking at the architecture, the GUI subscribes to the event bus, so it will receive events. The only issue is that Qt widgets need their event loop to be processed.

The simplest solution is to create a QApplication and process events in the main loop if GUI is enabled.

**Find and replace the main() function**:

```python
def main() -> None:
    """Entry point for Hideko."""
    opts = parse_args()
    
    # Load config
    try:
        config = load_config(opts.config)
    except ConfigError as e:
        logger.error("Config error: %s", e)
        sys.exit(1)
    
    # Handle early-exit CLI flags
    if opts.list_devices:
        from audio_manager import list_devices
        for device in list_devices():
            print(f"{device.get('index', '?')}: {device.get('name', 'Unknown')} "
                  f"({device.get('max_input_channels', 0)} in, "
                  f"{device.get('max_output_channels', 0)} out)")
        sys.exit(0)
    
    if opts.calibrate:
        from audio_manager import Microphone
        try:
            mic = Microphone(config)
            with mic:
                print("Stay quiet for 1 second — calibrating...")
        except Exception as e:
            print(f"Calibration failed: {e}")
            sys.exit(1)
        sys.exit(0)
    
    if opts.facts:
        from memory_store import MemoryStore
        store = MemoryStore()
        facts = store.get_all_facts()
        if facts:
            print("Remembered facts:")
            for fact in facts:
                print(f"  - {fact}")
        else:
            print("No facts remembered yet.")
        sys.exit(0)
    
    if opts.forget:
        from memory_store import MemoryStore
        store = MemoryStore()
        store.clear()
        print("All facts forgotten.")
        sys.exit(0)
    
    # Create event bus
    bus = EventBus()
    
    # Launch GUI if requested
    gui_app = None
    qapp = None
    if opts.gui and GUI_AVAILABLE:
        try:
            # Create QApplication if it doesn't exist
            from PySide6.QtWidgets import QApplication
            qapp = QApplication.instance()
            if qapp is None:
                qapp = QApplication(sys.argv)
            
            gui_app = launch_gui(config, bus)
            if gui_app is None:
                logger.warning("GUI failed to launch, continuing with CLI")
        except Exception as e:
            logger.error("GUI launch error: %s", e)
            logger.info("Continuing with CLI only")
    elif opts.gui and not GUI_AVAILABLE:
        logger.warning("GUI requested but not available, continuing with CLI")
    
    # Create application
    app = HidekoApp(config, opts, bus=bus)
    
    # Run the application
    try:
        # If we have a GUI, we need to run Qt event loop alongside
        if qapp is not None and gui_app is not None:
            # Process Qt events periodically during audio loop
            # This is handled by the GUI app itself
            app.run()
            
            # After run() returns, we might need to exec Qt
            # But for now, just let the GUI handle itself
        else:
            # No GUI, run normally
            app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
    finally:
        # Clean up
        if gui_app is not None:
            gui_app.close()
        
        app.shutdown()
    
    sys.exit(app.exit_code)
```

Actually, this is getting complex. Let's take a simpler approach: the GUI will process its own events. We just need to make sure the QApplication exists and its events are processed.

**Simpler approach - modify main()**:

```python
def main() -> None:
    """Entry point for Hideko."""
    opts = parse_args()
    
    # Load config
    try:
        config = load_config(opts.config)
    except ConfigError as e:
        logger.error("Config error: %s", e)
        sys.exit(1)
    
    # Handle early-exit CLI flags
    if opts.list_devices:
        from audio_manager import list_devices
        for device in list_devices():
            print(f"{device.get('index', '?')}: {device.get('name', 'Unknown')} "
                  f"({device.get('max_input_channels', 0)} in, "
                  f"{device.get('max_output_channels', 0)} out)")
        sys.exit(0)
    
    if opts.calibrate:
        from audio_manager import Microphone
        try:
            mic = Microphone(config)
            with mic:
                print("Stay quiet for 1 second — calibrating...")
        except Exception as e:
            print(f"Calibration failed: {e}")
            sys.exit(1)
        sys.exit(0)
    
    if opts.facts:
        from memory_store import MemoryStore
        store = MemoryStore()
        facts = store.get_all_facts()
        if facts:
            print("Remembered facts:")
            for fact in facts:
                print(f"  - {fact}")
        else:
            print("No facts remembered yet.")
        sys.exit(0)
    
    if opts.forget:
        from memory_store import MemoryStore
        store = MemoryStore()
        store.clear()
        print("All facts forgotten.")
        sys.exit(0)
    
    # Create event bus
    bus = EventBus()
    
    # Launch GUI if requested
    gui_app = None
    if opts.gui and GUI_AVAILABLE:
        try:
            gui_app = launch_gui(config, bus)
            if gui_app is None:
                logger.warning("GUI failed to launch, continuing with CLI")
        except Exception as e:
            logger.error("GUI launch error: %s", e)
            logger.info("Continuing with CLI only")
    elif opts.gui and not GUI_AVAILABLE:
        logger.warning("GUI requested but not available, continuing with CLI")
    
    # Create application
    app = HidekoApp(config, opts, bus=bus)
    
    # If GUI is available, pass it to the app
    app._gui_app = gui_app
    
    # Run the application
    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
    finally:
        # Clean up GUI
        if gui_app is not None:
            gui_app.close()
        
        # Shutdown application
        app.shutdown()
    
    sys.exit(app.exit_code)
```

**Now we need to modify HidekoApp.run() to process Qt events**:

Find the `run()` method in HidekoApp and modify it to process Qt events:

```python
def run(self) -> None:
    """Run the main application loop."""
    self.setup()
    
    # Main loop
    try:
        self._main_loop()
    finally:
        self.shutdown()

def _main_loop(self) -> None:
    """Main event loop."""
    import time
    
    while not self._closed:
        # Process a block of audio
        self._process_audio_block()
        
        # Process Qt events if GUI is available
        if hasattr(self, '_gui_app') and self._gui_app is not None:
            self._gui_app.process_events()
        
        # Small sleep to prevent CPU overload
        time.sleep(0.01)
```

Wait, but we don't want to modify the core _main_loop if it already exists. Let's check the actual HidekoApp structure.

**Alternative: Modify the existing run method to integrate Qt events**:

Actually, let's take an even simpler approach. We'll modify the main() function to either run with GUI or without.

**Final approach for main()**:

```python
def main() -> None:
    """Entry point for Hideko."""
    opts = parse_args()
    
    # Load config
    try:
        config = load_config(opts.config)
    except ConfigError as e:
        logger.error("Config error: %s", e)
        sys.exit(1)
    
    # Handle early-exit CLI flags
    if opts.list_devices:
        from audio_manager import list_devices
        for device in list_devices():
            print(f"{device.get('index', '?')}: {device.get('name', 'Unknown')} "
                  f"({device.get('max_input_channels', 0)} in, "
                  f"{device.get('max_output_channels', 0)} out)")
        sys.exit(0)
    
    if opts.calibrate:
        from audio_manager import Microphone
        try:
            mic = Microphone(config)
            with mic:
                print("Stay quiet for 1 second — calibrating...")
        except Exception as e:
            print(f"Calibration failed: {e}")
            sys.exit(1)
        sys.exit(0)
    
    if opts.facts:
        from memory_store import MemoryStore
        store = MemoryStore()
        facts = store.get_all_facts()
        if facts:
            print("Remembered facts:")
            for fact in facts:
                print(f"  - {fact}")
        else:
            print("No facts remembered yet.")
        sys.exit(0)
    
    if opts.forget:
        from memory_store import MemoryStore
        store = MemoryStore()
        store.clear()
        print("All facts forgotten.")
        sys.exit(0)
    
    # Create event bus
    bus = EventBus()
    
    # Create application
    app = HidekoApp(config, opts, bus=bus)
    
    # Launch GUI if requested
    gui_app = None
    if opts.gui and GUI_AVAILABLE:
        try:
            # First, set up the application
            app.setup()
            
            # Now launch GUI with the configured bus
            gui_app = launch_gui(config, bus)
            
            if gui_app is not None:
                logger.info("GUI launched successfully")
                # The GUI subscribes to events and updates itself
                # We just need to ensure Qt events are processed
            else:
                logger.warning("GUI failed to launch")
        except Exception as e:
            logger.error("GUI error: %s", e)
    
    # Run the application
    try:
        if gui_app is not None and gui_app.qapp is not None:
            # Run with Qt event loop
            import threading
            
            # Start audio processing in a separate thread
            audio_thread = threading.Thread(target=app._main_loop, daemon=True)
            audio_thread.start()
            
            # Run Qt event loop
            gui_app.exec()
            
            # Wait for audio thread to finish (briefly)
            app._closed = True
            audio_thread.join(timeout=2.0)
        else:
            # Run without GUI
            app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
    finally:
        # Clean up
        if gui_app is not None:
            gui_app.close()
        
        app.shutdown()
    
    sys.exit(app.exit_code)
```

This is getting too complex. Let me simplify and provide a cleaner solution.

**Clean Solution**:

The key insight is that the GUI subscribes to the event bus, so it will receive all events. The only thing we need to ensure is that Qt events are processed.

The simplest way is to:
1. Create the GUI (which creates QApplication)
2. Run the Qt event loop in the main thread
3. Run the audio processing in the Qt event loop using a timer

But this requires significant changes to the audio processing.

**Simpler Solution**:

Process Qt events in the existing audio loop. This is what we'll do.

**Modify `main.py`**:

Add at the top:

```python
# GUI availability
try:
    from gui import launch_gui
    from PySide6.QtWidgets import QApplication
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
    logger.debug("GUI not available: PySide6 not installed")
```

**Replace the main() function**:

```python
def main() -> None:
    """Entry point for Hideko."""
    opts = parse_args()
    
    # Load config
    try:
        config = load_config(opts.config)
    except ConfigError as e:
        logger.error("Config error: %s", e)
        sys.exit(1)
    
    # Handle early-exit CLI flags
    if opts.list_devices:
        from audio_manager import list_devices
        for device in list_devices():
            print(f"{device.get('index', '?')}: {device.get('name', 'Unknown')} "
                  f"({device.get('max_input_channels', 0)} in, "
                  f"{device.get('max_output_channels', 0)} out)")
        sys.exit(0)
    
    if opts.calibrate:
        from audio_manager import Microphone
        try:
            mic = Microphone(config)
            with mic:
                print("Stay quiet for 1 second — calibrating...")
        except Exception as e:
            print(f"Calibration failed: {e}")
            sys.exit(1)
        sys.exit(0)
    
    if opts.facts:
        from memory_store import MemoryStore
        store = MemoryStore()
        facts = store.get_all_facts()
        if facts:
            print("Remembered facts:")
            for fact in facts:
                print(f"  - {fact}")
        else:
            print("No facts remembered yet.")
        sys.exit(0)
    
    if opts.forget:
        from memory_store import MemoryStore
        store = MemoryStore()
        store.clear()
        print("All facts forgotten.")
        sys.exit(0)
    
    # Create event bus
    bus = EventBus()
    
    # Launch GUI if requested
    gui_app = None
    if opts.gui:
        if not GUI_AVAILABLE:
            logger.warning("GUI requested but PySide6 not available, continuing with CLI")
        else:
            try:
                gui_app = launch_gui(config, bus)
                if gui_app is None:
                    logger.warning("GUI failed to launch, continuing with CLI")
            except Exception as e:
                logger.error("GUI launch error: %s", e)
                logger.info("Continuing with CLI")
    
    # Create application
    app = HidekoApp(config, opts, bus=bus, gui_app=gui_app)
    
    # Run the application
    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception("Unexpected error")
    finally:
        if gui_app is not None:
            gui_app.close()
        app.shutdown()
    
    sys.exit(app.exit_code)
```

**Modify HidekoApp to accept gui_app**:

Find the `__init__` method of HidekoApp and modify it:

```python
def __init__(
    self,
    config: AppConfig,
    opts: CliOptions,
    bus: EventBus | None = None,
    status: Status | None = None,
    turn: TurnController | None = None,
    registry: ToolRegistry | None = None,
    scheduler: Scheduler | None = None,
    gui_app: GUIApp | None = None,  # Add this parameter
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
    self._gui_app = gui_app  # Add this line
```

**Modify the run() method to process Qt events**:

Find the run() method and modify it:

```python
def run(self) -> None:
    """Run the main application loop."""
    self.setup()
    
    import time
    
    try:
        while not self._closed:
            # Process a block of audio
            self._process_block()
            
            # Process Qt events if GUI is available
            if self._gui_app is not None:
                self._gui_app.process_events()
            
            # Small sleep to prevent CPU overload
            time.sleep(0.001)
    finally:
        self.shutdown()
```

This should integrate the GUI with the CLI while keeping the core functionality intact.

---

## Verification

Run these commands and paste the output in your report.

```powershell
# Verify CLI still works
python -c "from cli import parse_args; opts=parse_args(['--help'])" 2>&1 | head -5

# Verify GUI flag is recognized
python -c "from cli import parse_args; opts=parse_args(['--gui']); print('gui flag:', opts.gui)"

# Verify imports work
python -c "from main import main; from gui import launch_gui; print('All imports OK')"

# Test that --help includes the new flag
python main.py --help 2>&1 | Select-String --Pattern "\-\-gui"
```

---

## Done criteria

- [ ] `cli.py` updated with `--gui` flag
- [ ] `main.py` updated to integrate GUI
- [ ] All imports work without errors
- [ ] `--help` shows the new `--gui` flag
- [ ] `--gui` flag is recognized and parsed correctly
- [ ] GUI can be launched via `--gui` flag
- [ ] No other files were modified

---

## Common pitfalls

- **Import errors**: GUI imports might fail without PySide6
- **Event loop conflicts**: Qt and audio loop might conflict
- **Thread safety**: GUI updates must be on Qt main thread
- **Resource leaks**: GUI resources must be cleaned up properly
- **Flag conflicts**: New flag shouldn't conflict with existing ones

---

## Do NOT

- Do not break existing CLI functionality
- Do not make GUI mandatory (must work without --gui)
- Do not modify core audio processing logic
- Do not start task 09

---

## Report

Report: files created/modified, pasted verification output, any issues encountered, anything unfinished.
