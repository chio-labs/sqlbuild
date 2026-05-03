def base_repo_files() -> dict[str, str]:
    return {
        "sqlbuild_project.yml": (
            "name: demo\nadapter: duckdb\nsettings:\n  default_audit_severity: warn\n"
        ),
    }
