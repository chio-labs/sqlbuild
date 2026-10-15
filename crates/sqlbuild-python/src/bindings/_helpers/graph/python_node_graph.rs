//! The executable Python-node graph built from discovered project inputs.

use crate::bindings::_helpers::compiler_records::shape_classes::shape_class_at;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::python_selection::main::python_node_graph_indexes::python_node_graph_indexes as graph_indexes;
use sqlbuild_analysis::python_selection::models::{InventoryIndexes, InventoryNode};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::graph::python_selection::resolve_python_sql_run_selection;
use crate::bindings::_helpers::graph::views::compiled_graph_keys;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const USER_INVENTORY_MODULE: &str = "sqlbuild.compiler.python_nodes._helpers.user_inventory";
const NODE_MODELS_MODULE: &str = "sqlbuild.compiler.python_nodes.models";
const NODE_TYPES_MODULE: &str = "sqlbuild.compiler.python_nodes.types";
const SQL_REF_MODULE: &str = "sqlbuild.python_nodes.models";
const NAME_KEY: &str = "name";

/// One discovered function collection, its node kind and whether it carries documentation.
const KINDS: [(&str, &str, bool); 4] = [
    ("loader_functions", "LOADER", false),
    ("task_functions", "TASK", true),
    ("asset_functions", "ASSET", true),
    ("check_functions", "CHECK", true),
];

/// Python classes and shims every node is built with.
struct Vocabulary<'py> {
    node: Bound<'py, PyAny>,
    kinds: Bound<'py, PyAny>,
    sql_ref: Bound<'py, PyAny>,
    user_facts: Bound<'py, PyAny>,
    providers: Bound<'py, PyDict>,
}

fn attribute_value<'py>(value: &Bound<'py, PyAny>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    value.getattr(name)
}

fn optional_value<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    if value.is_none() {
        return Ok(value.clone());
    }
    value.getattr("value")
}

/// The kind-specific decorator configuration and metadata record of one discovered function.
fn kind_parts<'py>(
    py: Python<'py>,
    kind: &str,
    discovered: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyDict>, &'static str, Bound<'py, PyAny>)> {
    let config: Bound<'py, PyDict> = PyDict::new(py);
    let get = |name: &str| attribute_value(discovered, name);
    let metadata = |class: &str, fields: &[&str]| -> PyResult<Bound<'py, PyAny>> {
        let pairs: Vec<(&str, Bound<'py, PyAny>)> = fields
            .iter()
            .map(|field| Ok((*field, get(field)?)))
            .collect::<PyResult<_>>()?;
        call_with(&shape_class_at(py, NODE_MODELS_MODULE, class)?, &pairs)
    };
    Ok(match kind {
        "LOADER" => {
            config.set_item("columns", get("columns")?)?;
            config.set_item("contract", get("contract")?)?;
            config.set_item("cursor_column", get("cursor_column")?)?;
            config.set_item("destination", get("destination")?)?;
            config.set_item("unique_key", get("unique_key")?)?;
            config.set_item("write_strategy", optional_value(&get("write_strategy")?)?)?;
            let record = metadata(
                "DiscoveredPythonLoaderMetadata",
                &[
                    "destination",
                    "write_strategy",
                    "cursor_column",
                    "unique_key",
                    "columns",
                    "contract",
                    "connection_mode",
                ],
            )?;
            (config, "loader", record)
        }
        "TASK" => (
            config,
            "task",
            metadata("DiscoveredPythonTaskMetadata", &["retry"])?,
        ),
        "ASSET" => {
            config.set_item("columns", get("columns")?)?;
            config.set_item("column_lineage", get("column_lineage")?)?;
            let record = metadata(
                "DiscoveredPythonAssetMetadata",
                &["columns", "column_lineage", "retry"],
            )?;
            (config, "asset", record)
        }
        _ => {
            config.set_item("severity", get("severity")?.getattr("value")?)?;
            let record = metadata("DiscoveredPythonCheckMetadata", &["severity"])?;
            (config, "check", record)
        }
    })
}

