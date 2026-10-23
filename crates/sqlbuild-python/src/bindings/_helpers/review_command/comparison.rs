//! Compare each built model with `--against`: schema, row counts, keys and values.

use std::collections::BTreeMap;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyTuple, PyTupleMethods};
use sqlbuild_analysis::review_command::constants::{EXACT_LIMIT, MAX_FINDING_EXAMPLES};
use sqlbuild_analysis::review_command::models::{
    ColumnEvidence, IncompleteCheck, NodeComparison, ReviewExample, ReviewFinding, ReviewNode,
};
use sqlbuild_cli::diff_report::models::{DiffModelFacts, DiffValue};
use sqlbuild_host::entries::models::ExecutorHost;

use crate::bindings::_helpers::boundary::python_calls::{call_with, keywords};
use crate::bindings::_helpers::compile_driver::diff::run_diff_pipeline;
use crate::bindings::_helpers::compiled_views::project_reads;
use crate::bindings::_helpers::diff_report::command::target_max_full_rows;
use crate::bindings::_helpers::diff_report::facts::diff_facts;
use crate::bindings::_helpers::diff_report::support::{error_text, matches_class};
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::review_command::planning::ReviewSettings;
use crate::bindings::_helpers::review_command::support::{boolean, optional_text, text, texts};

const KEYED_CHECK: &str = "keyed comparison";
const MAX_EXAMPLE_LENGTH: usize = 80;

/// The comparison of every built model, and the findings and incomplete checks it produced.
#[derive(Default)]
pub(crate) struct Comparisons {
    pub(crate) by_node: BTreeMap<String, NodeComparison>,
    pub(crate) findings: Vec<ReviewFinding>,
    pub(crate) incomplete: Vec<IncompleteCheck>,
}

/// The two compiled projects and the connection a comparison runs on.
pub(crate) struct ComparisonContext<'a, 'py> {
    pub(crate) request: &'a Bound<'py, PyAny>,
    pub(crate) discovered: &'a Bound<'py, PyAny>,
    pub(crate) adapter: &'a Bound<'py, PyAny>,
    pub(crate) connection: &'a Bound<'py, PyAny>,
    pub(crate) connection_config: &'a Bound<'py, PyAny>,
    pub(crate) review_target: &'a str,
}

fn short(value: &DiffValue) -> String {
    let text: &str = &value.text;
    if text.chars().count() <= MAX_EXAMPLE_LENGTH {
        return text.to_owned();
    }
    let kept: String = text.chars().take(MAX_EXAMPLE_LENGTH).collect();
    format!("{kept}…")
}

fn key_text(values: &[(String, DiffValue)]) -> String {
    values
        .iter()
        .map(|(name, value)| format!("{name}={}", short(value)))
        .collect::<Vec<String>>()
        .join(", ")
}

fn models_by_name<'py>(
    project: &Bound<'py, PyAny>,
) -> PyResult<BTreeMap<String, Bound<'py, PyAny>>> {
    let mut models: BTreeMap<String, Bound<'py, PyAny>> = BTreeMap::new();
    for model in project_reads::models(project)?.try_iter()? {
        let model: Bound<'py, PyAny> = model?;
        models.insert(native_field(&model, "name")?.extract()?, model);
    }
    Ok(models)
}

/// Whether the target's relation of `model` exists.
fn target_exists(context: &ComparisonContext<'_, '_>, model: &Bound<'_, PyAny>) -> PyResult<bool> {
    let destination: Bound<'_, PyAny> = native_field(model, "destination")?;
    let exists = call_with(
        &context.adapter.getattr("relation_exists")?,
        &[
            ("connection", context.connection.clone()),
            ("database", native_field(&destination, "database")?),
            ("schema", native_field(&destination, "schema")?),
            ("name", native_field(&destination, "name")?),
        ],
    );
    Ok(exists.is_ok_and(|exists| exists.is_truthy().unwrap_or(false)))
}

