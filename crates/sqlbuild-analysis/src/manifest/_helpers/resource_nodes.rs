//! The dbt-compatible source and seed nodes.

use crate::manifest::_helpers::node_fields::{columns, fqn};
use crate::manifest::_helpers::values::{
    docs, empty_array, empty_object, inserted, object, optional_text, text, text_or_empty, texts,
    zero_float,
};
use crate::manifest::constants::{
    CHECKSUM_HASH_NAME, RESOURCE_TYPE_SEED, RESOURCE_TYPE_SOURCE, SQLBUILD_META_KEY,
};
use crate::manifest::models::{ManifestSeedInput, ManifestSourceInput};
use crate::python_values::main::text_key::text_key;
use crate::python_values::models::{PythonKey, PythonValue};

fn object_entries(value: Option<PythonValue>) -> Vec<(PythonKey, PythonValue)> {
    match value {
        Some(PythonValue::Object(entries)) => entries,
        _ => Vec::new(),
    }
}

fn source_meta(source: &ManifestSourceInput, auto_load: bool) -> PythonValue {
    let meta: Vec<(PythonKey, PythonValue)> = object_entries(source.meta.clone());
    let Some(loader) = &source.loader else {
        return PythonValue::Object(meta);
    };
    let mut fields: Vec<(&str, PythonValue)> = vec![
        ("loader", text(loader)),
        ("auto_load", PythonValue::Bool(auto_load)),
    ];
    if let Some(strategy) = &source.write_strategy {
        fields.push(("write_strategy", text(strategy)));
    }
    if let Some(cursor) = &source.cursor_column {
        fields.push(("cursor_column", cursor.clone()));
    }
    if let Some(unique_key) = &source.unique_key {
        fields.push(("unique_key", unique_key.clone()));
    }
    PythonValue::Object(inserted(meta, text_key(SQLBUILD_META_KEY), object(fields)))
}

/// One dbt-compatible source node.
pub(crate) fn source_node(
    source: &ManifestSourceInput,
    project_name: &str,
    auto_load: bool,
) -> PythonValue {
    let name: &str = &source.entry_name;
    object(vec![
        ("database", optional_text(source.database.as_deref())),
        ("schema", text_or_empty(source.schema.as_deref())),
        ("name", text(name)),
        ("resource_type", text(RESOURCE_TYPE_SOURCE)),
        ("package_name", text(project_name)),
        ("path", text(&source.path)),
        ("original_file_path", text(&source.path)),
        (
            "unique_id",
            text(&format!("{RESOURCE_TYPE_SOURCE}.{project_name}.{name}")),
        ),
        ("fqn", texts([project_name, name])),
        ("source_name", text(name)),
        ("source_description", text("")),
        ("loader", text("")),
        ("identifier", text(source.table.as_deref().unwrap_or(name))),
        ("quoting", empty_object()),
        ("loaded_at_field", PythonValue::Null),
        ("freshness", PythonValue::Null),
        ("external", PythonValue::Null),
        ("description", text_or_empty(source.description.as_deref())),
        ("columns", columns(&source.columns)),
        ("meta", source_meta(source, auto_load)),
        ("source_meta", empty_object()),
        ("tags", empty_array()),
        ("config", empty_object()),
        ("patch_path", PythonValue::Null),
        ("unrendered_config", empty_object()),
        ("relation_name", PythonValue::Null),
        ("created_at", zero_float()),
    ])
}

fn seed_config(seed: &ManifestSeedInput) -> PythonValue {
    object(vec![
        ("enabled", PythonValue::Bool(true)),
        ("alias", PythonValue::Null),
        ("schema", optional_text(seed.destination.schema.as_deref())),
        (
            "database",
            optional_text(seed.destination.database.as_deref()),
        ),
        ("tags", texts(seed.tags.iter().map(String::as_str))),
        ("meta", empty_object()),
        ("group", PythonValue::Null),
        ("materialized", text("seed")),
        ("persist_docs", empty_object()),
        ("post-hook", empty_array()),
        ("pre-hook", empty_array()),
        ("quoting", empty_object()),
        ("column_types", empty_object()),
        ("full_refresh", PythonValue::Null),
        ("unique_key", PythonValue::Null),
        ("on_schema_change", text("ignore")),
        ("on_configuration_change", text("apply")),
        ("grants", empty_object()),
        ("packages", empty_array()),
        ("docs", docs()),
        (
            "contract",
            object(vec![
                ("enforced", PythonValue::Bool(false)),
                ("alias_types", PythonValue::Bool(true)),
            ]),
        ),
        ("delimiter", text(",")),
        ("quote_columns", PythonValue::Null),
    ])
}

/// One dbt-compatible seed node.
pub(crate) fn seed_node(seed: &ManifestSeedInput, project_name: &str) -> PythonValue {
    let path: &str = &seed.path.text;
    object(vec![
        (
            "database",
            optional_text(seed.destination.database.as_deref()),
        ),
        ("schema", optional_text(seed.destination.schema.as_deref())),
        ("name", text(&seed.name)),
        ("resource_type", text(RESOURCE_TYPE_SEED)),
        ("package_name", text(project_name)),
        ("path", text(path)),
        ("original_file_path", text(path)),
        (
            "unique_id",
            text(&format!(
                "{RESOURCE_TYPE_SEED}.{project_name}.{}",
                seed.name
            )),
        ),
        ("fqn", fqn(project_name, &seed.path)),
        ("alias", optional_text(seed.destination.name.as_deref())),
        (
            "checksum",
            object(vec![
                ("name", text(CHECKSUM_HASH_NAME)),
                ("checksum", text("")),
            ]),
        ),
        ("config", seed_config(seed)),
        ("tags", texts(seed.tags.iter().map(String::as_str))),
        ("description", text_or_empty(seed.description.as_deref())),
        ("columns", columns(&seed.columns)),
        ("meta", seed.meta.clone().unwrap_or_else(empty_object)),
        ("group", PythonValue::Null),
        ("docs", docs()),
        ("patch_path", PythonValue::Null),
        ("build_path", PythonValue::Null),
        ("unrendered_config", empty_object()),
        ("created_at", zero_float()),
        ("config_call_dict", empty_object()),
        ("unrendered_config_call_dict", empty_object()),
        (
            "relation_name",
            optional_text(seed.destination.qualified_name.as_deref()),
        ),
        ("raw_code", text("")),
        ("root_path", PythonValue::Null),
        ("depends_on", object(vec![("macros", empty_array())])),
    ])
}
