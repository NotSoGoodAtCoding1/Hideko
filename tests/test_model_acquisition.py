"""Tests for scripts/download_models.py and scripts/check_env.py (task 02)."""
from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dm = load_script("download_models")
ce = load_script("check_env")


class FakeResponse:
    def __init__(self, payload: bytes, chunk_size: int = 4) -> None:
        self.payload = payload
        self.chunk_size = chunk_size
        self.offset = 0
        self.headers = {"Content-Length": str(len(payload))}

    def read(self, size: int) -> bytes:
        del size
        chunk = self.payload[self.offset : self.offset + self.chunk_size]
        self.offset += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


# ---------------------------------------------------------------------------
# download_models.py
# ---------------------------------------------------------------------------


def test_voice_urls_are_pinned_to_a_compatible_revision():
    assert "/main/" not in dm.VOICE_MODEL_URL
    assert dm.VOICE_REVISION in dm.VOICE_MODEL_URL
    assert dm.VOICE_REVISION in dm.VOICE_CONFIG_URL


def test_selected_steps_defaults_to_all():
    args = dm.build_parser().parse_args([])
    assert dm.selected_steps(args) == ["piper", "voice", "stt"]


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (["--piper"], ["piper"]),
        (["--voice"], ["voice"]),
        (["--stt"], ["stt"]),
        (["--piper", "--stt"], ["piper", "stt"]),
    ],
)
def test_selected_steps_honors_individual_flags(flags, expected):
    args = dm.build_parser().parse_args(flags)
    assert dm.selected_steps(args) == expected


def test_download_writes_atomically_and_validates_size(tmp_path, monkeypatch, capsys):
    payload = b"0123456789"
    monkeypatch.setattr(
        dm.urllib.request,
        "urlopen",
        lambda req, timeout: FakeResponse(payload),
    )
    dest = tmp_path / "voice.onnx"

    size = dm.download("https://example.test/voice.onnx", dest, 8)

    assert size == len(payload)
    assert dest.read_bytes() == payload
    assert not dest.with_name(dest.name + ".part").exists()
    assert "voice.onnx" in capsys.readouterr().out


def test_download_rejects_short_file_and_leaves_no_part(tmp_path, monkeypatch):
    monkeypatch.setattr(
        dm.urllib.request,
        "urlopen",
        lambda req, timeout: FakeResponse(b"short"),
    )
    dest = tmp_path / "model.bin"

    with pytest.raises(dm.AcquisitionError, match="expected >= 100"):
        dm.download("https://example.test/model.bin", dest, 100)

    assert not dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()


def test_download_reports_http_status_and_url(tmp_path, monkeypatch):
    url = "https://example.test/voice.onnx"

    def raise_http(req, timeout):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(dm.urllib.request, "urlopen", raise_http)

    with pytest.raises(dm.AcquisitionError, match=r"403.*" + url.replace(".", r"\.")):
        dm.download(url, tmp_path / "voice.onnx", 8)


def test_voice_step_skips_complete_files_unless_forced(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "PIPER_DIR", tmp_path)
    (tmp_path / "en_US-amy-medium.onnx").write_bytes(b"x" * (11 * 1024 * 1024))
    (tmp_path / "en_US-amy-medium.onnx.json").write_bytes(b"{}" * 1024)
    calls = []

    def fake_download(url, dest, min_bytes):
        calls.append(url)

    monkeypatch.setattr(dm, "download", fake_download)

    dm.download_piper_voice(force=False)
    assert calls == []

    dm.download_piper_voice(force=True)
    assert calls == [dm.VOICE_MODEL_URL, dm.VOICE_CONFIG_URL]


def test_piper_step_skips_complete_installation_unless_forced(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "PIPER_DIR", tmp_path)
    exe = tmp_path / "piper" / "piper.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"x" * (500 * 1024))
    (tmp_path / "piper" / "espeak-ng-data").mkdir()
    (tmp_path / "piper" / "espeak-ng-data" / "phondata").write_bytes(b"data")
    calls = []

    def fake_download(url, dest, min_bytes):
        calls.append(url)

    monkeypatch.setattr(dm, "download", fake_download)

    dm.download_piper_binary(force=False)
    assert calls == []

    # Force must bypass the skip and re-download the archive.
    monkeypatch.setattr(dm, "extract_piper_zip", lambda zip_path: None)
    dm.download_piper_binary(force=True)
    assert calls == [dm.PIPER_URL]


