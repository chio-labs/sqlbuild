//! Display-ready Python plan entries and Python-aware selection warnings of a plan.

use std::collections::HashMap;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use sqlbuild_analysis::python_plan::main::ordered_python_names::ordered_python_names;
use sqlbuild_analysis::python_plan::main::upstream_closure::upstream_closure;

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, keywords,
};

const PIPELINE_MODELS_MODULE: &str = "sqlbuild.compiler.pipeline.models";
const PLANNER_MODELS_MODULE: &str = "sqlbuild.compiler.planner.models";
const PLANNER_TYPES_MODULE: &str = "sqlbuild.compiler.planner.types";
const NODE_GRAPH_MODULE: &str = "sqlbuild.compiler.python_nodes.main.graph";
const RUN_LIFECYCLE_MODULE: &str = "sqlbuild.compiler.python_nodes.main.run_lifecycle";
const PYTHON_NODE_MODELS_MODULE: &str = "sqlbuild.compiler.python_nodes.models";
const PYTHON_NODE_TYPES_MODULE: &str = "sqlbuild.compiler.python_nodes.types";
const REF_TYPES_MODULE: &str = "sqlbuild.python_nodes.types";
const SKIPPED_UPSTREAM_CODE: &str = "P501";

/// The Python node kinds and plan phases entries are built from.
struct NodeKinds<'py> {
    task: Bound<'py, PyAny>,
    asset: Bound<'py, PyAny>,
}

impl<'py> NodeKinds<'py> {
    fn load(py: Python<'py>) -> PyResult<Self> {
        let kinds: Bound<'py, PyAny> = imported(py, PYTHON_NODE_TYPES_MODULE, "PythonNodeKind")?;
        Ok(Self {
            task: kinds.getattr("TASK")?,
            asset: kinds.getattr("ASSET")?,
        })
    }

    /// Whether `kind` is a task or an asset.
    fn runs(&self, kind: &Bound<'py, PyAny>) -> PyResult<bool> {
        Ok(kind.eq(&self.task)? || kind.eq(&self.asset)?)
    }
}

/// `python_graph.upstream_deps` as names.
fn upstream_names(graph: &Bound<'_, PyAny>) -> PyResult<HashMap<String, Vec<String>>> {
    let mut upstream: HashMap<String, Vec<String>> = HashMap::new();
    for item in graph
        .getattr("upstream_deps")?
        .call_method0("items")?
        .try_iter()?
    {
        let item: Bound<'_, PyAny> = item?;
        let names: Vec<String> = item
            .get_item(1)?
            .try_iter()?
            .map(|name| name?.extract())
            .collect::<PyResult<_>>()?;
        upstream.insert(item.get_item(0)?.extract()?, names);
    }
    Ok(upstream)
}

/// The discovered Python node graph.
fn node_graph<'py>(discovered: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &imported(
            discovered.py(),
            NODE_GRAPH_MODULE,
            "build_discovered_python_node_graph",
        )?,
        &[("discovered_inputs", discovered.clone())],
    )
}

/// Return sources declared by the selected Python nodes and their Python upstreams.
#[pyfunction]
#[pyo3(signature = (**options))]
fn python_read_source_names_for<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "python_read_source_names_for",
        options,
        (&["discovered_inputs", "python_node_names"], &[]),
    )?;
    let frozenset: Bound<'py, PyAny> = imported(py, "builtins", "frozenset")?;
    let selected: Bound<'py, PyAny> = arguments.value("python_node_names")?;
    if !selected.is_truthy()? {
        return frozenset.call0();
    }
    let graph: Bound<'py, PyAny> = node_graph(&arguments.value("discovered_inputs")?)?;
    let source: Bound<'py, PyAny> =
        imported(py, REF_TYPES_MODULE, "SqlResourceRefKind")?.getattr("SOURCE")?;
    let mut names: Vec<Bound<'py, PyAny>> = Vec::new();
    for reference in call_with(
        &graph.getattr("selected_sql_refs")?,
        &[("selected_names", selected)],
    )?
    .try_iter()?
    {
        let reference: Bound<'py, PyAny> = reference?;
        if reference.getattr("kind")?.eq(&source)? {
            names.push(reference.getattr("name")?);
        }
    }
    frozenset.call1((PyTuple::new(py, names)?,))
}

