# NanoArgs

A tiny, opinionated configuration loader and CLI framework built around Pydantic models.

NanoArgs provides a clean interface for loading YAML configuration files with advanced features like imports, overrides, JSONPath-like syntax for value modification, and multi-command CLIs via `Nested` subcommands.

## Features

- **YAML Configuration Loading** -- Load and merge multiple YAML files with left-to-right precedence
- **Smart Imports** -- Use `!import` directives with deep-merging and paths resolved relative to the importing file
- **Runtime Overrides** -- Apply point overrides using JSONPath-like syntax via CLI flags
- **Pydantic Validation** -- Automatic validation and type conversion using your Pydantic models
- **Schema Generation** -- Auto-generated JSON schema output with beautiful formatting
- **Rich CLI Interface** -- Beautiful help messages and error output using Rich
- **Subcommands** -- Multi-command CLIs via the `Nested` base class; each command owns its own config model
- **Type Safety** -- Full type safety with modern Python type hints, pyright strict

## Installation

```bash
# Install from GitHub
pip install git+https://github.com/cusp-ai-oss/nanoargs.git

# Or install from local clone
git clone https://github.com/cusp-ai-oss/nanoargs.git
cd nanoargs
pip install -e .
```

## Requirements

- Python 3.10+
- Dependencies: `lark`, `pydantic`, `pyyaml`, `rich`, `rich-argparse`

## Quick Example

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
python app.py config.yaml --override '$.batch_size=128'
```

Multi-command CLI with `Nested`:

```python
from nanoargs import NanoArgs, Nested

class TrainConfig(BaseModel):
    lr: float = 0.001

class EvalConfig(BaseModel):
    checkpoint: str

class CLI(Nested):
    train: TrainConfig | None = None
    evaluate: EvalConfig | None = None

result = NanoArgs(CLI).parse()
# result.train or result.evaluate is populated based on the selected command
```

```bash
python app.py train config.yaml --override '$.lr=0.01'
python app.py evaluate config.yaml
```

See the [Getting Started](getting-started.md) guide for a full walkthrough.
