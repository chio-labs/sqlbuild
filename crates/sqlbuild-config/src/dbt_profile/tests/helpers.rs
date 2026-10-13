use crate::dbt_profile::models::{DbtInitConfig, ProfileEntry, ProfileValue};

pub(super) fn entry(key: &str, value: ProfileValue) -> ProfileEntry {
    ProfileEntry {
        key: Some(key.to_owned()),
        value,
    }
}

pub(super) fn text(key: &str, value: &str) -> ProfileEntry {
    entry(key, ProfileValue::Text(value.to_owned()))
}

pub(super) fn init_config(target_name: &str, target_schema: Option<&str>) -> DbtInitConfig {
    DbtInitConfig {
        project_name: "analytics".to_owned(),
        adapter: "duckdb".to_owned(),
        target_name: target_name.to_owned(),
        profile_name: "ana\"lytics".to_owned(),
        dbt_project_dir: "../dbt_project".to_owned(),
        profiles_dir: "C:\\profiles".to_owned(),
        target_path: "../dbt_project/target".to_owned(),
        target_schema: target_schema.map(str::to_owned),
        target_database: None,
    }
}