/// Attach python-aware selection warnings and plan entries to the plan output.
#[pyfunction]
#[pyo3(signature = (**options))]
fn build_python_run_plan_outputs<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_python_run_plan_outputs",
        options,
        (
            &[
                "discovered_inputs",
                "plan_output",
                "run_selection",
                "selected_python_node_names",
            ],
            &[],
        ),
    )?;
    let outputs: Bound<'py, PyAny> = imported(py, PIPELINE_MODELS_MODULE, "PythonRunPlanOutputs")?;
    let plan_output: Bound<'py, PyAny> = arguments.value("plan_output")?;
    let run_selection: Bound<'py, PyAny> = arguments.value("run_selection")?;
    let selected: Bound<'py, PyAny> = arguments.value("selected_python_node_names")?;
    if run_selection.is_none() {
        return call_with(
            &outputs,
            &[
                ("plan_output", plan_output),
                ("python_plan_entries", PyTuple::empty(py).into_any()),
                ("selected_python_node_names", selected),
            ],
        );
    }
    let graph: Bound<'py, PyAny> = node_graph(&arguments.value("discovered_inputs")?)?;
    let kinds: NodeKinds<'py> = NodeKinds::load(py)?;
    let mut warnings: Vec<Bound<'py, PyAny>> = plan_output
        .getattr("warnings")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    warnings.extend(skipped_ingress_warnings(
        &plan_output,
        &run_selection,
        (&graph, &kinds),
    )?);
    let plan_output: Bound<'py, PyAny> = imported(py, "dataclasses", "replace")?.call(
        (plan_output,),
        Some(&keywords(
            py,
            &[("warnings", PyTuple::new(py, warnings)?.into_any())],
        )?),
    )?;
    let selection: Bound<'py, PyAny> = call_with(
        &imported(py, PYTHON_NODE_MODELS_MODULE, "PythonSqlRunSelection")?,
        &[
            ("sql_keys", plan_output.getattr("selected_keys")?),
            ("python_node_names", selected.clone()),
        ],
    )?;
    let lifecycle: Bound<'py, PyAny> = call_with(
        &imported(py, RUN_LIFECYCLE_MODULE, "build_python_sql_run_lifecycle")?,
        &[("selection", selection), ("python_graph", graph.clone())],
    )?;
    let entries: Bound<'py, PyTuple> = plan_entries(
        &lifecycle,
        (&graph, &kinds),
        &plan_output.getattr("python_identity_fingerprints")?,
    )?;
    call_with(
        &outputs,
        &[
            ("plan_output", plan_output),
            ("python_plan_entries", entries.into_any()),
            ("selected_python_node_names", selected),
        ],
    )
}

/// Return task/asset plan entries ordered by lifecycle dependency readiness.
#[pyfunction]
#[pyo3(signature = (**options))]
fn build_python_plan_entries<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_python_plan_entries",
        options,
        (
            &["lifecycle_plan", "python_graph"],
            &["previous_identities"],
        ),
    )?;
    let previous: Bound<'py, PyAny> = arguments.value("previous_identities")?;
    let previous: Bound<'py, PyAny> = if previous.is_none() {
        PyDict::new(py).into_any()
    } else {
        previous
    };
    plan_entries(
        &arguments.value("lifecycle_plan")?,
        (&arguments.value("python_graph")?, &NodeKinds::load(py)?),
        &previous,
    )
}

/// The entries of the lifecycle's ingress and then read-side tasks and assets.
fn plan_entries<'py>(
    lifecycle: &Bound<'py, PyAny>,
    (graph, kinds): (&Bound<'py, PyAny>, &NodeKinds<'py>),
    previous_identities: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = lifecycle.py();
    let phases: Bound<'py, PyAny> = imported(py, PYTHON_NODE_TYPES_MODULE, "PythonRunPhase")?;
    let entry_class: Bound<'py, PyAny> = imported(py, PIPELINE_MODELS_MODULE, "PythonPlanEntry")?;
    let upstream: HashMap<String, Vec<String>> = upstream_names(graph)?;
    let nodes: Bound<'py, PyAny> = graph.getattr("nodes_by_name")?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    for (attribute, phase) in [
        ("ingress_python_node_names", "PRE_SQL_INGRESS"),
        ("read_side_python_node_names", "READ_SIDE"),
    ] {
        let selected: Vec<String> = lifecycle
            .getattr(attribute)?
            .try_iter()?
            .map(|name| name?.extract())
            .collect::<PyResult<_>>()?;
        for name in ordered_python_names(&selected, &upstream) {
            let node: Bound<'py, PyAny> = nodes.get_item(name.as_str())?;
            let kind: Bound<'py, PyAny> = node.getattr("kind")?;
            if !kinds.runs(&kind)? {
                continue;
            }
            let identity: Bound<'py, PyAny> = node.getattr("identity")?;
            let previous: Bound<'py, PyAny> = previous_identity(&identity, previous_identities)?;
            let attribute_or_none = |value: &Bound<'py, PyAny>, name: &str| {
                if value.is_none() {
                    Ok(py.None().into_bound(py))
                } else {
                    value.getattr(name)
                }
            };
            entries.push(call_with(
                &entry_class,
                &[
                    ("name", node.getattr("name")?),
                    ("kind", kind),
                    ("phase", phases.getattr(phase)?),
                    (
                        "identity_status",
                        identity_status(&identity, previous_identities)?,
                    ),
                    (
                        "current_definition_json",
                        attribute_or_none(&identity, "definition_json")?,
                    ),
                    (
                        "previous_definition_json",
                        attribute_or_none(&previous, "definition")?,
                    ),
                    (
                        "current_metadata_json",
                        attribute_or_none(&identity, "metadata_json")?,
                    ),
                    (
                        "previous_metadata_json",
                        attribute_or_none(&previous, "metadata_json")?,
                    ),
                    ("provider_usages", node.getattr("provider_usages")?),
                ],
            )?);
        }
    }
    PyTuple::new(py, entries)
}

