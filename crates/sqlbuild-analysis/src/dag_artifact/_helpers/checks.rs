//! `DagCheck` values of SQL tests, audits, scenarios and Python checks, sorted.

use std::collections::HashMap;

use crate::dag_artifact::_helpers::edges::python_kinds;
use crate::dag_artifact::_helpers::nodes::{node_id, python_node_id};
use crate::dag_artifact::_helpers::values::{integer, object, optional_text, text, texts};
use crate::dag_artifact::constants::{
    AUDIT_KIND, CHECK_KIND, MODEL_KIND, PYTHON_CHECK_KIND, SCENARIO_KIND, SQL_TEST_KIND,
};
use crate::dag_artifact::errors::DagArtifactError;
use crate::dag_artifact::models::{
    DagAuditInput, DagProjectInput, DagPythonGraphInput, DagPythonNodeInput, DagScenarioInput,
    DagSqlTestInput,
};
use crate::dag_artifact::types::DagValue;

/// Every `DagCheck` field, `None` or empty where a check kind leaves it out.
#[derive(Default)]
struct CheckFields {
    id: String,
    kind: String,
    name: String,
    checked_asset_ids: Vec<String>,
    path: Option<String>,
    description: Option<String>,
    severity: Option<String>,
    tags: Vec<String>,
    group: Option<String>,
    meta: Option<DagValue>,
    attachment_kind: Option<String>,
    attached_target_name: Option<String>,
    attached_column_name: Option<String>,
    mode: Option<String>,
    assertion_names: Vec<String>,
    expected_model_names: Vec<String>,
    graph_asset_ids: Vec<String>,
    fixture_refs: Vec<String>,
}

fn strings(values: &[String]) -> DagValue {
    texts(values.iter().map(String::as_str))
}

impl CheckFields {
    fn value(self) -> DagValue {
        object(vec![
            ("id", text(&self.id)),
            ("kind", text(&self.kind)),
            ("name", text(&self.name)),
            ("checked_asset_ids", strings(&self.checked_asset_ids)),
            ("path", optional_text(self.path.as_deref())),
            ("description", optional_text(self.description.as_deref())),
            ("severity", optional_text(self.severity.as_deref())),
            ("tags", strings(&self.tags)),
            ("group", optional_text(self.group.as_deref())),
            ("meta", self.meta.unwrap_or(DagValue::Object(Vec::new()))),
            (
                "attachment_kind",
                optional_text(self.attachment_kind.as_deref()),
            ),
            (
                "attached_target_name",
                optional_text(self.attached_target_name.as_deref()),
            ),
            (
                "attached_column_name",
                optional_text(self.attached_column_name.as_deref()),
            ),
            ("mode", optional_text(self.mode.as_deref())),
            ("assertion_names", strings(&self.assertion_names)),
            ("expected_model_names", strings(&self.expected_model_names)),
            ("graph_asset_ids", strings(&self.graph_asset_ids)),
            ("fixture_refs", strings(&self.fixture_refs)),
        ])
    }
}

fn optional_integer(value: Option<i64>) -> DagValue {
    value.map_or(DagValue::Null, integer)
}

fn sql_test_meta(test: &DagSqlTestInput) -> Result<DagValue, DagArtifactError> {
    let Some(case) = &test.case else {
        return Ok(DagValue::Object(Vec::new()));
    };
    let types: HashMap<&str, &str> = case
        .parameter_schema
        .iter()
        .map(|(name, value_type, _)| (name.as_str(), value_type.as_str()))
        .collect();
    let parameters: Vec<DagValue> = case
        .parameters
        .iter()
        .map(|(name, value)| {
            let value_type: &str = types
                .get(name.as_str())
                .ok_or_else(|| DagArtifactError::MissingParameterType(name.clone()))?;
            Ok(object(vec![
                ("name", text(name)),
                ("type", text(value_type)),
                ("value", value.clone()),
            ]))
        })
        .collect::<Result<_, DagArtifactError>>()?;
    Ok(object(vec![
        ("source_path", text(&test.source_path)),
        ("block_index", optional_integer(case.block_index)),
        ("parent_name", optional_text(case.parent_name.as_deref())),
        ("case_name", text(&case.case_name)),
        ("case_index", optional_integer(case.case_index)),
        (
            "case_fingerprint",
            optional_text(case.case_fingerprint.as_deref()),
        ),
        (
            "parameter_schema",
            DagValue::Array(
                case.parameter_schema
                    .iter()
                    .map(|(name, value_type, nullable)| {
                        object(vec![
                            ("name", text(name)),
                            ("type", text(value_type)),
                            ("nullable", DagValue::Bool(*nullable)),
                        ])
                    })
                    .collect(),
            ),
        ),
        ("parameters", DagValue::Array(parameters)),
    ]))
}

