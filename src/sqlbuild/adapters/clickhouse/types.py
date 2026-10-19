"""ClickHouse adapter type declarations."""

type RecallFailure = tuple[bool, str] | None
type RecallCell = None | int | float | str | bytes
type RecallStatistics = tuple[int | None, int | None, str | None]