fn row_count(context: &ComparisonContext<'_, '_>, relation: &str) -> PyResult<Option<i64>> {
    let cursor: Bound<'_, PyAny> = call_with(
        &context.adapter.getattr("execute")?,
        &[
            ("connection", context.connection.clone()),
            (
                "sql",
                text(
                    context.adapter.py(),
                    &format!("SELECT COUNT(*) FROM {relation}"),
                ),
            ),
        ],
    )?;
    let row: Bound<'_, PyAny> = cursor.call_method0("fetchone")?;
    if row.is_none() {
        return Ok(None);
    }
    row.get_item(0)?.extract()
}

/// One `execute_diff` call for `name`.
fn run_one<'py>(
    context: &ComparisonContext<'_, 'py>,
    (left, right): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    name: &str,
    options: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Option<DiffModelFacts>> {
    let py: Python<'py> = context.adapter.py();
    let mut pairs: Vec<(&str, Bound<'py, PyAny>)> = vec![
        ("collect_samples", boolean(py, true)),
        (
            "max_column_examples",
            pyo3::IntoPyObjectExt::into_bound_py_any(MAX_FINDING_EXAMPLES, py)?,
        ),
        (
            "max_row_only_examples",
            pyo3::IntoPyObjectExt::into_bound_py_any(MAX_FINDING_EXAMPLES, py)?,
        ),
    ];
    pairs.extend(options.iter().cloned());
    let options: Bound<'py, PyAny> = call_with(
        &host::entry(py, ExecutorHost::DiffExecutionOptions)?,
        &pairs,
    )?;
    let result: Bound<'py, PyAny> = call_with(
        &host::entry(py, ExecutorHost::ExecuteDiff)?,
        &[
            ("adapter", context.adapter.clone()),
            ("connection", context.connection.clone()),
            ("left_project", left.clone()),
            ("right_project", right.clone()),
            ("selected_names", PyTuple::new(py, [name])?.into_any()),
            ("options", options),
        ],
    )?;
    Ok(diff_facts(&result)?.into_iter().next())
}

fn incomplete(node: &str, reason: String) -> IncompleteCheck {
    IncompleteCheck {
        node: node.to_owned(),
        check: KEYED_CHECK.to_owned(),
        reason,
    }
}

