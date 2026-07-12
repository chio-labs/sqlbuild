"""Public Python-node fingerprint write entrypoint."""

from __future__ import annotations

import logging
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.python_nodes.models import PythonNodeIdentity
from sqlbuild.executor.python_nodes.helpers.fingerprinting import (
    try_write_python_node_identity_fingerprint as _try_write_python_node_identity_fingerprint,
)


def try_write_python_node_identity_fingerprint(
    *,
    identity: PythonNodeIdentity | None,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    schema: str | None,
    database: str | None = None,
    target_name: str | None = None,
    logger: logging.Logger | None = None,
) -> None:
    """Append one Python identity row without affecting execution success."""

    _ = _try_write_python_node_identity_fingerprint(
        identity=identity,
        adapter=adapter,
        connection=connection,
        run_id=run_id,
        schema=schema,
        database=database,
        target_name=target_name,
        logger=logger,
    )
