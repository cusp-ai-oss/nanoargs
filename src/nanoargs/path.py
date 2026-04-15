# Copyright 2024-2026 Cusp AI
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json as _json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import TypeAlias, TypeGuard, overload

import lark
from lark import Token, Transformer

IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

PATH_GRAMMAR = r"""

// path types
path: ROOT path_component*

// path components
ROOT: "$"
property_accessor: "." name
index_accessor: "[" index_like "]"
?path_component: property_accessor
               | index_accessor

// index components — negative integers resolve Python-style
?index_like: string
           | slice
           | integer
name: /[a-zA-Z_][a-zA-Z0-9_]*/
slice: slice_start ":" slice_end (":" slice_step)?
slice_start: (integer)?
slice_end: (integer)?
?slice_step: (integer)?

// terminals
string: ESCAPED_STRING | SINGLE_QUOTED_STRING
SINGLE_QUOTED_STRING: "'" /[^']*/ "'"
integer: SIGNED_INT

// imports
%import common.ESCAPED_STRING
%import common.SIGNED_INT
"""

parser = lark.Lark(PATH_GRAMMAR, start="path", parser="lalr")


# Recursive type for JSON-like data structures
JsonValue: TypeAlias = (
    dict[str, "JsonValue"]
    | list["JsonValue"]
    | tuple["JsonValue", ...]
    | str
    | int
    | float
    | bool
    | None
)


def is_json_value(value: object) -> TypeGuard[JsonValue]:
    """TypeGuard for narrowing object to JsonValue."""
    return (
        isinstance(value, (dict, list, tuple, str, int, float, bool)) or value is None
    )


@dataclass(frozen=True)
class Root:
    """Root ($) of a JSON path."""

    def to_string(self) -> str:
        return "$"


@dataclass(frozen=True)
class Property:
    """Named property access (.name or ["name"]) in a JSON path."""

    name: str

    def to_string(self) -> str:
        if IDENTIFIER_RE.match(self.name):
            return f".{self.name}"
        return f"[{_json.dumps(self.name)}]"


@dataclass(frozen=True)
class NumericIndex:
    """Numeric index access ([n]) in a JSON path."""

    value: int

    def to_string(self) -> str:
        return f"[{self.value}]"


@dataclass(frozen=True)
class SliceIndex:
    """Slice access ([start:end:step]) in a JSON path."""

    start: int | None
    end: int | None
    step: int | None

    def to_string(self) -> str:
        start = "" if self.start is None else str(self.start)
        end = "" if self.end is None else str(self.end)
        step = "" if self.step is None else str(self.step)

        if self.step is not None:
            return f"[{start}:{end}:{step}]"
        else:
            return f"[{start}:{end}]"


Chunk: TypeAlias = Root | Property | NumericIndex | SliceIndex


def _propagate(
    new_val: JsonValue,
    stack: list[tuple[JsonValue, str | int]],
    data: JsonValue,
) -> JsonValue:
    """Propagate a replaced node to its parent or update the data root.

    Returns the (possibly updated) data root.
    """
    if stack:
        parent, key = stack[-1]
        if isinstance(parent, dict) and isinstance(key, str):
            parent[key] = new_val
        elif isinstance(parent, list) and isinstance(key, int):
            parent[key] = new_val
        return data
    return new_val


def _collect_concrete(
    chunks: tuple[Chunk, ...],
) -> list[Property | NumericIndex | SliceIndex]:
    """Collect non-Root chunks as concrete path steps."""
    return [c for c in chunks if not isinstance(c, Root)]  # type: ignore[return-value]


_NavState = tuple[JsonValue, JsonValue, list[tuple[JsonValue, str | int]]]


def _nav_property(
    name: str,
    current: JsonValue,
    data: JsonValue,
    stack: list[tuple[JsonValue, str | int]],
) -> tuple[JsonValue, JsonValue]:
    """Navigate into a dict property, auto-vivifying None and missing keys."""
    current, data = _autovivify(current, stack, data)
    if name not in current:
        current[name] = {}
    stack.append((current, name))
    return current[name], data


def _autovivify(
    current: JsonValue,
    stack: list[tuple[JsonValue, str | int]],
    data: JsonValue,
) -> tuple[dict[str, JsonValue], JsonValue]:
    """Ensure current is a dict, creating one when current is None."""
    if current is None:
        current = dict[str, JsonValue]()
        data = _propagate(current, stack, data)
    if not isinstance(current, dict):
        raise TypeError(
            f"Property can only be applied to objects, applied to {current!r}"
        )
    return current, data


def _nav_index(
    idx: int,
    current: JsonValue,
    data: JsonValue,
    stack: list[tuple[JsonValue, str | int]],
) -> tuple[JsonValue, JsonValue]:
    """Navigate into a list by numeric index, converting tuples to lists."""
    if not isinstance(current, (list, tuple)):
        raise TypeError(
            f"NumericIndex can only be applied to arrays, applied to {current!r}"
        )
    lst, data = _ensure_list(current, stack, data)
    idx = _resolve_index(idx, len(lst), "NumericIndex")
    stack.append((lst, idx))
    return lst[idx], data


