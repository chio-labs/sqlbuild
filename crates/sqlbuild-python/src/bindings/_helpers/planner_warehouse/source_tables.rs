//! Selected-scope validation that external source tables exist in the warehouse.

use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::planner_phases::objects::{planner_error, tuple};
use crate::bindings::_helpers::planner_warehouse::constants::{
    MISSING_SOURCE_TABLE_CODE, RENDER_SOURCE_READ, RUN_BOUNDED, WILDCARD_TABLE_CHARACTER,
    YAML_ENTRY_LINE,
};
use crate::bindings::_helpers::records::registry;
use pyo3::IntoPyObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::pyfunction;
use pyo3::types::PyDict as KeywordDict;
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use sqlbuild_analysis::planner_warehouse::main::missing_source_tables_help::missing_source_tables_help;
use sqlbuild_analysis::planner_warehouse::main::missing_source_tables_message::missing_source_tables_message;
use sqlbuild_analysis::planner_warehouse::models::MissingSourceTable;
use std::collections::HashMap;

fn selected_source_readers(scope: &Bound<'_, PyAny>) -> PyResult<HashMap<String, Vec<String>>> {
    let mut readers: HashMap<String, Vec<String>> = HashMap::new();
    let deps = scope.getattr("upstream_deps")?;
    for key in scope.getattr("selected_keys")?.try_iter()? {
        let key = key?;
        if key.getattr("resource_type")?.eq("source")? {
            continue;
        }
        let reader: String = key.getattr("name")?.extract()?;
        for dep in deps
            .call_method1("get", (&key, PyTuple::empty(key.py())))?
            .try_iter()?
        {
            let dep = dep?;
            if dep.getattr("resource_type")?.eq("source")? {
                readers
                    .entry(dep.getattr("name")?.extract()?)
                    .or_default()
                    .push(reader.clone());
            }
        }
    }
    Ok(readers)
}

fn table_name(entry: &Bound<'_, PyAny>) -> PyResult<String> {
    let table = entry.getattr("table")?;
    if table.is_none() {
        entry.getattr("name")?.extract()
    } else {
        table.extract()
    }
}

fn external_table(entry: &Bound<'_, PyAny>) -> PyResult<bool> {
    Ok(!entry.getattr("managed")?.is_truthy()?
        && entry.getattr("loader")?.is_none()
        && entry.getattr("integration_loader")?.is_none()
        && entry.getattr("expression")?.is_none()
        && !entry.getattr("schema")?.is_none()
        && !table_name(entry)?.contains(WILDCARD_TABLE_CHARACTER))
}

fn read_relation<'py>(
    adapter: &Bound<'py, PyAny>,
    entry: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &registry::native(adapter.py(), RENDER_SOURCE_READ)?,
        &[
            ("adapter", adapter.clone()),
            ("source_entry", entry.clone()),
        ],
    )
}

fn declaration_location(source: &Bound<'_, PyAny>) -> PyResult<String> {
    let file = source.getattr("source_file")?;
    let path: String = file
        .getattr("relative_path")?
        .call_method0("as_posix")?
        .extract()?;
    let line = call_with(
        &registry::native(source.py(), YAML_ENTRY_LINE)?,
        &[
            ("contents", file.getattr("contents")?),
            ("name", source.getattr("name")?),
        ],
    )?;
    if line.is_none() {
        Ok(path)
    } else {
        Ok(format!("{path}:{}", line.str()?))
    }
}

