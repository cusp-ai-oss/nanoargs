# Copyright 2024-2026 Cusp AI
# SPDX-License-Identifier: Apache-2.0

import json
import pathlib
import textwrap
from enum import Enum
from typing import Annotated, Any, List, Literal, Optional

import pytest
from pydantic import BaseModel, Field, ValidationError

from nanoargs.cli import NanoArgs
from nanoargs.path import Path


class Cfg(BaseModel):
    a: int
    b: int | None = None


class OvCfg(BaseModel):
    a: int
    nested: dict[str, int]


class Conf(BaseModel):
    outer: dict


class ComplexCfg(BaseModel):
    """Complex configuration for testing advanced features."""

    name: str = Field(description="The name of the configuration")
    values: List[int] = Field(
        default_factory=list, description="List of integer values"
    )
    settings: dict[str, str] = Field(
        default_factory=dict, description="String settings"
    )
    nested: Optional["NestedCfg"] = None
    enabled: bool = True


class NestedCfg(BaseModel):
    """Nested configuration model."""

    level: int = 1
    tags: List[str] = Field(default_factory=list)
    metadata: dict[str, int] = Field(default_factory=dict)


def write(p: pathlib.Path, content: str):
    p.write_text(textwrap.dedent(content))


def _render_schema(t: "NanoArgs") -> str:
    from io import StringIO

    from rich.console import Console

    buf = StringIO()
    Console(file=buf, width=120).print(NanoArgs._schema_table(t.schema))
    return buf.getvalue()


def test_print_schema(run_parse, tmp_path: pathlib.Path):
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1")
    out, _ = run_parse(Cfg, [str(cfg), "--print-schema"])
    assert "properties" in out and "a" in out


def test_override_wildcard_error(tmp_path: pathlib.Path):
    """Wildcards not allowed in overrides."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1")
    with pytest.raises(ValueError):
        NanoArgs(Cfg).parse(argv=[str(cfg), "--override", "$.*=2"])


def test_override_missing_nested_autovivifies(tmp_path: pathlib.Path):
    """C6: Nested property of non-existent field now auto-vivifies."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1")
    # Auto-vivification creates missing.nested=2, but Pydantic ignores unknown fields
    c = NanoArgs(Cfg).parse(argv=[str(cfg), "--override", "$.missing.nested=2"])
    assert c.a == 1  # original value preserved


def test_override_creates_missing_property(tmp_path: pathlib.Path):
    """Test that we can override properties not present in YAML (Issue #2)"""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1")
    # Should be able to set optional field 'b' that's not in YAML
    c = NanoArgs(Cfg).parse(argv=[str(cfg), "--override", "$.b=2"])
    assert c.b == 2


def test_colon_yaml_override(tmp_path: pathlib.Path):
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1")
    c = NanoArgs(Cfg).parse(argv=[str(cfg), "--override", "$.a: 5"])
    assert c.a == 5


def test_caching_identity():
    p1 = Path.from_string("$.a.b")
    p2 = Path.from_string("$.a.b")
    assert p1 is p2


@pytest.mark.parametrize(
    "override,value",
    [("$.a=2", 2), ("$.a: 3", 3)],
)
def test_scalar_overrides(tmp_path: pathlib.Path, override: str, value: int):
    cfg_file = tmp_path / "base.yaml"
    write(cfg_file, "a: 1\nnested:\n  x: 10")
    c = NanoArgs(OvCfg).parse(argv=[str(cfg_file), "--override", override])
    assert c.a == value


def test_override_file_indirection(tmp_path: pathlib.Path):
    cfg_file = tmp_path / "base.yaml"
    write(cfg_file, "a: 1\nnested:\n  x: 10")
    payload = tmp_path / "val.json"
    payload.write_text("99")
    c = NanoArgs(OvCfg).parse(argv=[str(cfg_file), "--override", f"$.a=@{payload}"])
    assert c.a == 99


