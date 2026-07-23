# Getting Started

## 1. Define Your Configuration Model

Create a Pydantic model describing your configuration shape:

```python
from pydantic import BaseModel
from nanoargs import NanoArgs

class Config(BaseModel):
    mode: str = "train"
    batch_size: int = 32
    learning_rate: float = 0.001
    model: dict[str, str] = {"type": "transformer"}

cli = NanoArgs(Config)
config = cli.parse()       # uses sys.argv by default
print(config)
```

## 2. Create Configuration Files

**base.yaml**:

```yaml
mode: train
batch_size: 64
learning_rate: 0.01
model:
  type: transformer
  layers: 12
```

**experiment.yaml** (with imports):

```yaml
!merge
  - !import [base.yaml]
  - learning_rate: 0.001
```

Or import into a specific field:

```yaml
mode: experiment
learning_rate: 0.001
model: !import ["base_model.yaml"]
```

## 3. Use from the Command Line

```bash
# Basic usage
python app.py experiment.yaml

# Multiple config files (later files override earlier ones)
python app.py base.yaml experiment.yaml

# Runtime overrides using JSONPath syntax
python app.py base.yaml \
  --override '$.batch_size=128' \
  --override '$.model.layers=24'

# Additional overrides
python app.py base.yaml \
  --override '$.learning_rate=0.0001'

# Read config from stdin
echo 'batch_size: 128' | python app.py -

# Print the final merged configuration
python app.py experiment.yaml --print-config

# Print the JSON schema
python app.py --print-schema
```

## 4. Programmatic Usage

```python
cli = NanoArgs(Config)

# Parse with explicit argv
config = cli.parse(argv=["config.yaml", "--override", "$.mode=test"])

# Access the JSON schema
schema = cli.get_schema()
```

## 5. Multi-Command CLIs with `Nested`

Use `Nested` to build CLIs with multiple subcommands, each backed by its own Pydantic model.

**Define subcommand models:**

```python
from pydantic import BaseModel
from nanoargs import NanoArgs, Nested

class TrainConfig(BaseModel):
    lr: float = 0.001
    epochs: int = 10

class EvalConfig(BaseModel):
    checkpoint: str
    batch_size: int = 32

class CLI(Nested):
    train: TrainConfig | None = None
    evaluate: EvalConfig | None = None

cli = NanoArgs(CLI)
result = cli.parse()
```

**Use from the command line:**

```bash
# Select a subcommand — everything after it is that command's config
python app.py train config.yaml --override '$.lr=0.01'
python app.py evaluate config.yaml

# Print the help listing available subcommands
python app.py --help

# Print schema for a specific subcommand
python app.py train --print-schema
```

**Access the result:**

```python
result = cli.parse(argv=["train", "config.yaml"])
# result is a CLI instance — fully typed
if result.train is not None:
    print(result.train.lr)     # TrainConfig
elif result.evaluate is not None:
    print(result.evaluate.checkpoint)  # EvalConfig
```

**Parent fields and pre-command overrides:**

`Nested` models can have both subcommand fields and regular config fields. Pre-command
overrides set the parent fields; everything after the command goes to the child:

```python
class CLI(Nested):
    verbose: bool = False          # parent field
    train: TrainConfig | None = None
    evaluate: EvalConfig | None = None
```

```bash
# CLI.verbose applies to CLI, $.lr applies to TrainConfig
python app.py --override '$.verbose=true' train config.yaml --override '$.lr=0.01'
```

**Nesting:**

`Nested` composes naturally — a field of type `Nested` creates nested subcommands:

```python
class DataCommands(Nested):
    preprocess: PreprocessConfig | None = None
    validate: ValidateConfig | None = None

class AllCommands(Nested):
    train: TrainConfig | None = None
    data: DataCommands | None = None  # nested group

result = NanoArgs(AllCommands).parse(argv=["data", "preprocess", "config.yaml"])
assert result.data is not None
assert result.data.preprocess is not None
```

## Next Steps

- [Configuration Guide](configuration.md) -- import system, overrides, merge rules, subcommands
- [Path Syntax](path-syntax.md) -- JSONPath-like grammar reference
- [API Reference](api/cli.md) -- full API documentation
