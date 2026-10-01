"""Function definition fingerprint entrypoint."""

from sqlbuild.compiler.fingerprints._helpers.query import compute_function_definition_hash_impl


def compute_function_definition_hash(
    *, fingerprint_sql: str, language: str, dialect: str | None
) -> str:
    """Fingerprint a function definition; non-SQL bodies are hashed exactly."""

    return compute_function_definition_hash_impl(
        fingerprint_sql=fingerprint_sql, language=language, dialect=dialect
    )
