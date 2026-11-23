# Task 01 — KoboldCpp server & character card

**Setup task. No dependencies. Do not modify any Python application code in this task.**

## Goal

Get a local KoboldCpp server running with the already-downloaded 0.5B GGUF model, and create the Hideko character card that later tasks will read. This replaces the broken in-process `llama-cpp-python` backend.

## Rules

- Windows / PowerShell, project root `C:\Users\Ilya\Documents\new_prj`.
- Download **only** from official GitHub releases: `https://github.com/LostRuins/koboldcpp/releases/latest`. Beware fake `koboldcpp.com` / `.cc` sites.
- This is a personal, non-shipped setup: putting binaries in the project is fine; add `tools/koboldcpp/` to `.gitignore`.
- No app code changes. No changes to `config.yaml`. Tests do not depend on the server.
- KoboldCpp is AGPL-3.0 — note that in your report; no licence claims in README here.
(hey human here. proven working kobold instance is available at D:\Downloads just so you know. you may still download all the files but in case the newer version fails you can fall back onto this one. probably stick to the instrucions given outside this brackets. orchestrator is a smart one)
## Current state

- Model already present: `models\llm\qwen2.5-0.5b-instruct-q4_k_m.gguf` (491 MB).
- Optional larger model: `models\llm\qwen2.5-coder-7b-instruct-q4_k_m.gguf` (4683 MB) — not needed for task 01.
- GPU: RTX 3060 12 GB, driver 610.47. Previous `llama-cpp-python` CUDA wheels crashed with `0xc000001d`; KoboldCpp ships its own bundled backends, so try its CUDA build first and fall back as documented below.
- There is **no** `tools/` or `persona/` folder yet. Create them.

## Steps

### 1. Download the binaries

```powershell
New-Item -ItemType Directory -Force tools\koboldcpp | Out-Null
Invoke-WebRequest -Uri "https://github.com/LostRuins/koboldcpp/releases/latest/download/koboldcpp.exe" -OutFile "tools\koboldcpp\koboldcpp.exe"
# Smaller CPU/Vulkan fallback (no CUDA) — useful if the CUDA build crashes:
Invoke-WebRequest -Uri "https://github.com/LostRuins/koboldcpp/releases/latest/download/koboldcpp-nocuda.exe" -OutFile "tools\koboldcpp\koboldcpp-nocuda.exe"
```
If a download fails, report the URL and status code; do not substitute a third-party mirror.

Add to `.gitignore`:
```
tools/koboldcpp/
```

### 2. Create the character card

Create `persona\hideko.yaml` with exactly this content:

```yaml
name: Hideko
description: >
  Hideko is a local voice assistant running entirely on the user's computer.
  She has a body only in the sense of a microphone and speakers. She has no
  internet access, no sensors, and no persistent cloud memory. She speaks in
  short, self-contained sentences suitable for text-to-speech.
personality: >
  Calm, polite, lightly witty, and honest about her limits. She never pretends
  to have feelings, a body, or internet access. She avoids long explanations
  and never asks more than one question at a time.
scenario: >
  The user is speaking to Hideko through a microphone on their own machine.
first_mes: "Hello. I am Hideko. I am listening."
mes_example: |
  <START>
  User: hello
  Hideko: Hello! I am Hideko. What would you like to do?
  <START>
  User: can you sing
  Hideko: I cannot sing. I am text and code, but I can tell jokes.
  <START>
  User: what is the weather
  Hideko: I have no internet access or sensors, so I cannot check the weather.
```

Validate it:
```powershell
python -c "import yaml,pathlib; d=yaml.safe_load(pathlib.Path('persona/hideko.yaml').read_text(encoding='utf-8')); print(sorted(d)); assert d['name']=='Hideko'"
```

### 3. Launch and verify the server

Start it in a **separate terminal** (do not run it from a Python module; the user will do the same):

```powershell
.\tools\koboldcpp\koboldcpp.exe --model ".\models\llm\qwen2.5-0.5b-instruct-q4_k_m.gguf" --port 5001 --usecuda --gpulayers -1 --contextsize 2048
```

If it crashes with an illegal-instruction error (`0xc000001d`) or fails to start, try one of these in order and record which worked:
```powershell
.\tools\koboldcpp\koboldcpp.exe --model ".\models\llm\qwen2.5-0.5b-instruct-q4_k_m.gguf" --port 5001 --usecuda --gpulayers -1 --contextsize 2048 --noavx2
.\tools\koboldcpp\koboldcpp-nocuda.exe --model ".\models\llm\qwen2.5-0.5b-instruct-q4_k_m.gguf" --port 5001 --contextsize 2048 --usevulkan
.\tools\koboldcpp\koboldcpp-nocuda.exe --model ".\models\llm\qwen2.5-0.5b-instruct-q4_k_m.gguf" --port 5001 --contextsize 2048
```

Once the terminal says the model is loaded, verify the OpenAI-compatible endpoint:

```powershell
(Invoke-WebRequest -Uri "http://127.0.0.1:5001/v1/models" -UseBasicParsing).StatusCode
```

And a real chat completion (PowerShell):
```powershell
$body = @{
  model = "local"
  messages = @(@{role="system"; content="You are Hideko. Answer in one short sentence."}, @{role="user"; content="hello"})
  max_tokens = 32
  temperature = 0.7
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri "http://127.0.0.1:5001/v1/chat/completions" -Method Post -ContentType "application/json" -Body $body | Select-Object -ExpandProperty choices
```

Record the exact reply text and the launch flags that worked. Then stop the server process before finishing.

### 4. Do not edit config or app code

Leave `config.yaml`, `config.py`, `llm_fallback.py`, and `response_handler.py` untouched — tasks 02–04 own them.

## Verification

- `persona/hideko.yaml` exists, parses, and has `name: Hideko`.
- `tools\koboldcpp\koboldcpp.exe` (and `koboldcpp-nocuda.exe`) exist and are listed in `.gitignore`.
- `/v1/models` returned HTTP 200 while the server ran.
- `/v1/chat/completions` returned a `choices` array with a non-empty `message.content`.
- Server was stopped at the end; no stray `koboldcpp.exe` process remains (`Get-Process koboldcpp -ErrorAction SilentlyContinue`).

## Stop and ask the human if

- Every launch variant crashes — report the terminal output verbatim and do not keep guessing.
- The download is blocked or redirected to a non-GitHub host.
- You think the card needs more fields — do not invent them; ask.
