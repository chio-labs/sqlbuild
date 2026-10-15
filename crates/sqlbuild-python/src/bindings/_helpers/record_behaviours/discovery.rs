//! Computed attributes of the natively hosted discovery and pipeline records.

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult};

use crate::bindings::_helpers::graph::views::lineage_graph_views;

/// SQL scalar type labels by logical value kind.
const SCALAR_TYPE_LABELS: [(&str, &str); 6] = [
    ("string", "VARCHAR"),
    ("integer", "INTEGER"),
    ("boolean", "BOOLEAN"),
    ("float", "FLOAT"),
    ("decimal", "DECIMAL"),
    ("null", "NULL"),
];

/// `ConstantDeclaration.logical_type`: the normalized logical type.
pub(crate) fn constant_logical_type(declaration: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    Ok(declaration
        .getattr("value")?
        .getattr("logical_type")?
        .unbind())
}

/// `ConstantDeclaration.scalar_type`: the SQL scalar type label, or the upper-cased logical type.
pub(crate) fn constant_scalar_type(declaration: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let value: Bound<'_, PyAny> = declaration.getattr("value")?;
    let kind: String = value.getattr("kind")?.str()?.extract()?;
    if let Some((_, label)) = SCALAR_TYPE_LABELS.iter().find(|(name, _)| *name == kind) {
        return label.into_py_any(declaration.py());
    }
    let display: String = value
        .getattr("logical_type")?
        .getattr("display_name")?
        .extract()?;
    display.to_uppercase().into_py_any(declaration.py())
}

/// `ProjectGraph.lineage_views`: lineage edges and selector indexes, converted once.
pub(crate) fn graph_lineage_views(graph: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let native = graph.getattr("native")?;
    Ok(lineage_graph_views(graph.py(), native.extract()?)?.unbind())
}

fn view(graph: &Bound<'_, PyAny>, name: &str) -> PyResult<Py<PyAny>> {
    Ok(graph.getattr("lineage_views")?.getattr(name)?.unbind())
}

/// `ProjectGraph.upstream_deps`.
pub(crate) fn graph_upstream_deps(graph: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    view(graph, "upstream_deps")
}

/// `ProjectGraph.downstream_deps`.
pub(crate) fn graph_downstream_deps(graph: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    view(graph, "downstream_deps")
}

/// `ProjectGraph.tag_index`.
pub(crate) fn graph_tag_index(graph: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    view(graph, "tag_index")
}

/// `ProjectGraph.path_index`.
pub(crate) fn graph_path_index(graph: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    view(graph, "path_index")
}

/// `ProjectGraph.all_keys`.
pub(crate) fn graph_all_keys(graph: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    view(graph, "all_keys")
}
