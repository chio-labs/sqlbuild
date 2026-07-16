"""Adapter discovery models."""

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter


@dataclass(frozen=True)
class DiscoveredAdapter:
    """A discovered project-local adapter class."""

    adapter_name: str
    adapter_class: type[StrictAdapter]
    file_path: Path
