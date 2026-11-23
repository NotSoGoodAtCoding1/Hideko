# Task 09 — Response data files & validator

**Goal (one sentence).** Create two YAML data files and one validator script. **No application logic** — only data plus a validator.

**You only need this file.** Everything is inlined. Do **not** open `README.md`, `plan.md`, or any other task file.

| | |
|---|---|
| Files you touch | `responses/triggers.yaml`, `responses/fallbacks.yaml`, `scripts/validate_responses.py` — nothing else |
| Depends on | task 01 |
| Blocks | task 10 |
| Time budget | ~40 min |

Also delete `responses/.gitkeep` if it still exists.

---

## 1. `responses/triggers.yaml` — schema

```yaml
version: 1
triggers:
  - name: greeting              # unique, lowercase, [a-z0-9_]
    priority: 100               # higher wins when several triggers match
    should_exit: false          # true = say the line, then stop the program
    patterns:                   # lowercase literal words/phrases. NO regex. NO punctuation.
      - hello
      - hi
      - good morning
    responses:                  # one picked at random, never the same twice in a row
      - "Hello! I am Hideko."
      - "Hi there. What should we talk about?"
```

**Hard data rules**

1. `patterns` are literal lowercase strings. The matcher wraps them in `\b` word boundaries and `re.escape`s them: `hi` will not match "this"; `hello` will match "hello there"; multi-word patterns match as a phrase.
2. No punctuation, no regex metacharacters (`.*+?[](){}|^$\`), no emoji in `patterns`.
3. Each `responses` entry is a complete spoken sentence: 1–2 short sentences, **max ~140 characters**. No markdown, asterisks, emoji, or URLs. Write numbers as words if pronunciation matters. Prefer "I am" over "I'm".
4. `name` values unique.
5. `priority`: greeting/exit = 100, direct commands = 80, small talk = 50, weak/ambiguous = 20.
6. **At least 2 responses per trigger, at least 12 triggers total.**

## 2. Required triggers (write all 15; you may add more, not remove)

| name | priority | patterns (minimum) | intent |
|------|----------|--------------------|--------|
| `greeting` | 100 | hello, hi, hey, good morning, good evening, yo | greet back |
| `how_are_you` | 60 | how are you, how is it going, how are you doing | cheerful, brief |
| `name` | 70 | what is your name, who are you, what are you | "I am Hideko, a local voice assistant" |
| `sing` | 80 | sing, sing a song, can you sing | **decline playfully** — singing is out of scope; never output lyrics |
| `dance` | 80 | dance, can you dance, do a dance | describe a silly dance, no video |
| `joke` | 80 | joke, tell me a joke, say something funny | 2–3 original one-liners, no copyrighted material |
| `thank_you` | 60 | thank you, thanks, appreciate it | warm, short |
| `goodbye` | 100 | goodbye, bye, see you, good night, i am done | `should_exit: true` — **this is the only exit trigger** |
| `stop` | 100 | stop, be quiet, shut up, silence | acknowledge and go quiet for one turn (**no exit**) |
| `help` | 70 | help, what can you do, commands, what do you do | list 4–5 example phrases |
| `compliment` | 50 | you are great, you are cute, good job, i like you | shy thanks |
| `insult` | 40 | you are stupid, you are dumb, i hate you | unbothered, deflecting, never rude back |
| `weather` | 30 | weather, is it raining, temperature outside | admit no internet access |
| `real` | 50 | are you real, are you alive, are you a robot, are you human | honest: local program, no cloud |
| `meaning_of_life` | 20 | meaning of life, why are we here | playful non-answer |

Tone: friendly, slightly deadpan, never mean. Never claims feelings or a body. Do not promise capabilities the MVP lacks (no singing, no internet, no memory between sessions). `stop` deliberately does not exit — do not invent extra behaviour.

## 3. `responses/fallbacks.yaml` — schema

```yaml
version: 1
fallbacks:
  - "I did not catch that. Try saying hello."
  - "I only know a few phrases so far. Say help to hear them."
```

- 8–10 entries. Each steers the user toward a working phrase (`hello`, `help`, `joke`, `goodbye`).
- Never blame the user. Never invent knowledge ("let me look that up" is a lie — there is no internet).

## 4. `scripts/validate_responses.py`

Usage: `python validate_responses.py [--triggers PATH] [--fallbacks PATH]` (defaults point at the two YAML files, resolved relative to the project root, not CWD).

For each failure print `FAIL <file>:<line-ish> <message>` and exit 1. Checks:

1. File parses with `yaml.safe_load` and is a mapping with `version: 1`.
2. `triggers` is a non-empty list; each entry has **exactly** the keys `name`, `priority`, `patterns`, `responses` and optionally `should_exit`.
3. `name` matches `^[a-z][a-z0-9_]*$`, unique.
4. `priority` is an `int` in `0..1000` (bool is an int subclass — reject it).
5. `patterns` is a non-empty list of non-empty lowercase strings; each matches `^[a-z0-9 ]+$`. **Strip before testing** so a trailing space fails.
6. No pattern duplicated across the whole file.
7. `responses` is a non-empty list of strings, each 1–160 chars, no `*`, `_`, `#`, `` ` ``, `http`, `{`, `}`.
8. `fallbacks` is a list of 5–20 strings with the same character rules.
9. Print a summary: `OK: 15 triggers, 47 patterns, 38 responses, 9 fallbacks` (with real counts).
10. **Warn** (do not fail) when two triggers share a pattern where one is a substring of another with the same priority, e.g. `sing` vs `sing a song`.

Exit 0 only with zero failures. Use `argparse`; `Path(__file__).resolve().parent.parent` for default paths.

## 5. YAML pitfalls that will bite you

- A response containing `:` **must be quoted** (`"I have one rule: be kind."`). Unquoted `:` starts a mapping.
- Always use **double quotes**. `'It's fine.'` breaks YAML.
- YAML 1.1 turns `yes`/`no` into booleans. Quote a response beginning with "No".
- Trailing spaces in patterns make them unmatchable — the validator strips before checking.

## 6. Rules checklist

- [ ] Both YAML files parse with `yaml.safe_load` as UTF-8
- [ ] Validator exits 0, prints the summary with real counts
- [ ] All 15 required triggers exist with the required patterns
- [ ] `goodbye` is the only `should_exit: true` trigger
- [ ] `sing` contains no lyrics
- [ ] No response exceeds 160 characters
- [ ] Every pattern is lowercase ASCII, no punctuation, no trailing space
- [ ] Type hints + docstrings on all public functions
- [ ] `print()` only inside `__main__` / validator script

## 7. Do NOT

- Do not write regex in `patterns`, or add a `regex:`/`match:` key.
- Do not put logic or templates in YAML.
- Do not include copyrighted lyrics, known comedians' jokes, or brand names.
- Do not create `greetings.txt` / `commands.txt` / `fallbacks.txt`.
- Do not write any matching code in this task (that is task 10).

## 8. Verify — run and paste output

```powershell
python scripts\validate_responses.py
```
Expected: `OK: 15 triggers, ...` and exit 0.

```powershell
python -c "import yaml; d=yaml.safe_load(open('responses/triggers.yaml',encoding='utf-8')); print(len(d['triggers'])); print([t['name'] for t in d['triggers'] if t.get('should_exit')])"
```
Expected: `15` (or more) and `['goodbye']`.

```powershell
python -m pytest -q
```
Expected: still passes.

## 9. Report

Report: files changed, pasted verification output, anything unfinished. Do not start task 10.
