//! dbt-compatible macro nodes of project macros and SQL hook definitions.

use std::collections::HashMap;

use crate::manifest::_helpers::values::{
    docs, empty_array, keyed, object, optional_text, text, text_or_empty, zero_float,
};
use crate::manifest::constants::{RESOURCE_TYPE_MACRO, SQL_HOOK_PACKAGE_SUFFIX};
use crate::manifest::models::{
    ManifestInput, ManifestMacroDeclarationInput, ManifestMacroInput, ManifestSqlHookInput,
};
use crate::python_values::models::PythonValue;

fn macro_node(
    loaded: &ManifestMacroInput,
    project_name: &str,
    declaration: (Option<&Vec<String>>, Option<&ManifestMacroDeclarationInput>),
) -> PythonValue {
    let (dependencies, record) = declaration;
    let path: &str = &loaded.relative_path;
    object(vec![
        ("name", text(&loaded.name)),
        ("resource_type", text(RESOURCE_TYPE_MACRO)),
        ("package_name", text(project_name)),
        ("path", text(path)),
        ("original_file_path", text(path)),
        (
            "unique_id",
            text(&format!(
                "{RESOURCE_TYPE_MACRO}.{project_name}.{}",
                loaded.name
            )),
        ),
        ("macro_sql", text(&loaded.raw_source)),
        (
            "depends_on",
            object(vec![(
                "macros",
                PythonValue::Array(
                    dependencies
                        .map(Vec::as_slice)
                        .unwrap_or_default()
                        .iter()
                        .map(|name| text(&format!("{RESOURCE_TYPE_MACRO}.{project_name}.{name}")))
                        .collect(),
                ),
            )]),
        ),
        ("description", text("")),
        (
            "meta",
            object(vec![
                (
                    "sqlbuild_visibility",
                    text(record.map_or("global", |record| record.scope.as_str())),
                ),
                (
                    "sqlbuild_scope_path",
                    optional_text(record.and_then(|record| record.owning_path.as_deref())),
                ),
            ]),
        ),
        ("docs", docs()),
        ("patch_path", PythonValue::Null),
        ("arguments", empty_array()),
        ("created_at", zero_float()),
        ("supported_languages", PythonValue::Null),
    ])
}

fn sql_hook_node(hook: &ManifestSqlHookInput, project_name: &str) -> PythonValue {
    let package: String = format!("{project_name}{SQL_HOOK_PACKAGE_SUFFIX}");
    object(vec![
        ("name", text(&hook.name)),
        ("resource_type", text(RESOURCE_TYPE_MACRO)),
        ("package_name", text(&package)),
        ("path", text(&hook.relative_path)),
        ("original_file_path", text(&hook.relative_path)),
        (
            "unique_id",
            text(&format!("{RESOURCE_TYPE_MACRO}.{package}.{}", hook.name)),
        ),
        ("macro_sql", text(&hook.sql_body)),
        ("depends_on", object(vec![("macros", empty_array())])),
        ("description", text_or_empty(hook.description.as_deref())),
        (
            "meta",
            object(vec![
                ("sqlbuild_resource_type", text("sql_hook")),
                ("sqlbuild_hook_name", text(&hook.name)),
            ]),
        ),
        ("docs", docs()),
        ("patch_path", PythonValue::Null),
        ("arguments", empty_array()),
        ("created_at", zero_float()),
        ("supported_languages", PythonValue::Null),
    ])
}

/// Every macro node: project macros, then SQL hook definitions.
pub(crate) fn macro_nodes(input: &ManifestInput) -> PythonValue {
    let project_name: &str = &input.project_name;
    let mut dependencies: HashMap<&str, &Vec<String>> = HashMap::new();
    let mut records: HashMap<&str, &ManifestMacroDeclarationInput> = HashMap::new();
    for record in &input.macro_declarations {
        if let Some(names) = &record.dependencies {
            dependencies.insert(&record.name, names);
        }
        records.insert(&record.name, record);
    }
    let mut nodes: Vec<(String, PythonValue)> = Vec::new();
    for loaded in &input.macros {
        let name: &str = &loaded.key;
        nodes.push((
            format!("{RESOURCE_TYPE_MACRO}.{project_name}.{name}"),
            macro_node(
                loaded,
                project_name,
                (dependencies.get(name).copied(), records.get(name).copied()),
            ),
        ));
    }
    for hook in &input.sql_hooks {
        nodes.push((
            format!(
                "{RESOURCE_TYPE_MACRO}.{project_name}{SQL_HOOK_PACKAGE_SUFFIX}.{}",
                hook.name
            ),
            sql_hook_node(hook, project_name),
        ));
    }
    keyed(nodes)
}
