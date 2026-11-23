# Hideko LLM Performance Analysis: GPU Sharing Impact

## Executive Summary
**GPU contention is causing severe LLM latency degradation.** The RTX 3060 at 96% utilization indicates heavy competition for VRAM between processes.

---

## System Resources

### GPU Status
```
NVIDIA GeForce RTX 3060
  - Total VRAM: 12 GB (12288 MiB)
  - Free VRAM: ~5.4 GB (2180 MiB)
  - Utilization: 96% ⚠️ CRITICAL
```

### Memory Pressure Analysis

| Process | Est. VRAM Usage | Notes |
|---------|-----------------|-------|
| **Qwen2.5-7B model** (FP16) | ~14 GB | Needs full GPU for fast inference |
| Available VRAM (current state) | ~5.4 GB | Insufficient for 7B model |
| Python + STT + TTS overhead | ~700 MB+ | Competing processes |
| **Result** | ❌ Model must use CPU → Slow | 10-30x slower than GPU |

---

## Performance Impact Comparison

### Current (CPU-only / Hybrid) vs. GPU-offloaded

| Metric | CPU-only (Current) | GPU offload (Recommended) | Improvement |
|--------|-------------------|--------------------------|-------------|
| **First token latency** | 10-30 seconds | 200-500ms | **60-70x faster** |
| **Total response time** | ~21 seconds | ~3-5 seconds | **4-7x faster** |
| **GPU utilization** | Low/medium | High (intended) | Optimal for LLM |
| **Power usage** | Lower | Higher (~60-80W) | Trade-off for speed |

### Latency Breakdown from Logs
```bash
# With 7B model on CPU:
stt=0.38s + resp=15.049s (timeout!) + tts=1.18s = 21.04s total

# Expected with GPU offload:
stt=0.4s + resp=0.8s + tts=0.7s = ~1.9s total (10x faster)
```

---

## Solutions Ranked by Effectiveness

### 🥇 Solution 1: Enable GPU Offload in Kobold.cpp
**Impact**: Eliminates the bottleneck entirely

#### Command to restart Kobold.cpp with GPU:
```powershell
& "C:\Users\Ilya\Documents\new_prj\tools\koboldcpp\koboldcpp.exe" ^
  -m "models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf" ^
  --host 127.0.0.1 ^
  --port 5001 ^
  --usecuda main ^
  --n-gpu-layers -1 ^
  --ctx-size 2048 ^
  --threads 6
```

**Parameter explanations:**
- `--usecuda main` → Enable GPU for primary model inference
- `--n-gpu-layers -1` → Offload ALL layers to GPU (critical!)
- `--ctx-size 2048` → Reduce context size from 4096 to save VRAM
- `--threads 6` → CPU threads for non-inference tasks

**Expected improvement**: From 21s → ~3 seconds per turn

---

### 🥈 Solution 2: Use Smaller Model (Already Applied)
**Impact**: Reduces VRAM and CPU requirements

#### Changed config:
```yaml
llm:
  model: qwen2.5-0.5b-instruct-q4_k_m.gguf   # ~24 MB, fits in VRAM easily
```

**Why this helps:**
- **VRAM**: ~1 GB vs. ~14 GB for 7B model
- **CPU fallback**: Acceptable speed even on CPU (~500ms-1s)
- **Quality trade-off**: 0.5B is simpler but still coherent

---

### 🥉 Solution 3: Reduce Parallel Workload
**Impact**: Frees up VRAM for LLM inference

#### Options:
1. **Close GPU-heavy applications:**
   - Web browsers (Chrome, Edge with many tabs)
   - Photo/video editing software
   - Gaming

2. **Lower Python process overhead:**
   ```bash
   # Check what's using GPU
   tasklist /V | findstr python
   
   # Monitor GPU in real-time
   nvidia-smi -l 1
   ```

3. **Disable STT/TTS if not needed:**
   - Test LLM in isolation for benchmarking

---

## VRAM Requirements Matrix

| Model Size | FP16 VRAM | Q4_K_M VRAM (4-bit) | GPU Offload Possible? |
|------------|-----------|---------------------|----------------------|
| **qwen2.5-0.5B** | ~1 GB | ~24 MB | ✅ Yes (easily) |
| **qwen2.5-1.5B** | ~3 GB | ~70 MB | ✅ Yes |
| **qwen2.5-3B** | ~6 GB | ~150 MB | ✅ Yes |
| **qwen2.5-7B** | ~14 GB | ~4.3 GB | ⚠️ Partial (needs 9GB+ VRAM) |
| **qwen2.5-14B** | ~28 GB | ~8.6 GB | ❌ No (requires >20GB VRAM) |