def test_at_file_nested_import(tmp_path: pathlib.Path):
    inner = tmp_path / "dir" / "inner.yaml"
    inner.parent.mkdir(parents=True, exist_ok=True)
    write(inner, "value: 42")
    nested = tmp_path / "dir" / "nested.yaml"
    write(nested, "!import\n  - inner.yaml")
    root = tmp_path / "cfg.yaml"
    write(root, "outer: {}")
    c = NanoArgs(Conf).parse(argv=[str(root), "--override", f"$.outer=@{nested}"])
    assert c.outer == {"value": 42}


def test_print_config(run_parse, tmp_path: pathlib.Path):
    """Test --print-config flag outputs final merged configuration."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 42\nb: 24")
    out, _ = run_parse(Cfg, [str(cfg), "--print-config"])
    assert "42" in out and "24" in out


def test_multiple_config_files_merge(tmp_path: pathlib.Path):
    """Test merging multiple configuration files with later files overriding earlier ones."""
    base = tmp_path / "base.yaml"
    override_file = tmp_path / "override.yaml"
    write(base, "a: 1\nnested:\n  x: 10\n  y: 20")
    write(
        override_file, "a: 2\nnested:\n  x: 15\n  y: 20"
    )  # Include y since merging replaces entire nested dict

    c = NanoArgs(OvCfg).parse(argv=[str(base), str(override_file)])
    assert c.a == 2  # overridden
    assert c.nested["x"] == 15  # overridden
    assert c.nested["y"] == 20  # preserved


def test_multiple_overrides_same_path(tmp_path: pathlib.Path):
    """Test that multiple overrides to the same path apply in order."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1")

    c = NanoArgs(Cfg).parse(
        argv=[str(cfg), "--override", "$.a=10", "--override", "$.a=20"]
    )
    assert c.a == 20  # last override wins


def test_json_override_complex_values(tmp_path: pathlib.Path):
    """Test overriding with complex JSON values."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1\nnested: {}")

    c = NanoArgs(OvCfg).parse(
        argv=[str(cfg), "--override", '$.nested={"key1": 100, "key2": 200}']
    )
    assert c.nested == {"key1": 100, "key2": 200}


def test_file_override_json(tmp_path: pathlib.Path):
    """Test file override with JSON file."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1\nnested: {}")

    json_file = tmp_path / "values.json"
    json_file.write_text(json.dumps({"x": 42, "y": 24}))

    c = NanoArgs(OvCfg).parse(argv=[str(cfg), "--override", f"$.nested=@{json_file}"])
    assert c.nested == {"x": 42, "y": 24}


def test_file_override_yaml(tmp_path: pathlib.Path):
    """Test file override with YAML file."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1\nnested: {}")

    yaml_file = tmp_path / "values.yaml"
    write(yaml_file, "x: 99\ny: 88")

    c = NanoArgs(OvCfg).parse(argv=[str(cfg), "--override", f"$.nested=@{yaml_file}"])
    assert c.nested == {"x": 99, "y": 88}


def test_override_nonexistent_file(tmp_path: pathlib.Path):
    """Test that referencing nonexistent file raises appropriate error."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1")

    with pytest.raises(FileNotFoundError):
        NanoArgs(Cfg).parse(argv=[str(cfg), "--override", "$.a=@nonexistent.json"])


def test_colon_syntax_variations(tmp_path: pathlib.Path):
    """Test various YAML scalar overrides using colon syntax."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1")

    # Test with spaces
    c1 = NanoArgs(Cfg).parse(argv=[str(cfg), "--override", "$.a: 42"])
    assert c1.a == 42

    # Test without spaces
    c2 = NanoArgs(Cfg).parse(argv=[str(cfg), "--override", "$.a:99"])
    assert c2.a == 99


def test_invalid_override_syntax(tmp_path: pathlib.Path):
    """Test that invalid override syntax raises appropriate errors."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1")

    # Missing value separator
    with pytest.raises(ValueError, match="Expected.*syntax"):
        NanoArgs(Cfg).parse(argv=[str(cfg), "--override", "$.a"])

    # Empty path
    with pytest.raises(ValueError, match="Empty path"):
        NanoArgs(Cfg).parse(argv=[str(cfg), "--override", "=42"])


