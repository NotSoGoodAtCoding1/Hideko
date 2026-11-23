#!/usr/bin/env python3
"""Validate response data files for the voice assistant project.

This script validates triggers.yaml and fallbacks.yaml according to strict rules.
Usage: python validate_responses.py [--triggers PATH] [--fallbacks PATH]
"""

import argparse
import re
import sys
from pathlib import Path

import yaml


def load_yaml_file(path: Path) -> dict:
    """Load and parse a YAML file safely."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a mapping, got {type(data).__name__}")
    return data


def validate_name(name: str) -> bool:
    """Validate trigger name matches ^[a-z][a-z0-9_]*$."""
    return bool(re.match(r"^[a-z][a-z0-9_]*$", name))


def validate_priority(priority) -> tuple[bool, str]:
    """Validate priority is an int in 0..1000 (not a bool)."""
    if isinstance(priority, bool):
        return False, "priority must not be a boolean"
    if not isinstance(priority, int):
        return False, "priority must be an integer"
    if priority < 0 or priority > 1000:
        return False, "priority must be between 0 and 1000"
    return True, ""


def validate_pattern(pattern: str) -> tuple[bool, str]:
    """Validate pattern is non-empty lowercase string matching ^[a-z0-9 ]+$."""
    stripped = pattern.strip()
    if not stripped:
        return False, "pattern must not be empty or whitespace only"
    if not re.match(r"^[a-z0-9 ]+$", stripped):
        return False, f"pattern contains invalid characters: {pattern!r}"
    return True, ""


def validate_response(response: str) -> tuple[bool, str]:
    """Validate response string rules."""
    if not isinstance(response, str):
        return False, "response must be a string"
    if len(response) < 1 or len(response) > 160:
        return False, f"response length must be 1-160 chars, got {len(response)}"
    if "*" in response or "_" in response or "#" in response or "`" in response:
        return False, "response contains forbidden characters: * _ # `"
    if "http" in response.lower():
        return False, "response contains http URL"
    if "{" in response or "}" in response:
        return False, "response contains curly braces"
    return True, ""


def validate_triggers_file(path: Path) -> list[str]:
    """Validate triggers.yaml and return list of failure messages."""
    failures = []
    data = load_yaml_file(path)

    if data.get("version") != 1:
        failures.append(f"{path}: version must be 1, got {data.get('version')}")
        return failures

    triggers = data.get("triggers", [])
    if not isinstance(triggers, list) or len(triggers) == 0:
        failures.append(f"{path}: triggers must be a non-empty list")
        return failures

    seen_names = set()
    seen_patterns = set()
    all_patterns = []
    trigger_priorities = {}

    for i, trigger in enumerate(triggers):
        line_num = i + 2  # Approximate line number (after version and triggers keys)

        if not isinstance(trigger, dict):
            failures.append(f"{path}:{line_num}: each trigger must be a mapping")
            continue

        # Check required keys exist
        required_keys = {"name", "priority", "patterns", "responses"}
        actual_keys = set(trigger.keys())
        missing_keys = required_keys - actual_keys
        extra_keys = actual_keys - required_keys - {"should_exit", "llm_only"}

        if missing_keys:
            failures.append(f"{path}:{line_num}: missing keys: {missing_keys}")
        if extra_keys:
            failures.append(f"{path}:{line_num}: unexpected keys: {extra_keys}")

        # Validate llm_only is a boolean if present
        if "llm_only" in trigger and not isinstance(trigger["llm_only"], bool):
            failures.append(f"{path}:{line_num}: llm_only must be a boolean")

        # Validate name
        name = trigger.get("name")
        if not validate_name(name):
            failures.append(f"{path}:{line_num}: invalid name {name!r}")

        # Check uniqueness
        if name in seen_names:
            failures.append(f"{path}:{line_num}: duplicate name {name!r}")
        seen_names.add(name)

        # Validate priority
        priority = trigger.get("priority")
        valid, msg = validate_priority(priority)
        if not valid:
            failures.append(f"{path}:{line_num}: {msg}")
        else:
            trigger_priorities[name] = priority

        # Validate patterns
        patterns = trigger.get("patterns", [])
        if not isinstance(patterns, list) or len(patterns) == 0:
            failures.append(f"{path}:{line_num}: patterns must be a non-empty list")
        else:
            for j, pattern in enumerate(patterns):
                valid, msg = validate_pattern(pattern)
                if not valid:
                    failures.append(f"{path}:{line_num}.patterns[{j}]: {msg}")
                else:
                    stripped = pattern.strip()
                    if stripped in seen_patterns:
                        failures.append(f"{path}:{line_num}.patterns[{j}]: duplicate pattern {stripped!r}")
                    seen_patterns.add(stripped)
                    all_patterns.append((name, stripped))

        # Validate responses
        responses = trigger.get("responses", [])
        if not isinstance(responses, list) or len(responses) == 0:
            failures.append(f"{path}:{line_num}: responses must be a non-empty list")
        else:
            for k, response in enumerate(responses):
                valid, msg = validate_response(response)
                if not valid:
                    failures.append(f"{path}:{line_num}.responses[{k}]: {msg}")

    # Check should_exit is only true for goodbye
    exit_triggers = [t["name"] for t in triggers if isinstance(t.get("should_exit"), bool) and t.get("should_exit")]
    if "goodbye" not in exit_triggers:
        failures.append(f"{path}: goodbye must have should_exit: true")
    if len(exit_triggers) > 1:
        failures.append(f"{path}: only goodbye should have should_exit: true, got {exit_triggers}")

    return failures


def check_substring_warnings(path: Path) -> list[str]:
    """Check for substring pattern warnings (same trigger, one pattern is substring of another with same priority)."""
    warnings = []
    data = load_yaml_file(path)
    triggers = data.get("triggers", [])

    for trigger in triggers:
        name = trigger.get("name")
        priority = trigger.get("priority")
        patterns = trigger.get("patterns", [])

        if not name or not isinstance(priority, int) or isinstance(priority, bool):
            continue

        # Check within this trigger's patterns
        for i, p1 in enumerate(patterns):
            if not isinstance(p1, str):
                continue
            stripped_p1 = p1.strip()
            for j, p2 in enumerate(patterns):
                if i >= j:
                    continue
                if not isinstance(p2, str):
                    continue
                stripped_p2 = p2.strip()
                if stripped_p1 != stripped_p2 and (stripped_p1 in stripped_p2 or stripped_p2 in stripped_p1):
                    warnings.append(
                        f"WARNING: {name} has patterns {stripped_p1!r} and {stripped_p2!r}, one is substring of the other, priority {priority}"
                    )

    return warnings


def validate_fallbacks_file(path: Path) -> list[str]:
    """Validate fallbacks.yaml and return list of failure messages."""
    failures = []
    data = load_yaml_file(path)

    if data.get("version") != 1:
        failures.append(f"{path}: version must be 1, got {data.get('version')}")
        return failures

    fallbacks = data.get("fallbacks", [])
    if not isinstance(fallbacks, list):
        failures.append(f"{path}: fallbacks must be a list")
        return failures

    if len(fallbacks) < 5 or len(fallbacks) > 20:
        failures.append(f"{path}: fallbacks must have 5-20 entries, got {len(fallbacks)}")

    for i, fb in enumerate(fallbacks):
        line_num = i + 2
        if not isinstance(fb, str):
            failures.append(f"{path}:{line_num}: each fallback must be a string")
            continue
        valid, msg = validate_response(fb)
        if not valid:
            failures.append(f"{path}:{line_num}: {msg}")

    return failures


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate response data files")
    parser.add_argument("--triggers", type=str, default=None, help="Path to triggers.yaml")
    parser.add_argument("--fallbacks", type=str, default=None, help="Path to fallbacks.yaml")

    args = parser.parse_args()

    # Resolve paths relative to project root if not absolute
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    triggers_path = Path(args.triggers) if args.triggers else project_root / "responses" / "triggers.yaml"
    fallbacks_path = Path(args.fallbacks) if args.fallbacks else project_root / "responses" / "fallbacks.yaml"

    all_failures = []
    all_warnings = []

    # Validate triggers
    if not triggers_path.exists():
        print(f"FAIL {triggers_path}: file not found")
        return 1
    failures = validate_triggers_file(triggers_path)
    all_failures.extend(failures)
    warnings = check_substring_warnings(triggers_path)
    all_warnings.extend(warnings)

    # Validate fallbacks
    if not fallbacks_path.exists():
        print(f"FAIL {fallbacks_path}: file not found")
        return 1
    failures = validate_fallbacks_file(fallbacks_path)
    all_failures.extend(failures)

    # Print warnings first (do not fail on them)
    for warning in all_warnings:
        print(warning)

    # Print failures
    for failure in all_failures:
        print(f"FAIL {failure}")

    if all_failures:
        return 1

    # Print summary with real counts
    data = load_yaml_file(triggers_path)
    triggers = data.get("triggers", [])
    total_patterns = sum(len(t.get("patterns", [])) for t in triggers)
    total_responses = sum(len(t.get("responses", [])) for t in triggers)
    fallback_data = load_yaml_file(fallbacks_path)
    total_fallbacks = len(fallback_data.get("fallbacks", []))

    print(f"OK: {len(triggers)} triggers, {total_patterns} patterns, {total_responses} responses, {total_fallbacks} fallbacks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