/// One `DiscoveredPythonNode` with its identity and provider usages read by the user shim.
fn python_node<'py>(
    vocabulary: &Vocabulary<'py>,
    (kind, documented): (&str, bool),
    discovered: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let get = |name: &str| attribute_value(discovered, name);
    let (config, metadata_field, metadata) = kind_parts(py, kind, discovered)?;
    if documented {
        for field in ["description", "group", "meta", "tags"] {
            config.set_item(field, get(field)?)?;
        }
    }
    let kind_member: Bound<'py, PyAny> = vocabulary.kinds.getattr(kind)?;
    let (usages, identity): (Bound<'py, PyAny>, Bound<'py, PyAny>) = call_with(
        &vocabulary.user_facts,
        &[
            ("kind", kind_member.getattr("value")?),
            ("name", get("name")?),
            ("function", get("function")?),
            ("file_path", get("file_path")?),
            ("provider_by_name", vocabulary.providers.clone().into_any()),
            ("decorator_config", config.into_any()),
        ],
    )?
    .extract()?;
    let depends_on: Bound<'py, PyAny> = get("depends_on")?;
    let mut sql_deps: Vec<Bound<'py, PyAny>> = Vec::new();
    for dependency in depends_on.try_iter()? {
        let dependency: Bound<'py, PyAny> = dependency?;
        if dependency.is_instance(&vocabulary.sql_ref)? {
            sql_deps.push(dependency);
        }
    }
    let mut pairs: Vec<(&str, Bound<'py, PyAny>)> = vec![
        ("kind", kind_member),
        ("file_path", get("file_path")?),
        ("relative_path", get("relative_path")?),
        ("name", get("name")?),
        ("function", get("function")?),
        ("depends_on", depends_on),
        ("sql_deps", PyTuple::new(py, sql_deps)?.into_any()),
        ("provider_usages", usages),
        ("identity", identity),
        ("description", get("description")?),
        (metadata_field, metadata),
    ];
    if documented {
        for field in ["tags", "group", "meta"] {
            pairs.push((field, get(field)?));
        }
    }
    call_with(&vocabulary.node, &pairs)
}

/// Each node's upstream Python-node names, resolving decorated dependencies through the shim.
fn upstream_names(
    py: Python<'_>,
    nodes: &[Bound<'_, PyAny>],
    sql_ref: &Bound<'_, PyAny>,
) -> PyResult<Vec<Vec<String>>> {
    let by_key: Bound<'_, PyDict> = PyDict::new(py);
    for node in nodes {
        by_key.set_item(node.getattr("function")?, node.getattr("name")?)?;
    }
    for node in nodes {
        let name: Bound<'_, PyAny> = node.getattr("name")?;
        by_key.set_item(
            PyTuple::new(py, [PyString::new(py, NAME_KEY).into_any(), name.clone()])?,
            name,
        )?;
    }
    let dependency_key: Bound<'_, PyAny> =
        imported(py, USER_INVENTORY_MODULE, "python_node_dependency_key")?;
    nodes
        .iter()
        .map(|node| {
            let mut names: Vec<String> = Vec::new();
            for dependency in node.getattr("depends_on")?.try_iter()? {
                let dependency: Bound<'_, PyAny> = dependency?;
                if dependency.is_instance(sql_ref)? {
                    continue;
                }
                let key: Bound<'_, PyAny> = dependency_key.call1((dependency,))?;
                if let Some(upstream) = by_key.get_item(key)? {
                    names.push(upstream.extract()?);
                }
            }
            Ok(names)
        })
        .collect()
}

fn inventory_node(node: &Bound<'_, PyAny>, upstream: Vec<String>) -> PyResult<InventoryNode> {
    Ok(InventoryNode {
        name: node.getattr("name")?.extract()?,
        tags: node.getattr("tags")?.extract()?,
        relative_path: node
            .getattr("relative_path")?
            .call_method0("as_posix")?
            .extract()?,
        upstream,
    })
}

/// The internal executable Python-node graph of discovered project inputs.
pub(crate) fn python_node_graph<'py>(
    discovered_inputs: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered_inputs.py();
    let providers: Bound<'py, PyDict> = PyDict::new(py);
    for provider in discovered_inputs.getattr("providers")?.try_iter()? {
        let provider: Bound<'py, PyAny> = provider?;
        providers.set_item(provider.getattr("name")?, provider)?;
    }
    let vocabulary: Vocabulary<'py> = Vocabulary {
        node: imported(py, NODE_MODELS_MODULE, "DiscoveredPythonNode")?,
        kinds: imported(py, NODE_TYPES_MODULE, "PythonNodeKind")?,
        sql_ref: imported(py, SQL_REF_MODULE, "SqlResourceRef")?,
        user_facts: imported(py, USER_INVENTORY_MODULE, "python_node_user_facts")?,
        providers,
    };
    let mut nodes: Vec<Bound<'py, PyAny>> = Vec::new();
    for (collection, kind, documented) in KINDS {
        for discovered in discovered_inputs.getattr(collection)?.try_iter()? {
            nodes.push(python_node(&vocabulary, (kind, documented), &discovered?)?);
        }
    }
    let inventory: Vec<InventoryNode> = nodes
        .iter()
        .zip(upstream_names(py, &nodes, &vocabulary.sql_ref)?)
        .map(|(node, upstream)| inventory_node(node, upstream))
        .collect::<PyResult<_>>()?;
    graph_record(py, &nodes, graph_indexes(&inventory))
}

