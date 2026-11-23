#!/usr/bin/env python
"""Minimal repro for llama-cpp-python GPU offload. Standalone."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import llama_cpp  # noqa: E402

MODEL = ROOT / "models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf"
BIG = ROOT / "models/llm/qwen2.5-coder-7b-instruct-q4_k_m.gguf"


def probe(model: Path, n_gpu_layers: int) -> None:
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
        print(f"reply={out['choices'][0]['text'].strip()!r} gen={time.perf_counter() - t1:.2f}s")
    except Exception as exc:
        print(f"FAILED type={type(exc).__name__} error={exc!r}")


if __name__ == "__main__":
    target = BIG if "--big" in sys.argv else MODEL
    layers = [int(a) for a in sys.argv[1:] if a.lstrip("-").isdigit()] or [-1]
    for ngl in layers:
        probe(target, ngl)