def test_schema_output_content(run_parse, tmp_path: pathlib.Path):
    """Test that schema output contains expected JSON schema fields."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "name: test\nvalues: [1, 2, 3]\nsettings: {}\nenabled: true")

    out, _ = run_parse(ComplexCfg, [str(cfg), "--print-schema"])

    # Check for key schema elements
    assert "properties" in out
    assert "name" in out
    assert "values" in out
    assert "settings" in out
    assert "description" in out  # Field descriptions should be included
    assert "type" in out


def test_config_validation_errors(tmp_path: pathlib.Path):
    """Test that Pydantic validation errors are properly raised."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: not_an_integer")

    with pytest.raises(ValidationError):
        NanoArgs(Cfg).parse(argv=[str(cfg)])


def test_empty_config_file(tmp_path: pathlib.Path):
    """Test handling of actually empty configuration files."""
    cfg = tmp_path / "empty.yaml"
    cfg.write_text("")  # Truly empty file

    # Empty file loads as None, which fails validation for Cfg (requires a: int)
    with pytest.raises((ValidationError, TypeError)):
        NanoArgs(Cfg).parse(argv=[str(cfg)])


def test_complex_nested_overrides(tmp_path: pathlib.Path):
    """Test complex nested structure overrides."""
    cfg = tmp_path / "complex.yaml"
    write(
        cfg,
        """
    name: test
    values: [1, 2, 3]
    settings:
      mode: debug
      level: info
    nested:
      level: 1
      tags: ["a", "b"]
      metadata:
        count: 10
    enabled: true
    """,
    )

    c = NanoArgs(ComplexCfg).parse(
        argv=[
            str(cfg),
            "--override",
            "$.values[1]=99",
            "--override",
            '$.settings.mode="production"',
            "--override",
            "$.nested.level=5",
            "--override",
            "$.nested.metadata.count=50",
            "--override",
            "$.enabled=false",
        ]
    )

    assert c.values == [1, 99, 3]
    assert c.settings["mode"] == "production"
    assert c.nested is not None
    assert c.nested.level == 5
    assert c.nested.metadata["count"] == 50
    assert c.enabled is False


def test_array_slice_overrides(tmp_path: pathlib.Path):
    """Test overriding array slices."""
    cfg = tmp_path / "array.yaml"
    write(cfg, "name: test\nvalues: [1, 2, 3, 4, 5]")

    c = NanoArgs(ComplexCfg).parse(
        argv=[
            str(cfg),
            "--override",
            "$.values[1:4]=[10, 20, 30]",
        ]
    )

    assert c.values == [1, 10, 20, 30, 5]


