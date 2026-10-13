//! Lineage output: box-drawing dependency and column-trace trees, and column JSON payloads.

use std::collections::HashSet;

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyListMethods, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::lineage_graph::main::trace_limit_note::trace_limit_note;
use sqlbuild_analysis::lineage_graph::main::tree_lines::tree_lines;
use sqlbuild_analysis::lineage_graph::models::TreeLine;
use sqlbuild_analysis::lineage_graph::types::TreeVisitor;

use crate::bindings::_helpers::boundary::keyword_request::Request;

const BUILTINS_MODULE: &str = "builtins";

/// Box-drawing dependency tree lines for one focus node, expanding each node once.
#[pyfunction]
#[pyo3(signature = (**request))]
fn render_dependency_tree(request: Option<&Bound<'_, PyDict>>) -> PyResult<Vec<String>> {
    let request = Request::new("render_dependency_tree", request)?;
    let py: Python<'_> = request.py();
    let mut tree = DependencyTree {
        deps: request.get("deps")?,
        sort_key: request.get("sort_key")?,
        format_node: request.get("format_node")?,
        branch_style: request.get("branch_style")?,
        already_shown: request.get("already_shown")?,
        sorted: py.import(BUILTINS_MODULE)?.getattr("sorted")?,
        identities: PyDict::new(py),
        lines: Vec::new(),
    };
    let focus: Bound<'_, PyAny> = request.get("focus")?;
    let seen: Bound<'_, PyAny> = request.get("seen")?;
    let roots: Vec<Bound<'_, PyAny>> = tree.children(&focus)?;
    let mut shown: HashSet<usize> = HashSet::new();
    for node in seen.try_iter()? {
        let _ = shown.insert(tree.key(&node?)?);
    }
    tree_lines(roots, shown, &mut tree)?;
    Ok(tree.lines)
}

/// Box-drawing column-trace tree lines plus any truncation note.
#[pyfunction]
#[pyo3(signature = (**request))]
fn render_column_trace_tree(request: Option<&Bound<'_, PyDict>>) -> PyResult<Vec<String>> {
    let request = Request::new("render_column_trace_tree", request)?;
    let target: Bound<'_, PyAny> = request.get("target")?;
    let mut tree = ColumnTraceTree {
        deps: request.get("deps")?,
        column_id: request.get("column_id")?,
        related_column: request.get("related_column")?,
        format_related: request.get("format_related")?,
        branch_style: request.get("branch_style")?,
        already_shown: request.get("already_shown")?,
        last_key: String::new(),
        lines: Vec::new(),
    };
    let seen: HashSet<String> = HashSet::from([text(&tree.column_id.call1((&target,))?)?]);
    let roots: Vec<Bound<'_, PyAny>> =
        tree.sorted_edges(&text(&tree.column_id.call1((&target,))?)?)?;
    tree_lines(roots, seen, &mut tree)?;
    let mut lines: Vec<String> = tree.lines;
    lines.extend(limit_note(
        &request.get("total")?,
        &request.get("limit")?,
        &request.get("note_style")?,
    )?);
    Ok(lines)
}

/// The shared truncation note when a column trace is limited.
#[pyfunction]
#[pyo3(signature = (**request))]
fn render_column_trace_limit_note(request: Option<&Bound<'_, PyDict>>) -> PyResult<Vec<String>> {
    let request = Request::new("render_column_trace_limit_note", request)?;
    limit_note(
        &request.get("total")?,
        &request.get("limit")?,
        &request.get("note_style")?,
    )
}

/// A qualified lineage column's JSON payload, its resource type rendered by the caller.
#[pyfunction]
#[pyo3(signature = (**request))]
fn serialize_column<'py>(request: Option<&Bound<'py, PyDict>>) -> PyResult<Bound<'py, PyDict>> {
    let request = Request::new("serialize_column", request)?;
    column_payload(
        &request.get("column")?,
        &request.get("render_resource_type")?,
    )
}

/// A column lineage edge's JSON payload, resource types rendered by the caller.
#[pyfunction]
#[pyo3(signature = (**request))]
fn serialize_column_edge<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyDict>> {
    let request = Request::new("serialize_column_edge", request)?;
    let edge: Bound<'py, PyAny> = request.get("edge")?;
    let render: Bound<'py, PyAny> = request.get("render_resource_type")?;
    let payload: Bound<'py, PyDict> = PyDict::new(request.py());
    payload.set_item("source", column_payload(&edge.getattr("source")?, &render)?)?;
    payload.set_item("target", column_payload(&edge.getattr("target")?, &render)?)?;
    payload.set_item("transform", edge.getattr("transform_kind")?.str()?)?;
    payload.set_item("confidence", edge.getattr("confidence")?.str()?)?;
    Ok(payload)
}

/// `str(value)`, as an f-string renders a callback's text.
fn text(value: &Bound<'_, PyAny>) -> PyResult<String> {
    value.str()?.extract()
}

fn limit_note(
    total: &Bound<'_, PyAny>,
    limit: &Bound<'_, PyAny>,
    note_style: &Bound<'_, PyAny>,
) -> PyResult<Vec<String>> {
    let notes: Vec<String> = trace_limit_note(total.extract()?, limit.extract()?);
    if notes.is_empty() {
        return Ok(notes);
    }
    let mut lines: Vec<String> = vec![String::new()];
    for note in notes {
        lines.push(note_style.call1((note,))?.extract()?);
    }
    Ok(lines)
}

