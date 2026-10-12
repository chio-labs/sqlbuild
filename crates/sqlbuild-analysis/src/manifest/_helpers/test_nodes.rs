//! dbt-compatible generic and singular test nodes of planned audits and SQL tests.

use std::collections::HashMap;

use crate::manifest::_helpers::node_fields::{unique_id, unique_ids};
use crate::manifest::_helpers::values::{
    docs, empty_array, empty_object, keyed, object, optional_text, text, texts, zero_float,
};
use crate::manifest::constants::{CHECKSUM_HASH_NAME, RESOURCE_TYPE_TEST};
use crate::manifest::errors::ManifestError;
use crate::manifest::models::{ManifestAuditPlanInput, ManifestSqlTestPlanInput};
use crate::python_values::models::PythonValue;

fn test_config() -> PythonValue {
    object(vec![
        ("enabled", PythonValue::Bool(true)),
        ("alias", PythonValue::Null),
        ("schema", PythonValue::Null),
        ("database", PythonValue::Null),
        ("tags", empty_array()),
        ("meta", empty_object()),
        ("group", PythonValue::Null),
        ("materialized", text("test")),
        ("severity", text("ERROR")),
        ("store_failures", PythonValue::Null),
        ("store_failures_as", PythonValue::Null),
        ("where", PythonValue::Null),
        ("limit", PythonValue::Null),
        ("fail_calc", text("count(*)")),
        ("warn_if", text("!= 0")),
        ("error_if", text("!= 0")),
    ])
}

/// The test node fields shared by audits and SQL tests, after `fqn` and before `checksum`.
struct TestNodeHead<'a> {
    unique_id: &'a str,
    name: &'a str,
    project_name: &'a str,
}

fn head(node: &TestNodeHead<'_>) -> Vec<(&'static str, PythonValue)> {
    vec![
        ("database", PythonValue::Null),
        ("schema", text("")),
        ("name", text(node.name)),
        ("resource_type", text(RESOURCE_TYPE_TEST)),
        ("package_name", text(node.project_name)),
        ("path", text("")),
        ("original_file_path", text("")),
        ("unique_id", text(node.unique_id)),
        ("fqn", texts([node.project_name, node.name])),
        ("alias", text(node.name)),
    ]
}

fn tail(compiled_code: &str, depends_on: PythonValue) -> Vec<(&'static str, PythonValue)> {
    vec![
        ("group", PythonValue::Null),
        ("docs", docs()),
        ("patch_path", PythonValue::Null),
        ("build_path", PythonValue::Null),
        ("unrendered_config", empty_object()),
        ("created_at", zero_float()),
        ("config_call_dict", empty_object()),
        ("unrendered_config_call_dict", empty_object()),
        ("relation_name", PythonValue::Null),
        ("raw_code", text(compiled_code)),
        ("compiled_code", text(compiled_code)),
        (
            "depends_on",
            object(vec![("macros", empty_array()), ("nodes", depends_on)]),
        ),
    ]
}

/// The generic test node of one planned audit, keyed by its unique id.
pub(crate) fn audit_test_node(
    audit: &ManifestAuditPlanInput,
    project_name: &str,
) -> (String, PythonValue) {
    let id: String = format!("{RESOURCE_TYPE_TEST}.{project_name}.{}", audit.name);
    let mut kwargs: Vec<(String, PythonValue)> = Vec::new();
    if let Some(target) = &audit.attached_target_name {
        kwargs.push(("model".to_owned(), text(target)));
    }
    if let Some(column) = &audit.attached_column_name {
        kwargs.push(("column_name".to_owned(), text(column)));
    }
    let mut fields: Vec<(&str, PythonValue)> = head(&TestNodeHead {
        unique_id: &id,
        name: &audit.name,
        project_name,
    });
    fields.extend([
        (
            "checksum",
            object(vec![
                ("name", text(CHECKSUM_HASH_NAME)),
                ("checksum", text("")),
            ]),
        ),
        ("config", test_config()),
        ("tags", empty_array()),
        ("description", text("")),
        ("columns", empty_object()),
        ("meta", object(vec![("sqlbuild_test_type", text("audit"))])),
    ]);
    fields.extend(tail(
        &audit.resolved_sql,
        unique_ids(&audit.scope_deps, project_name),
    ));
    fields.extend([
        (
            "test_metadata",
            object(vec![("name", text(&audit.name)), ("kwargs", keyed(kwargs))]),
        ),
        (
            "column_name",
            optional_text(audit.attached_column_name.as_deref()),
        ),
    ]);
    (id, object(fields))
}