def test_main_returns_failure_and_prints_error(monkeypatch, capsys):
    def explode(force):
        raise dm.AcquisitionError(f"HTTP 403 for {dm.VOICE_MODEL_URL}")

    monkeypatch.setitem(dm.STEP_FUNCS, "voice", explode)
    args = dm.build_parser().parse_args(["--voice"])

    assert dm.main(args) == 1
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "403" in output
    assert dm.VOICE_MODEL_URL in output


def test_summary_table_lists_all_four_artifacts(monkeypatch, capsys):
    monkeypatch.setattr(dm, "piper_is_complete", lambda: True)
    monkeypatch.setattr(dm, "voice_is_complete", lambda: True)
    monkeypatch.setattr(dm, "whisper_is_complete", lambda: True)
    monkeypatch.setattr(dm, "piper_size", lambda: 509_952)
    monkeypatch.setattr(dm, "voice_size", lambda: 63_201_294)
    monkeypatch.setattr(dm, "config_size", lambda: 4_882)
    monkeypatch.setattr(dm, "whisper_size", lambda: 75_537_502)

    dm.print_summary(set(dm.STEP_FUNCS))
    out = capsys.readouterr().out
    for label in ("Piper binary", "Piper voice", "Voice config", "Whisper model"):
        assert label in out
    assert "artifact" in out and "size" in out


# ---------------------------------------------------------------------------
# check_env.py
# ---------------------------------------------------------------------------


def test_check_env_prints_table_header(capsys):
    assert ce.main(["--no-audio"]) in (0, 1)
    out = capsys.readouterr().out
    assert "check" in out and "status" in out and "detail" in out


def test_no_audio_reports_warning_rows(monkeypatch, capsys):
    monkeypatch.setattr(ce, "check_python_version", lambda: ("OK", "ok"))
    monkeypatch.setattr(ce, "check_numpy_version", lambda: ("OK", "ok"))
    monkeypatch.setattr(ce, "check_imports", lambda: ("OK", "ok"))
    monkeypatch.setattr(ce, "check_portaudio", lambda: ("OK", "ok"))
    monkeypatch.setattr(ce, "check_piper_binary", lambda: ("OK", "ok"))
    monkeypatch.setattr(ce, "check_piper_espeak_data", lambda: ("OK", "ok"))
    monkeypatch.setattr(ce, "check_piper_voice", lambda: ("OK", "ok"))
    monkeypatch.setattr(ce, "check_voice_config", lambda: ("OK", "ok"))
    monkeypatch.setattr(ce, "check_voice_compatibility", lambda: ("OK", "ok"))
    monkeypatch.setattr(ce, "check_whisper_model", lambda: ("OK", "ok"))
    monkeypatch.setattr(ce, "check_llm_server", lambda: ("-", "disabled"))
    monkeypatch.setattr(ce, "check_input_device", lambda: ("WARN", "skipped"))
    monkeypatch.setattr(ce, "check_output_device", lambda: ("WARN", "skipped"))

    assert ce.main(["--no-audio"]) == 0
    out = capsys.readouterr().out
    assert "Input device" in out and "WARN" in out
    assert "Output device" in out and "WARN" in out


def test_voice_config_compatibility_check(tmp_path, monkeypatch):
    config = tmp_path / "en_US-amy-medium.onnx.json"
    monkeypatch.setattr(ce, "VOICE_CONFIG", config)

    config.write_text(
        json.dumps({"piper_version": "1.0.0", "phoneme_id_map": {"a": [14], "ɪ": [74]}}),
        encoding="utf-8",
    )
    assert ce.check_voice_compatibility()[0] == "OK"

    config.write_text(
        json.dumps({"piper_version": "1.5.0", "phoneme_id_map": {"aɪ": [161]}}),
        encoding="utf-8",
    )
    status, detail = ce.check_voice_compatibility()
    assert status == "FAILED"
    assert "multi-codepoint" in detail


def test_portaudio_check_uses_human_readable_version(monkeypatch):
    text = "PortAudio V19.7.0-devel, revision 147dd722548358763a8b649b3e4b41dfffbcfbb6"
    monkeypatch.setattr(
        ce,
        "_portaudio_version",
        lambda: (1246976, text),
    )
    status, detail = ce.check_portaudio()
    assert status == "OK"
    assert text in detail
