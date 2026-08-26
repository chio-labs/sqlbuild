"""Adapter resolution from project configuration."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.discovery.main.resolve_adapter import (
    resolve_adapter as resolve_registered_adapter,
)
from sqlbuild.cli.commands.exceptions import CliUserError


def resolve_adapter(*, adapter_name: str, project_dir: Path | None = None) -> BaseAdapter:
    """Resolve an adapter name from project config to an adapter instance."""

    try:
        return resolve_registered_adapter(adapter_name=adapter_name, project_dir=project_dir)
    except AdapterUserError as error:
        raise CliUserError(error.message, code="C601", help=error.help) from error
