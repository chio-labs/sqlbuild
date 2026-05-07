def base_repo_files() -> dict[str, str]:
    return {
        "sqlbuild_project.toml": (
            'name = "demo"\nadapter = "duckdb"\n\n[settings]\ndefault_audit_severity = "warn"\n'
        ),
    }


def expected_or_actual[T](expected: T | None, actual: T) -> T:
    if expected is None:
        return actual
    return expected
