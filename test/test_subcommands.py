# Copyright 2024-2026 Cusp AI
# SPDX-License-Identifier: Apache-2.0

import pathlib
import textwrap
from typing import Annotated

import pytest
from pydantic import BaseModel, Field, ValidationError

from nanoargs.cli import NanoArgs, Nested


class TrainConfig(BaseModel):
    lr: float = 0.001
    epochs: int = 10


class EvalConfig(BaseModel):
    checkpoint: str
    batch_size: int = 32


class Programs(Nested):
    train: TrainConfig | None = None
    evaluate: EvalConfig | None = None


def write(p: pathlib.Path, content: str) -> pathlib.Path:
    p.write_text(textwrap.dedent(content))
    return p


class SimpleCfg(BaseModel):
    x: int


def test_single_model_unchanged(tmp_path: pathlib.Path) -> None:
    cfg = write(tmp_path / "c.yaml", "x: 42")
    cli = NanoArgs(SimpleCfg)
    result = cli.parse(argv=[str(cfg)])
    assert result.x == 42


def test_prog_kwarg(tmp_path: pathlib.Path) -> None:
    cfg = write(tmp_path / "c.yaml", "x: 1")
    cli = NanoArgs(SimpleCfg, prog="myapp")
    result = cli.parse(argv=[str(cfg)])
    assert result.x == 1


def test_nested_enters_subcommand_mode() -> None:
    cli = NanoArgs(Programs)
    assert cli._subcommands is not None
    assert "train" in cli._subcommands
    assert "evaluate" in cli._subcommands


def test_basemodel_no_subcommand_mode() -> None:
    cli = NanoArgs(SimpleCfg)
    assert cli._subcommands is None


def test_parse_first_command(tmp_path: pathlib.Path) -> None:
    cfg = write(tmp_path / "c.yaml", "lr: 0.01\nepochs: 5")
    cli = NanoArgs(Programs)
    result = cli.parse(argv=["train", str(cfg)])
    assert isinstance(result, Programs)
    assert result.train is not None
    assert result.train.lr == 0.01
    assert result.train.epochs == 5
    assert result.evaluate is None


def test_parse_second_command(tmp_path: pathlib.Path) -> None:
    cfg = write(tmp_path / "c.yaml", "checkpoint: model.pt\nbatch_size: 16")
    cli = NanoArgs(Programs)
    result = cli.parse(argv=["evaluate", str(cfg)])
    assert result.evaluate is not None
    assert result.evaluate.checkpoint == "model.pt"
    assert result.train is None


def test_subcommand_explicit_override(tmp_path: pathlib.Path) -> None:
    cfg = write(tmp_path / "c.yaml", "lr: 0.001\nepochs: 10")
    cli = NanoArgs(Programs)
    result = cli.parse(argv=["train", str(cfg), "--override", "$.lr=0.5"])
    assert result.train is not None
    assert result.train.lr == 0.5


class Level2(Nested):
    train: TrainConfig | None = None


class Level1(Nested):
    ml: Level2 | None = None


def test_two_level_nesting(tmp_path: pathlib.Path) -> None:
    cfg = write(tmp_path / "c.yaml", "lr: 0.1\nepochs: 3")
    cli = NanoArgs(Level1)
    result = cli.parse(argv=["ml", "train", str(cfg)])
    assert result.ml is not None
    assert result.ml.train is not None
    assert result.ml.train.lr == 0.1


def test_no_command_error() -> None:
    cli = NanoArgs(Programs)
    with pytest.raises(SystemExit) as exc:
        cli.parse(argv=[])
    assert exc.value.code == 2


def test_unknown_command_error() -> None:
    cli = NanoArgs(Programs)
    with pytest.raises(SystemExit) as exc:
        cli.parse(argv=["unknown"])
    assert exc.value.code == 2


def test_command_no_config_error() -> None:
    cli = NanoArgs(Programs)
    with pytest.raises(SystemExit) as exc:
        cli.parse(argv=["train"])
    assert exc.value.code == 2


def test_print_schema_exits() -> None:
    cli = NanoArgs(Programs)
    with pytest.raises(SystemExit) as exc:
        cli.parse(argv=["--print-schema"])
    assert exc.value.code == 0


def test_subcommand_print_schema_exits() -> None:
    cli = NanoArgs(Programs)
    with pytest.raises(SystemExit) as exc:
        cli.parse(argv=["train", "--print-schema"])
    assert exc.value.code == 0


def test_help_exits() -> None:
    cli = NanoArgs(Programs)
    with pytest.raises(SystemExit) as exc:
        cli.parse(argv=["--help"])
    assert exc.value.code == 0


def test_subcommand_help_exits() -> None:
    cli = NanoArgs(Programs)
    with pytest.raises(SystemExit) as exc:
        cli.parse(argv=["train", "--help"])
    assert exc.value.code == 0


def test_detect_subcommands_nested_type() -> None:
    cli = NanoArgs(Level1)
    assert cli._subcommands is not None
    assert "ml" in cli._subcommands


# --- Bug fixes ---


def test_annotated_field_detected_as_subcommand() -> None:
    """BUG 2: Annotated[T, Field(...)] | None must be detected as a subcommand."""

    class WithAnnotated(Nested):
        train: Annotated[TrainConfig, Field(description="Training config")] | None = (
            None
        )

    cli = NanoArgs(WithAnnotated)
    assert cli._subcommands is not None
    assert "train" in cli._subcommands


def test_empty_nested_raises_value_error() -> None:
    """BUG 5: Nested with no detectable fields must raise ValueError at construction."""

    class EmptyNested(Nested):
        pass

    with pytest.raises(ValueError, match="no detectable subcommand fields"):
        NanoArgs(EmptyNested)


