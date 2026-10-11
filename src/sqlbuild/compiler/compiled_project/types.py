"""Row shapes the native model loop hands its Python host."""

from collections.abc import Callable

from sqlbuild.spec.contracts.models import SourceLocation

type ReferenceRow = tuple[str, str, str | None, int | None]
type SpanRow = tuple[int, int, int, int]
type PythonResourceRow = tuple[str, str, str | None, Callable[[], SourceLocation], str]