def test_help_message_formatting(capsys, tmp_path: pathlib.Path):
    """Test that help message is properly formatted and contains schema information."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "name: test")

    with pytest.raises(SystemExit):
        NanoArgs(ComplexCfg).parse(argv=["--help"])

    captured = capsys.readouterr()
    help_output = captured.out

    # Check for key help elements
    assert "override" in help_output.lower()
    assert "print-schema" in help_output.lower()
    assert "print-config" in help_output.lower()
    assert "path" in help_output.lower()  # Path syntax should be shown
    assert "schema" in help_output.lower()  # Schema table should be shown


# Tests for Issue #1: Partial object merging with defaults
def test_partial_nested_object_merges_with_defaults(tmp_path: pathlib.Path):
    """Test that partial nested objects in YAML merge with Pydantic model defaults (Issue #1)."""
    from dataclasses import field

    from pydantic.dataclasses import dataclass

    @dataclass(frozen=True)
    class DatabaseConfig:
        host: str
        port: int
        name: str = "default_db"
        ssl: bool = True

    @dataclass(frozen=True)
    class AppConfig:
        app_name: str
        database: DatabaseConfig = field(
            default_factory=lambda: DatabaseConfig(
                host="localhost", port=5432, name="default_db", ssl=True
            )
        )

    # Create YAML with partial database config (missing 'name' and 'ssl')
    cfg = tmp_path / "partial.yaml"
    write(
        cfg,
        """
        app_name: myapp
        database:
          host: remote.example.com
          port: 3306
    """,
    )

    # Should merge partial YAML with model defaults
    c = NanoArgs(AppConfig).parse(argv=[str(cfg)])

    assert c.app_name == "myapp"
    assert c.database.host == "remote.example.com"
    assert c.database.port == 3306
    # These should come from defaults since they're not in YAML
    assert c.database.name == "default_db"
    assert c.database.ssl is True


def test_nested_object_with_all_defaults(tmp_path: pathlib.Path):
    """Test that nested objects use model defaults when completely missing from YAML (Issue #1)."""
    from dataclasses import field

    from pydantic.dataclasses import dataclass

    @dataclass(frozen=True)
    class ServerConfig:
        host: str = "localhost"
        port: int = 8080

    @dataclass(frozen=True)
    class Config:
        name: str
        server: ServerConfig = field(
            default_factory=lambda: ServerConfig(host="localhost", port=8080)
        )

    # YAML without server config - should use defaults
    cfg = tmp_path / "minimal.yaml"
    write(cfg, "name: test_app")

    c = NanoArgs(Config).parse(argv=[str(cfg)])

    assert c.name == "test_app"
    assert c.server.host == "localhost"
    assert c.server.port == 8080


# Tests for Issue #4: Flag-style override syntax
def test_print_schema_without_config_file(run_parse):
    """Test --print-schema works without any config file (GitHub Issue #2)."""
    out, _ = run_parse(Cfg, ["--print-schema"])
    assert "properties" in out and "a" in out


def test_print_config_without_config_file(run_parse):
    """Test --print-config without config files uses model defaults."""

    class DefaultCfg(BaseModel):
        x: int = 10
        y: str = "hello"

    out, _ = run_parse(DefaultCfg, ["--print-config"])
    assert "10" in out and "hello" in out


def test_no_config_no_flags_raises_error():
    """Test that calling parse with no config files and no special flags raises an error."""
    with pytest.raises(SystemExit):
        NanoArgs(Cfg).parse(argv=[])


def test_unknown_flag_errors(tmp_path):
    """Unknown flags now error immediately with strict parse_args."""
    cfg = tmp_path / "c.yaml"
    cfg.write_text("a: 1\n")
    with pytest.raises(SystemExit) as exc:
        NanoArgs(Cfg).parse(argv=[str(cfg), "--nonexistent_flag", "42"])
    assert exc.value.code == 2


def test_stdin_config(monkeypatch):
    """'-' as a config file reads YAML from stdin."""
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO("a: 42\nb: 7\n"))
    c = NanoArgs(Cfg).parse(argv=["-"])
    assert c.a == 42 and c.b == 7


def test_stdin_mixed_with_file(monkeypatch, tmp_path):
    """'-' can be mixed with real file paths; merge order is preserved."""
    cfg = tmp_path / "base.yaml"
    cfg.write_text("a: 1\nb: 2\n")
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO("a: 99\n"))
    c = NanoArgs(Cfg).parse(argv=[str(cfg), "-"])
    assert c.a == 99
    assert c.b == 2


def test_stdin_with_override(monkeypatch):
    """'-' with --override applies override after stdin merge."""
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO("a: 1\n"))
    c = NanoArgs(Cfg).parse(argv=["-", "--override", "$.a=5"])
    assert c.a == 5


def test_schema_with_enum_type(run_parse):
    """Test schema output with enum field doesn't show 'Unknown' (GitHub Issue #1)."""
    import enum

    class Color(enum.Enum):
        RED = "red"
        GREEN = "green"
        BLUE = "blue"

    class EnumCfg(BaseModel):
        color: Color

    out, _ = run_parse(EnumCfg, ["--print-schema"])
    assert "Unknown" not in out