/// `_previous_identity`: the stored fingerprint of a node's identity, or `None`.
fn previous_identity<'py>(
    identity: &Bound<'py, PyAny>,
    previous_identities: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if identity.is_none() {
        return Ok(identity.clone());
    }
    let key: Bound<'py, PyTuple> = PyTuple::new(
        identity.py(),
        [
            identity.getattr("node_type")?,
            identity.getattr("node_name")?,
        ],
    )?;
    previous_identities.call_method1("get", (key,))
}

/// `_identity_status`: whether a node's identity is unknown, new, unchanged or changed.
fn identity_status<'py>(
    identity: &Bound<'py, PyAny>,
    previous_identities: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let statuses: Bound<'py, PyAny> = imported(
        identity.py(),
        PYTHON_NODE_TYPES_MODULE,
        "PythonIdentityStatus",
    )?;
    if identity.is_none() {
        return statuses.getattr("UNKNOWN");
    }
    let previous: Bound<'py, PyAny> = previous_identity(identity, previous_identities)?;
    if previous.is_none() {
        return statuses.getattr("NEW");
    }
    if previous
        .getattr("version_hash")?
        .eq(identity.getattr("version_hash")?)?
    {
        return statuses.getattr("UNCHANGED");
    }
    statuses.getattr("CHANGED")
}

/// Warnings for skipped task/asset deps of planned source loaders.
fn skipped_ingress_warnings<'py>(
    plan_output: &Bound<'py, PyAny>,
    run_selection: &Bound<'py, PyAny>,
    (graph, kinds): (&Bound<'py, PyAny>, &NodeKinds<'py>),
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py: Python<'py> = plan_output.py();
    let mut loaders: Vec<String> = Vec::new();
    for entry in plan_output.getattr("source_load_entries")?.try_iter()? {
        let loader: String = entry?.getattr("loader")?.extract()?;
        if !loaders.contains(&loader) {
            loaders.push(loader);
        }
    }
    loaders.sort();
    let nodes: Bound<'py, PyAny> = graph.getattr("nodes_by_name")?;
    let selected: Bound<'py, PyAny> = run_selection.getattr("python_node_names")?;
    let upstream: HashMap<String, Vec<String>> = upstream_names(graph)?;
    let warning_class: Bound<'py, PyAny> = imported(py, PLANNER_MODELS_MODULE, "PlanWarning")?;
    let severity: Bound<'py, PyAny> =
        imported(py, PLANNER_TYPES_MODULE, "WarningSeverity")?.getattr("WARNING")?;
    let mut warnings: Vec<Bound<'py, PyAny>> = Vec::new();
    for loader in loaders {
        if !nodes.contains(loader.as_str())? {
            continue;
        }
        for upstream_name in upstream_closure(&loader, &upstream) {
            if selected.contains(upstream_name.as_str())? {
                continue;
            }
            let kind: Bound<'py, PyAny> =
                nodes.get_item(upstream_name.as_str())?.getattr("kind")?;
            if !kinds.runs(&kind)? {
                continue;
            }
            let message: String = format!(
                "Source loader '{loader}' has unselected upstream {} '{upstream_name}'. SQLBuild \
                 will not run it and cannot verify side effects or payload availability; use \
                 +source:{loader} to refresh upstream ingress dependencies.",
                kind.getattr("value")?.str()?
            );
            warnings.push(call_with(
                &warning_class,
                &[
                    ("model_name", py.None().into_bound(py)),
                    ("severity", severity.clone()),
                    ("message", PyString::new(py, &message).into_any()),
                    ("code", PyString::new(py, SKIPPED_UPSTREAM_CODE).into_any()),
                ],
            )?);
        }
    }
    Ok(warnings)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(python_read_source_names_for, module)?)?;
    module.add_function(wrap_pyfunction!(build_python_run_plan_outputs, module)?)?;
    module.add_function(wrap_pyfunction!(build_python_plan_entries, module)?)
}
