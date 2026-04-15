# CLI API

The `nanoargs.cli` module exposes two public classes:

- **`NanoArgs`** — the main entry point. Wraps a Pydantic model and provides `parse()` and `get_schema()`.
- **`Nested`** — a `BaseModel` subclass that enables multi-command CLIs. Fields typed as `T | None = None` become selectable subcommands.

Both are importable directly from `nanoargs`:

```python
from nanoargs import NanoArgs, Nested
```

---

## `NanoArgs`

::: nanoargs.cli.NanoArgs
    options:
      members:
        - __init__
        - parse
        - get_schema
      show_root_heading: true
      show_source: false

## `Nested`

::: nanoargs.cli.Nested
    options:
      show_root_heading: true
      show_source: false
      show_bases: true
