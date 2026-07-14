"""Parse dbt ls output."""

from sqlbuild.integrations.dbt.helpers.cli.runner import parse_dbt_ls_json_lines as _parse
from sqlbuild.integrations.dbt.models import DbtLsNode


def parse_dbt_ls_json_lines(*, stdout: str) -> tuple[DbtLsNode, ...]:
    """Parse dbt ls JSON-lines output."""

    return _parse(stdout=stdout)
