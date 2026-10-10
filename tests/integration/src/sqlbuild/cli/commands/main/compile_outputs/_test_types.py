from dataclasses import dataclass


@dataclass(frozen=True)
class CompileOutputsSequenceTestCase:
    """One engine's cached edit sequence and the native output work counted per step."""

    description: str
    engine: str
    expected_exit_codes: tuple[int, ...]
    expected_work: tuple[dict[str, int], ...]


@dataclass(frozen=True)
class PublicationFailureTestCase:
    """One engine's staged publication onto a path a directory blocks."""

    description: str
    engine: str
    expected_error: str
    expected_published_files: int
