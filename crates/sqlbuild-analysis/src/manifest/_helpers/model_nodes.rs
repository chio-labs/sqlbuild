//! The dbt-compatible model node.

use crate::manifest::_helpers::node_fields::{
    columns, config, config_tags, depends_on, fqn, lifecycle_hooks,
};
use crate::manifest::_helpers::values::{
    docs, empty_object, inserted, object, optional_text, text, text_or_empty,
};
use crate::manifest::constants::{CHECKSUM_HASH_NAME, RESOURCE_TYPE_MODEL, SQLBUILD_META_KEY};
use crate::manifest::models::{ManifestModelInput, ManifestPythonHookInput};
use crate::python_values::main::text_key::text_key;
use crate::python_values::models::{PythonKey, PythonValue};

/// The model node's inputs besides the model.
pub(crate) struct ModelNodeContext<'a> {
    pub(crate) project_name: &'a str,
    pub(crate) compiled_code: Option<&'a str>,
    pub(crate) query_hash: &'a str,
    pub(crate) python_hooks: &'a [ManifestPythonHookInput],
}

fn meta_entry(meta: &[(PythonKey, PythonValue)], key: &str) -> PythonValue {
    meta.iter()
        .find(|(existing, _)| *existing == text_key(key))
        .map_or(PythonValue::Null, |(_, value)| value.clone())
}

/// The `str`-keyed entries of an authored `sqlbuild` dict, or its non-dict value as `authored_value`.
fn authored_sqlbuild(authored: PythonValue) -> Vec<(PythonKey, PythonValue)> {
    match authored {
        PythonValue::Object(entries) => entries
            .into_iter()
            .filter(|(key, _)| key.is_str)
            .fold(Vec::new(), |fields, (key, value)| {
                inserted(fields, key, value)
            }),
        PythonValue::Null => Vec::new(),
        other => vec![(text_key("authored_value"), other)],
    }
}

fn with_sqlbuild_fact(
    meta: Vec<(PythonKey, PythonValue)>,
    (field, value): (&str, PythonValue),
) -> Vec<(PythonKey, PythonValue)> {
    let fields: Vec<(PythonKey, PythonValue)> = inserted(
        authored_sqlbuild(meta_entry(&meta, SQLBUILD_META_KEY)),
        text_key(field),
        value,
    );
    inserted(
        meta,
        text_key(SQLBUILD_META_KEY),
        PythonValue::Object(fields),
    )
}

fn meta(model: &ManifestModelInput, python_hooks: &[ManifestPythonHookInput]) -> PythonValue {
    let mut meta: Vec<(PythonKey, PythonValue)> = Vec::new();
    if let Some(PythonValue::Object(authored)) =
        model.schema.as_ref().and_then(|schema| schema.meta.clone())
    {
        for (key, value) in authored {
            meta = inserted(meta, key, value);
        }
    }
    let mut hooks: Vec<(PythonKey, PythonValue)> = Vec::new();
    for (key, entries) in [
        ("pre_hooks", model.config.pre_hooks.as_deref()),
        ("post_hooks", model.config.post_hooks.as_deref()),
    ] {
        let serialized: Vec<PythonValue> = lifecycle_hooks(entries, python_hooks);
        if !serialized.is_empty() {
            hooks.push((text_key(key), PythonValue::Array(serialized)));
        }
    }
    if !hooks.is_empty() {
        meta = with_sqlbuild_fact(meta, ("lifecycle_hooks", PythonValue::Object(hooks)));
    }
    let families = model
        .schema
        .as_ref()
        .map(|schema| schema.dynamic_columns.as_slice())
        .unwrap_or_default();
    if !families.is_empty() {
        let families: Vec<PythonValue> = families
            .iter()
            .map(|family| {
                object(vec![
                    ("name", family.name.clone()),
                    ("pivot_column", family.pivot_column.clone()),
                    ("value_column", family.value_column.clone()),
                    ("aggregate", family.aggregate.clone()),
                    ("type", family.data_type.clone()),
                    ("name_pattern", family.name_pattern.clone()),
                ])
            })
            .collect();
        meta = with_sqlbuild_fact(meta, ("dynamic_columns", PythonValue::Array(families)));
    }
    PythonValue::Object(meta)
}

/// One dbt-compatible model node.
pub(crate) fn model_node(
    model: &ManifestModelInput,
    context: &ModelNodeContext<'_>,
) -> PythonValue {
    let project_name: &str = context.project_name;
    let path: &str = &model.path.text;
    object(vec![
        (
            "database",
            optional_text(model.destination.database.as_deref()),
        ),
        ("schema", optional_text(model.destination.schema.as_deref())),
        ("name", text(&model.name)),
        ("resource_type", text(RESOURCE_TYPE_MODEL)),
        ("package_name", text(project_name)),
        ("path", text(path)),
        ("original_file_path", text(path)),
        (
            "unique_id",
            text(&format!(
                "{RESOURCE_TYPE_MODEL}.{project_name}.{}",
                model.name
            )),
        ),
        ("fqn", fqn(project_name, &model.path)),
        ("alias", optional_text(model.destination.name.as_deref())),
        (
            "checksum",
            object(vec![
                ("name", text(CHECKSUM_HASH_NAME)),
                ("checksum", text(context.query_hash)),
            ]),
        ),
        ("config", config(&model.config)),
        ("tags", config_tags(&model.config)),
        (
            "description",
            text_or_empty(
                model
                    .schema
                    .as_ref()
                    .and_then(|schema| schema.description.as_deref()),
            ),
        ),
        (
            "columns",
            model
                .schema
                .as_ref()
                .map_or_else(empty_object, |schema| columns(&schema.columns)),
        ),
        ("meta", meta(model, context.python_hooks)),
        ("group", PythonValue::Null),
        ("docs", docs()),
        ("patch_path", PythonValue::Null),
        ("build_path", PythonValue::Null),
        ("unrendered_config", empty_object()),
        ("created_at", PythonValue::Float(0.0)),
        ("config_call_dict", empty_object()),
        ("unrendered_config_call_dict", empty_object()),
        (
            "relation_name",
            optional_text(model.destination.qualified_name.as_deref()),
        ),
        ("raw_code", text(&model.query_sql)),
        (
            "compiled_code",
            text(context.compiled_code.unwrap_or(&model.query_sql)),
        ),
        ("depends_on", depends_on(&model.deps, project_name)),
    ])
}
