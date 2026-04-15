# Path Syntax

NanoArgs uses a JSONPath-inspired syntax for navigating and modifying nested data structures.

## Grammar Reference

| Chunk | Syntax | Description |
|-------|--------|-------------|
| Root | `$` | Root object (required prefix) |
| Property | `.name` | Property by identifier |
| Key | `["name"]` or `['name']` | Property by quoted key (single or double quotes) |
| Index | `[n]` | Array element by integer (negative indices supported: `$[-1]` = last) |
| Slice | `[start:end:step]` | Array slice (all parts optional; negative bounds supported) |

### Examples

```
$                       # root
$.name                  # top-level property
$.model.layers          # nested property
$.items[0]              # first array element
$.items[-1]             # last array element
$.items[0].name         # property of first element
$["complex-key"]        # key with special characters (double quotes)
$['complex-key']        # same, single quotes also work
$[0:3]                  # first three elements
$[::2]                  # every other element
$[-3:]                  # last three elements
$[:-1]                  # all but last
```

## Operations

### Extract

Reads the value at a path. Returns the value directly for property/index paths; returns a tuple of matched values for slice paths.

```python
from nanoargs.path import Path

data = {"items": [{"name": "a"}, {"name": "b"}]}

Path.from_string("$.items[0].name").extract(data)
# "a"

Path.from_string("$.items[0:2]").extract(data)
# ({"name": "a"}, {"name": "b"})

Path.from_string("$.items[-1]").extract(data)
# {"name": "b"}
```

### Modify

Sets or replaces values at a path. Returns a new data structure (never mutates in-place for dicts; lists are converted to lists if they were tuples).

```python
data = {"x": 1, "y": 2}

Path.from_string("$.x").modify(data, 10)
# {"x": 10, "y": 2}

Path.from_string("$.items[0]").modify({"items": [1, 2, 3]}, 99)
# {"items": [99, 2, 3]}

Path.from_string("$.items[-1]").modify({"items": [1, 2, 3]}, 99)
# {"items": [1, 2, 99]}
```

**Auto-vivification**: Setting a deeply nested path creates intermediate dicts for missing keys or `None` values:

```python
Path.from_string("$.a.b.c").modify({}, 1)
# {"a": {"b": {"c": 1}}}
```

## Override paths must be concrete

A **concrete** path addresses exactly one location (properties and indices only). A **non-concrete** path contains slices and can match multiple locations.

`--override` specs must be concrete — slices are not allowed in override paths.

## Utilities

### `is_json_value`

Type guard that checks if a Python object is a valid `JsonValue` (dict, list, tuple, str, int, float, bool, or None):

```python
from nanoargs.path import is_json_value

is_json_value({"a": 1})   # True
is_json_value({1, 2})     # False (set)
```
