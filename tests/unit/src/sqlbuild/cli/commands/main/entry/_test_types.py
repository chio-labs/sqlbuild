from dataclasses import dataclass


@dataclass(frozen=True)
class MainTestCase:
    description: str
    argv: list[str]
    expected_exit_code: int


@dataclass(frozen=True)
class MainErrorRenderingTestCase:
    description: str
    argv: list[str]
    expected_stderr_fragment: str
    expected_exit_code: int
