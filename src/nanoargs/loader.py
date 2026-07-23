# Copyright 2024-2026 Cusp AI
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import json
import threading
import warnings
from collections.abc import Iterable, Sequence
from pathlib import Path as FSPath
from typing import overload

import yaml
from yaml import ScalarNode, SequenceNode

from nanoargs.path import JsonValue, Path, is_json_value


def _validate_json_result(result: object) -> JsonValue:
    """Validate and narrow a parsed JSON result to JsonValue."""
    if is_json_value(result):
        return result
    raise TypeError(f"Unexpected JSON type: {type(result).__name__}")


class _LoadingFiles(threading.local):
    """Thread-local storage for tracking files being loaded (circular import detection)."""

    stack: set[str]

    def __init__(self) -> None:
        super().__init__()
        self.stack = set()


_loading_files = _LoadingFiles()


def parse_kv_specs(raw: Iterable[str]) -> list[tuple[str, str]]:
    """Parse key=value or key: value specs into (path, value) pairs."""
    pairs: list[tuple[str, str]] = []
    for item in raw:
        if "=" in item:
            path_spec, val = item.split("=", 1)
            path_spec = path_spec.strip()
            val = val.strip()
        elif ":" in item:
            path_spec, val = item.split(":", 1)
            path_spec = path_spec.strip()
            val = val.strip()
        else:
            raise ValueError(
                f"Expected <path>=<value> or <path>: <value> syntax, got: {item!r}"
            )
        if not path_spec:
            raise ValueError(f"Empty path in spec: {item!r}")
        pairs.append((path_spec, val))
    return pairs


def _resolve_file_ref(file_ref: str, base_dir: FSPath | None) -> JsonValue:
    """Resolve an @file reference to its parsed content."""
    file_path = FSPath(file_ref)
    if base_dir is not None and not file_path.is_absolute():
        file_path = (base_dir / file_path).resolve()
    if file_path.is_dir():
        raise FileNotFoundError(
            f"@ reference points to a directory, not a file: {file_path}"
        )
    if not file_path.exists():
        raise FileNotFoundError(f"@ reference file not found: {file_path}")
    suffix: str = file_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        with open(file_path, "r") as fh:
            result: JsonValue = yaml.load(fh, Loader=Loader)
            return result
    if suffix == ".json":
        text = file_path.read_text()
        if not text.strip():
            return None
        return _validate_json_result(json.loads(text))
    # Unknown extension: try JSON, fall back to raw text (not YAML)
    text = file_path.read_text()
    try:
        return _validate_json_result(json.loads(text))
    except json.JSONDecodeError:
        return text


def _resolve_literal(raw: str) -> JsonValue:
    """Parse a literal value as JSON, then structured YAML, then raw string."""
    try:
        return _validate_json_result(json.loads(raw))
    except json.JSONDecodeError:
        pass
    # Only try YAML for explicit structures ({...} or [...]).
    # YAML's scalar coercion is too aggressive for CLI overrides.
    stripped = raw.strip()
    if stripped.startswith(("{", "[")):
        try:
            yaml_result: JsonValue = yaml.safe_load(raw)
        except yaml.YAMLError:
            return raw
        if isinstance(yaml_result, (dict, list)):
            return yaml_result
    return raw


def resolve_value(raw: str, *, base_dir: FSPath | None = None) -> JsonValue:
    """Resolve a raw override string to JsonValue, handling @file refs, JSON, and YAML."""
    if raw.startswith("@@"):
        return raw[1:]
    if raw.startswith("@") and len(raw) > 1:
        file_ref = raw[1:].strip()
        if not file_ref:
            return raw
        return _resolve_file_ref(file_ref, base_dir)
    return _resolve_literal(raw)


def override_constructor(loader: yaml.Loader, node: SequenceNode) -> JsonValue:
    """YAML constructor for !override. Applies path-based overrides to a target."""
    value: list[JsonValue] = loader.construct_sequence(node, deep=True)

    base_dir = FSPath(str(getattr(loader, "name", "."))).parent.resolve()

    # Accept either [target, overrides] or [[target, overrides]] forms
    if len(value) == 1 and isinstance(value[0], list) and len(value[0]) == 2:
        value = value[0]
    if len(value) != 2:
        raise ValueError(
            "!override expects two elements: target and list of override specs"
        )
    target: JsonValue = value[0]
    # Initialize None target (e.g. from empty file) to empty dict
    if target is None:
        target = {}
    override_specs_raw = value[1]
    if not isinstance(override_specs_raw, list):
        raise ValueError("!override specs must be a list")

    override_specs: list[str] = [str(s) for s in override_specs_raw]

    for path_spec, raw_val in parse_kv_specs(override_specs):
        target = Path.from_string(path_spec).modify(
            target, resolve_value(raw_val, base_dir=base_dir)
        )
    return target