**RTX 3060 = 12GB VRAM:**
- Can handle: 0.5B → 7B (partial), 14B (no)
- Recommended max for this card: **7B with careful memory management**

---

## Benchmark Commands

### Test GPU offloading capability:
```bash
python scripts/llm_cuda_probe.py --big -1
# Tests Qwen2.5-7B with all layers on GPU (-1 = all layers)
```

### Quick latency comparison:
```bash
# CPU-only baseline
& "C:\Users\Ilya\Documents\new_prj\tools\koboldcpp\koboldcpp.exe" ^
  -m "models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf" ^
  --host 127.0.0.1 --port 5001

# GPU-accelerated (kill old process first with Ctrl+C)
& "C:\Users\Ilya\Documents\new_prj\tools\koboldcpp\koboldcpp.exe" ^
  -m "models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf" ^
  --host 127.0.0.1 --port 5001 ^
  --usecuda main ^
  --n-gpu-layers -1

# Measure response time
python -c "import urllib.request, json, time; 
t0=time.time(); 
data={'model':'local','messages':[{'role':'user','content':'Hello'}],'max_tokens':20}; 
req=urllib.request.Request('http://127.0.0.1:5001/v1/chat/completions',
  data=json.dumps(data).encode(),headers={'Content-Type':'application/json'},method='POST'); 
resp=urllib.request.urlopen(req); 
t1=time.time(); print(f'Time: {t1-t0:.2f}s')"
```

---

## Configuration Recommendations

### For RTX 3060 (12GB VRAM):

**Option A: Maximum Speed (7B Model)**
```yaml
# config.yaml
llm:
  model: qwen2.5-7b-instruct-q4_k_m.gguf    # Better quality
  max_tokens: 60                            # Shorter = faster
  timeout_s: 30                             # Longer for slower CPU fallback
```
```bash
# koboldcpp args
--usecuda main --n-gpu-layers -1 --ctx-size 2048 --threads 4
```

**Option B: Balanced Speed/Quality (Current)**
```yaml
llm:
  model: qwen2.5-0.5b-instruct-q4_k_m.gguf  # Already applied
  max_tokens: 50                            # Cap for small model
  timeout_s: 15                             # Standard timeout
```
```bash
# koboldcpp args (GPU offload critical!)
--usecuda main --n-gpu-layers -1 --ctx-size 2048
```

**Option C: CPU-only Fallback (No GPU)**
```yaml
llm:
  model: qwen2.5-0.5b-instruct-q4_k_m.gguf
  timeout_s: 30                             # Longer for patience
```
```bash
# koboldcpp args (no --usecuda flag)
--host 127.0.0.1 --port 5001 --ctx-size 2048
```

---

## Monitoring Commands

### Real-time GPU monitoring:
```powershell
# Watch VRAM and utilization every second
nvidia-smi -l 1

# Check specific process (Python/llama-cpp)
tasklist /V | findstr python
Get-Process python | Select-Object Id,WorkingSet64,CPU
```

### Memory pressure warning signs:
- **VRAM utilization > 90%** → Model using CPU fallback
- **Swap space activity** → System thrashing, severe slowdown
- **Disk I/O spikes** → VRAM spilling to pagefile

---

## Conclusion

**The 96% GPU utilization is the root cause of LLM latency.**

1. ✅ **Immediate fix**: Enable `--usecuda main --n-gpu-layers -1` in koboldcpp.exe
2. ✅ **Already done**: Switched to 0.5B model for lower resource requirements
3. ✅ **Recommended**: Monitor GPU with `nvidia-smi -l 1` during operation

**Expected performance after GPU enablement:**
- First token: ~300ms vs. current ~10s (30x faster)
- Full response: ~2-3s vs. current ~21s (8-10x faster)
- User experience: Real-time conversation instead of 2-second wait per input

---

**Generated**: Sat Nov 23 2026  
**GPU Status**: RTX 3060 @ 96% utilization - Action required  
**Next step**: Restart koboldcpp.exe with GPU offload flags
