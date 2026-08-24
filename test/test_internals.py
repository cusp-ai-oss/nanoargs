# Copyright 2024-2026 Cusp AI
# SPDX-License-Identifier: Apache-2.0

"""Focused unit tests for internal helpers and behavioral contracts.

Pins exact error messages, edge cases, and branch coverage for internal
functions that are otherwise only tested indirectly through integration tests.
"""

import pathlib
import textwrap
from enum import Enum, IntEnum

import pytest

from nanoargs.cli import NanoArgs
from nanoargs.path import Path


def write(p: pathlib.Path, content: str) -> None:
    p.write_text(textwrap.dedent(content))


# === 1A: _coerce_default (cli.py) ===


class TestCoerceDefault:
    """Pin all branches of NanoArgs._coerce_default."""

    def test_model_dump_happy_path(self):
        class FakeModel:
            def model_dump(self) -> dict:
                return {"x": 1}

        assert NanoArgs._coerce_default(FakeModel()) == {"x": 1}

    def test_model_dump_non_json_value(self):
        class BadModel:
            def model_dump(self) -> set:
                return {1, 2}

        with pytest.raises(TypeError, match="model_dump\\(\\) returned non-JsonValue"):
            NanoArgs._coerce_default(BadModel())

    def test_json_value_passthrough(self):
        original = {"a": [1, 2]}
        result = NanoArgs._coerce_default(original)
        assert result == original
        assert result is not original  # deepcopy

    def test_pydantic_fields_happy_path(self):
        class FakeDataclass:
            __pydantic_fields__ = {"x": None, "y": None}
            x = 42
            y = "hello"

        result = NanoArgs._coerce_default(FakeDataclass())
        assert result == {"x": 42, "y": "hello"}

    def test_enum_value_happy_path(self):
        class Color(Enum):
            RED = "red"

        assert NanoArgs._coerce_default(Color.RED) == "red"

    def test_enum_mutable_value_is_copied(self):
        class Opts(Enum):
            DEFAULT = {"a": 1}

        result = NanoArgs._coerce_default(Opts.DEFAULT)
        assert result == {"a": 1}
        assert result is not Opts.DEFAULT.value  # deepcopy

    def test_enum_value_non_json_value(self):
        class Weird(Enum):
            W = object()

        with pytest.raises(TypeError, match="Enum .value is non-JsonValue"):
            NanoArgs._coerce_default(Weird.W)

    def test_int_enum_kept_as_member(self):
        # int/str based members are JsonValue already, so they pass through as members.
        class Speed(IntEnum):
            FAST = 1

        assert NanoArgs._coerce_default(Speed.FAST) is Speed.FAST

    def test_duck_typed_value_not_treated_as_enum(self):
        class Version:
            def __init__(self) -> None:
                self.value = [1, 2]

        with pytest.raises(TypeError, match="Cannot coerce Version"):
            NanoArgs._coerce_default(Version())

    def test_fallback_type_error(self):
        with pytest.raises(TypeError, match="Cannot coerce"):
            NanoArgs._coerce_default(object())


# === 1B: _type_repr helpers (cli.py) ===


class TestTypeReprHelpers:
    """Pin _type_repr dispatch and helper behavior."""

    def test_non_dict_returns_unknown(self):
        result = NanoArgs._type_repr("not_a_dict")
        assert result.plain == "Unknown"

    def test_type_array_no_items(self):
        result = NanoArgs._type_repr_type({"type": "array"})
        assert result is not None
        assert "Unknown" in result.plain

    def test_type_object_with_additional_properties(self):
        result = NanoArgs._type_repr_type(
            {"type": "object", "additionalProperties": {"type": "string"}}
        )
        assert result is not None
        assert "string" in result.plain
        assert "{*:" in result.plain

    def test_ref_format(self):
        result = NanoArgs._type_repr_ref({"$ref": "#/$defs/MyModel"})
        assert result is not None
        assert "@MyModel" in result.plain


# === 1C: Path edge cases (path.py) ===


class TestPathEdgeCases:
    """Pin edge-case behavior for Path operations."""

    def test_add_two_empty_paths(self):
        combined = Path(()) + Path(())
        assert combined.is_empty
        assert combined.chunks == ()

    def test_head_on_empty_path_raises(self):
        with pytest.raises(IndexError, match="Path is empty"):
            Path(()).head


# === 1D: Error message pinning ===


class TestErrorMessages:
    """Pin exact error message formats for internal validation helpers."""

    def test_resolve_index_out_of_bounds(self):
        from nanoargs.path import _resolve_index

        with pytest.raises(IndexError, match=r"out of bounds"):
            _resolve_index(5, 3)

    def test_require_sequence_message(self):
        from nanoargs.path import _require_sequence

        with pytest.raises(TypeError, match=r"can only be applied to arrays"):
            _require_sequence({"a": 1}, "Test")

    def test_autovivify_list_raises_property_error(self):
        from nanoargs.path import _autovivify

        with pytest.raises(TypeError, match="Property"):
            _autovivify([1, 2], [], [1, 2])

    def test_from_string_invalid_path_syntax(self):
        with pytest.raises(ValueError, match="Invalid path syntax"):
            Path.from_string("$.learning-rate")


# === 1E: resolve_value edge cases (loader.py) ===


class TestResolveValueEdgeCasesInternal:
    """Pin resolve_value behavior for borderline @ inputs."""

    def test_at_space_returns_raw(self):
        from nanoargs.loader import resolve_value

        assert resolve_value("@ ") == "@ "

    def test_double_at_alone(self):
        from nanoargs.loader import resolve_value

        assert resolve_value("@@") == "@"

    def test_at_multiple_spaces_returns_raw(self):
        from nanoargs.loader import resolve_value

        assert resolve_value("@  ") == "@  "


# === 1F: deep_merge with None ===


class TestDeepMergeNone:
    """Pin deep_merge behavior when base or incoming is None."""

    def test_merge_dict_with_none_incoming(self):
        from nanoargs.loader import deep_merge

        result = deep_merge({"a": 1}, None)
        assert result is None

    def test_merge_none_base_with_dict(self):
        from nanoargs.loader import deep_merge

        result = deep_merge(None, {"a": 1})
        assert result == {"a": 1}


# === 1G: is_json_value type guard ===


class TestIsJsonValue:
    """Pin is_json_value type guard behavior."""

    @pytest.mark.parametrize(
        "val",
        [
            {},
            [],
            (),
            "string",
            42,
            3.14,
            True,
            False,
            None,
        ],
    )
    def test_valid_types(self, val):
        from nanoargs.path import is_json_value

        assert is_json_value(val) is True

    @pytest.mark.parametrize(
        "val",
        [
            set(),
            b"bytes",
            object(),
            frozenset(),
        ],
    )
    def test_invalid_types(self, val):
        from nanoargs.path import is_json_value

        assert is_json_value(val) is False


# === 1H: parse_kv_specs edge cases ===


class TestParseKvSpecsEdge:
    """Pin parse_kv_specs behavior with multiple delimiters."""

    def test_multiple_colons_splits_on_first(self):
        from nanoargs.loader import parse_kv_specs

        result = parse_kv_specs(["$.a: value: with: colons"])
        assert result == [("$.a", "value: with: colons")]

    def test_multiple_equals_splits_on_first(self):
        from nanoargs.loader import parse_kv_specs

        result = parse_kv_specs(["$.a=val=ue=stuff"])
        assert result == [("$.a", "val=ue=stuff")]


# === 1I: resolve() vs parse() contract ===
