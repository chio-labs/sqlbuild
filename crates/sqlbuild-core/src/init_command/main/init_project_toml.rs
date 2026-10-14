//! The configuration of a blank DuckDB project.

/// `sqlbuild_project.toml` with dev and prod targets on one local connection.
#[must_use]
pub fn init_project_toml(project_name: &str) -> String {
    format!(
        "name = \"{project_name}\"\nadapter = \"duckdb\"\ndefault_target = \"dev\"\n\n\
         [connections.developer]\ndatabase = \"{project_name}.duckdb\"\n\n\
         [settings]\ndefault_audit_severity = \"warn\"\n\n\
         [defaults]\nmaterialized = \"table\"\n\n\
         [targets.prod]\nconnection = \"developer\"\nschema = \"prod\"\n\n\
         [targets.dev]\nconnection = \"developer\"\nschema = \"dev\"\n"
    )
}
