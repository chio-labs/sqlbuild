"""Public targeted seed-state read entrypoint."""

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledSeed
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.command_planning.seed_state import read_seed_fingerprints


def read_selected_seed_fingerprints(
    *, adapter: BaseAdapter, connection: Any, seeds: tuple[CompiledSeed, ...]
) -> dict[str, Fingerprint]:
    """Read only fingerprint state required by selected direct seeds."""

    return read_seed_fingerprints(adapter=adapter, connection=connection, seeds=seeds)
