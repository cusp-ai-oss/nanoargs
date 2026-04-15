from __future__ import annotations

from dataclasses import field

from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Just a simple test config class."""

    foo: int = field(
        metadata={
            "description": "this is the foo value this is the foo value this is the foo value this is the foo valuethis is the foo value this is the foo value this is the foo value this is the foo value "
        }
    )
    bar: float = field(metadata={"description": "this is the bar value"})
    sub: SubConfig = field(metadata={"description": "and this is the sub config"})


@dataclass(frozen=True)
class SubConfig:
    """Just a simple sub config class."""

    baz: dict[int, str]
    qux: list[SubConfig] | None
    asdf: AnotherSubConfig


@dataclass(frozen=True)
class AnotherSubConfig:
    asdf: list[int]


if __name__ == "__main__":
    import sys

    from nanoargs.cli import NanoArgs

    config = NanoArgs(Config).parse()
    print(config, file=sys.stderr)