/// Raise S405 when a selected resource reads an external source table that does not exist.
pub(crate) fn check_selected_source_tables_exist<'py>(
    project: &Bound<'py, PyAny>,
    (adapter, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    scope: &Bound<'py, PyAny>,
    relations: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let py = project.py();
    let readers = selected_source_readers(scope)?;
    let read_map = relations.getattr("source_read_map")?;
    let listed = relations.getattr("listed_source_names")?;
    let mut unlisted: Vec<(Bound<'py, PyAny>, Bound<'py, PyAny>, Vec<String>)> = Vec::new();
    for source in project.getattr("sources")?.try_iter()? {
        let source = source?;
        let name: String = source.getattr("name")?.extract()?;
        let Some(source_readers) = readers.get(&name).filter(|readers| !readers.is_empty()) else {
            continue;
        };
        let declared = source.getattr("source_entry")?;
        let entry = read_map.call_method1("get", (&name, &declared))?;
        if !external_table(&declared)? || !external_table(&entry)? {
            continue;
        }
        if listed.contains(&name)? {
            continue;
        }
        let mut sorted = source_readers.clone();
        sorted.sort();
        unlisted.push((source, entry, sorted));
    }
    if unlisted.is_empty() {
        return Ok(());
    }
    let probe = adapter.getattr("probe_relation_read")?;
    let mut tasks: Vec<_> = Vec::new();
    for (_, entry, _) in &unlisted {
        let fields = keywords(
            py,
            &[
                ("connection", connection.clone()),
                ("relation", read_relation(adapter, entry)?),
            ],
        )?;
        tasks.push(imported(py, "functools", "partial")?.call((&probe,), Some(&fields))?);
    }
    let concurrency: i64 = imported(py, "builtins", "int")?
        .call1((adapter.getattr("metadata_inspection_concurrency")?,))?
        .extract()?;
    let probes = call_with(
        &host::entry(py, RUN_BOUNDED)?,
        &[
            ("tasks", tuple(py, tasks)?),
            (
                "concurrency",
                concurrency.max(1).into_pyobject(py)?.into_any(),
            ),
        ],
    )?;
    let mut missing: Vec<_> = Vec::new();
    let mut entries: Vec<_> = Vec::new();
    for ((source, entry, read_by), probe) in unlisted.into_iter().zip(probes.try_iter()?) {
        let probe = probe?;
        let status = probe.getattr("status")?;
        if status.eq("readable")? {
            continue;
        }
        let role = probe.getattr("role")?;
        missing.push(MissingSourceTable {
            source_name: source.getattr("name")?.extract()?,
            relation: String::new(),
            read_by,
            unreadable: status.eq("missing_or_unreadable")?,
            role: if role.is_none() {
                None
            } else {
                Some(role.str()?.extract()?)
            },
            location: String::new(),
        });
        entries.push(entry);
    }
    if missing.is_empty() {
        return Ok(());
    }
    for (item, entry) in missing.iter_mut().zip(&entries).take(10) {
        item.relation = read_relation(adapter, entry)?.str()?.extract()?;
    }
    let message = missing_source_tables_message(&missing);
    let sources = PyDict::new(py);
    for source in project.getattr("sources")?.try_iter()? {
        let source = source?;
        sources.set_item(source.getattr("name")?, source)?;
    }
    for item in missing.iter_mut().take(10) {
        if let Some(source) = sources.get_item(&item.source_name)? {
            item.location = declaration_location(&source)?;
        }
    }
    let help = missing_source_tables_help(&missing);
    Err(planner_error(
        py,
        &message,
        (Some(MISSING_SOURCE_TABLE_CODE), Some(&help)),
    ))
}

#[pyfunction]
#[pyo3(name = "check_selected_source_tables_exist")]
#[pyo3(signature = (**options))]
pub(crate) fn check_selected_source_tables_exist_binding<'py>(
    py: pyo3::Python<'py>,
    options: Option<Bound<'py, KeywordDict>>,
) -> PyResult<()> {
    let args = KeywordArguments::read(
        py,
        "check_selected_source_tables_exist",
        options,
        (
            &["project", "adapter", "connection", "scope", "relations"],
            &[],
        ),
    )?;
    let project = &args.value("project")?;
    let adapter = &args.value("adapter")?;
    let connection = &args.value("connection")?;
    let scope = &args.value("scope")?;
    let relations = &args.value("relations")?;

    check_selected_source_tables_exist(project, (adapter, connection), scope, relations)
}
