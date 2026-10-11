"""The launch record the native `sqb` executable offered this invocation."""

from contextvars import ContextVar, Token
from pathlib import Path

_OFFERED: ContextVar[Path | None] = ContextVar("sqlbuild_launch_record", default=None)
_WITHHELD: ContextVar[bool] = ContextVar("sqlbuild_launch_record_withheld", default=False)


def offer_launch_record(path: Path) -> Token[Path | None]:
    """Remember where `sqb` looks for this invocation's launch record."""

    return _OFFERED.set(path)


def withhold_offered_launch_record() -> Token[bool]:
    """Forget the offered launch record for the rest of this invocation."""

    return _WITHHELD.set(True)


def offered_launch_record() -> Path | None:
    """The offered launch record path, unless it was withheld."""

    return None if _WITHHELD.get() else _OFFERED.get()