def test_schema_with_literal_type(run_parse):
    """Test schema output with Literal field shows values (GitHub Issue #1)."""
    from typing import Literal

    class LiteralCfg(BaseModel):
        mode: Literal["fast", "slow"]

    out, _ = run_parse(LiteralCfg, ["--print-schema"])
    assert "Unknown" not in out


def test_schema_defs_without_title(run_parse):
    """Test that $defs entries without 'title' derive title from the key name."""
    import enum

    class Priority(enum.Enum):
        LOW = "low"
        HIGH = "high"

    class TaskCfg(BaseModel):
        priority: Priority

    out, _ = run_parse(TaskCfg, ["--print-schema"])
    assert "Unknown" not in out


def test_type_repr_enum_without_type():
    """Test _type_repr handles enum-only schemas (GitHub Issue #1)."""
    from rich.text import Text

    result = NanoArgs._type_repr({"enum": ["a", "b", "c"]})
    assert isinstance(result, Text)
    assert "Unknown" not in result.plain
    assert "a" in result.plain


def test_type_repr_const():
    """Test _type_repr handles const schemas."""
    from rich.text import Text

    result = NanoArgs._type_repr({"const": 42})
    assert isinstance(result, Text)
    assert "Unknown" not in result.plain
    assert "42" in result.plain


def test_where_clause_type_alias_literal():
    """Issue #11: TypeAliasType wrapping Literal appears in where legend."""
    from typing_extensions import TypeAliasType

    X = TypeAliasType("X", Literal["a", "b"])

    class M(BaseModel):
        x: X

    output = _render_schema(NanoArgs(M))
    assert "where" in output
    assert "@X" in output
    assert "a" in output and "b" in output


def test_where_clause_enum():
    """Enum $defs appear in where legend."""

    class Color(str, Enum):
        red = "red"
        blue = "blue"

    class M(BaseModel):
        c: Color

    output = _render_schema(NanoArgs(M))
    assert "where" in output
    assert "@Color" in output
    assert "red" in output and "blue" in output


def test_where_clause_nested_model_not_in_where():
    """Nested BaseModel sub-section is NOT in the where legend."""

    class Sub(BaseModel):
        y: int

    class M(BaseModel):
        s: Sub

    output = _render_schema(NanoArgs(M))
    assert "where" not in output
    assert "Sub" in output


def test_where_clause_mixed_model_and_alias():
    """Model with both nested model and type alias field."""
    from typing_extensions import TypeAliasType

    Mode = TypeAliasType("Mode", Literal["train", "eval"])

    class Config(BaseModel):
        lr: float

    class M(BaseModel):
        cfg: Config
        mode: Mode

    output = _render_schema(NanoArgs(M))
    assert "where" in output
    assert "@Mode" in output
    assert "train" in output and "eval" in output
    assert "Config" in output


def test_where_clause_type_alias_int():
    """TypeAliasType wrapping int appears in where legend."""
    from typing_extensions import TypeAliasType

    X = TypeAliasType("X", int)

    class M(BaseModel):
        x: X

    output = _render_schema(NanoArgs(M))
    assert "where" in output
    assert "@X" in output
    assert "integer" in output


def test_where_clause_no_defs_no_where():
    """Model with no $defs produces no where section."""

    class M(BaseModel):
        x: int
        y: str

    output = _render_schema(NanoArgs(M))
    assert "where" not in output


def test_const_type_order_single_literal():
    """Single-value Literal shows the value, not the type name."""
    result = NanoArgs._type_repr({"const": "yes", "type": "string"})
    assert result.plain == "yes"
    assert "string" not in result.plain


