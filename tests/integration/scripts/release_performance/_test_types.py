"""Local candidate installation cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LocalWheelTestCase:
    """A synchronized candidate and companion version."""

    version: str
