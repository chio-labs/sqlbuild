//! Planner scope assembly using native graph and selector operations.

use crate::bindings::_helpers::boundary::python_calls::KeywordArguments;
use crate::bindings::_helpers::compiled_views::model_reads;
use crate::bindings::_helpers::compiled_views::project_reads;
use crate::bindings::_helpers::compiled_views::source_reads;
use crate::bindings::_helpers::graph::keys::KeyCache;
use crate::bindings::_helpers::graph::project_graph::NativeProjectGraph;
use crate::bindings::_helpers::graph::views::lineage_graph_names;
use crate::bindings::_helpers::planner_identity::graph::{
    build_downstream_deps, build_execution_edge_origins, build_execution_upstream_deps,
    topologically_order_keys,
};
use crate::bindings::_helpers::planner_scope::loaders::expand_selected_loader_dependencies;
use crate::bindings::_helpers::planner_scope::values::{edges, keys};
use crate::bindings::_helpers::planner_selection::carrier::{Carrier, py_strings};
use crate::bindings::_helpers::planner_selection::selectors::resolve_graph_selection;
use crate::bindings::_helpers::records::construct::{new_record, new_record_with};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_items;
use crate::bindings::_helpers::records::ids::RecordId;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyDictMethods;
use pyo3::types::{PyBool, PyDict, PyFrozenSet, PyTuple};
use sqlbuild_analysis::planner_scope::constants::SOURCE;
use sqlbuild_analysis::planner_scope::main::{
    managed_sources::managed_sources, source_selectors::source_selectors,
};
use std::collections::HashSet;

pub(crate) fn managed_source_upstream_keys<'py>(
    selected_keys: &Bound<'py, PyAny>,
    upstream_deps: &Bound<'py, PyAny>,
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let mut managed: HashSet<String> = HashSet::new();
    for source in project_reads::sources(project)?.try_iter()? {
        let source = source?;
        if !native_field(&source_reads::source_entry(&source)?, "loader")?.is_none() {
            managed.insert(source_reads::name(&source)?.extract()?);
        }
    }
    let selected = managed_sources(&keys(selected_keys)?, &edges(upstream_deps)?, &managed);
    PyFrozenSet::new(
        project.py(),
        KeyCache::new(project.py())?.keys(&selected.into_iter().collect::<Vec<_>>())?,
    )
}

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
    let mut upstream = build_execution_upstream_deps(&project)?.into_any();
    let mut downstream = build_downstream_deps(&upstream)?.into_any();
    let lineage: Bound<'py, NativeProjectGraph> =
        native_field(&project, "lineage_graph")?.cast_into()?;
    let all_keys = lineage_graph_names(py, lineage.borrow())?.into_any();
    let mut selected = args.value("selected_keys")?;
    if selected.is_none() {
        selected = resolve_graph_selection(lineage.borrow(), &select, &exclude)?.into_any();
    }
    let names: Vec<(String, (String, String))> = mapping_items(&all_keys)?
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
    let sent = carrier.send_all(&texts)?;
    let selected_names = keys(&selected)?;
    let source_keys = source_selectors(&sent, &names, &selected_names, true)
        .map_err(|error| carrier.error(error))?;
    let named_sources = source_selectors(&sent, &names, &selected_names, false)
        .map_err(|error| carrier.error(error))?;
    let cache = KeyCache::new(py)?;
    let explicit_sources: Vec<(String, String)> = source_keys.into_iter().collect();
    let mut executable = PyFrozenSet::new(py, cache.keys(&explicit_sources)?)?.into_any();
    if !auto_load {
        executable = PyFrozenSet::empty(py)?.into_any();
    }
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
        downstream = build_downstream_deps(&upstream)?.into_any();
    }
    let end_audit_sources: Vec<(String, String)> = keys(&selected)?
        .into_iter()
        .filter(|key| key.0 == SOURCE && (!auto_load || named_sources.contains(key)))
        .collect();
    let end_audit_sources = PyFrozenSet::new(py, cache.keys(&end_audit_sources)?)?.into_any();
    let origins = build_execution_edge_origins(&project)?.into_any();
    let order = topologically_order_keys(&upstream, Some(origins))?.into_any();
    let models = PyDict::new(py);
    for model in project_reads::models(&project)?.try_iter()? {
        let model = model?;
        models.set_item(model_reads::name_object(&model)?, model)?;
    }
    let mut reads = args.value("python_read_source_names")?;
    if reads.is_none() {
        reads = PyFrozenSet::empty(py)?.into_any();
    }
    let mut tests = args.value("sql_test_selection")?;
    if !tests.is_truthy()? {
        tests = new_record(py, RecordId::SqlTestSelection, (), None)?;
    }
    new_record_with(
        py,
        RecordId::PlannerScope,
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
            (
                "load_sources",
                PyBool::new(py, auto_load).to_owned().into_any(),
            ),
            ("end_audit_source_keys", end_audit_sources),
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