def test_const_type_order_chained_alias():
    """Chained TypeAliasType resolving to single-value Literal shows value."""
    from typing_extensions import TypeAliasType

    A = TypeAliasType("A", Literal["x"])
    B = TypeAliasType("B", A)

    class M(BaseModel):
        b: B

    output = _render_schema(NanoArgs(M))
    assert "where" in output
    assert "x" in output


def test_where_clause_constrained_alias_shows_base_type():
    """Constrained Annotated alias shows base type (known limitation)."""
    from pydantic import Field
    from typing_extensions import TypeAliasType

    X = TypeAliasType("X", Annotated[int, Field(gt=0)])

    class M(BaseModel):
        x: X

    output = _render_schema(NanoArgs(M))
    assert "where" in output
    assert "@X" in output
    assert "integer" in output


def test_type_repr_allof():
    """Test _type_repr handles allOf schemas."""
    from rich.text import Text

    result = NanoArgs._type_repr({"allOf": [{"type": "string"}, {"type": "integer"}]})
    assert isinstance(result, Text)
    assert "Unknown" not in result.plain


def test_type_repr_oneof():
    """Test _type_repr handles oneOf schemas."""
    from rich.text import Text

    result = NanoArgs._type_repr({"oneOf": [{"type": "string"}, {"type": "integer"}]})
    assert isinstance(result, Text)
    assert "Unknown" not in result.plain


def test_add_schema_defs_without_title():
    """Test _add_schema handles $defs entries without title."""
    from rich.table import Table

    t = Table()
    t.add_column("Name")
    t.add_column("Type")
    t.add_column("Description")
    NanoArgs._add_schema(
        t, {"properties": {"x": {"type": "string"}}}, def_key="MyModel"
    )
    assert t.row_count == 3  # title row + property row + spacer row


def test_import_does_not_install_rich_traceback():
    """Test that importing nanoargs does not override sys.excepthook."""
    import importlib
    import sys

    hook_before = sys.excepthook
    # Reimporting should not change excepthook
    importlib.reload(__import__("nanoargs"))
    assert sys.excepthook is hook_before


def test_safe_loader_not_mutated():
    """Test that importing nanoargs does not mutate global yaml.SafeLoader."""
    import yaml

    assert "!import" not in yaml.SafeLoader.yaml_constructors
    assert "!override" not in yaml.SafeLoader.yaml_constructors


def test_root_level_override(tmp_path: pathlib.Path):
    """Test that root-level override ($=value) replaces entire data."""
    cfg = tmp_path / "c.yaml"
    write(cfg, "a: 1\nb: 2")
    c = NanoArgs(Cfg).parse(argv=[str(cfg), "--override", '$={"a": 99, "b": 77}'])
    assert c.a == 99
    assert c.b == 77


def test_pydantic_dataclass_default_factory(tmp_path: pathlib.Path):
    """Test that pydantic dataclass defaults are correctly extracted."""
    from dataclasses import field

    from pydantic.dataclasses import dataclass

    @dataclass(frozen=True)
    class Inner:
        x: int = 10
        y: int = 20

    @dataclass(frozen=True)
    class Outer:
        name: str
        inner: Inner = field(default_factory=lambda: Inner(x=10, y=20))

    cfg = tmp_path / "c.yaml"
    write(cfg, "name: test")
    c = NanoArgs(Outer).parse(argv=[str(cfg)])
    assert c.name == "test"
    assert c.inner.x == 10
    assert c.inner.y == 20


def test_all_required_fields_no_defaults(tmp_path: pathlib.Path):
    """Test model with all required fields and no defaults parses correctly."""

    class RequiredCfg(BaseModel):
        x: int
        y: str

    cfg = tmp_path / "c.yaml"
    write(cfg, "x: 42\ny: hello")
    c = NanoArgs(RequiredCfg).parse(argv=[str(cfg)])
    assert c.x == 42
    assert c.y == "hello"


# === Phase 1 correctness tests ===


