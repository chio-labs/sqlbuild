use crate::dbt_profile::models::{
    DbtInitConfig, DbtProfileOutputs, DbtYamlValue, LoadedDbtProfile, ProfileEntry, ProfileValue,
};

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

pub(super) fn yaml_text(value: &str) -> DbtYamlValue {
    DbtYamlValue::Text(value.to_owned())
}

pub(super) const YAML_MAPPING: DbtYamlValue = DbtYamlValue::Mapping { empty: false };

/// A loaded mapping profile whose outputs are the given `(name, output)` entries.
pub(super) fn loaded_profile(
    output_entries: Vec<(DbtYamlValue, DbtYamlValue)>,
    target: DbtYamlValue,
) -> LoadedDbtProfile {
    LoadedDbtProfile {
        profile: YAML_MAPPING,
        outputs: DbtYamlValue::Mapping {
            empty: output_entries.is_empty(),
        },
        output_entries,
        target,
    }
}

pub(super) fn profile_outputs(default_target: Option<&str>, names: &[&str]) -> DbtProfileOutputs {
    DbtProfileOutputs {
        name: "shop".to_owned(),
        default_target: default_target.map(str::to_owned),
        outputs: names
            .iter()
            .enumerate()
            .map(|(index, name)| ((*name).to_owned(), index))
            .collect(),
    }
}