def _navigate_to_parent(
    concrete: list[Property | NumericIndex | SliceIndex],
    data: JsonValue,
) -> _NavState:
    """Walk concrete[:-1] to reach the parent of the final chunk."""
    stack: list[tuple[JsonValue, str | int]] = []
    current: JsonValue = data
    for chunk in concrete[:-1]:
        match chunk:
            case Property(name):
                current, data = _nav_property(name, current, data, stack)
            case NumericIndex(idx):
                current, data = _nav_index(idx, current, data, stack)
            case SliceIndex():
                raise TypeError(
                    "SliceIndex is only supported as the last path component in modify"
                )
    return current, data, stack


def _ensure_list(
    current: list[JsonValue] | tuple[JsonValue, ...],
    stack: list[tuple[JsonValue, str | int]],
    data: JsonValue,
) -> tuple[list[JsonValue], JsonValue]:
    """Convert tuple to list if needed, propagating the change."""
    if isinstance(current, tuple):
        current = list(current)
        data = _propagate(current, stack, data)
    return current, data


def _apply_property(
    name: str,
    current: JsonValue,
    value: JsonValue,
    stack: list[tuple[JsonValue, str | int]],
    data: JsonValue,
) -> JsonValue:
    current, data = _autovivify(current, stack, data)
    current[name] = value
    return data


def _apply_index(
    idx: int,
    current: JsonValue,
    value: JsonValue,
    stack: list[tuple[JsonValue, str | int]],
    data: JsonValue,
) -> JsonValue:
    if not isinstance(current, (list, tuple)):
        raise TypeError(
            f"NumericIndex can only be applied to arrays, applied to {current!r}"
        )
    lst, data = _ensure_list(current, stack, data)
    idx = _resolve_index(idx, len(lst), "NumericIndex")
    lst[idx] = value
    return data


def _apply_slice(
    start: int | None,
    end: int | None,
    step: int | None,
    current: JsonValue,
    value: JsonValue,
    stack: list[tuple[JsonValue, str | int]],
    data: JsonValue,
) -> JsonValue:
    if not isinstance(current, (list, tuple)):
        raise TypeError(
            f"SliceIndex can only be applied to arrays, applied to {current!r}"
        )
    lst, data = _ensure_list(current, stack, data)
    if not isinstance(value, (list, tuple)):
        raise TypeError(
            f"SliceIndex can only be set with a list or tuple, got {value!r}"
        )
    indices = tuple(range(*slice(start, end, step).indices(len(lst))))
    if len(indices) != len(value):
        raise ValueError(
            f"Cannot set slice of length {len(indices)} with value of length {len(value)}"
        )
    for i, v in zip(indices, value):
        lst[i] = v
    return data


def _apply_final(
    last: Property | NumericIndex | SliceIndex,
    current: JsonValue,
    value: JsonValue,
    stack: list[tuple[JsonValue, str | int]],
    data: JsonValue,
) -> JsonValue:
    """Apply the value at the final path chunk. Returns (possibly updated) data root."""
    match last:
        case Property(name):
            return _apply_property(name, current, value, stack, data)
        case NumericIndex(idx):
            return _apply_index(idx, current, value, stack, data)
        case SliceIndex(start, end, step):
            return _apply_slice(start, end, step, current, value, stack, data)
    return data


def _extract_property(name: str, data: JsonValue) -> JsonValue:
    """Extract a property from a dict."""
    if not isinstance(data, dict):
        raise TypeError(f"Property can only be applied to objects, applied to {data!r}")
    if name not in data:
        raise KeyError(f"Property {name} not found in object {data!r}")
    return data[name]


def _extract_index(idx: int, data: JsonValue) -> JsonValue:
    """Extract an element by numeric index."""
    if not isinstance(data, (list, tuple)):
        raise TypeError(
            f"NumericIndex can only be applied to arrays, applied to {data!r}"
        )
    idx = _resolve_index(idx, len(data), "NumericIndex")
    return data[idx]


def _require_sequence(
    data: JsonValue, label: str
) -> list[JsonValue] | tuple[JsonValue, ...]:
    """Validate data is a list/tuple, raise TypeError otherwise."""
    if not isinstance(data, (list, tuple)):
        raise TypeError(f"{label} can only be applied to arrays, applied to {data!r}")
    return data


def _resolve_index(index: int, length: int, label: str = "Index") -> int:
    """Resolve a (possibly negative) index Python-style. Raises IndexError if OOB."""
    if index < 0:
        index += length
    if index < 0 or index >= length:
        raise IndexError(f"{label} {index} out of bounds for array of length {length}")
    return index