def test_print_config_no_command_error() -> None:
    """BUG 4: --print-config without a command must give a clear error (exit 2)."""
    cli = NanoArgs(Programs)
    with pytest.raises(SystemExit) as exc:
        cli.parse(argv=["--print-config"])
    assert exc.value.code == 2


def test_child_prog_name() -> None:
    """BUG 3: child parser prog must include parent program name."""
    cli = NanoArgs(Programs, prog="myapp")
    assert cli._children["train"].parser.prog == "myapp train"
    assert cli._children["evaluate"].parser.prog == "myapp evaluate"


def test_unknown_command_error_lists_choices(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Error message for unknown command must list valid choices."""
    cli = NanoArgs(Programs)
    with pytest.raises(SystemExit) as exc:
        cli.parse(argv=["notacommand"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "train" in captured.err or "evaluate" in captured.err


# --- Recursive design features ---


class AppCLI(Nested):
    """CLI with a regular parent field and subcommands."""

    verbose: bool = False
    train: TrainConfig | None = None
    evaluate: EvalConfig | None = None


def test_parent_override_applies_to_parent_field(tmp_path: pathlib.Path) -> None:
    """Pre-command --override $.field=value sets parent non-subcommand fields."""
    cfg = write(tmp_path / "c.yaml", "lr: 0.001\nepochs: 10")
    cli = NanoArgs(AppCLI)
    result = cli.parse(argv=["--override", "$.verbose=true", "train", str(cfg)])
    assert result.verbose is True


def test_parent_defaults_preserved(tmp_path: pathlib.Path) -> None:
    """Parent field defaults apply even without any pre-command flags."""
    cfg = write(tmp_path / "c.yaml", "lr: 0.001\nepochs: 10")
    cli = NanoArgs(AppCLI)
    result = cli.parse(argv=["train", str(cfg)])
    assert result.verbose is False  # default preserved


def test_child_override_does_not_affect_parent(tmp_path: pathlib.Path) -> None:
    """Post-command overrides apply only to the child, not the parent."""
    cfg = write(tmp_path / "c.yaml", "lr: 0.001\nepochs: 10")
    cli = NanoArgs(AppCLI)
    result = cli.parse(argv=["train", str(cfg), "--override", "$.lr=0.9"])
    assert result.verbose is False  # parent field unaffected
    assert result.train is not None
    assert result.train.lr == 0.9


def test_pre_command_positional_is_error() -> None:
    """A positional before the command that is not a known command is an error."""
    cli = NanoArgs(Programs)
    with pytest.raises(SystemExit) as exc:
        cli.parse(argv=["train.yaml", "train"])  # positional before valid command
    assert exc.value.code == 2


def test_pre_command_positional_error_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Error when config file placed before command mentions position."""
    cli = NanoArgs(Programs)
    with pytest.raises(SystemExit):
        cli.parse(argv=["config.yaml", "train"])
    assert "before command" in capsys.readouterr().err


def test_subcommand_validation_error_propagates(tmp_path: pathlib.Path) -> None:
    """ValidationError from child config propagates to the caller."""
    cfg = write(tmp_path / "c.yaml", "checkpoint: model.pt\nbatch_size: not_a_number")
    cli = NanoArgs(Programs)
    with pytest.raises((SystemExit, ValidationError)):
        cli.parse(argv=["evaluate", str(cfg)])


def test_subcommand_print_config(tmp_path: pathlib.Path) -> None:
    """--print-config after a subcommand prints merged config and exits 0."""
    cfg = write(tmp_path / "c.yaml", "lr: 0.001\nepochs: 10")
    cli = NanoArgs(Programs)
    with pytest.raises(SystemExit) as exc:
        cli.parse(argv=["train", str(cfg), "--print-config"])
    assert exc.value.code == 0


def test_subcommand_multi_file_merge(tmp_path: pathlib.Path) -> None:
    """Multiple config files after a subcommand are merged correctly."""
    base = write(tmp_path / "base.yaml", "lr: 0.001\nepochs: 10")
    override_file = write(tmp_path / "override.yaml", "lr: 0.5")
    cli = NanoArgs(Programs)
    result = cli.parse(argv=["train", str(base), str(override_file)])
    assert result.train is not None
    assert result.train.lr == 0.5  # override file wins


def test_subcommand_default_fallthrough(tmp_path: pathlib.Path) -> None:
    """Fields absent from YAML use the model default."""
    cfg = write(tmp_path / "c.yaml", "lr: 0.5")  # epochs absent
    cli = NanoArgs(Programs)
    result = cli.parse(argv=["train", str(cfg)])
    assert result.train is not None
    assert result.train.lr == 0.5
    assert result.train.epochs == 10  # model default


# === Issue #16/#17: docs/help consistency ===


def test_pre_command_override_single_token(tmp_path: pathlib.Path) -> None:
    """--override=value (single-token) before command applies to parent field."""
    cfg = write(tmp_path / "c.yaml", "lr: 0.001\nepochs: 10")
    cli = NanoArgs(AppCLI)
    result = cli.parse(argv=["--override=$.verbose=true", "train", str(cfg)])
    assert result.verbose is True


def test_subcommand_help_contains_grammar_description(capsys) -> None:
    """Subcommand --help must explain pre/post command grammar."""
    cli = NanoArgs(AppCLI)
    with pytest.raises(SystemExit):
        cli.parse(argv=["--help"])
    captured = capsys.readouterr()
    assert (
        "pre-command" in captured.out.lower() or "post-command" in captured.out.lower()
    )
