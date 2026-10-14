use crate::dbt_command::models::DbtInitSummary;

/// Owned copies of string literals.
pub(super) fn texts(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// A DuckDB twin project summary.
pub(super) fn summary() -> DbtInitSummary {
    DbtInitSummary {
        output_dir: "/w/sqlbuild_project".to_owned(),
        project_file: "/w/sqlbuild_project/sqlbuild_project.toml".to_owned(),
        project_name: "analytics".to_owned(),
        adapter: "duckdb".to_owned(),
        target_name: "dev".to_owned(),
        profile_name: "analytics".to_owned(),
        toml: "name = \"analytics\"\n\n".to_owned(),
    }
}
