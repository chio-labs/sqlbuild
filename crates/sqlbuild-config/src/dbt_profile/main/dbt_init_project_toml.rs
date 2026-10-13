//! The `sqlbuild_project.toml` that `sqb dbt init` writes.

use sqlbuild_core::text::main::python_isalnum::python_isalnum;

use crate::dbt_profile::models::DbtInitConfig;

fn escaped(value: &str) -> String {
    value.replace('\\', "\\\\").replace('"', "\\\"")
}

/// A bare TOML key when it is alphanumeric apart from `_` and `-`, else a quoted one.
fn table_key(value: &str) -> String {
    let stripped: String = value.replace(['_', '-'], "");
    if !stripped.is_empty() && stripped.chars().all(python_isalnum) {
        return value.to_owned();
    }
    format!("\"{}\"", escaped(value))
}

/// The project config pointing SQLBuild at the dbt project and its profile target.
#[must_use]
pub fn dbt_init_project_toml(config: &DbtInitConfig) -> String {
    let connection_name: String = format!("{}_dbt_profile", config.target_name);
    let mut target_lines: Vec<String> = vec![
        format!("[connections.{}]", table_key(&connection_name)),
        "source = \"dbt_profile\"".to_owned(),
        format!("profile = \"{}\"", escaped(&config.profile_name)),
        format!("target = \"{}\"", escaped(&config.target_name)),
        String::new(),
        format!("[targets.{}]", table_key(&config.target_name)),
        format!("connection = \"{}\"", escaped(&connection_name)),
    ];
    if let Some(database) = &config.target_database {
        target_lines.push(format!("database = \"{}\"", escaped(database)));
    }
    if let Some(schema) = &config.target_schema {
        target_lines.push(format!("schema = \"{}\"", escaped(schema)));
    }
    format!(
        "name = \"{}\"\nadapter = \"{}\"\ndefault_target = \"{}\"\n\n[dbt]\nproject_dir = \"{}\"\nprofiles_dir = \"{}\"\ntarget_path = \"{}\"\ntarget = \"{}\"\n\n{}\n",
        escaped(&config.project_name),
        escaped(&config.adapter),
        escaped(&config.target_name),
        escaped(&config.dbt_project_dir),
        escaped(&config.profiles_dir),
        escaped(&config.target_path),
        escaped(&config.target_name),
        target_lines.join("\n")
    )
}
