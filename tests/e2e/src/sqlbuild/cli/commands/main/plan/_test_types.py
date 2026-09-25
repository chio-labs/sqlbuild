from dataclasses import dataclass


@dataclass(frozen=True)
class RemovedInterfaceTestCase:
    description: str
    command: tuple[str, ...]
    expected_error: str
    expected_exit_code: int = 2


@dataclass(frozen=True)
class RemovedConfigTestCase:
    description: str
    content: str
    expected_key: str
    filename: str = "sqlbuild_project.toml"
    prefix: str = 'name = "orders"\nadapter = "duckdb"\n'
    expected_exit_code: int = 1


@dataclass(frozen=True)
class RemovedHookTestCase:
    description: str
    expected_error: str
    expected_exit_code: int = 1
