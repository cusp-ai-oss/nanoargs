# Configuration Guide

## Configuration Merging

NanoArgs merges configuration files left to right:

1. Start with model defaults
2. Load each config file and **deep-merge** (nested dicts are merged recursively; non-dict values are replaced)
3. Apply CLI overrides in order
4. Validate against the Pydantic model

## Import System

The `!import` directive loads a single external YAML file, its path resolved relative to the importing file. Both the scalar form (`!import file.yaml`) and the one-element sequence form (`!import [file.yaml]`) are accepted; combining several files is `!merge`'s job.

### Document-Level Import

```yaml
!import base.yaml
```

### Field-Level Import

Imports into a specific key:

```yaml
app_name: myapp
version: 1.0.0
database: !import [database.yaml]
settings: !import [settings.yaml]
```

### Relative Path Resolution

If `/path/to/config.yaml` contains:

```yaml
database: !import ["subdir/db.yaml"]
```

Then `subdir/db.yaml` is resolved relative to `/path/to/`, not the current working directory.

### Circular Import Detection

NanoArgs detects circular imports and raises a clear error. Import tracking is thread-local so concurrent loads are safe.

## Merge System (`!merge`)

The `!merge` directive deep-merges a sequence of mappings left to right — later entries win. Entries can be `!import` results, inline mappings, or any mix, which makes "import a file, then tweak a few values" a one-liner:

```yaml
model: !merge
  - !import [models/base.yaml]
  - hidden: 64
    dropout: 0.1
```

Combining several files is the same pattern — one `!import` per file:

```yaml
!merge
  - !import [database.yaml]
  - !import [logging.yaml]
```

Rules:

- Every entry must be a mapping; anything else raises an error naming the position.
- `None` entries (e.g. an `!import` of an empty file) are skipped.
- Deep merge: nested dicts merge recursively, other values are replaced.

## Override System

### In YAML (`!override`)

The `!override` directive applies JSONPath overrides within a YAML file:

```yaml
config: !override
  - !import ["base.yaml"]
  - ["$.training.batch_size=128", "$.model.layers=24"]
```

### From the CLI (`--override`)

```bash
python app.py base.yaml \
  --override '$.batch_size=128' \
  --override '$.model.layers=24'
```

## Override Value Formats

Values are parsed in this order:

| Format | Example | Result |
|--------|---------|--------|
| JSON literal | `128`, `true`, `null`, `"hello"` | Parsed JSON value |
| YAML structure | `{type: transformer}`, `[1, 2]` | Parsed YAML (only `{`/`[` forms) |
| File reference | `@model.yaml` | Loaded file content |
| Escaped `@` | `@@user` | Literal string `"@user"` |
| Plain string | `train` | Raw string `"train"` |

!!! note
    Bare values like `yes`, `no`, `0777` are treated as **plain strings** in CLI overrides, not coerced by YAML. JSON keywords (`true`/`false`/`null`) *are* parsed. Use quoted JSON (`"\"true\""`) if you need the literal string.

## File References (`@file`)

Override values starting with `@` load a file:

```bash
--override '$.model=@configs/large_model.yaml'
```

- `.yaml` / `.yml` files are loaded with NanoArgs (supporting `!import`)
- `.json` files are parsed as JSON
- Other extensions try JSON, then fall back to plain text
- `@@` escapes a literal `@` prefix

From the CLI, `@file` paths resolve relative to the **current working directory**. Inside YAML files (`!override`), they resolve relative to the **YAML file's directory**.

## CLI Flags Reference

| Flag | Description |
|------|-------------|
| `<file> [<file> ...]` | Config files to load and merge (positional) |
| `-` (positional) | Read config from stdin (YAML or JSON) |
| `--override <path>=<value>` | JSONPath override (repeatable) |
| `--print-schema` | Print JSON schema and exit (no config files required) |
| `--print-config` | Print final merged config and exit (no config files required) |
| `-h`, `--help` | Print help and exit |

## Schema Display

`--print-schema` renders a human-readable table of the model's JSON schema. Understanding its notation helps when working with complex types.

### Field type column

Each field's type is rendered compactly:

