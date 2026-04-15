# Subcommands (Nested)

## Overview

`Nested` turns a single NanoArgs CLI into a multi-command interface where each subcommand has its own Pydantic model. Use it when you want separate configurations per command (e.g., `train`, `evaluate`) while keeping a shared entrypoint. If your CLI is a single config model with no subcommands, stick to a normal `NanoArgs(BaseModel)` for simpler usage.

## Basic Example

A minimal two-command CLI with `train` and `evaluate`.

**app.py**:

```python
from pydantic import BaseModel
from nanoargs import NanoArgs, Nested

class TrainConfig(BaseModel):
    data_path: str
    epochs: int = 10
    lr: float = 0.001

class EvalConfig(BaseModel):
    checkpoint: str
    batch_size: int = 32

class CLI(Nested):
    train: TrainConfig | None = None
    evaluate: EvalConfig | None = None

cli = NanoArgs(CLI)
result = cli.parse()

if result.train is not None:
    print("training", result.train)
elif result.evaluate is not None:
    print("evaluating", result.evaluate)
```

**train.yaml**:

```yaml
data_path: data/train
epochs: 20
lr: 0.0005
```

**eval.yaml**:

```yaml
checkpoint: checkpoints/epoch_20.pt
batch_size: 64
```

**CLI usage**:

```bash
python app.py train train.yaml
python app.py evaluate eval.yaml

# Override with --override (post-command)
python app.py train train.yaml --override '$.lr=0.0001'
```

**Accessing the result**:

```python
result = cli.parse(argv=["train", "train.yaml"])
assert result.train is not None
print(result.train.lr)
```

## Parent Fields

`Nested` can mix subcommands with parent-level fields. Parent fields are set by pre-command overrides.

**app.py**:

```python
from pydantic import BaseModel
from nanoargs import NanoArgs, Nested

class TrainConfig(BaseModel):
    data_path: str
    epochs: int = 10

class EvalConfig(BaseModel):
    checkpoint: str

class CLI(Nested):
    verbose: bool = False
    log_dir: str = "runs"
    train: TrainConfig | None = None
    evaluate: EvalConfig | None = None

result = NanoArgs(CLI).parse()
```

**CLI usage**:

```bash
# CLI.verbose and CLI.log_dir apply to the parent CLI
# $.epochs applies to the TrainConfig child
python app.py --override '$.verbose=true' --override '$.log_dir=experiments' \
  train train.yaml --override '$.epochs=25'
```

## Nested Groups (Multi-level)

Nested subcommands compose naturally. A `Nested` field inside another `Nested` creates multi-level command groups.

**app.py**:

```python
from pydantic import BaseModel
from nanoargs import NanoArgs, Nested

class PreprocessConfig(BaseModel):
    input_path: str
    output_path: str

class ValidateConfig(BaseModel):
    input_path: str
    strict: bool = False

class DataCommands(Nested):
    preprocess: PreprocessConfig | None = None
    validate: ValidateConfig | None = None

class TrainConfig(BaseModel):
    data_path: str
    epochs: int = 10

class AllCommands(Nested):
    data: DataCommands | None = None
    train: TrainConfig | None = None

cli = NanoArgs(AllCommands)
result = cli.parse()
```

**CLI usage**:

```bash
python app.py data preprocess preprocess.yaml
```

**Accessing the result**:

```python
result = cli.parse(argv=["data", "preprocess", "preprocess.yaml"])
assert result.data is not None
assert result.data.preprocess is not None
print(result.data.preprocess.output_path)
```

## Override Behavior

Overrides are split by command position:

1. Pre-command overrides (`--override`) apply to parent `Nested` fields.
2. Post-command overrides apply to the selected child model.

Examples:

```bash
# Parent override via --override
python app.py --override '$.verbose=true' train train.yaml

# Child override via --override
python app.py train train.yaml --override '$.epochs=20'
```

Schema and config display rules:

- `--print-schema` before a command prints the full parent schema (including all subcommands).
- `train --print-schema` prints only the schema for `TrainConfig`.
- `--print-config` requires a command. It prints the merged config for that specific command.

```bash
python app.py --print-schema
python app.py train --print-schema
python app.py train train.yaml --print-config
```

## Rules and Constraints

- Subcommand fields must be typed as `T | None = None` or `Annotated[T, Field(...)] | None = None`.
- `T` must be a `BaseModel` subclass, a pydantic dataclass, or another `Nested`.
- A `Nested` model with no detectable subcommand fields raises `ValueError` at `NanoArgs` construction time.
- `prog` is inherited by children: if the parent is created with `prog="app"`, child parsers use `"app <command>"`.

## Schema Display

`--print-schema` prints the JSON schema for the parent `Nested` model (including `$defs`). A simplified, readable view uses `@X` to reference definitions:

```text
CLI
 .train        @TrainConfig
 .evaluate     @EvalConfig

TrainConfig
 .data_path    string
 .epochs       integer
 .lr           number

EvalConfig
 .checkpoint   string
 .batch_size   integer
```

Think of this as:

```text
CLI where
  train -> @TrainConfig
  evaluate -> @EvalConfig
```

If you need the exact JSON schema, use `python app.py --print-schema` or `cli.get_schema()` in Python.

## Testing Subcommands

Use `parse(argv=[...])` to test specific command paths without touching `sys.argv`:

```python
from pydantic import BaseModel
from nanoargs import NanoArgs, Nested

class TrainConfig(BaseModel):
    data_path: str

class CLI(Nested):
    train: TrainConfig | None = None

cli = NanoArgs(CLI)
result = cli.parse(argv=["train", "train.yaml"])
assert result.train is not None
assert result.train.data_path == "data/train"
```