/// The comparison evidence and findings of one model's diff facts.
fn evidence(facts: &DiffModelFacts, mode: &str, out: &mut Comparisons) -> NodeComparison {
    let name: &str = &facts.name;
    let mut comparison: NodeComparison = NodeComparison {
        mode: mode.to_owned(),
        target_relation: Some(facts.left_relation.clone()),
        branch_relation: Some(facts.right_relation.clone()),
        unique_key: facts.unique_key.clone(),
        added_columns: facts.added_columns.clone(),
        removed_columns: facts.removed_columns.clone(),
        type_changes: facts.type_changes.clone(),
        complete: mode == "full",
        ..NodeComparison::default()
    };
    let schema_changes: usize =
        facts.added_columns.len() + facts.removed_columns.len() + facts.type_changes.len();
    if schema_changes > 0 {
        let mut parts: Vec<String> = Vec::new();
        if !facts.added_columns.is_empty() {
            parts.push(format!("added {}", facts.added_columns.join(", ")));
        }
        if !facts.removed_columns.is_empty() {
            parts.push(format!("removed {}", facts.removed_columns.join(", ")));
        }
        for (column, from, to) in &facts.type_changes {
            parts.push(format!("{column} {from} → {to}"));
        }
        out.findings.push(ReviewFinding {
            node: name.to_owned(),
            kind: "schema".to_owned(),
            metric: format!("schema changed: {}", parts.join("; ")),
            limit: EXACT_LIMIT.to_owned(),
            ..ReviewFinding::default()
        });
    }
    let Some(rows) = &facts.rows else {
        return comparison;
    };
    comparison.target_rows = Some(rows.left_count);
    comparison.branch_rows = Some(rows.right_count);
    comparison.compared_rows = Some(rows.compared_count);
    comparison.branch_only_keys = rows.right_only_count;
    comparison.target_only_keys = rows.left_only_count;
    if rows.left_count != rows.right_count {
        out.findings.push(ReviewFinding {
            node: name.to_owned(),
            kind: "row_count".to_owned(),
            metric: "row count".to_owned(),
            target_value: Some(rows.left_count.to_string()),
            branch_value: Some(rows.right_count.to_string()),
            limit: EXACT_LIMIT.to_owned(),
            ..ReviewFinding::default()
        });
    }
    for (count, side, keys) in [
        (rows.right_only_count, "branch-only", &facts.right_only_keys),
        (rows.left_only_count, "target-only", &facts.left_only_keys),
    ] {
        if count == 0 {
            continue;
        }
        out.findings.push(ReviewFinding {
            node: name.to_owned(),
            kind: "keys".to_owned(),
            metric: format!("{count} {side} keys"),
            limit: EXACT_LIMIT.to_owned(),
            examples: keys
                .iter()
                .take(MAX_FINDING_EXAMPLES)
                .map(|key| ReviewExample {
                    key: key_text(key),
                    ..ReviewExample::default()
                })
                .collect(),
            ..ReviewFinding::default()
        });
    }
    let mut changed: usize = 0;
    for column in &rows.columns {
        if column.mismatched_count == 0 {
            continue;
        }
        changed += 1;
        comparison.columns.push(ColumnEvidence {
            column: column.name.clone(),
            metric: "rows that differ".to_owned(),
            target: "0".to_owned(),
            branch: column.mismatched_count.to_string(),
            limit: "0".to_owned(),
        });
        let examples: Vec<ReviewExample> = facts
            .unequal_samples
            .iter()
            .filter_map(|sample| {
                let cell = sample
                    .changed_cells
                    .iter()
                    .find(|cell| cell.name == column.name)?;
                Some(ReviewExample {
                    key: key_text(&sample.key_values),
                    target: Some(short(&cell.left)),
                    branch: Some(short(&cell.right)),
                })
            })
            .take(MAX_FINDING_EXAMPLES)
            .collect();
        out.findings.push(ReviewFinding {
            node: name.to_owned(),
            kind: "values".to_owned(),
            metric: format!(
                "values differ in {} of {} matched rows",
                column.mismatched_count, rows.joined_count
            ),
            column: Some(column.name.clone()),
            limit: EXACT_LIMIT.to_owned(),
            examples,
            ..ReviewFinding::default()
        });
    }
    comparison.unchanged_columns = rows.columns.len().saturating_sub(changed);
    comparison
}

