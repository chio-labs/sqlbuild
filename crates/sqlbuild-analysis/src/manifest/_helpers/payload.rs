//! The complete manifest payload.

use std::collections::{HashMap, HashSet};

use crate::graph::main::unique_id_edges::unique_id_edges;
use crate::graph::models::{EdgeDirection, ProjectGraph};
use crate::manifest::_helpers::macros::macro_nodes;
use crate::manifest::_helpers::model_nodes::{ModelNodeContext, model_node};
use crate::manifest::_helpers::resource_nodes::{seed_node, source_node};
use crate::manifest::_helpers::test_nodes::{audit_test_node, sql_test_node};
use crate::manifest::_helpers::values::{empty_object, keyed, object, text};
use crate::manifest::constants::{
    DBT_MANIFEST_SCHEMA_VERSION, DBT_VERSION, RESOURCE_TYPE_MODEL, RESOURCE_TYPE_PREFIXES,
    RESOURCE_TYPE_SEED, RESOURCE_TYPE_SOURCE,
};
use crate::manifest::errors::ManifestError;
use crate::manifest::models::{ManifestInput, ManifestPlanInput};
use crate::python_values::models::PythonValue;
use crate::sql_tokens::main::compiler_query_fingerprint::compiler_query_fingerprint;

/// Each planned model's resolved SQL; a later entry of the same name wins.
fn resolved_sql(plan: &ManifestPlanInput) -> HashMap<&str, &str> {
    plan.models
        .iter()
        .map(|(name, sql)| (name.as_str(), sql.as_str()))
        .collect()
}

fn id_list(ids: &[String]) -> PythonValue {
    PythonValue::Array(ids.iter().map(|id| text(id)).collect())
}

fn nodes(input: &ManifestInput) -> Result<PythonValue, ManifestError> {
    let project_name: &str = &input.project_name;
    let plan: Option<&ManifestPlanInput> = input.plan.as_ref();
    let resolved: HashMap<&str, &str> = plan.map(resolved_sql).unwrap_or_default();
    let mut nodes: Vec<(String, PythonValue)> = Vec::new();
    for model in &input.models {
        let query_hash: String =
            compiler_query_fingerprint(&model.query_sql, input.sql_analysis_dialect.as_deref())
                .map_err(ManifestError::QueryFingerprint)?;
        nodes.push((
            format!("{RESOURCE_TYPE_MODEL}.{project_name}.{}", model.name),
            model_node(
                model,
                &ModelNodeContext {
                    project_name,
                    compiled_code: resolved.get(model.name.as_str()).copied(),
                    query_hash: &query_hash,
                    python_hooks: &input.python_hooks,
                },
            ),
        ));
    }
    for seed in &input.seeds {
        nodes.push((
            format!("{RESOURCE_TYPE_SEED}.{project_name}.{}", seed.name),
            seed_node(seed, project_name),
        ));
    }
    if let Some(plan) = plan {
        nodes.extend(
            plan.audits
                .iter()
                .map(|audit| audit_test_node(audit, project_name)),
        );
        for test in &plan.sql_tests {
            nodes.push(sql_test_node(test, project_name)?);
        }
    }
    Ok(keyed(nodes))
}

fn sources(input: &ManifestInput) -> PythonValue {
    let project_name: &str = &input.project_name;
    let loaded: HashSet<&str> = input
        .plan
        .as_ref()
        .map(|plan| plan.source_load_names.iter().map(String::as_str).collect())
        .unwrap_or_default();
    keyed(
        input
            .sources
            .iter()
            .map(|source| {
                (
                    format!("{RESOURCE_TYPE_SOURCE}.{project_name}.{}", source.name),
                    source_node(source, project_name, loaded.contains(source.name.as_str())),
                )
            })
            .collect(),
    )
}

fn id_map(graph: &ProjectGraph, direction: EdgeDirection, project_name: &str) -> PythonValue {
    let prefixes: HashMap<String, String> = RESOURCE_TYPE_PREFIXES
        .iter()
        .map(|(kind, prefix)| ((*kind).to_owned(), (*prefix).to_owned()))
        .collect();
    keyed(
        unique_id_edges(graph, direction, project_name, &prefixes)
            .into_iter()
            .map(|(id, neighbours)| (id, id_list(&neighbours)))
            .collect(),
    )
}

fn metadata(input: &ManifestInput) -> PythonValue {
    object(vec![
        ("dbt_schema_version", text(DBT_MANIFEST_SCHEMA_VERSION)),
        ("dbt_version", text(DBT_VERSION)),
        ("generated_at", text(&input.generated_at)),
        ("invocation_id", text(&input.run_id)),
        ("env", empty_object()),
        ("project_name", text(&input.project_name)),
        ("project_id", PythonValue::Null),
        ("user_id", PythonValue::Null),
        ("send_anonymous_usage_stats", PythonValue::Bool(false)),
        ("adapter_type", text(&input.adapter_type)),
    ])
}

/// The manifest dict `build_manifest_payload` returned.
pub(crate) fn payload(
    input: &ManifestInput,
    graph: &ProjectGraph,
) -> Result<PythonValue, ManifestError> {
    let macros: PythonValue = macro_nodes(input);
    let nodes: PythonValue = nodes(input)?;
    let sources: PythonValue = sources(input);
    let project_name: &str = &input.project_name;
    Ok(object(vec![
        ("metadata", metadata(input)),
        ("nodes", nodes),
        ("sources", sources),
        ("macros", macros),
        ("exposures", empty_object()),
        ("metrics", empty_object()),
        ("groups", empty_object()),
        ("selectors", empty_object()),
        ("disabled", empty_object()),
        (
            "parent_map",
            id_map(graph, EdgeDirection::Upstream, project_name),
        ),
        (
            "child_map",
            id_map(graph, EdgeDirection::Downstream, project_name),
        ),
        ("group_map", empty_object()),
        ("docs", empty_object()),
        ("saved_queries", empty_object()),
        ("semantic_models", empty_object()),
        ("unit_tests", empty_object()),
    ]))
}
