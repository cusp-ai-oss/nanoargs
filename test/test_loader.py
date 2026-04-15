import pathlib
import textwrap

import pytest
import yaml

from nanoargs.loader import Loader


def write(p: pathlib.Path, content: str):
    p.write_text(textwrap.dedent(content))


def test_import_merge_and_relative(tmp_path: pathlib.Path):
    """Test basic import functionality with file merging and relative paths."""
    # relative layout
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    write(a, "x: 1\ny: 2\nz: 3")
    write(b, "y: 3\nz: 4")
    root = tmp_path / "root.yaml"
    write(root, f"!import\n  - {a.name}\n  - {b.name}")
    with open(root, "r") as f:
        data = yaml.load(f, Loader=Loader)
    assert data == {"x": 1, "y": 3, "z": 4}

    # relative path resolution
    sub = tmp_path / "sub"
    sub.mkdir()
    write(sub / "values.yaml", "a: 1\nb: 2")
    rel = tmp_path / "config.yaml"
    write(rel, "!import\n  - sub/values.yaml\n")
    with open(rel, "r") as f:
        rel_data = yaml.load(f, Loader=Loader)
    assert rel_data == {"a": 1, "b": 2}


def test_override_constructor(tmp_path: pathlib.Path):
    root = tmp_path / "root.yaml"
    write(root, '!override\n  -\n    - {a: 1, b: 2}\n    - [ "$.a=3", "$.b=4" ]')
    with open(root, "r") as f:
        data = yaml.load(f, Loader=Loader)
    assert data == {"a": 3, "b": 4}


def test_simple_import_functionality(tmp_path: pathlib.Path):
    """Test simple import functionality."""
    # Create a simple import test that just imports without adding more content
    simple_file = tmp_path / "simple.yaml"
    write(simple_file, "simple_val: 123\nother_val: 456")

    root = tmp_path / "root.yaml"
    write(root, f"!import\n  - {simple_file.name}")

    with open(root, "r") as f:
        data = yaml.load(f, Loader=Loader)

    # Should have imported values
    assert data == {"simple_val": 123, "other_val": 456}


def test_import_multiple_files_basic(tmp_path: pathlib.Path):
    """Test importing multiple files with basic merging."""
    write(tmp_path / "base.yaml", "a: 1\nb: 2\nc: 0")  # Include 'c' in base
    write(tmp_path / "override.yaml", "b: 20\nc: 3")  # Override 'b' and 'c'

    root = tmp_path / "root.yaml"
    write(
        root,
        f"!import\n  - {(tmp_path / 'base.yaml').name}\n  - {(tmp_path / 'override.yaml').name}",
    )

    with open(root, "r") as f:
        data = yaml.load(f, Loader=Loader)

    assert data == {"a": 1, "b": 20, "c": 3}


def test_import_nested_structure(tmp_path: pathlib.Path):
    """Test importing files with nested data structures."""
    write(
        tmp_path / "config.yaml",
        """
database:
  host: localhost
  port: 5432
settings:
  debug: true
  timeout: 30
""",
    )

    root = tmp_path / "main.yaml"
    write(root, f"!import\n  - {(tmp_path / 'config.yaml').name}")

    with open(root, "r") as f:
        data = yaml.load(f, Loader=Loader)

    # Verify nested structure is preserved
    assert data["database"]["host"] == "localhost"
    assert data["database"]["port"] == 5432
    assert data["settings"]["debug"] is True
    assert data["settings"]["timeout"] == 30


def test_import_nonexistent_file(tmp_path: pathlib.Path):
    """Test that importing nonexistent files raises appropriate errors."""
    root = tmp_path / "root.yaml"
    write(root, "!import\n  - nonexistent.yaml")

    with pytest.raises(FileNotFoundError):
        with open(root, "r") as f:
            yaml.load(f, Loader=Loader)