def test_empty_yaml_does_not_destroy_merge_chain(tmp_path: pathlib.Path):
    """Empty YAML file should not wipe previously merged data (Bug 1b)."""
    base = tmp_path / "base.yaml"
    write(base, "a: 42\nb: 7")
    empty = tmp_path / "empty.yaml"
    empty.write_text("")  # YAML returns None for empty file

    c = NanoArgs(Cfg).parse(argv=[str(base), str(empty)])
    assert c.a == 42
    assert c.b == 7


def test_get_model_defaults_basemodel_instance(tmp_path: pathlib.Path):
    """BaseModel instance as direct default should be captured (Bug 1f)."""

    class Inner(BaseModel):
        x: int = 10
        y: int = 20

    class Outer(BaseModel):
        name: str
        inner: Inner = Inner(x=10, y=20)

    cfg = tmp_path / "c.yaml"
    write(cfg, "name: test")

    c = NanoArgs(Outer).parse(argv=[str(cfg)])
    assert c.name == "test"
    assert c.inner.x == 10
    assert c.inner.y == 20


def test_enum_default_round_trip(tmp_path: pathlib.Path):
    """An Enum field default should survive the merge pipeline as its member."""

    class Mode(Enum):
        FAST = "fast"

    class Cfg(BaseModel):
        name: str
        mode: Mode = Mode.FAST

    cfg = tmp_path / "c.yaml"
    write(cfg, "name: test")

    assert NanoArgs(Cfg).parse(argv=[str(cfg)]).mode is Mode.FAST


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_duck_typed_default_rejected():
    """A non-Enum default carrying `.value` should raise, not coerce to `.value`."""

    class Version:
        def __init__(self) -> None:
            self.value = [1, 2]

    class Cfg(BaseModel):
        version: Any = Version()

    with pytest.raises(TypeError, match="Cannot coerce Version"):
        NanoArgs(Cfg)


def test_type_repr_const_none():
    """_type_repr should handle {"const": None} without returning 'Unknown' (Bug 1g)."""
    from rich.text import Text

    result = NanoArgs._type_repr({"const": None})
    assert isinstance(result, Text)
    assert "Unknown" not in result.plain


# === Phase 2 API robustness tests ===


def test_get_schema_returns_dict():
    """get_schema() should return schema dict without SystemExit (2-pre)."""
    schema = NanoArgs(Cfg).get_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema
    assert "a" in schema["properties"]


def test_model_json_schema_override_honored():
    """A model's own model_json_schema() override should reach the CLI schema."""

    class OverrideCfg(BaseModel):
        mode: str = "train"

        @classmethod
        def model_json_schema(cls, *args, **kwargs) -> dict:
            out = super().model_json_schema(*args, **kwargs)
            out["x-from-model"] = True
            return out

    assert NanoArgs(OverrideCfg).get_schema()["x-from-model"] is True


def test_nonexistent_config_file_error_message(tmp_path: pathlib.Path):
    """Non-existent config file should raise FileNotFoundError with file path (2e)."""
    with pytest.raises(FileNotFoundError):
        NanoArgs(Cfg).parse(argv=["nonexistent_config.yaml"])


# === Adversarial stress test fixes ===


def test_deep_merge_does_not_corrupt_incoming(tmp_path: pathlib.Path):
    """_deep_merge should not leak references from incoming into result (D2).

    The else branch assigns incoming values by reference without copying.
    Mutating the result can corrupt the incoming dict.
    """
    base = tmp_path / "base.yaml"
    write(base, "a: 1\nnested:\n  x: 10")
    override = tmp_path / "override.yaml"
    write(override, "a: 2\nnested:\n  x: 15\n  y: 20")

    # Merge two files, then verify a second parse gets clean data
    ta = NanoArgs(OvCfg)
    c1 = ta.parse(argv=[str(base), str(override)])
    assert c1.a == 2
    assert c1.nested["x"] == 15

    # Second parse should get the same clean data
    c2 = ta.parse(argv=[str(base), str(override)])
    assert c2.a == 2
    assert c2.nested["x"] == 15


