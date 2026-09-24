from dataclasses import dataclass


@dataclass(frozen=True)
class SerializeHookEntriesTestCase:
    description: str
    value: object
    sql_fields: tuple[str, ...]
    python_hook_fields: dict[str, dict[str, object]]
    expected_hooks: list[dict[str, object]]
