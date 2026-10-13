from dataclasses import dataclass


@dataclass(frozen=True)
class NativeSourceModulePathTestCase:
    description: str
    source: str
    expected_errors: tuple[str, ...]


@dataclass(frozen=True)
class RepositoryModulePathTestCase:
    description: str
    expected_errors: tuple[str, ...]
    expected_logger_names: tuple[str, ...]