def test_override_constructor_variations(tmp_path: pathlib.Path):
    """Test various forms of the override constructor."""
    # Test single-level override format
    root1 = tmp_path / "override1.yaml"
    write(
        root1,
        """!override
  - {x: 1, y: 2}
  - ["$.x=10", "$.y=20"]
""",
    )

    with open(root1, "r") as f:
        data1 = yaml.load(f, Loader=Loader)
    assert data1 == {"x": 10, "y": 20}

    # Test nested list format (as in original test)
    root2 = tmp_path / "override2.yaml"
    write(
        root2,
        """!override
  -
    - {x: 1, y: 2}
    - ["$.x=100", "$.y=200"]
""",
    )

    with open(root2, "r") as f:
        data2 = yaml.load(f, Loader=Loader)
    assert data2 == {"x": 100, "y": 200}


def test_override_constructor_complex_paths(tmp_path: pathlib.Path):
    """Test override constructor with complex JSONPath expressions."""
    root = tmp_path / "complex_override.yaml"
    write(
        root,
        """!override
  -
    nested:
      items: [1, 2, 3]
      config:
        enabled: false
        values: {a: 10, b: 20}
  -
    - "$.nested.items[1]=99"
    - "$.nested.config.enabled=true"
    - "$.nested.config.values.a=50"
""",
    )

    with open(root, "r") as f:
        data = yaml.load(f, Loader=Loader)

    expected = {
        "nested": {
            "items": [1, 99, 3],
            "config": {"enabled": True, "values": {"a": 50, "b": 20}},
        }
    }
    assert data == expected


def test_override_constructor_error_cases(tmp_path: pathlib.Path):
    """Test error cases in override constructor."""
    # Missing equals sign in override spec
    root1 = tmp_path / "bad_override1.yaml"
    write(
        root1,
        """!override
  - {a: 1}
  - ["$.a-5"]  # dash instead of equals - should fail
""",
    )

    with pytest.raises(
        ValueError, match="Expected <path>=<value> or <path>: <value> syntax,"
    ):
        with open(root1, "r") as f:
            yaml.load(f, Loader=Loader)

    # Wrong number of elements
    root2 = tmp_path / "bad_override2.yaml"
    write(
        root2,
        """!override
  - ["just_one_element"]
""",
    )

    with pytest.raises(ValueError, match="expects two elements"):
        with open(root2, "r") as f:
            yaml.load(f, Loader=Loader)


def test_loader_file_name_attribute(tmp_path: pathlib.Path):
    """Test that loader correctly sets and uses the name attribute for relative imports."""
    sub_dir = tmp_path / "configs"
    sub_dir.mkdir()

    write(sub_dir / "values.yaml", "value: 42")

    root = tmp_path / "main.yaml"
    write(root, "!import\n  - configs/values.yaml")

    # Manually test the Loader name attribute usage
    with open(root, "r") as f:
        loader = Loader(f)
        loader.name = str(root)
        data = loader.get_single_data()

    assert data == {"value": 42}


def test_import_with_relative_paths(tmp_path: pathlib.Path):
    """Test that imports work with relative paths."""
    # Test relative path from subdirectory
    sub = tmp_path / "sub"
    sub.mkdir()
    write(sub / "data.yaml", "data_value: 123")

    # Config in subdirectory importing relatively
    write(sub / "config.yaml", "!import\n  - data.yaml")

    # Load from the subdirectory config
    with open(sub / "config.yaml", "r") as f:
        data = yaml.load(f, Loader=Loader)

    assert data == {"data_value": 123}


def test_parse_kv_specs_whitespace_stripping():
    """Test that parse_kv_specs strips whitespace for both = and : separators."""
    from nanoargs.loader import parse_kv_specs

    result = parse_kv_specs(["$.a = 5"])
    assert result == [("$.a", "5")]
    result2 = parse_kv_specs(["$.b : 10"])
    assert result2 == [("$.b", "10")]


def test_circular_import_raises_error(tmp_path: pathlib.Path):
    """Test that circular imports raise a clear error."""
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    write(a, f"!import\n  - {b.name}")
    write(b, f"!import\n  - {a.name}")
    with pytest.raises(ValueError, match="[Cc]ircular"):
        with open(a, "r") as f:
            yaml.load(f, Loader=Loader)


