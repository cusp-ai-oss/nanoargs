# Path & Chunks

## Path

::: nanoargs.path.Path
    options:
      members:
        - from_string
        - extract
        - modify
        - to_string
        - is_empty
        - chunks
      show_root_heading: true
      show_source: false

## Chunk Types

::: nanoargs.path.Root
    options:
      show_root_heading: true
      show_source: false

::: nanoargs.path.Property
    options:
      show_root_heading: true
      show_source: false

::: nanoargs.path.NumericIndex
    options:
      show_root_heading: true
      show_source: false

::: nanoargs.path.SliceIndex
    options:
      show_root_heading: true
      show_source: false

## Utilities

::: nanoargs.path.is_json_value
    options:
      show_root_heading: true
      show_source: false

## Types

`JsonValue` is a recursive type alias:

```python
JsonValue = (
    dict[str, JsonValue]
    | list[JsonValue]
    | tuple[JsonValue, ...]
    | str | int | float | bool | None
)
```

`Chunk` is a union of all chunk types:

```python
Chunk = Root | Property | NumericIndex | SliceIndex
```