type NameRows = Vec<(String, Vec<String>)>;

fn graph_record<'py>(
    py: Python<'py>,
    nodes: &[Bound<'py, PyAny>],
    indexes: InventoryIndexes,
) -> PyResult<Bound<'py, PyAny>> {
    let InventoryIndexes {
        edges,
        upstream,
        downstream,
        tags,
        paths,
    } = indexes;
    let edge_class: Bound<'py, PyAny> =
        imported(py, NATIVE_RECORDS_MODULE, "PythonNodeDependencyEdge")?;
    let dependency_edges: Vec<Bound<'py, PyAny>> = edges
        .into_iter()
        .map(|(upstream_name, downstream_name)| {
            call_with(
                &edge_class,
                &[
                    (
                        "upstream_name",
                        PyString::new(py, &upstream_name).into_any(),
                    ),
                    (
                        "downstream_name",
                        PyString::new(py, &downstream_name).into_any(),
                    ),
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    let adjacency = |rows: NameRows| -> PyResult<Bound<'py, PyDict>> {
        let mapping: Bound<'py, PyDict> = PyDict::new(py);
        for (name, names) in rows {
            mapping.set_item(name, PyTuple::new(py, names)?)?;
        }
        Ok(mapping)
    };
    let tag_index: Bound<'py, PyDict> = PyDict::new(py);
    for (tag, names) in tags {
        tag_index.set_item(tag, PyFrozenSet::new(py, names)?)?;
    }
    let path_index: Bound<'py, PyDict> = PyDict::new(py);
    for (name, path) in paths {
        path_index.set_item(name, path)?;
    }
    let by_name: Bound<'py, PyDict> = PyDict::new(py);
    let by_selector: Bound<'py, PyDict> = PyDict::new(py);
    for node in nodes {
        let name: Bound<'py, PyAny> = node.getattr("name")?;
        let kind: String = node.getattr("kind")?.getattr("value")?.extract()?;
        by_name.set_item(&name, node)?;
        by_selector.set_item(format!("{kind}:{}", name.str()?), node)?;
    }
    call_with(
        &imported(py, NODE_MODELS_MODULE, "PythonNodeGraph")?,
        &[
            ("nodes", PyTuple::new(py, nodes)?.into_any()),
            (
                "dependency_edges",
                PyTuple::new(py, dependency_edges)?.into_any(),
            ),
            ("upstream_deps", adjacency(upstream)?.into_any()),
            ("downstream_deps", adjacency(downstream)?.into_any()),
            ("tag_index", tag_index.into_any()),
            ("path_index", path_index.into_any()),
            ("nodes_by_name", by_name.into_any()),
            ("nodes_by_typed_selector", by_selector.into_any()),
        ],
    )
}

/// `PythonSqlRunSelection` of run selectors over the project graph and discovered Python nodes.
pub(crate) fn run_selection_from_inputs<'py>(
    (select, exclude): (Vec<String>, Vec<String>),
    project_graph: &Bound<'py, PyAny>,
    discovered_inputs: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_graph.py();
    let python_graph: Bound<'py, PyAny> = python_node_graph(discovered_inputs)?;
    let (sql_keys, python_node_names) =
        resolve_python_sql_run_selection(project_graph, &python_graph, select, exclude)?;
    call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "PythonSqlRunSelection")?,
        &[
            ("sql_keys", compiled_graph_keys(py, sql_keys)?.into_any()),
            (
                "python_node_names",
                PyFrozenSet::new(py, python_node_names)?.into_any(),
            ),
        ],
    )
}

/// Build the internal executable Python-node graph from discovered project inputs.
#[pyfunction]
#[pyo3(signature = (**options))]
fn build_python_node_graph<'py>(
    options: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let request = Request::new("build_python_node_graph", options)?;
    python_node_graph(&request.get("discovered_inputs")?)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_python_node_graph, module)?)?;
    Ok(())
}
