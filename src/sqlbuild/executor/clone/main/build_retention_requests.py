"""Public clone destination retention request entrypoint."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import RetentionRequest
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.executor.clone._helpers.retention import build_clone_retention_requests


def build_destination_retention_requests(
    *, project: CompiledProject, adapter_name: str, namespace_owned: bool
) -> dict[str, RetentionRequest]:
    """Build destination-only retention requests for clone execution."""

    return build_clone_retention_requests(
        project=project,
        adapter_name=adapter_name,
        namespace_owned=namespace_owned,
    )
