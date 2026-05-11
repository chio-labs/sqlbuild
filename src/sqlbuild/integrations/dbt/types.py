"""dbt integration type aliases."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlbuild.integrations.dbt.models import DbtCommandResult

type DbtInvoker = Callable[[tuple[str, ...], Path | None], DbtCommandResult]
