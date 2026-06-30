from __future__ import annotations

from pathlib import Path

from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project


def prepare_project_with_local_adapter(*, tmp_path: Path) -> Path:
    """Prepare a project that selects a nested project-local DuckDB adapter."""

    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="project_local_adapter",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "project_local_adapter"\n'
                'adapter = "duckdb_plus"\n\n'
                "[connection]\n"
                'database = "local.duckdb"\n'
            ),
            "adapters/warehouse/duckdb_plus.py": (
                "from sqlbuild.adapter.shared.models import QueryResult\n"
                "from sqlbuild.adapters.duckdb.client import DuckDbAdapter\n\n\n"
                "class DuckDbPlusAdapter(DuckDbAdapter):\n"
                "    adapter_name = 'duckdb_plus'\n\n"
                "    def query(self, connection, sql, *, limit):\n"
                "        return QueryResult(\n"
                "            columns=('adapter_name',),\n"
                "            rows=((self.adapter_name,),),\n"
                "            truncated=False,\n"
                "        )\n"
            ),
        },
    )