@overload
def deep_merge(
    base: dict[str, JsonValue], incoming: dict[str, JsonValue]
) -> dict[str, JsonValue]: ...


@overload
def deep_merge(base: JsonValue, incoming: JsonValue) -> JsonValue: ...


def deep_merge(base: JsonValue, incoming: JsonValue) -> JsonValue:
    """Deep merge incoming into base. Dict keys are merged recursively; other types replaced."""
    if isinstance(base, dict) and isinstance(incoming, dict):
        result = copy.deepcopy(base)
        for key, value in incoming.items():
            existing = result.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                result[key] = deep_merge(existing, value)
            else:
                result[key] = copy.deepcopy(value)
        return result
    return copy.deepcopy(incoming)


def import_constructor(loader: yaml.Loader, node: yaml.Node) -> JsonValue:
    """YAML constructor for !import. Loads a single file, path relative to the importing file.

    Accepts a scalar path (`!import file.yaml`) or a one-element sequence
    (`!import [file.yaml]`). Combining multiple files is `!merge`'s job.
    """
    import_path: JsonValue
    if isinstance(node, SequenceNode):
        paths: list[JsonValue] = loader.construct_sequence(node)
        if len(paths) != 1:
            raise ValueError(
                "!import takes a single path; combine files with !merge and one !import per file"
            )
        import_path = paths[0]
    elif isinstance(node, ScalarNode):
        import_path = loader.construct_scalar(node)
    else:
        raise ValueError("!import takes a path or a one-element sequence")
    if not isinstance(import_path, str) or not import_path:
        raise ValueError("Import path must be a non-empty string")

    # Determine base directory of the referring file (if available); fall back to CWD.
    base_dir = FSPath(str(getattr(loader, "name", "."))).parent.resolve()

    stack = _loading_files.stack
    resolved = (base_dir / import_path).resolve()
    resolved_str = str(resolved)
    if resolved_str in stack:
        raise ValueError(f"Circular import detected: {resolved_str}")
    stack.add(resolved_str)
    try:
        with open(resolved, "r") as f:
            # Load with the referring loader's class so subclass tags
            # remain available inside imported files.
            data: JsonValue = yaml.load(f, Loader=type(loader))
    finally:
        stack.discard(resolved_str)
    return data


def merge_constructor(loader: yaml.Loader, node: SequenceNode) -> JsonValue:
    """YAML constructor for !merge. Deep-merges a sequence of mappings left to right."""
    entries: list[JsonValue] = loader.construct_sequence(node, deep=True)

    result: JsonValue = None
    for index, entry in enumerate(entries):
        # Tolerate None entries (e.g. an !import of an empty file).
        if entry is None:
            continue
        if not isinstance(entry, dict):
            raise ValueError(
                f"!merge entry {index} must be a mapping, got {type(entry).__name__}"
            )
        result = entry if result is None else deep_merge(result, entry)
    return result


class NanoArgsLoader(yaml.SafeLoader):
    """YAML SafeLoader with !import, !merge, and !override tag support."""


NanoArgsLoader.add_constructor("!import", import_constructor)
NanoArgsLoader.add_constructor("!merge", merge_constructor)
NanoArgsLoader.add_constructor("!override", override_constructor)


Loader = NanoArgsLoader


def load_yaml_file(path: str | FSPath) -> JsonValue:
    """Load a YAML/JSON config file using the NanoArgs loader.

    Pass '-' as path to read from stdin.
    """
    if str(path) == "-":
        import sys

        result: JsonValue = yaml.load(sys.stdin.read(), Loader=Loader)
        return result
    with open(path, "r") as f:
        result = yaml.load(f, Loader=Loader)
        return result


def apply_overrides(data: JsonValue, override_specs: Sequence[str]) -> JsonValue:
    """Apply path=value override specs to config data, returning modified data."""
    for path_spec, raw_val in parse_kv_specs(override_specs):
        value = resolve_value(raw_val)
        path = Path.from_string(path_spec)
        data = path.modify(data, value)
    return data


def load_and_merge(
    config_files: Sequence[str],
    defaults: dict[str, JsonValue],
    override_specs: Sequence[str],
) -> JsonValue:
    """Load config files, merge with defaults, apply overrides. Returns raw data."""
    data: JsonValue = defaults

    for cfg_file in config_files:
        loaded = load_yaml_file(cfg_file)
        if loaded is None:
            continue
        if isinstance(data, dict) and isinstance(loaded, dict):
            data = deep_merge(data, loaded)
        else:
            if isinstance(data, dict) and not isinstance(loaded, dict):
                warnings.warn(
                    f"Config file {cfg_file!r} contains a scalar/list value that "
                    f"replaces the previously merged dict config. "
                    f"This is usually unintentional.",
                    stacklevel=4,
                )
            data = copy.deepcopy(loaded)

    if override_specs:
        data = copy.deepcopy(data)
        data = apply_overrides(data, override_specs)

    return data