@dataclass(frozen=True)
class Path:
    """Immutable sequence of chunks representing a JSON path expression (e.g. $.foo[0])."""

    chunks: tuple[Chunk, ...]

    def to_string(self) -> str:
        """Serialize this path to string form."""
        return "".join(c.to_string() for c in self.chunks)

    def __len__(self) -> int:
        return len(self.chunks)

    @overload
    def __getitem__(self, index: int) -> Chunk: ...

    @overload
    def __getitem__(self, index: slice) -> Path: ...

    def __getitem__(self, index: int | slice) -> Chunk | Path:
        if isinstance(index, int):
            return self.chunks[index]
        return Path(self.chunks[index])

    def __add__(self, other: Path) -> Path:
        # Strip Root from other when self is non-empty to avoid double Root
        other_chunks = other.chunks
        if self.chunks and other_chunks and isinstance(other_chunks[0], Root):
            other_chunks = other_chunks[1:]
        return Path(self.chunks + other_chunks)

    @property
    def is_empty(self) -> bool:
        return len(self) == 0

    @property
    def head(self) -> Chunk:
        if self.is_empty:
            raise IndexError("Path is empty")
        return self.chunks[0]

    @property
    def tail(self) -> Path:
        return Path(self.chunks[1:])

    @staticmethod
    def from_string(s: str) -> Path:
        """Parse a path string (e.g. '$.foo[0]') into a Path object. Results are cached."""
        return _parse_path_cached(s)

    def extract(self, data: JsonValue) -> JsonValue:
        """Extract the value at this path from the given data structure."""
        for i, chunk in enumerate(self.chunks):
            tail = Path(self.chunks[i + 1 :])
            match chunk:
                case Root():
                    continue
                case Property(name):
                    data = _extract_property(name, data)
                case NumericIndex(value):
                    data = _extract_index(value, data)
                case SliceIndex(start, end, step):
                    seq = _require_sequence(data, "SliceIndex")
                    return tuple(tail.extract(v) for v in seq[slice(start, end, step)])
                case _:
                    raise ValueError(f"Unknown path chunk: {chunk}")
        return data

    def modify(self, data: JsonValue, value: JsonValue) -> JsonValue:
        """Return a modified copy of data with the value at this path replaced."""
        if self.is_empty:
            return value
        concrete = _collect_concrete(self.chunks)
        if not concrete:
            return value
        current, data, stack = _navigate_to_parent(concrete, data)
        return _apply_final(concrete[-1], current, value, stack, data)


class PathTransformer(Transformer[Token, Path]):
    """Lark transformer that converts parse trees into Path objects."""

    def path(self, items: list[Chunk]) -> Path:
        return Path(tuple(items))

    def ROOT(self, items: str) -> Root:
        return Root()

    def property_accessor(self, items: list[str]) -> Property:
        (name,) = items
        return Property(name)

    def index_accessor(self, items: list[str | SliceIndex | int]) -> Chunk:
        (index_like,) = items
        if isinstance(index_like, str):
            return Property(index_like)
        elif isinstance(index_like, SliceIndex):
            return index_like
        else:
            return NumericIndex(index_like)

    def slice(self, items: list[int | None]) -> SliceIndex:
        if len(items) == 2:
            start, end = items
            step = None
        elif len(items) == 3:
            start, end, step = items
        else:
            raise ValueError("Invalid slice")
        if step == 0:
            raise ValueError("Slice step cannot be zero")
        return SliceIndex(start, end, step)

    def slice_start(self, items: list[int]) -> int | None:
        if len(items) == 0:
            return None
        (start,) = items
        return start

    def slice_end(self, items: list[int]) -> int | None:
        if len(items) == 0:
            return None
        (end,) = items
        return end

    def slice_step(self, items: list[int]) -> int | None:
        if len(items) == 0:
            return None
        (step,) = items
        return step

    def string(self, s: list[Token]) -> str:
        (s_val,) = s
        raw = str(s_val)
        if raw.startswith("'"):
            return raw[1:-1]
        return _json.loads(raw)

    def name(self, n: list[Token]) -> str:
        (n_val,) = n
        return str(n_val)

    def integer(self, n: list[Token]) -> int:
        (n_val,) = n
        return int(str(n_val))


_transformer = PathTransformer()


@lru_cache(maxsize=1024)
def _parse_path_cached(s: str) -> Path:
    try:
        result = _transformer.transform(parser.parse(s))  # pyright: ignore[reportUnknownMemberType]
    except lark.exceptions.LarkError as e:
        # Provide helpful hints for common mistakes
        hints: list[str] = []
        hint_str = " ".join(hints)
        detail = str(e)
        raise ValueError(
            f"Invalid path syntax: {s!r}. "
            f'Use $.prop for properties, $["key"] for keys with special characters. '
            f"{hint_str}"
            f"Details: {detail}"
        ) from e
    assert isinstance(result, Path)
    return result
