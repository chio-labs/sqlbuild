"""Public deterministic archive requirement identity entrypoint."""

from sqlbuild.archives._helpers.identity import archive_requirement_id


def build_archive_requirement_id(
    *,
    operation_kind: str,
    target_database: str | None,
    target_schema: str,
    target_name: str,
    source_physical_generation: str | None,
    archive_name: str,
) -> str:
    """Build one deterministic archive requirement identity."""

    return archive_requirement_id(
        operation_kind=operation_kind,
        target_database=target_database,
        target_schema=target_schema,
        target_name=target_name,
        source_physical_generation=source_physical_generation,
        archive_name=archive_name,
    )