fn sql_test_meta(test: &ManifestSqlTestPlanInput) -> Result<PythonValue, ManifestError> {
    let mut fields: Vec<(&str, PythonValue)> = vec![("sqlbuild_test_type", text("sql_native"))];
    let (Some(case_name), Some(source_path)) = (&test.case_name, &test.source_path) else {
        return Ok(object(fields));
    };
    let types: HashMap<&str, &str> = test
        .parameter_schema
        .iter()
        .map(|(name, value_type, _)| (name.as_str(), value_type.as_str()))
        .collect();
    let parameters: Vec<PythonValue> = test
        .parameters
        .iter()
        .map(|(name, value)| {
            let value_type: &str = types
                .get(name.as_str())
                .ok_or_else(|| ManifestError::MissingParameterType(name.clone()))?;
            Ok(object(vec![
                ("name", text(name)),
                ("type", text(value_type)),
                ("value", value.clone()),
            ]))
        })
        .collect::<Result<_, ManifestError>>()?;
    fields.extend([
        ("sqlbuild_source_path", text(source_path)),
        ("sqlbuild_block_index", test.block_index.clone()),
        ("sqlbuild_parent_name", test.parent_name.clone()),
        ("sqlbuild_case_name", text(case_name)),
        ("sqlbuild_case_index", test.case_index.clone()),
        (
            "sqlbuild_case_fingerprint",
            optional_text(test.case_fingerprint.as_deref()),
        ),
        (
            "sqlbuild_parameter_schema",
            PythonValue::Array(
                test.parameter_schema
                    .iter()
                    .map(|(name, value_type, nullable)| {
                        object(vec![
                            ("name", text(name)),
                            ("type", text(value_type)),
                            ("nullable", nullable.clone()),
                        ])
                    })
                    .collect(),
            ),
        ),
        ("sqlbuild_parameters", PythonValue::Array(parameters)),
    ]);
    Ok(object(fields))
}

/// The singular test node of one planned SQL test, keyed by its unique id.
pub(crate) fn sql_test_node(
    test: &ManifestSqlTestPlanInput,
    project_name: &str,
) -> Result<(String, PythonValue), ManifestError> {
    let id: String = unique_id(&test.key, project_name);
    let mut parts: Vec<String> = Vec::new();
    for (model_name, resolved_sql) in &test.chain {
        if resolved_sql.is_empty() {
            continue;
        }
        parts.push(format!("-- step: {model_name}"));
        parts.push(resolved_sql.clone());
    }
    let compiled_code: String = parts.join("\n\n");
    let mut fields: Vec<(&str, PythonValue)> = head(&TestNodeHead {
        unique_id: &id,
        name: &test.name,
        project_name,
    });
    fields.extend([
        (
            "checksum",
            object(vec![
                ("name", text(CHECKSUM_HASH_NAME)),
                (
                    "checksum",
                    text(test.case_fingerprint.as_deref().unwrap_or_default()),
                ),
            ]),
        ),
        ("config", test_config()),
        ("tags", empty_array()),
        ("description", text("")),
        ("columns", empty_object()),
        ("meta", sql_test_meta(test)?),
    ]);
    fields.extend(tail(
        &compiled_code,
        unique_ids(&test.scope_deps, project_name),
    ));
    Ok((id, object(fields)))
}
