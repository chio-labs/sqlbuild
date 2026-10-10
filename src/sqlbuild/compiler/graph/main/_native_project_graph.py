"""Native project graph entrypoint."""

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.graph._helpers.native_graph import build_native_project_graph_impl


def build_native_project_graph(project: CompiledProject) -> _native.NativeProjectGraph:
    """Index the project's lineage edges, tags, folders and names natively."""

    return build_native_project_graph_impl(project)
