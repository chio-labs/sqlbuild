//! Relation locations and source metadata for plan entry construction.

use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::planner_entries::models::RelationsRequest;
use crate::bindings::_helpers::planner_entries::values::{native, none, planner_model};
use crate::bindings::_helpers::planner_strategy::audit_entries::audit_is_selected;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PySet, PySetMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

/// Relation keys needed to render selected audits without selecting those relations.
fn selected_audit_relation_keys<'py>(
    project: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    let keys = PySet::empty(py)?;
    for audit in project.getattr("audits")?.try_iter()? {
        let audit = audit?;
        if audit_is_selected(&audit, selected_keys)? {
            for dependency in audit.getattr("scope_deps")?.try_iter()? {
                keys.add(dependency?)?;
            }
        }
    }
    Ok(PyFrozenSet::new(py, keys.iter())?.into_any())
}

/// Reuse already-gathered source columns for the read map, or gather them once.
fn source_warehouse_columns<'py>(
    (project, adapter, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>, &Bound<'py, PyAny>),
    source_read_map: &Bound<'py, PyAny>,
    known_source_columns: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py = project.py();
    if !known_source_columns.is_none() {
        let known = PyDict::new(py);
        for name in source_read_map.try_iter()? {
            let name = name?;
            if known_source_columns.contains(&name)? {
                known.set_item(&name, known_source_columns.get_item(&name)?)?;
            }
        }
        let names = PyFrozenSet::new(py, known.keys())?.into_any();
        return Ok((known.into_any(), names));
    }
    let entries = PyTuple::new(
        py,
        source_read_map
            .call_method0("values")?
            .try_iter()?
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    let gathered = native(
        py,
        NativeAttr::GatherSourceInspection,
        &[
            ("project", project.clone()),
            ("adapter", adapter.clone()),
            ("connection", connection.clone()),
            ("source_entries", entries.into_any()),
        ],
    )?;
    Ok((gathered.get_item(0)?, gathered.get_item(1)?))
}

/// Resolve relation locations and source metadata for plan entry construction.
pub(crate) fn planner_relations_context<'py>(
    request: RelationsRequest<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let RelationsRequest {
        project,
        adapter,
        connection,
        scope,
        deferral,
        project_config,
        local_config,
        known_source_columns,
        relation_keys,
    } = request;
    let py = project.py();
    let deferral = if deferral.is_none() {
        planner_model(py, RecordId::DeferralInputs, &[])?
    } else {
        deferral
    };
    let selected_keys = scope.getattr("selected_keys")?;
    let mut model_locations = native(
        py,
        NativeAttr::BuildModelLocations,
        &[("models", project.getattr("models")?)],
    )?;
    let mut seed_locations = native(
        py,
        NativeAttr::BuildSeedLocations,
        &[("seeds", project.getattr("seeds")?)],
    )?;
    let function_locations = native(
        py,
        NativeAttr::BuildFunctionLocations,
        &[("functions", project.getattr("functions")?)],
    )?;
    let deferred_locations = deferral.getattr("deferred_locations")?;
    if !deferred_locations.is_none() {
        let applied = native(
            py,
            NativeAttr::ApplyDeferredLocations,
            &[
                ("model_locations", model_locations),
                ("seed_locations", seed_locations),
                ("deferred_locations", deferred_locations),
                ("selected_keys", selected_keys.clone()),
            ],
        )?;
        model_locations = applied.get_item(0)?;
        seed_locations = applied.get_item(1)?;
    }
    let audit_keys = selected_audit_relation_keys(&project, &selected_keys)?;
    let load_keys = if relation_keys.is_none() {
        selected_keys.call_method1("__or__", (&audit_keys,))?
    } else {
        relation_keys
    };
    let source_map = native(
        py,
        NativeAttr::BuildSourceLoadMap,
        &[
            ("project", project.clone()),
            ("selected_keys", load_keys),
            (
                "upstream_deps",
                if scope.getattr("all_keys")?.is_truthy()? {
                    scope.getattr("upstream_deps")?
                } else {
                    none(py)
                },
            ),
        ],
    )?;
    let deferral_enabled = deferral.getattr("source_deferral_enabled")?.is_truthy()?;
    let read_map = |map: &Bound<'py, PyAny>, names: Option<Bound<'py, PyAny>>| {
        if !deferral_enabled {
            return Ok(map.clone());
        }
        let mut pairs = vec![
            ("project", project.clone()),
            ("source_map", map.clone()),
            ("selected_keys", selected_keys.clone()),
            ("project_config", project_config.clone()),
            ("local_config", local_config.clone()),
            ("defer_sources_to", deferral.getattr("defer_sources_to")?),
        ];
        if let Some(names) = names {
            pairs.push(("read_source_names", names));
        }
        native(py, NativeAttr::BuildSourceReadMap, &pairs)
    };
    let source_read_map = read_map(&source_map, None)?;
    let python_source_map = native(
        py,
        NativeAttr::WithDeclaredSourceReads,
        &[
            ("project", project.clone()),
            ("source_map", source_map.clone()),
            ("source_names", scope.getattr("python_read_source_names")?),
        ],
    )?;
    let python_names = PyFrozenSet::new(
        py,
        python_source_map
            .try_iter()?
            .collect::<PyResult<Vec<_>>>()?,
    )?
    .into_any();
    let python_source_read_map = read_map(&python_source_map, Some(python_names))?;
    let (columns, listed_source_names) = source_warehouse_columns(
        (&project, &adapter, &connection),
        &source_read_map,
        &known_source_columns,
    )?;
    let semantic_columns = native(
        py,
        NativeAttr::GetSemanticSourceColumns,
        &[
            ("project", project.clone()),
            ("adapter", adapter.clone()),
            ("connection", connection),
            ("source_read_map", source_read_map.clone()),
            ("selected_keys", selected_keys),
            ("columns", columns),
        ],
    )?;
    planner_model(
        py,
        RecordId::PlannerRelationsContext,
        &[
            ("model_locations", model_locations),
            ("seed_locations", seed_locations),
            ("function_locations", function_locations),
            ("source_map", source_map),
            ("source_read_map", source_read_map),
            ("python_source_read_map", python_source_read_map),
            ("source_warehouse_columns", semantic_columns),
            (
                "star_exclude_keyword",
                adapter.call_method0("star_exclude_keyword")?,
            ),
            ("listed_source_names", listed_source_names),
        ],
    )
}

/// Resolve relation locations and source metadata for plan entry construction.
#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn build_planner_relations_context<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "build_planner_relations_context",
        kwargs,
        (
            &["project", "adapter", "connection", "scope"],
            &[
                "deferral",
                "project_config",
                "local_config",
                "known_source_columns",
                "relation_keys",
            ],
        ),
    )?;
    planner_relations_context(RelationsRequest {
        project: args.value("project")?,
        adapter: args.value("adapter")?,
        connection: args.value("connection")?,
        scope: args.value("scope")?,
        deferral: args.value("deferral")?,
        project_config: args.value("project_config")?,
        local_config: args.value("local_config")?,
        known_source_columns: args.value("known_source_columns")?,
        relation_keys: args.value("relation_keys")?,
    })
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_planner_relations_context, module)?)
}