def test_yaml_anchors_not_corrupted_by_overrides(tmp_path: pathlib.Path):
    """YAML anchors create shared references that modify corrupts (D6).

    When YAML uses &anchor/*alias, the same dict object appears in multiple
    places. Path.modify mutates in-place, corrupting all references.
    """

    class AnchorCfg(BaseModel):
        defaults: dict
        a: dict
        b: dict

    cfg = tmp_path / "anchors.yaml"
    cfg.write_text("defaults: &d\n  x: 1\n  y: 2\na:\n  <<: *d\nb:\n  <<: *d\n")

    # Override a.x — should NOT affect b.x
    c = NanoArgs(AnchorCfg).parse(argv=[str(cfg), "--override", "$.a.x=99"])
    assert c.a["x"] == 99
    assert c.b["x"] == 1, "YAML anchor alias was corrupted by override"


# === Round 2: Phase A tests ===


def test_type_mismatch_replaces_entirely(tmp_path: pathlib.Path):
    """When a non-dict config file follows a dict, the non-dict replaces entirely."""
    from nanoargs.loader import deep_merge

    # deep_merge with dict+list: incoming wins (not a dict merge)
    result = deep_merge({"a": 1}, [1, 2, 3])
    assert result == [1, 2, 3]

    # deep_merge with list+dict: incoming wins
    result2 = deep_merge([1, 2], {"x": 1})
    assert result2 == {"x": 1}


def test_wildcard_path_is_invalid_syntax(tmp_path: pathlib.Path):
    """$.*=2 now fails at parse time since wildcards are removed from the grammar."""

    class M(BaseModel):
        x: int = 1

    cfg = tmp_path / "c.yaml"
    write(cfg, "x: 1")

    with pytest.raises(ValueError, match="Invalid path syntax"):
        NanoArgs(M).parse(argv=[str(cfg), "--override", "$.*=2"])


def test_literal_type_displays_values_not_type_name():
    """Issue #3: Literal['a', 'b'] should display as 'a | b', not 'string'."""
    result = NanoArgs._type_repr({"enum": ["train", "eval"], "type": "string"})
    assert "train" in result.plain
    assert "eval" in result.plain
    assert result.plain != "string"


def test_str_or_path_displays_distinct_types():
    """Issue #4: str | Path should display as 'string | path', not 'string | string'."""
    schema_prop = {
        "anyOf": [
            {"type": "string"},
            {"format": "path", "type": "string"},
        ]
    }
    result = NanoArgs._type_repr(schema_prop)
    parts = result.plain.split(" | ")
    assert len(set(parts)) == len(parts), f"Duplicate types in: {result.plain}"


def test_enum_defs_show_values_in_schema():
    """Issue #1: Enum $defs entries should display their values, not be empty."""
    from enum import Enum
    from io import StringIO

    from rich.console import Console

    class Color(str, Enum):
        red = "red"
        blue = "blue"

    class M(BaseModel):
        color: Color

    t = NanoArgs(M)
    table = NanoArgs._schema_table(t.schema)
    buf = StringIO()
    Console(file=buf, width=120).print(table)
    output = buf.getvalue()
    assert "red" in output or "blue" in output, (
        f"Enum values not displayed in schema table: {output}"
    )


def test_print_schema_without_config_files():
    """Issue #2: --print-schema should work without providing config files."""

    class M(BaseModel):
        x: int = 1

    with pytest.raises(SystemExit) as exc_info:
        NanoArgs(M).parse(argv=["--print-schema"])
    assert exc_info.value.code == 0


# === Issue #16/#17: docs/help consistency ===


def test_print_config_with_override_no_file(run_parse):
    """--print-config + --override with no config file prints overridden defaults."""

    class DefaultCfg(BaseModel):
        x: int = 10
        y: str = "hello"

    out, _ = run_parse(DefaultCfg, ["--override", "$.x=99", "--print-config"])
    assert "99" in out