/// Compare each of `models` (built, by name) between `--against` and the review schema.
pub(crate) fn compare_models(
    context: &ComparisonContext<'_, '_>,
    settings: &ReviewSettings,
    models: &[&ReviewNode],
) -> PyResult<Comparisons> {
    let py: Python<'_> = context.adapter.py();
    let mut out: Comparisons = Comparisons::default();
    if models.is_empty() {
        return Ok(out);
    }
    let names: Vec<String> = models.iter().map(|node| node.name.clone()).collect();
    let pipeline: Bound<'_, PyTuple> = run_diff_pipeline(
        py,
        Some(keywords(
            py,
            &[
                ("discovered_inputs", context.discovered.clone()),
                ("adapter", context.adapter.clone()),
                ("from_target", text(py, &settings.against)),
                ("to_target", text(py, context.review_target)),
                ("resolved_connection", context.connection_config.clone()),
                ("no_sql_validation", boolean(py, true)),
                ("select", texts(py, &names)?),
                ("exclude", PyTuple::empty(py).into_any()),
                ("cli_vars", native_field(context.request, "cli_vars")?),
            ],
        )?),
    )?;
    let left: Bound<'_, PyAny> = pipeline.get_item(0)?;
    let right: Bound<'_, PyAny> = pipeline.get_item(1)?;
    let left_models = models_by_name(&left)?;
    let bounded: Option<String> = optional_text(&native_field(context.request, "bounded")?)?;
    let limits: Bound<'_, PyAny> = call_with(
        &host::entry(py, ExecutorHost::FullDiffSizeLimits)?,
        &[
            ("left_target", text(py, &settings.against)),
            ("right_target", text(py, context.review_target)),
            (
                "left_max_rows",
                target_max_full_rows(context.discovered, &text(py, &settings.against))?,
            ),
            (
                "right_max_rows",
                target_max_full_rows(context.discovered, &text(py, context.review_target))?,
            ),
        ],
    )?;
    for node in models {
        let name: &str = &node.name;
        let exists: bool = match left_models.get(name) {
            Some(model) => target_exists(context, model)?,
            None => false,
        };
        if !exists {
            out.by_node.insert(
                name.to_owned(),
                NodeComparison {
                    mode: "none".to_owned(),
                    complete: true,
                    ..NodeComparison::default()
                },
            );
            continue;
        }
        if node.unique_key.is_empty() {
            let facts: Option<DiffModelFacts> = run_one(
                context,
                (&left, &right),
                name,
                &[("schema_only", boolean(py, true))],
            )?;
            let Some(facts) = facts else { continue };
            let mut comparison: NodeComparison = evidence(&facts, "schema_only", &mut out);
            comparison.target_rows = row_count(context, &facts.left_relation)?;
            comparison.branch_rows = row_count(context, &facts.right_relation)?;
            if let (Some(target), Some(branch)) = (comparison.target_rows, comparison.branch_rows)
                && target != branch
            {
                out.findings.push(ReviewFinding {
                    node: name.to_owned(),
                    kind: "row_count".to_owned(),
                    metric: "row count".to_owned(),
                    target_value: Some(target.to_string()),
                    branch_value: Some(branch.to_string()),
                    limit: EXACT_LIMIT.to_owned(),
                    ..ReviewFinding::default()
                });
            }
            out.incomplete.push(incomplete(
                name,
                "the model has no unique_key, so only the schema and row counts were compared"
                    .to_owned(),
            ));
            out.by_node.insert(name.to_owned(), comparison);
            continue;
        }
        let full = run_one(
            context,
            (&left, &right),
            name,
            &[
                ("schema_only", boolean(py, false)),
                ("full_size_limits", limits.clone()),
            ],
        );
        let (facts, mode) = match full {
            Ok(facts) => (facts, "full"),
            Err(error) if matches_class(py, &error, ExecutorHost::FullDiffSizeGuardError)? => {
                match (&bounded, node.has_cursor) {
                    (Some(window), true) => {
                        let facts = run_one(
                            context,
                            (&left, &right),
                            name,
                            &[
                                ("schema_only", boolean(py, false)),
                                ("bounded", text(py, window)),
                            ],
                        )?;
                        out.incomplete.push(IncompleteCheck {
                            node: name.to_owned(),
                            check: KEYED_CHECK.to_owned(),
                            reason: format!(
                                "too large for an exact comparison; compared the last {window} only"
                            ),
                        });
                        (facts, "bounded")
                    }
                    _ => {
                        let hint: &str = if node.has_cursor {
                            "; pass --bounded <window> to compare a recent window"
                        } else {
                            ""
                        };
                        out.incomplete.push(incomplete(
                            name,
                            format!(
                                "too large for an exact comparison, or its size is unknown{hint}"
                            ),
                        ));
                        let facts = run_one(
                            context,
                            (&left, &right),
                            name,
                            &[("schema_only", boolean(py, true))],
                        )?;
                        (facts, "schema_only")
                    }
                }
            }
            Err(error) if error.is_instance_of::<pyo3::exceptions::PyException>(py) => {
                out.incomplete
                    .push(incomplete(name, error_text(py, &error)?));
                out.by_node.insert(
                    name.to_owned(),
                    NodeComparison {
                        mode: "none".to_owned(),
                        target_relation: Some(String::new()),
                        ..NodeComparison::default()
                    },
                );
                continue;
            }
            Err(error) => return Err(error),
        };
        if let Some(facts) = facts {
            let comparison: NodeComparison = evidence(&facts, mode, &mut out);
            out.by_node.insert(name.to_owned(), comparison);
        }
    }
    Ok(out)
}