def test_import_with_mixed_data_types(tmp_path: pathlib.Path):
    """Test importing files with various YAML data types."""
    write(
        tmp_path / "types.yaml",
        """
string_val: "hello world"
integer_val: 42
float_val: 3.14159
boolean_val: true
null_val: null
list_val: [1, 2, 3, "four", 5.0]
dict_val:
  nested_string: "nested"
  nested_int: 100
  nested_list: ["a", "b", "c"]
""",
    )

    root = tmp_path / "main.yaml"
    write(root, f"!import\n  - {(tmp_path / 'types.yaml').name}")

    with open(root, "r") as f:
        data = yaml.load(f, Loader=Loader)

    # Verify all data types are preserved
    assert data["string_val"] == "hello world"
    assert data["integer_val"] == 42
    assert data["float_val"] == 3.14159
    assert data["boolean_val"] is True
    assert data["null_val"] is None
    assert data["list_val"] == [1, 2, 3, "four", 5.0]
    assert data["dict_val"]["nested_string"] == "nested"
    assert data["dict_val"]["nested_list"] == ["a", "b", "c"]


# === Phase 1 correctness tests ===


def test_import_constructor_captures_modify_return_value(tmp_path: pathlib.Path):
    """import_constructor must capture modify() return value (Bug 1d).

    When the second file completely replaces a top-level scalar value,
    the replacement must take effect.
    """
    write(tmp_path / "first.yaml", "a: 1\nb: 2")
    write(tmp_path / "second.yaml", "a: 99\nc: 3")

    root = tmp_path / "root.yaml"
    write(root, "!import\n  - first.yaml\n  - second.yaml")

    with open(root, "r") as f:
        data = yaml.load(f, Loader=Loader)

    assert data["a"] == 99  # replaced by second file
    assert data["b"] == 2  # from first file
    assert data["c"] == 3  # from second file


def test_resolve_value_type_check_not_stripped_by_optimize():
    """assert isinstance() should be replaced by explicit type checks (Bug 1a).

    This verifies the type checks work regardless of optimization mode.
    """
    from nanoargs.loader import resolve_value

    # These should all work normally
    assert resolve_value("42") == 42
    assert resolve_value('"hello"') == "hello"
    assert resolve_value("true") is True
    assert resolve_value("null") is None
    assert resolve_value('{"a": 1}') == {"a": 1}
    assert resolve_value("[1, 2, 3]") == [1, 2, 3]


# === Phase 3: resolve_value direct tests (3a) ===


class TestResolveValue:
    """Direct unit tests for resolve_value()."""

    def test_json_string(self):
        from nanoargs.loader import resolve_value

        assert resolve_value('"hello world"') == "hello world"

    def test_json_number_int(self):
        from nanoargs.loader import resolve_value

        assert resolve_value("42") == 42

    def test_json_number_float(self):
        from nanoargs.loader import resolve_value

        assert resolve_value("3.14") == 3.14

    def test_json_boolean_true(self):
        from nanoargs.loader import resolve_value

        assert resolve_value("true") is True

    def test_json_boolean_false(self):
        from nanoargs.loader import resolve_value

        assert resolve_value("false") is False

    def test_json_null(self):
        from nanoargs.loader import resolve_value

        assert resolve_value("null") is None

    def test_json_object(self):
        from nanoargs.loader import resolve_value

        assert resolve_value('{"key": "val", "num": 1}') == {"key": "val", "num": 1}

    def test_json_array(self):
        from nanoargs.loader import resolve_value

        assert resolve_value("[1, 2, 3]") == [1, 2, 3]

    def test_yaml_yes_is_string(self):
        from nanoargs.loader import resolve_value

        # D5: YAML boolean coercion should NOT happen for CLI overrides
        assert resolve_value("yes") == "yes"

    def test_yaml_no_is_string(self):
        from nanoargs.loader import resolve_value

        # D5: "NO" should remain a string, not become False
        assert resolve_value("no") == "no"

    def test_yaml_on_is_string(self):
        from nanoargs.loader import resolve_value

        assert resolve_value("on") == "on"

    def test_yaml_off_is_string(self):
        from nanoargs.loader import resolve_value

        assert resolve_value("off") == "off"

    def test_plain_string_passthrough(self):
        from nanoargs.loader import resolve_value

        # Strings that aren't valid JSON or special YAML → string
        assert resolve_value("just_a_string") == "just_a_string"

    def test_at_file_json(self, tmp_path: pathlib.Path):
        from nanoargs.loader import resolve_value

        f = tmp_path / "data.json"
        f.write_text('{"x": 42}')
        assert resolve_value(f"@{f}") == {"x": 42}

    def test_at_file_yaml(self, tmp_path: pathlib.Path):
        from nanoargs.loader import resolve_value

        f = tmp_path / "data.yaml"
        f.write_text("x: 42\ny: hello")
        assert resolve_value(f"@{f}") == {"x": 42, "y": "hello"}

    def test_at_file_unknown_extension(self, tmp_path: pathlib.Path):
        from nanoargs.loader import resolve_value

        f = tmp_path / "data.txt"
        f.write_text('{"x": 99}')
        assert resolve_value(f"@{f}") == {"x": 99}

    def test_at_file_nonexistent(self):
        from nanoargs.loader import resolve_value

        with pytest.raises(FileNotFoundError):
            resolve_value("@nonexistent_file.json")

    def test_at_file_with_base_dir(self, tmp_path: pathlib.Path):
        from nanoargs.loader import resolve_value

        sub = tmp_path / "sub"
        sub.mkdir()
        f = sub / "data.json"
        f.write_text("99")
        result = resolve_value("@sub/data.json", base_dir=tmp_path)
        assert result == 99

    def test_bare_at_sign(self):
        from nanoargs.loader import resolve_value

        # Single "@" is not a file reference (len == 1)
        # Falls through to JSON (fails), then YAML (fails), then string fallback
        result = resolve_value("@")
        assert result == "@"


