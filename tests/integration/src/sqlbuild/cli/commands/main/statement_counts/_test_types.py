from dataclasses import dataclass


@dataclass(frozen=True)
class StatementStep:
    """One CLI command in a sequence and the housekeeping statements it issues, by kind."""

    description: str
    args: tuple[str, ...]
    new_orders: int
    expected_counts: dict[str, int]


@dataclass(frozen=True)
class StatementBudgetTestCase:
    """A sequence of commands against one project, each with its housekeeping budget."""

    description: str
    steps: tuple[StatementStep, ...]
    expected_recreated_after_drop: tuple[str, ...] = ()


@dataclass(frozen=True)
class FingerprintWriteTestCase:
    """An edit between two builds and the fingerprint statements the second build issues."""

    description: str
    edited_models: tuple[str, ...]
    expected_setups: int
    expected_rows: dict[str, int]
    expected_later_inserts: int = 0


@dataclass(frozen=True)
class FingerprintLossTestCase:
    """A fingerprint table dropped by a model's post hook in the middle of a build."""

    description: str
    edited_models: tuple[str, ...]
    hooked_model: str
    hooked_model_reads: tuple[str, ...]
    expected_setups: int
    expected_rows_after_loss: dict[str, int]
    expected_models_after_rebuild: tuple[str, ...]


@dataclass(frozen=True)
class LeftoverRelationTestCase:
    """A relation another run left at a name SQLBuild builds through, and the build's result."""

    description: str
    leftover_sql: str
    expected_rows: dict[str, int]
    expected_intermediates: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioLeftoverTestCase:
    """What an earlier scenario run, or a user, left in the scenario namespace."""

    description: str
    retained_runs: int
    planted_sql: tuple[str, ...]
    expected_kinds: tuple[tuple[str, str], ...]
    expected_after_cleanup: tuple[tuple[str, str], ...] = ()
