"""The process environment as compile text reads it, rejecting values that are not UTF-8."""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping

from sqlbuild.compiler.compile.exceptions import CompileInputError


class UnicodeEnvironment(Mapping[str, str]):
    """`os.environ`, raising a clear error for a value holding undecodable bytes."""

    def __getitem__(self, name: str) -> str:
        value: str = os.environ[name]
        try:
            _ = value.encode("utf-8")
        except UnicodeEncodeError as error:
            byte_offset: int = len(value[: error.start].encode("utf-8"))
            raise CompileInputError(
                f"Environment variable '{name}' is not valid UTF-8 text: byte {byte_offset} "
                "starts an invalid UTF-8 sequence",
                help=(
                    f"Set '{name}' to UTF-8 text, since SQLBuild cannot send undecodable bytes "
                    "to a warehouse; the value is not shown because it may be a secret"
                ),
            ) from None
        return value

    def __contains__(self, name: object) -> bool:
        return name in os.environ

    def __iter__(self) -> Iterator[str]:
        return iter(os.environ)

    def __len__(self) -> int:
        return len(os.environ)
