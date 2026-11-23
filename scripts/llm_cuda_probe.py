#!/usr/bin/env python
"""Minimal repro for llama-cpp-python GPU offload. No Hideko app code required.

Usage:
    llm_cuda_probe.py [-1] [0] [--big]

Each positional integer is an ``n_gpu_layers`` value to test in turn (``-1``
offloads every layer). Exits non-zero if any variant fails to load or generate.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm_fallback import _prepare_native_library_dirs  # noqa: E402

_prepare_native_library_dirs()

import llama_cpp  # noqa: E402

MODEL = ROOT / "models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf"
BIG = ROOT / "models/llm/qwen2.5-coder-7b-instruct-q4_k_m.gguf"


def probe(model: Path, n_gpu_layers: int) -> bool:
    """Load ``model`` with the given offload setting and generate a short reply.

    Args:
        model: Path to the GGUF file.
        n_gpu_layers: Value passed to llama_cpp.Llama (-1 = all layers).

    Returns:
        True if the model loaded and generated text, False otherwise.
    """
    print(f"model={model.name} n_gpu_layers={n_gpu_layers} llama_cpp={llama_cpp.__version__}")
    t0 = time.perf_counter()
    try:
        llm = llama_cpp.Llama(
            model_path=str(model),
            n_ctx=512,
            n_threads=6,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )
        print(f"loaded in {time.perf_counter() - t0:.2f}s")
        t1 = time.perf_counter()
        out = llm(
            "User: what is the capital of France?\nHideko:",
            max_tokens=16,
            stop=["\n", "User:", "Hideko:"],
        )
        reply = out["choices"][0]["text"].strip()
        print(f"reply={reply!r} gen={time.perf_counter() - t1:.2f}s")
        return bool(reply)
    except Exception as exc:
        print(f"FAILED type={type(exc).__name__} error={exc!r}")
        return False


if __name__ == "__main__":
    target = BIG if "--big" in sys.argv else MODEL
    layers = [int(a) for a in sys.argv[1:] if a.lstrip("-").isdigit()] or [-1]
    if not target.is_file():
        print(f"model not found: {target}; run: python scripts/download_models.py --llm")
        sys.exit(2)
    results = [probe(target, ngl) for ngl in layers]
    sys.exit(0 if all(results) else 1)
