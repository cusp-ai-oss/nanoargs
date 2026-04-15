# NanoArgs

A tiny, opinionated configuration loader and CLI framework built around Pydantic models.

## Features

- **YAML Configuration Loading** — load and merge multiple files with left-to-right precedence
- **Smart Imports** — `!import` with deep-merging, paths resolved relative to the importing file
- **Runtime Overrides** — JSONPath-like syntax via `--override`
- **Pydantic Validation** — automatic validation and type coercion
- **Schema Generation** — `--print-schema` renders a formatted JSON schema; `--print-config` dumps the merged result
- **Rich CLI Interface** — styled help, errors, and schema output via Rich
- **Subcommands** — multi-command CLIs via `Nested`; each command owns its own config model
- **Type Safety** — pyright strict, modern Python type hints

## Installation

```bash
pip install git+https://github.com/cusp-ai-oss/nanoargs.git
```

Requires Python 3.10+. Dependencies: `lark`, `pydantic`, `pyyaml`, `rich`, `rich-argparse`.

## Quick Start

```python
from pydantic import BaseModel
from nanoargs import NanoArgs

class Config(BaseModel):
    mode: str = "train"
    batch_size: int = 32
    learning_rate: float = 0.001

config = NanoArgs(Config).parse()
```

```bash
python app.py config.yaml                                    # load a YAML file
python app.py base.yaml exp.yaml                             # merge multiple files
python app.py config.yaml --override '$.batch_size=128'      # JSONPath override
echo 'batch_size: 128' | python app.py -                     # read from stdin
python app.py --print-schema                                 # inspect the schema
python app.py config.yaml --print-config                     # inspect merged result
```

## Subcommands

Use `Nested` to define multi-command CLIs. Fields typed as `T | None = None` become subcommands:

```python
from nanoargs import NanoArgs, Nested

class TrainConfig(BaseModel):
    lr: float = 0.001
    epochs: int = 10

class EvalConfig(BaseModel):
    checkpoint: str

class CLI(Nested):
    verbose: bool = False          # pre-command parent field
    train: TrainConfig | None = None
    evaluate: EvalConfig | None = None

result = NanoArgs(CLI).parse()
```

```bash
python app.py train config.yaml --override '$.lr=0.01'
python app.py --override '$.verbose=true' evaluate config.yaml
python app.py --help                   # lists available commands
python app.py train --print-schema     # schema for a specific command
```

`Nested` composes naturally — a field whose type is itself `Nested` creates a sub-group (`app data preprocess config.yaml`).

See the [Subcommands guide](docs/subcommands.md) for full details.

## Documentation

- [Getting Started](docs/getting-started.md) — full walkthrough
- [Configuration Guide](docs/configuration.md) — import system, merge rules, override syntax, CLI flags
- [Subcommands](docs/subcommands.md) — `Nested` patterns, parent fields, multi-level nesting
- [Path Syntax](docs/path-syntax.md) — JSONPath-like grammar reference
- [API Reference](docs/api/cli.md)
- [Changelog](docs/changelog.md)

## Gotchas

- **YAML booleans in config files**: `yes`, `no`, `on`, `off` are booleans in YAML. Quote them for strings: `"yes"`. This does *not* affect `--override` values.
- **List merging**: config file merging replaces lists entirely — it does not append.
- **Hyphenated keys**: `--override` paths require bracket syntax: `--override '$["learning-rate"]=0.001'`.
- **Negative array indices**: `$[-1]` works Python-style (last element). Negative slice bounds are also supported: `$[-3:]`, `$[:-1]`.
- **Bracket notation quotes**: both `$["key"]` and `$['key']` are supported.
- **`--print-config` without config files**: prints Pydantic-validated defaults and exits.
- **Unknown fields**: overriding a path that doesn't match any model field is silently ignored by Pydantic.
- **Auto-vivification**: `$.a.b.c=1` creates intermediate dicts for missing keys or `None` values.
- **`@file` resolution**: from the CLI, `@file` resolves relative to the working directory; inside YAML (`!override`), relative to the YAML file. Use `@@` to escape a literal `@`.

## License

MIT