fn sql_test_check(test: &DagSqlTestInput) -> Result<(String, String, DagValue), DagArtifactError> {
    let id: String = match &test.case {
        None => node_id(&test.key),
        Some(case) => {
            let block_index: String = case
                .block_index
                .map_or_else(|| String::from("None"), |index| index.to_string());
            format!(
                "{SQL_TEST_KIND}:{}:{block_index}:{}",
                test.source_path, case.case_name
            )
        }
    };
    let value: DagValue = CheckFields {
        id,
        kind: SQL_TEST_KIND.to_owned(),
        name: test.name.clone(),
        checked_asset_ids: test.scope_deps.iter().map(node_id).collect(),
        path: Some(test.path.clone()),
        mode: Some(test.mode.clone()),
        meta: Some(sql_test_meta(test)?),
        ..CheckFields::default()
    }
    .value();
    Ok((SQL_TEST_KIND.to_owned(), test.name.clone(), value))
}

fn audit_check(audit: &DagAuditInput) -> (String, String, DagValue) {
    let checked_asset_ids: Vec<String> =
        match (&audit.attached_target_kind, &audit.attached_target_name) {
            (Some(kind), Some(name)) => vec![node_id(&(kind.clone(), name.clone()))],
            _ => audit.scope_deps.iter().map(node_id).collect(),
        };
    let id: String = [
        Some(node_id(&audit.key)),
        audit.attached_target_kind.clone(),
        audit.attached_target_name.clone(),
        audit.attached_column_name.clone(),
    ]
    .into_iter()
    .flatten()
    .filter(|part| !part.is_empty())
    .collect::<Vec<String>>()
    .join(":");
    let value: DagValue = CheckFields {
        id,
        kind: AUDIT_KIND.to_owned(),
        name: audit.name.clone(),
        checked_asset_ids,
        path: Some(audit.path.clone()),
        severity: audit.severity.clone(),
        attachment_kind: audit.attached_target_kind.clone(),
        attached_target_name: audit.attached_target_name.clone(),
        attached_column_name: audit.attached_column_name.clone(),
        ..CheckFields::default()
    }
    .value();
    (AUDIT_KIND.to_owned(), audit.name.clone(), value)
}

fn model_id(name: &str) -> String {
    node_id(&(MODEL_KIND.to_owned(), name.to_owned()))
}

fn scenario_check(scenario: &DagScenarioInput) -> (String, String, DagValue) {
    let value: DagValue = CheckFields {
        id: node_id(&scenario.key),
        kind: SCENARIO_KIND.to_owned(),
        name: scenario.name.clone(),
        checked_asset_ids: scenario
            .expected_model_names
            .iter()
            .map(|name| model_id(name))
            .collect(),
        path: Some(scenario.path.clone()),
        assertion_names: scenario.assertion_names.clone(),
        expected_model_names: scenario.expected_model_names.clone(),
        graph_asset_ids: scenario
            .authored_cte_names
            .iter()
            .map(|name| model_id(name))
            .collect(),
        fixture_refs: scenario.fixture_names.concat(),
        ..CheckFields::default()
    }
    .value();
    (SCENARIO_KIND.to_owned(), scenario.name.clone(), value)
}

fn python_check(
    node: &DagPythonNodeInput,
    python: &DagPythonGraphInput,
    kinds: &HashMap<&str, &str>,
) -> (String, String, DagValue) {
    let mut checked_asset_ids: Vec<String> = python
        .dependency_edges
        .iter()
        .filter(|(_, downstream)| *downstream == node.name)
        .map(|(upstream, _)| python_node_id(kinds[upstream.as_str()], upstream))
        .collect();
    checked_asset_ids.extend(node.sql_deps.iter().map(node_id));
    let value: DagValue = CheckFields {
        id: python_node_id(&node.kind, &node.name),
        kind: PYTHON_CHECK_KIND.to_owned(),
        name: node.name.clone(),
        checked_asset_ids,
        path: Some(node.path.clone()),
        description: node.description.clone(),
        severity: node.check_severity.clone(),
        tags: node.tags.clone(),
        group: node.group.clone(),
        meta: Some(node.meta.clone()),
        ..CheckFields::default()
    }
    .value();
    (PYTHON_CHECK_KIND.to_owned(), node.name.clone(), value)
}

/// Every check, sorted by `(kind, name)`.
pub(crate) fn checks(
    project: &DagProjectInput,
    python: Option<&DagPythonGraphInput>,
) -> Result<DagValue, DagArtifactError> {
    let mut checks: Vec<(String, String, DagValue)> = project
        .sql_tests
        .iter()
        .map(sql_test_check)
        .collect::<Result<_, _>>()?;
    checks.extend(project.audits.iter().map(audit_check));
    checks.extend(project.scenarios.iter().map(scenario_check));
    if let Some(python) = python {
        let kinds: HashMap<&str, &str> = python_kinds(python);
        checks.extend(
            python
                .nodes
                .iter()
                .filter(|node| node.kind == CHECK_KIND)
                .map(|node| python_check(node, python, &kinds)),
        );
    }
    checks.sort_by(|left, right| (&left.0, &left.1).cmp(&(&right.0, &right.1)));
    Ok(DagValue::Array(
        checks.into_iter().map(|(_, _, value)| value).collect(),
    ))
}