fn column_payload<'py>(
    column: &Bound<'py, PyAny>,
    render_resource_type: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let payload: Bound<'py, PyDict> = PyDict::new(column.py());
    payload.set_item("resource_type", render_resource_type.call1((column,))?)?;
    payload.set_item("resource_name", column.getattr("resource_name")?)?;
    payload.set_item("column_name", column.getattr("column_name")?)?;
    Ok(payload)
}

/// Dependency nodes shown once by Python equality, children sorted by the caller's key.
struct DependencyTree<'py> {
    deps: Bound<'py, PyAny>,
    sort_key: Bound<'py, PyAny>,
    format_node: Bound<'py, PyAny>,
    branch_style: Bound<'py, PyAny>,
    already_shown: Bound<'py, PyAny>,
    sorted: Bound<'py, PyAny>,
    identities: Bound<'py, PyDict>,
    lines: Vec<String>,
}

impl<'py> TreeVisitor<Bound<'py, PyAny>, usize, PyErr> for DependencyTree<'py> {
    fn key(&mut self, node: &Bound<'py, PyAny>) -> PyResult<usize> {
        if let Some(identity) = self.identities.get_item(node)? {
            return identity.extract();
        }
        let identity: usize = self.identities.len();
        self.identities.set_item(node, identity)?;
        Ok(identity)
    }

    fn line(&mut self, line: TreeLine<'_, Bound<'py, PyAny>>) -> PyResult<()> {
        let suffix: String = if line.repeated {
            text(&self.already_shown.call0()?)?
        } else {
            String::new()
        };
        let branch: String = text(
            &self
                .branch_style
                .call1((format!("{}{}", line.prefix, line.branch),))?,
        )?;
        let node: String = text(&self.format_node.call1((line.node,))?)?;
        self.lines.push(format!("{branch}{node}{suffix}"));
        Ok(())
    }

    fn children(&mut self, node: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
        let children: Bound<'py, PyAny> = self
            .deps
            .call_method1("get", (node, PyTuple::empty(node.py())))?;
        let kwargs: Bound<'py, PyDict> = PyDict::new(node.py());
        kwargs.set_item("key", &self.sort_key)?;
        let sorted: Bound<'py, PyAny> = self.sorted.call((children,), Some(&kwargs))?;
        Ok(sorted.downcast::<PyList>()?.iter().collect())
    }
}

/// Column-trace edges shown once per related column id, sorted by that id.
struct ColumnTraceTree<'py> {
    deps: Bound<'py, PyAny>,
    column_id: Bound<'py, PyAny>,
    related_column: Bound<'py, PyAny>,
    format_related: Bound<'py, PyAny>,
    branch_style: Bound<'py, PyAny>,
    already_shown: Bound<'py, PyAny>,
    last_key: String,
    lines: Vec<String>,
}

impl<'py> ColumnTraceTree<'py> {
    fn related_id(&self, edge: &Bound<'py, PyAny>) -> PyResult<String> {
        text(
            &self
                .column_id
                .call1((self.related_column.call1((edge,))?,))?,
        )
    }

    /// `deps.get(column_id, ())` sorted by each edge's related column id, stably.
    fn sorted_edges(&self, column_id: &str) -> PyResult<Vec<Bound<'py, PyAny>>> {
        let py: Python<'py> = self.deps.py();
        let edges: Bound<'py, PyAny> = self
            .deps
            .call_method1("get", (PyString::new(py, column_id), PyTuple::empty(py)))?;
        let mut keyed: Vec<(String, Bound<'py, PyAny>)> = Vec::new();
        for edge in edges.try_iter()? {
            let edge: Bound<'py, PyAny> = edge?;
            keyed.push((self.related_id(&edge)?, edge));
        }
        keyed.sort_by(|left, right| left.0.cmp(&right.0));
        Ok(keyed.into_iter().map(|(_, edge)| edge).collect())
    }
}

impl<'py> TreeVisitor<Bound<'py, PyAny>, String, PyErr> for ColumnTraceTree<'py> {
    fn key(&mut self, edge: &Bound<'py, PyAny>) -> PyResult<String> {
        self.last_key = self.related_id(edge)?;
        Ok(self.last_key.clone())
    }

    fn line(&mut self, line: TreeLine<'_, Bound<'py, PyAny>>) -> PyResult<()> {
        let suffix: String = if line.repeated {
            text(&self.already_shown.call0()?)?
        } else {
            String::new()
        };
        let branch: String = text(&self.branch_style.call1((line.branch,))?)?;
        let related: String = text(&self.format_related.call1((line.node,))?)?;
        self.lines
            .push(format!("{}{branch}{related}{suffix}", line.prefix));
        Ok(())
    }

    fn children(&mut self, _edge: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
        let key: String = self.last_key.clone();
        self.sorted_edges(&key)
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(render_dependency_tree, module)?)?;
    module.add_function(wrap_pyfunction!(render_column_trace_tree, module)?)?;
    module.add_function(wrap_pyfunction!(render_column_trace_limit_note, module)?)?;
    module.add_function(wrap_pyfunction!(serialize_column, module)?)?;
    module.add_function(wrap_pyfunction!(serialize_column_edge, module)?)?;
    Ok(())
}