# === Phase 3: _deep_merge direct tests (3d) ===


class TestDeepMerge:
    """Direct unit tests for deep_merge."""

    def test_dict_overwritten_by_scalar(self):
        from nanoargs.loader import deep_merge

        result = deep_merge({"a": {"x": 1}}, {"a": 5})
        assert result == {"a": 5}

    def test_three_levels_deep(self):
        from nanoargs.loader import deep_merge

        base = {"a": {"b": {"c": 1, "d": 2}}}
        incoming = {"a": {"b": {"c": 99}}}
        result = deep_merge(base, incoming)
        assert result == {"a": {"b": {"c": 99, "d": 2}}}

    def test_empty_base(self):
        from nanoargs.loader import deep_merge

        result = deep_merge({}, {"a": 1})
        assert result == {"a": 1}

    def test_base_not_mutated(self):
        from nanoargs.loader import deep_merge

        base = {"a": {"b": 1}}
        incoming = {"a": {"b": 2}}
        deep_merge(base, incoming)
        assert base == {"a": {"b": 1}}  # not mutated

    def test_new_keys_added(self):
        from nanoargs.loader import deep_merge

        result = deep_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}


# === Phase 3: negative tests (3h) ===


def test_override_nested_on_none_field(tmp_path: pathlib.Path):
    """C6: Override nested property on None field should auto-vivify and work."""
    from typing import Optional

    from pydantic import BaseModel

    from nanoargs.cli import NanoArgs

    class Inner(BaseModel):
        x: int = 1

    class Outer(BaseModel):
        name: str
        inner: Optional[Inner] = None

    cfg = tmp_path / "c.yaml"
    write(cfg, "name: test")

    # C6: Now auto-vivifies None → {} so the override succeeds
    result = NanoArgs(Outer).parse(argv=[str(cfg), "--override", "$.inner.x=42"])
    assert result.inner is not None
    assert result.inner.x == 42


def test_import_non_string_path(tmp_path: pathlib.Path):
    """!import with non-string path should raise ValueError."""
    root = tmp_path / "root.yaml"
    write(root, "!import\n  - 42")

    with pytest.raises((ValueError, TypeError)):
        with open(root, "r") as f:
            yaml.load(f, Loader=Loader)


def test_override_non_list_specs(tmp_path: pathlib.Path):
    """!override with non-list specs should raise ValueError."""
    root = tmp_path / "root.yaml"
    write(root, '!override\n  - {a: 1}\n  - "not_a_list"')

    with pytest.raises(ValueError, match="specs must be a list"):
        with open(root, "r") as f:
            yaml.load(f, Loader=Loader)


