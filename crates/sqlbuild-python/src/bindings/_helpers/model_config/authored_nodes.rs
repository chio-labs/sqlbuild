//! Python objects read in place as authored header values.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods};
use pyo3::types::{
    PyBool, PyBoolMethods, PyDict, PyDictMethods, PyInt, PyList, PyListMethods, PyString,
    PyStringMethods, PyTuple, PyTupleMethods,
};
use sqlbuild_model_config::types::{AuthoredNode, NodeKind};

/// One Python object viewed as an authored value; parsed results keep the object itself.
#[derive(Clone, Debug)]
pub(crate) struct PyNode<'py>(pub(crate) Bound<'py, PyAny>);

impl AuthoredNode for PyNode<'_> {
    fn kind(&self) -> NodeKind {
        let value = &self.0;
        if value.is_none() {
            NodeKind::Null
        } else if let Ok(flag) = value.downcast::<PyBool>() {
            NodeKind::Bool(flag.is_true())
        } else if value.is_instance_of::<PyInt>() {
            value
                .lt(0)
                .map_or(NodeKind::Other, |negative| NodeKind::Int { negative })
        } else if value.is_instance_of::<PyString>() {
            NodeKind::Str
        } else if value.is_instance_of::<PyList>() {
            NodeKind::List
        } else if value.is_instance_of::<PyTuple>() {
            NodeKind::Tuple
        } else if value.is_instance_of::<PyDict>() {
            NodeKind::Map
        } else {
            NodeKind::Other
        }
    }

    fn integer(&self) -> Option<i64> {
        if !self.0.is_instance_of::<PyBool>()
            && self.0.is_instance_of::<PyInt>()
            && let Ok(number) = self.0.extract::<i64>()
        {
            Some(number)
        } else {
            None
        }
    }

    fn text(&self) -> Option<String> {
        self.with_text(str::to_owned)
    }

    fn with_text<R>(&self, read: impl FnOnce(&str) -> R) -> Option<R> {
        if let Ok(value) = self.0.downcast::<PyString>()
            && let Ok(text) = value.to_str()
        {
            Some(read(text))
        } else {
            None
        }
    }

    fn is_text(&self, text: &str) -> bool {
        self.with_text(|value| value == text).unwrap_or(false)
    }

    fn items(&self) -> Vec<Self> {
        if let Ok(items) = self.0.downcast::<PyList>() {
            items.iter().map(PyNode).collect()
        } else if let Ok(items) = self.0.downcast::<PyTuple>() {
            items.iter().map(PyNode).collect()
        } else {
            Vec::new()
        }
    }

    fn entries(&self) -> Vec<(Self, Self)> {
        if let Ok(entries) = self.0.downcast::<PyDict>() {
            entries.iter().map(entry_nodes).collect()
        } else {
            Vec::new()
        }
    }
}

fn entry_nodes<'py>(
    (key, value): (Bound<'py, PyAny>, Bound<'py, PyAny>),
) -> (PyNode<'py>, PyNode<'py>) {
    (PyNode(key), PyNode(value))
}
