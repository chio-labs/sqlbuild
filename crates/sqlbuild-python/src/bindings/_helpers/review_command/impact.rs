//! The downstream columns a change reaches, from column lineage.

use sqlbuild_analysis::review_command::constants::NO_COMPARISON_MODE;
use std::collections::{BTreeMap, BTreeSet};

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet};
use sqlbuild_analysis::review_command::models::NodeComparison;

use crate::bindings::_helpers::compiled_views::{model_reads, project_reads};
use crate::bindings::_helpers::records::construct::enum_member;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;

/// The columns of a changed model a comparison proved changed, or `None` when every column may.
fn changed_columns(comparison: Option<&NodeComparison>) -> Option<Vec<String>> {
    let comparison: &NodeComparison = comparison?;
    if !comparison.complete || comparison.mode == NO_COMPARISON_MODE {
        return None;
    }
    let mut columns: Vec<String> = comparison.added_columns.clone();
    columns.extend(
        comparison
            .type_changes
            .iter()
            .map(|(column, _, _)| column.clone()),
    );
    columns.extend(
        comparison
            .columns
            .iter()
            .map(|column| column.column.clone()),
    );
    Some(columns)
}

/// Affected columns of each downstream node of `changed`, within `affected`.
pub(crate) fn affected_columns(
    project: &Bound<'_, PyAny>,
    (changed, affected): (&[String], &BTreeSet<String>),
    comparisons: &BTreeMap<String, NodeComparison>,
) -> PyResult<BTreeMap<String, Vec<String>>> {
    let py: Python<'_> = project.py();
    let mut models: BTreeMap<String, Bound<'_, PyAny>> = BTreeMap::new();
    for model in project_reads::models(project)?.try_iter()? {
        let model: Bound<'_, PyAny> = model?;
        let name: String = model_reads::model_name(&model)?;
        if affected.contains(&name) {
            models.insert(name, model);
        }
    }
    let names: Vec<&String> = models.keys().collect();
    let lineage: PyResult<Bound<'_, PyAny>> =
        registry::native(py, NativeAttr::BuildProjectColumnLineage)?.call1((
            project,
            py.None(),
            enum_member(py, RecordId::ColumnLineageMode, "FAST")?,
            PyFrozenSet::new(py, &names)?,
        ));
    let Ok(lineage) = lineage else {
        return Ok(BTreeMap::new());
    };
    if lineage.is_none() {
        return Ok(BTreeMap::new());
    }
    let mut pending: Vec<(String, String)> = Vec::new();
    for name in changed {
        let Some(model) = models.get(name) else {
            continue;
        };
        let columns: Vec<String> = match changed_columns(comparisons.get(name)) {
            Some(columns) => columns,
            None => model_reads::inferred_names(model)?.unwrap_or_default(),
        };
        pending.extend(columns.into_iter().map(|column| (name.clone(), column)));
    }
    let mut seen: BTreeSet<(String, String)> = BTreeSet::new();
    let mut reached: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    while let Some((resource, column)) = pending.pop() {
        if !seen.insert((resource.clone(), column.clone())) {
            continue;
        }
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("resource_name", &resource)?;
        options.set_item("column_name", &column)?;
        let Ok(edges) = lineage.call_method("column_consumers", (), Some(&options)) else {
            continue;
        };
        for edge in edges.try_iter()? {
            let target: Bound<'_, PyAny> = native_field(&edge?, "target")?;
            let name: String = native_field(&target, "resource_name")?.extract()?;
            let column_name: String = native_field(&target, "column_name")?.extract()?;
            if !affected.contains(&name) || changed.contains(&name) {
                continue;
            }
            reached
                .entry(name.clone())
                .or_default()
                .insert(column_name.clone());
            pending.push((name, column_name));
        }
    }
    Ok(reached
        .into_iter()
        .map(|(name, columns)| (name, columns.into_iter().collect()))
        .collect())
}
