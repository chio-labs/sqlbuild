"""Type aliases for the compiler differential harness."""

from collections.abc import Callable

type NodeResolvers = tuple[Callable[[object], object], Callable[[object], object]]

type FallbackKey = tuple[str, str, str, str]