def test_empty_override_value(tmp_path: pathlib.Path):
    """Empty override value '$.a=' should resolve to empty string."""
    from nanoargs.loader import resolve_value

    result = resolve_value("")
    assert result == ""


# === Adversarial stress test fixes ===


def test_resolve_value_invalid_yaml_falls_back_to_string():
    """resolve_value should not crash on strings invalid in both JSON and YAML (C2).

    Some strings are invalid JSON and also cause yaml.safe_load to raise
    ScannerError or ParserError. These should fall back to the raw string.
    """
    from nanoargs.loader import resolve_value

    # yaml.safe_load raises ScannerError on this
    result = resolve_value("abc: def: {ghi")
    assert result == "abc: def: {ghi"

    # yaml.safe_load raises ParserError on this
    result2 = resolve_value("{invalid yaml: }}}")
    assert result2 == "{invalid yaml: }}}"


class TestResolveValueYamlCoercion:
    """D4+D5: resolve_value should not let YAML coerce scalars unexpectedly."""

    def test_colon_string_stays_string(self):
        """D4: 'error: disk full' should NOT become a dict."""
        from nanoargs.loader import resolve_value

        result = resolve_value("error: disk full")
        assert result == "error: disk full"
        assert isinstance(result, str)

    def test_country_code_NO_stays_string(self):
        """D5: 'NO' should NOT become False."""
        from nanoargs.loader import resolve_value

        assert resolve_value("NO") == "NO"

    def test_tilde_stays_string(self):
        """D5: '~' should NOT become None."""
        from nanoargs.loader import resolve_value

        assert resolve_value("~") == "~"

    def test_octal_stays_string(self):
        """D5: '0777' should NOT become 511."""
        from nanoargs.loader import resolve_value

        assert resolve_value("0777") == "0777"

    def test_hex_stays_string(self):
        """D5: '0x1F' should NOT become 31."""
        from nanoargs.loader import resolve_value

        assert resolve_value("0x1F") == "0x1F"

    def test_inf_stays_string(self):
        """D5: '.inf' should NOT become float('inf')."""
        from nanoargs.loader import resolve_value

        assert resolve_value(".inf") == ".inf"

    def test_yaml_dict_still_works(self):
        """YAML dicts should still be parsed."""
        from nanoargs.loader import resolve_value

        result = resolve_value("{a: 1, b: 2}")
        assert result == {"a": 1, "b": 2}

    def test_yaml_list_still_works(self):
        """YAML lists should still be parsed."""
        from nanoargs.loader import resolve_value

        result = resolve_value("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_json_true_still_works(self):
        """JSON 'true' should still parse as True (handled by JSON, not YAML)."""
        from nanoargs.loader import resolve_value

        assert resolve_value("true") is True

    def test_json_null_still_works(self):
        """JSON 'null' should still parse as None (handled by JSON, not YAML)."""
        from nanoargs.loader import resolve_value

        assert resolve_value("null") is None

    def test_json_numbers_still_work(self):
        """JSON numbers should still parse correctly."""
        from nanoargs.loader import resolve_value

        assert resolve_value("42") == 42
        assert resolve_value("3.14") == 3.14


# === Round 2: Phase A tests ===


def test_import_deep_merge_nested_dicts(tmp_path: pathlib.Path):
    """D1: !import must deep-merge nested dicts, not lose keys."""
    write(
        tmp_path / "first.yaml",
        """
database:
  host: localhost
  port: 5432
  name: mydb
""",
    )
    write(
        tmp_path / "second.yaml",
        """
database:
  host: remote
""",
    )
    root = tmp_path / "root.yaml"
    write(root, "!import\n  - first.yaml\n  - second.yaml")
    with open(root, "r") as f:
        data = yaml.load(f, Loader=Loader)
    assert data == {"database": {"host": "remote", "port": 5432, "name": "mydb"}}


def test_import_type_mismatch_dict_then_list(tmp_path: pathlib.Path):
    """C1: !import merging dict + list should not crash — list wins."""
    write(tmp_path / "dict_file.yaml", "a: 1\nb: 2")
    write(tmp_path / "list_file.yaml", "- 1\n- 2\n- 3")
    root = tmp_path / "root.yaml"
    write(root, "!import\n  - dict_file.yaml\n  - list_file.yaml")
    with open(root, "r") as f:
        data = yaml.load(f, Loader=Loader)
    assert data == [1, 2, 3]


def test_import_type_mismatch_list_then_dict(tmp_path: pathlib.Path):
    """C1: !import merging list + dict should not crash — dict wins."""
    write(tmp_path / "list_file.yaml", "- 1\n- 2")
    write(tmp_path / "dict_file.yaml", "a: 1")
    root = tmp_path / "root.yaml"
    write(root, "!import\n  - list_file.yaml\n  - dict_file.yaml")
    with open(root, "r") as f:
        data = yaml.load(f, Loader=Loader)
    assert data == {"a": 1}


def test_resolve_value_empty_json_file(tmp_path: pathlib.Path):
    """C2: Empty .json file via @ reference should return None, not crash."""
    from nanoargs.loader import resolve_value

    empty_json = tmp_path / "empty.json"
    empty_json.write_text("")
    result = resolve_value(f"@{empty_json}")
    assert result is None


def test_resolve_value_whitespace_json_file(tmp_path: pathlib.Path):
    """C2: Whitespace-only .json file should return None."""
    from nanoargs.loader import resolve_value

    ws_json = tmp_path / "ws.json"
    ws_json.write_text("   \n  ")
    result = resolve_value(f"@{ws_json}")
    assert result is None


def test_resolve_value_at_directory(tmp_path: pathlib.Path):
    """C3: @directory should raise FileNotFoundError for consistency with @missing_file."""
    from nanoargs.loader import resolve_value

    with pytest.raises(FileNotFoundError, match="directory"):
        resolve_value(f"@{tmp_path}")


def test_resolve_value_at_nonexistent(tmp_path: pathlib.Path):
    """C3: @nonexistent should raise FileNotFoundError."""
    from nanoargs.loader import resolve_value

    with pytest.raises(FileNotFoundError):
        resolve_value(f"@{tmp_path / 'nope.txt'}")


def test_resolve_value_at_whitespace_stripped(tmp_path: pathlib.Path):
    """C3: @ reference should strip whitespace from the path."""
    from nanoargs.loader import resolve_value

    f = tmp_path / "data.json"
    f.write_text("42")
    result = resolve_value(f"@  {f}  ")
    assert result == 42


def test_override_on_none_target(tmp_path: pathlib.Path):
    """C5: !override on None target (empty import) should init to {} and work."""
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    root = tmp_path / "root.yaml"
    write(
        root,
        f'!override\n  - !import ["{empty.name}"]\n  - ["$.x=5"]',
    )
    with open(root, "r") as f:
        data = yaml.load(f, Loader=Loader)
    assert data == {"x": 5}


def test_resolve_value_double_at_escape():
    """D8: @@ prefix should return literal string starting with @."""
    from nanoargs.loader import resolve_value

    result = resolve_value("@@user")
    assert result == "@user"

    result2 = resolve_value("@@/path/to/something")
    assert result2 == "@/path/to/something"


# === Round 2: Phase C tests ===


def test_resolve_value_unsupported_format_toml(tmp_path: pathlib.Path):
    """E9: .toml file via @ should try JSON, fall back to raw text."""
    from nanoargs.loader import resolve_value

    f = tmp_path / "config.toml"
    f.write_text("[section]\nkey = 'value'")
    # Not valid JSON, so falls back to raw text
    result = resolve_value(f"@{f}")
    assert isinstance(result, str)
    assert "[section]" in result


def test_resolve_value_unsupported_format_ini(tmp_path: pathlib.Path):
    """E9: .ini file via @ should try JSON, fall back to raw text."""
    from nanoargs.loader import resolve_value

    f = tmp_path / "config.ini"
    f.write_text("[DEFAULT]\nkey = value")
    result = resolve_value(f"@{f}")
    assert isinstance(result, str)
    assert "[DEFAULT]" in result
