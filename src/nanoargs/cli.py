# Copyright 2024-2026 Cusp AI
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import copy
import sys
import types
from collections.abc import Sequence
from typing import ClassVar, Generic, TypeVar, Union, cast, get_args, get_origin

import rich
from pydantic import BaseModel, TypeAdapter
from pydantic_core import PydanticUndefined
from rich import box
from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.pretty import Pretty
from rich.style import StyleType
from rich.table import Table
from rich.text import Text
from rich_argparse import RichHelpFormatter

from nanoargs.loader import load_and_merge
from nanoargs.path import JsonValue, is_json_value

_ModelT = TypeVar("_ModelT")

SchemaDict = dict[str, JsonValue]


class Nested(BaseModel):
    """Base class for multi-command CLI groups.

    Subclass `Nested` and add fields typed as `ChildModel | None = None` to define
    subcommands. Each field name becomes a CLI command; the field type is the config
    model for that command.

    Example:
        ```python
        from nanoargs import NanoArgs, Nested

        class TrainConfig(BaseModel):
            lr: float = 0.001

        class EvalConfig(BaseModel):
            checkpoint: str

        class CLI(Nested):
            verbose: bool = False          # parent field — set via pre-command override
            train: TrainConfig | None = None
            evaluate: EvalConfig | None = None

        result = NanoArgs(CLI).parse()
        # Usage: app [--override <path>=<value>] <command> [config.yaml] [--override ...]
        ```

    Rules:
        - Subcommand fields must be typed as `T | None = None` where `T` is a
          `BaseModel` subclass or pydantic dataclass.
        - `Annotated[T, Field(...)] | None = None` is also supported.
        - Non-subcommand fields are regular config fields applied from pre-command flags.
        - A `Nested` class with no detectable subcommand fields raises `ValueError`
          at `NanoArgs` construction time.
        - Nesting is supported: a subcommand field whose type is itself `Nested` creates
          a sub-group (e.g. `app data preprocess config.yaml`).
    """


def _strip_annotated(tp: object) -> object:
    from typing import Annotated

    if get_origin(tp) is Annotated:
        return get_args(tp)[0]
    return tp


def _is_subcommand_type(x: object) -> bool:
    from pydantic.dataclasses import is_pydantic_dataclass

    if not isinstance(x, type):
        return False
    return issubclass(x, BaseModel) or is_pydantic_dataclass(cast(type[object], x))


def _unwrap_subcommand_type(tp: object) -> type[object] | None:
    """Extract T from T | None if T is a BaseModel/pydantic-dataclass subclass, else None.
    Also handles Annotated[T, ...] | None (strips Annotated from each Union arg).
    """
    tp = _strip_annotated(tp)
    origin = get_origin(tp)
    if origin is None:
        return cast(type[object], tp) if _is_subcommand_type(tp) else None
    if origin in (types.UnionType, Union):
        args = [_strip_annotated(a) for a in get_args(tp) if a is not type(None)]
        if len(args) == 1 and _is_subcommand_type(args[0]):
            return cast(type[object], args[0])
    return None


