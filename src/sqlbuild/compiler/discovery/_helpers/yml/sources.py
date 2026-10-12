"""Parsing of authored sources/*.yml files, run natively."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.yml.yaml_classes import yaml_entry_classes
from sqlbuild.spec.contracts.models import SourceEntry


def parse_loaded_sources_yml(*, loaded: object, file_path: Path) -> tuple[SourceEntry, ...]:
    """Parse the document one sources/*.yml file loads to into raw source declarations."""

    return _native.parse_sources_document(loaded, str(file_path), yaml_entry_classes())
