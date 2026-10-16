//! Planner scope assembly using native graph and selector operations.

use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::graph::keys::KeyCache;
use crate::bindings::_helpers::planner_scope::loaders::expand_selected_loader_dependencies;
use crate::bindings::_helpers::planner_scope::values::{edges, keys};
use crate::bindings::_helpers::planner_selection::carrier::{Carrier, py_strings};
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python, pyfunction};
use pyo3::types::PyDictMethods;
use pyo3::types::{PyDict, PyFrozenSet, PyTuple};
use sqlbuild_analysis::planner_scope::constants::SOURCE;
use sqlbuild_analysis::planner_scope::main::{
    managed_sources::managed_sources, source_selectors::source_selectors,
};
use std::collections::HashSet;

#[pyfunction]
#[pyo3(signature = (*, selected_keys, upstream_deps, project))]
pub(crate) fn managed_source_upstream_keys<'py>(
    selected_keys: &Bound<'py, PyAny>,
    upstream_deps: &Bound<'py, PyAny>,
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let mut managed: HashSet<String> = HashSet::new();
    for source in project.getattr("sources")?.try_iter()? {
        let source = source?;
        if !source.getattr("source_entry")?.getattr("loader")?.is_none() {
            managed.insert(source.getattr("name")?.extract()?);
        }
    }
    let selected = managed_sources(&keys(selected_keys)?, &edges(upstream_deps)?, &managed);
    PyFrozenSet::new(
        project.py(),
        KeyCache::new(project.py())?.keys(&selected.into_iter().collect::<Vec<_>>())?,
    )
}

#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn build_planner_scope<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "build_planner_scope",
        options,
        (
            &["project"],
            &[
                "select",
                "exclude",
                "auto_load_sources",
                "selected_keys",
                "python_read_source_names",
                "sql_test_selection",
            ],
        ),
    )?;
    let project = args.value("project")?;
    let select = default_tuple(&args.value("select")?);
    let exclude = default_tuple(&args.value("exclude")?);
    let auto_load = args.value("auto_load_sources")?.is_truthy()?;
    let mut upstream =
        registry::native(py, NativeAttr::BuildExecutionUpstreamDeps)?.call1((&project,))?;
    let mut downstream =
        registry::native(py, NativeAttr::BuildDownstreamDeps)?.call1((&upstream,))?;
    let lineage = project.getattr("lineage_graph")?;
    let all_keys = registry::native(py, NativeAttr::LineageGraphNames)?.call1((&lineage,))?;
    let mut selected = args.value("selected_keys")?;
    if selected.is_none() {
        selected = call_with(
            &registry::native(py, NativeAttr::ResolveGraphSelection)?,
            &[
                ("graph", lineage),
                ("select", select.clone()),
                ("exclude", exclude),
            ],
        )?;
    }
    let names: Vec<(String, (String, String))> = all_keys
        .call_method0("items")?
        .try_iter()?
        .map(|item| {
            let (name, key): (String, Bound<'py, PyAny>) = item?.extract()?;
            Ok((
                name,
                crate::bindings::_helpers::graph::keys::native_key(&key)?,
            ))
        })
        .collect::<PyResult<_>>()?;
    let texts = py_strings(&select)?;
    let carrier = Carrier::new(py, &texts, || {
        Ok(names.iter().map(|(name, _)| name.clone()).collect())
    })?;
    let source_keys = source_selectors(&carrier.send_all(&texts)?, &names, &keys(&selected)?)
        .map_err(|error| carrier.error(error))?;
    let cache = KeyCache::new(py)?;
    let mut executable = PyFrozenSet::new(
        py,
        cache.keys(&source_keys.into_iter().collect::<Vec<_>>())?,
    )?
    .into_any();
    if auto_load {
        let loaded = managed_source_upstream_keys(&selected, &upstream, &project)?;
        selected = selected.call_method1("union", (&loaded,))?;
        executable = executable.call_method1("union", (&loaded,))?;
    }
    executable = executable.call_method1("intersection", (&selected,))?;
    if auto_load || keys(&selected)?.iter().any(|key| key.0 == SOURCE) {
        let (expanded, deps) =
            expand_selected_loader_dependencies(&project, &selected, &upstream, Some(&executable))?;
        selected = expanded.into_any();
        upstream = deps.into_any();
        downstream = registry::native(py, NativeAttr::BuildDownstreamDeps)?.call1((&upstream,))?;
    }
    let origins =
        registry::native(py, NativeAttr::BuildExecutionEdgeOrigins)?.call1((&project,))?;
    let order = call_with(
        &registry::native(py, NativeAttr::TopologicallyOrderKeys)?,
        &[
            ("upstream", upstream.clone()),
            ("injected_edge_origins", origins),
        ],
    )?;
    let models = PyDict::new(py);
    for model in project.getattr("models")?.try_iter()? {
        let model = model?;
        models.set_item(model.getattr("name")?, model)?;
    }
    let mut reads = args.value("python_read_source_names")?;
    if reads.is_none() {
        reads = PyFrozenSet::empty(py)?.into_any();
    }
    let mut tests = args.value("sql_test_selection")?;
    if !tests.is_truthy()? {
        tests = registry::class(py, RecordId::SqlTestSelection)?.call0()?;
    }
    call_with(
        &registry::class(py, RecordId::PlannerScope)?,
        &[
            ("upstream_deps", upstream),
            ("downstream_deps", downstream),
            ("all_keys", all_keys),
            ("models_by_name", models.into_any()),
            ("selected_keys", selected.clone()),
            ("execution_order", order),
            ("user_selected_keys", selected),
            ("python_read_source_names", reads),
            ("sql_test_selection", tests),
        ],
    )
}

fn default_tuple<'py>(value: &Bound<'py, PyAny>) -> Bound<'py, PyAny> {
    if value.is_none() {
        PyTuple::empty(value.py()).into_any()
    } else {
        value.clone()
    }
}