class NanoArgs(Generic[_ModelT]):
    class Formatter(RichHelpFormatter):
        """Rich-powered argparse help formatter with custom styles."""

        styles: ClassVar[dict[str, StyleType]] = {
            "argparse.args": "yellow",
            "argparse.groups": "bold",
            "argparse.help": "default",
            "argparse.metavar": "blue",
            "argparse.syntax": "bold dark_orange",
            "argparse.text": "default",
            "argparse.prog": "default",
            "argparse.default": "default",
            "schema.description": "italic",
            "schema.type": "cyan",
            "schema.title": "yellow",
            "schema.name": "blue",
            "schema.border": "bold",
        }

        def __init__(
            self,
            prog: str,
            indent_increment: int = 2,
            max_help_position: int = 24,
            width: int | None = None,
        ) -> None:
            super().__init__(prog, indent_increment, max_help_position, width)
            self.console = rich.console.Console(emoji=False)

    def __init__(self, model: type[_ModelT], *, prog: str | None = None):
        """Create a NanoArgs CLI instance for the given Pydantic model or dataclass.

        If `model` is a `Nested` subclass, the instance enters subcommand dispatch
        mode: fields typed as `T | None = None` become subcommands and child
        `NanoArgs` instances are built eagerly at construction time.

        Args:
            model: A Pydantic `BaseModel` subclass, pydantic dataclass, or `Nested`
                subclass. For `Nested` models the fields define the available commands.
            prog: Optional program name shown in `--help` usage lines. Defaults to the
                value argparse infers from `sys.argv[0]`. When `prog` is set, child
                parsers inherit it as `"{prog} {command}"`.

        Raises:
            ValueError: If `model` is a `Nested` subclass with no detectable subcommand
                fields (i.e. no `T | None = None` typed fields where `T` is a model).
        """
        self.model = model
        self._prog = prog
        self.adapter: TypeAdapter[_ModelT] = TypeAdapter(model)
        self.schema: SchemaDict = self.adapter.json_schema()
        self._subcommands: dict[str, type[object]] | None = self._detect_subcommands(
            model
        )
        if self._subcommands is not None and not self._subcommands:
            raise ValueError(
                f"{model.__name__!r} inherits from Nested but has no detectable "
                "subcommand fields. Add fields typed as 'ChildModel | None = None'."
            )
        self.parser = self._build_arg_parser()
        self._cached_defaults = self._get_model_defaults(model)
        # Cache child parsers after _build_arg_parser so self.parser.prog is resolved
        self._children: dict[str, NanoArgs[object]] = {}
        if self._subcommands:
            for _name, _child_model in self._subcommands.items():
                _child_prog = f"{self.parser.prog} {_name}"
                self._children[_name] = NanoArgs(_child_model, prog=_child_prog)

    @staticmethod
    def _detect_subcommands(model: type[object]) -> dict[str, type[object]] | None:
        """Inspect `model` for subcommand fields.

        Returns `None` if model is not a `Nested` subclass, or a dict mapping field
        names to child model types for `Nested` models (empty dict when no subcommand
        fields are found — the caller raises `ValueError`).
        """
        if not issubclass(model, Nested):
            return None
        result: dict[str, type[object]] = {}
        for name, field in model.model_fields.items():
            child = _unwrap_subcommand_type(field.annotation)
            if child is not None:
                result[name] = child
        return result  # empty dict means Nested with no detectable fields (checked in __init__)

    @classmethod
    def _type_repr(cls, prop: JsonValue) -> Text:
        """Build a styled Rich Text representation of a JSON schema type."""
        if not isinstance(prop, dict):
            return Text("Unknown", cls.Formatter.styles["schema.type"])
        for handler in (
            cls._type_repr_ref,
            cls._type_repr_enum,
            cls._type_repr_const,
            cls._type_repr_type,
            cls._type_repr_combiner,
        ):
            result = handler(prop)
            if result is not None:
                return result
        return Text("Unknown", cls.Formatter.styles["schema.type"])

    @classmethod
    def _type_repr_type(cls, prop: SchemaDict) -> Text | None:
        type_val = prop.get("type")
        if not isinstance(type_val, str):
            return None
        if type_val == "array":
            return Text("[*: ") + cls._type_repr(prop.get("items")) + Text("]")
        if type_val == "object" and isinstance(prop.get("additionalProperties"), dict):
            return (
                Text("{*: ") + cls._type_repr(prop["additionalProperties"]) + Text("}")
            )
        fmt = prop.get("format")
        if isinstance(fmt, str):
            return Text(fmt, cls.Formatter.styles["schema.type"])
        return Text(type_val, cls.Formatter.styles["schema.type"])

    @classmethod
    def _type_repr_ref(cls, prop: SchemaDict) -> Text | None:
        ref = prop.get("$ref")
        if not isinstance(ref, str):
            return None
        return Text("@") + Text(ref.split("/")[-1], cls.Formatter.styles["schema.type"])

    @classmethod
    def _type_repr_combiner(cls, prop: SchemaDict) -> Text | None:
        for key, sep in (("anyOf", " | "), ("allOf", " & "), ("oneOf", " | ")):
            vals = prop.get(key)
            if isinstance(vals, list):
                return Text(sep).join(list(map(cls._type_repr, vals)))
        return None

    @classmethod
    def _type_repr_enum(cls, prop: SchemaDict) -> Text | None:
        enum_vals = prop.get("enum")
        if not isinstance(enum_vals, list):
            return None
        return Text(
            " | ".join(str(v) for v in enum_vals), cls.Formatter.styles["schema.type"]
        )

    @classmethod
    def _type_repr_const(cls, prop: SchemaDict) -> Text | None:
        _MISSING = object()
        const_val = prop.get("const", _MISSING)
        if const_val is _MISSING:
            return None
        return Text(str(const_val), cls.Formatter.styles["schema.type"])

    @classmethod
    def _add_schema(
        cls, table: Table, obj: SchemaDict, *, def_key: str | None = None
    ) -> None:
        """Add a schema object's properties as rows in a Rich table."""
        title_val = obj.get("title")
        title = str(title_val) if isinstance(title_val, str) else (def_key or "Unknown")
        desc_val = obj.get("description")
        desc = str(desc_val) if isinstance(desc_val, str) else ""
        table.add_row(
            Text(title, style=cls.Formatter.styles["schema.title"]),
            "",
            Text(
                desc,
                style=cls.Formatter.styles["schema.description"],
            ),
        )
        props = obj.get("properties")
        if isinstance(props, dict):
            for name, prop in props.items():
                prop_desc = ""
                if isinstance(prop, dict):
                    desc_v = prop.get("description")
                    if isinstance(desc_v, str):
                        prop_desc = desc_v
                table.add_row(" ." + name, cls._type_repr(prop), prop_desc)
        elif isinstance(obj.get("enum"), list):
            enum_repr = cls._type_repr_enum(obj)
            if enum_repr is not None:
                table.add_row("", enum_repr, "")
        table.add_row("", "", "")

    @classmethod
    def _schema_table(cls, schema: SchemaDict) -> Table:
        """Build a Rich Table displaying the full JSON schema with definitions."""
        t = Table(
            box=None,
            padding=(0, 1),
            title_justify="left",
            caption_justify="left",
            show_header=False,
            show_edge=False,
            show_lines=False,
            show_footer=False,
            pad_edge=True,
        )
        S = cls.Formatter.styles
        t.add_column("Name", style=S["schema.name"], no_wrap=True)
        t.add_column("Type", style=S["schema.type"])
        t.add_column("Description", style=S["schema.description"])
        cls._add_schema(t, schema)
        defs = schema.get("$defs")
        if isinstance(defs, dict):
            value_defs = {
                k: v
                for k, v in defs.items()
                if isinstance(v, dict) and "properties" not in v
            }
            object_defs = {
                k: v
                for k, v in defs.items()
                if isinstance(v, dict) and "properties" in v
            }
            for k, v in object_defs.items():
                cls._add_schema(t, v, def_key=k)
            if value_defs:
                t.add_row(Text("where", style=S["schema.title"]), "", "")
                for k, v in value_defs.items():
                    t.add_row(" @" + k, cls._type_repr(v), "")
                t.add_row("", "", "")
        return t

    @classmethod
    def _path_syntax_table(cls) -> Table:
        """Build the path syntax reference table."""
        S = cls.Formatter.styles
        t = Table(
            box=box.ROUNDED,
            padding=(0, 1),
            title_justify="left",
            border_style=S["schema.border"],
            header_style=S["argparse.groups"],
            show_header=True,
            show_edge=False,
            show_lines=False,
            pad_edge=True,
        )
        t.add_column("Chunk", style=S["schema.name"], no_wrap=True)
        t.add_column("Syntax", style=S["schema.type"], no_wrap=True)
        t.add_column("Description", style=S["schema.description"])
        t.add_row("Root", "$", "Root object")
        t.add_row("Property", ".name", "Property by name")
        t.add_row("Index", escape("[n]"), "Array element by index")
        t.add_row("Key", escape('["k"]'), "Object property by key")
        t.add_row("Slice", escape("[start:end:step]"), "Array slice")
        return t

    @classmethod
    def _make_panel(cls, content: Table | Group, title: str) -> Panel:
        """Wrap content in a styled panel."""
        return Panel(
            content,
            title=title,
            title_align="left",
            border_style=cls.Formatter.styles["schema.border"],
            box=box.ROUNDED,
            padding=(2, 2),
        )

    @classmethod
    def _epilog(cls, schema: SchemaDict) -> Group:
        """Build the Rich epilog group containing schema and path syntax panels."""
        return Group(
            cls._make_panel(cls._schema_table(schema), "Schema"),
            Text(""),
            cls._make_panel(cls._path_syntax_table(), "Path Syntax"),
        )

    # ----- core helpers -----
    @staticmethod
    def _coerce_default(value: object) -> JsonValue:
        """Coerce a Pydantic field default to JsonValue."""
        if hasattr(value, "model_dump"):
            dumped: object = getattr(value, "model_dump")()
            if is_json_value(dumped):
                return dumped
            raise TypeError(
                f"model_dump() returned non-JsonValue: {type(dumped).__name__}"
            )
        if is_json_value(value):
            return copy.deepcopy(value)
        if hasattr(value, "__pydantic_fields__"):
            fields: dict[str, object] = getattr(value, "__pydantic_fields__")
            result: dict[str, JsonValue] = {}
            for k in fields:
                attr = getattr(value, k)
                if not is_json_value(attr):
                    raise TypeError(
                        f"Field {k!r} has non-JsonValue type: {type(attr).__name__}"
                    )
                result[k] = attr
            return result
        if hasattr(value, "value"):
            enum_val: object = getattr(value, "value")
            if is_json_value(enum_val):
                return enum_val
            raise TypeError(f"Enum .value is non-JsonValue: {type(enum_val).__name__}")
        raise TypeError(f"Cannot coerce {type(value).__name__} to JsonValue")

    @staticmethod
    def _get_model_defaults(model_type: type[object]) -> dict[str, JsonValue]:
        """Extract default values from a Pydantic model or dataclass."""
        defaults: dict[str, JsonValue] = {}

        fields_dict: dict[str, object] | None = None
        if hasattr(model_type, "model_fields"):
            fields_dict = getattr(model_type, "model_fields")
        elif hasattr(model_type, "__pydantic_fields__"):
            fields_dict = getattr(model_type, "__pydantic_fields__")

        if not fields_dict:
            return defaults

        for field_name, field_info in fields_dict.items():
            default: object = getattr(field_info, "default", PydanticUndefined)
            if default is not PydanticUndefined:
                defaults[field_name] = NanoArgs._coerce_default(default)
            else:
                factory = getattr(field_info, "default_factory", None)
                if factory is not None:
                    defaults[field_name] = NanoArgs._coerce_default(factory())

        return defaults

    def _build_arg_parser(self) -> argparse.ArgumentParser:
        """Create the argparse parser with config, override, and display args."""
        epilog = self._epilog(self.schema)
        p = argparse.ArgumentParser(
            prog=self._prog,
            formatter_class=self.Formatter,
            epilog=epilog,  # type: ignore[arg-type]  # RichHelpFormatter handles Group
            allow_abbrev=False,
        )
        if self._subcommands:
            # Subcommand mode: usage shows <command>, lists available commands
            choices_str = ", ".join(self._subcommands)
            p.usage = "%(prog)s [--override <path>=<value>] <command> ..."
            p.description = (
                f"Available commands: {choices_str}\n\n"
                "Pre-command: --override <path>=<value> sets parent fields.\n"
                "Post-command: config files and --override apply to the chosen command."
            )
            p.add_argument(
                "--override",
                action="append",
                default=None,
                metavar="<path>=<value>",
                help="Pre-command override for parent fields.",
            )
            p.add_argument(
                "--print-schema", action="store_true", help="Print JSON schema and exit"
            )
        else:
            p.add_argument(
                "config",
                type=str,
                nargs="*",
                metavar="<file>",
                help="Path to one or more config files (required unless --print-schema).",
            )
            p.add_argument(
                "--override",
                action="append",
                default=None,
                metavar="<path>=<value>",
                help="Repeatable override. Value may be JSON, YAML, or @file reference.",
            )
            p.add_argument(
                "--print-schema", action="store_true", help="Print JSON schema and exit"
            )
            p.add_argument(
                "--print-config",
                action="store_true",
                help="Print final merged config and exit",
            )
        return p

    def get_schema(self) -> SchemaDict:
        """Return the JSON schema dict for the model.

        For `Nested` models this returns the wrapper model's schema (with subcommand shapes
        in `$defs`). To print a specific subcommand's schema from the CLI, use:
            myapp <command> --print-schema
        """
        return self.schema

    def _collect_overrides_ordered(self, args: argparse.Namespace) -> list[str]:
        """Collect --override specs from parsed args."""
        return list(args.override or [])

    def parse(self, *, argv: Sequence[str] | None = None) -> _ModelT:
        """Parse configuration from YAML files and CLI arguments into a validated model.

        For regular (non-`Nested`) models the pipeline is:

        1. Parse argv with argparse (captures config files and `--override` specs).
        2. Load and deep-merge config files with model defaults.
        3. Apply `--override` CLI overrides in order.
        4. Validate the merged dict with Pydantic and return the model instance.

        For `Nested` subcommand models the pipeline is recursive:

        1. Scan argv for the command name (first non-flag token matching a known command).
        2. Apply pre-command overrides to parent `Nested` fields.
        3. Delegate post-command argv to the selected child `NanoArgs` instance.
        4. Assemble and validate the full parent model.

        Args:
            argv: Argument list. Defaults to `sys.argv[1:]`.

        Returns:
            A validated instance of `_ModelT` (the model passed to `__init__`).

        Raises:
            SystemExit(0): On `--help`, `--print-schema`, `--print-config`.
            SystemExit(2): On missing/invalid arguments.
            pydantic.ValidationError: If the merged config fails Pydantic validation.
        """
        if self._subcommands:
            return self._parse_subcommand(argv)

        args = self.parser.parse_args(list(argv) if argv is not None else None)

        # Handle --print-schema early (no config files needed)
        if args.print_schema:
            Console().print(Pretty(self.schema))
            raise SystemExit(0)

        # Require config files if not using --print-config
        if not args.config and not args.print_config:
            self.parser.error("the following arguments are required: <file>")

        override_specs = self._collect_overrides_ordered(args)

        data = load_and_merge(
            args.config or [],
            copy.deepcopy(self._cached_defaults),
            override_specs,
        )

        validated = self.adapter.validate_python(data)

        if args.print_config:
            Console().print(Pretty(self.adapter.dump_python(validated)))
            raise SystemExit(0)

        return validated

    def _split_subcommand_argv(
        self, raw: list[str]
    ) -> tuple[list[str], str, list[str]]:
        """Scan argv for the first token matching a known command name.

        Pre-command positionals (non-flags not matching a command) are an error.
        Display flags (--help, --print-schema) with no command found raise SystemExit.
        Returns (pre_argv, command, sub_argv).
        """
        assert self._subcommands is not None
        i = 0
        while i < len(raw):
            arg = raw[i]
            if arg in self._subcommands:
                return raw[:i], arg, raw[i + 1 :]
            if not arg.startswith("-"):
                choices = ", ".join(repr(c) for c in self._subcommands)
                self.parser.error(
                    f"unexpected positional argument before command: {arg!r}. "
                    f"Config files must come after the command. "
                    f"Usage: {self.parser.prog} <command> [config.yaml] [flags] "
                    f"(available commands: {choices})"
                )
            # --override takes the next token as its value — skip it
            if arg == "--override" and i + 1 < len(raw):
                i += 2
            else:
                i += 1
        # No command found — handle display flags or error
        if "--help" in raw or "-h" in raw:
            self.parser.print_help()
            raise SystemExit(0)
        if "--print-schema" in raw:
            Console().print(Pretty(self.schema))
            raise SystemExit(0)
        self.parser.error("the following arguments are required: <command>")

    def _parse_subcommand(self, argv: Sequence[str] | None) -> _ModelT:
        """Dispatch subcommand parse recursively.

        Splits `argv` at the command token, applies pre-command overrides to parent
        fields, delegates post-command argv to the cached child `NanoArgs`, then
        assembles and validates the full parent model.
        """
        raw = list(argv) if argv is not None else sys.argv[1:]
        assert self._subcommands is not None

        pre_argv, command, sub_argv = self._split_subcommand_argv(raw)

        # Pre-command display flags (command found but flags precede it)
        if "--help" in pre_argv or "-h" in pre_argv:
            self.parser.print_help()
            raise SystemExit(0)
        if "--print-schema" in pre_argv:
            Console().print(Pretty(self.schema))
            raise SystemExit(0)
        if "--print-config" in pre_argv:
            self.parser.error(
                f"--print-config requires a command: "
                f"{self.parser.prog} <command> <file> --print-config"
            )

        # Parse pre_argv for parent-level overrides using the subcommand parser
        args = self.parser.parse_args(pre_argv)
        override_specs = self._collect_overrides_ordered(args)

        # Apply pre-command overrides to parent non-subcommand defaults only
        subcommand_names = set(self._subcommands.keys())
        parent_defaults = copy.deepcopy(
            {
                k: v
                for k, v in self._cached_defaults.items()
                if k not in subcommand_names
            }
        )
        parent_data = load_and_merge([], parent_defaults, override_specs)

        # Recursive child dispatch using cached child NanoArgs
        child_result = self._children[command].parse(argv=sub_argv)

        # Assemble full payload
        payload: dict[str, object] = {k: None for k in self._subcommands}
        if isinstance(parent_data, dict):
            payload.update(
                {k: v for k, v in parent_data.items() if k not in subcommand_names}
            )
        payload[command] = child_result
        return self.adapter.validate_python(payload)