| Schema type | Display |
|-------------|---------|
| `string` | `string` |
| `integer` | `integer` |
| `array` | `[*: <item-type>]` |
| `object` (dict) | `{*: <value-type>}` |
| `anyOf` / `oneOf` | `typeA \| typeB` |
| enum values | `val1 \| val2 \| val3` |
| `$ref` to a definition | `@TypeName` |

### The `where` legend

When a field's type is defined in `$defs` (e.g. an `Enum`, a `TypeAliasType`, or a `Literal` alias), the field column shows `@TypeName`. The actual expanded type appears in a `where` block at the bottom of the schema panel:

```
Config
 .mode   @Mode
 .lr     number

where
 @Mode   train | eval
```

This means `.mode` is of type `Mode`, which expands to `train | eval`.

Nested model types (those with their own fields) are rendered as a separate titled sub-section rather than in the `where` block:

```
App
 .train     @TrainConfig
 .evaluate  @EvalConfig

TrainConfig
 .data_path  string
 .epochs     integer

EvalConfig
 .checkpoint  string
```

### Single-value `Literal`

A `Literal["yes"]` alias renders as `yes` (the value itself) rather than `string`, since
`_type_repr_const` fires before `_type_repr_type`.

## Subcommands

Use `Nested` to build multi-command CLIs where each subcommand has its own Pydantic config model.

### Defining Subcommands

```python
from nanoargs import NanoArgs, Nested

class TrainConfig(BaseModel):
    lr: float = 0.001

class EvalConfig(BaseModel):
    checkpoint: str

class CLI(Nested):
    train: TrainConfig | None = None    # subcommand
    evaluate: EvalConfig | None = None  # subcommand

cli = NanoArgs(CLI)
result = cli.parse(argv=["train", "config.yaml"])
# result: CLI(train=TrainConfig(...), evaluate=None) — fully typed
```

Fields typed as `ChildModel | None = None` are detected as subcommands. All other fields
on the `Nested` model are regular parent config fields.

### CLI Grammar

```
app [pre-command-overrides] <command> [config-files] [--override ...]
```

- **Pre-command overrides** apply to parent-level fields (e.g. `--override '$.verbose=true'`)
- **Post-command** config files and overrides apply to the selected child model

```bash
# CLI.verbose applies to CLI, $.lr applies to TrainConfig
python app.py --override '$.verbose=true' train config.yaml --override '$.lr=0.01'
```

### Subcommand Display

```bash
# List available commands
python app.py --help

# Print schema for the full CLI (shows all subcommand shapes)
python app.py --print-schema

# Print schema for a specific command
python app.py train --print-schema

# Print merged config for a specific command
python app.py train config.yaml --print-config
```

### Nesting

A `Nested` field inside a `Nested` creates nested subcommands naturally:

```python
class DataCommands(Nested):
    preprocess: PreprocessConfig | None = None

class CLI(Nested):
    train: TrainConfig | None = None
    data: DataCommands | None = None
```

```bash
python app.py data preprocess config.yaml
```

### Rules

- Subcommand fields must be typed as `T | None = None` (Optional with a default of `None`)
- A `Nested` class with no detectable subcommand fields raises `ValueError` at construction
- Pydantic dataclasses are supported in addition to `BaseModel` subclasses
- `Annotated[T, Field(...)] | None = None` is also supported

## Gotchas

- **YAML booleans in config files**: `yes`, `no`, `on`, `off` are booleans in YAML config files. Quote them for strings: `"yes"`.
- **List merging**: Lists are replaced entirely, not appended.
- **Hyphenated keys**: In `--override` paths, use bracket syntax: `$["learning-rate"]`.
- **Negative array indices**: `$[-1]` works (Python-style last element). Use slices for end-relative access: `$[-1:]`.
- **Bracket notation quotes**: both `$["key"]` and `$['key']` are supported.
- **Auto-vivification**: Setting `$.a.b.c=1` creates intermediate dicts for missing keys or `None` values.
- **Unknown fields**: Overriding a path that doesn't match any model field is silently ignored by Pydantic (Pydantic discards extra keys by default).
