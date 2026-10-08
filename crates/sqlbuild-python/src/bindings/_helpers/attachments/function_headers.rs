//! SQL and Python function header parsing and namespaces for the preview compile attachments.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{
    PyDict, PyDictMethods, PyList, PyListMethods, PyString, PyTuple, PyTupleMethods,
};
use pyo3::{FromPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_attachments::functions::main::parse_function_header::parse_function_header;
use sqlbuild_attachments::functions::main::resolve_function_namespace::resolve_function_namespace;
use sqlbuild_attachments::functions::models::{
    FunctionHeader, FunctionLanguage, FunctionNamespace, FunctionReturns, HeaderValue, NamedType,
    NamespaceInputs,
};

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// `(authored name, name, type)` rows.
type Pairs = Vec<(String, String, String)>;
/// Arguments, scalar type, table columns, tags, description, runtime, entry point, packages.
type HeaderRow = (
    Pairs,
    Option<String>,
    Option<Pairs>,
    Vec<String>,
    Option<String>,
    Option<String>,
    Option<String>,
    Vec<String>,
);
type NamespaceRow = [Option<String>; 8];

/// The expanded namespace inputs of one function.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct NamespaceInput {
    header_database: Option<String>,
    header_schema: Option<String>,
    default_database: Option<String>,
    default_schema: Option<String>,
    target_database: Option<String>,
    target_schema: Option<String>,
    python: bool,
    inherit_default_namespace: bool,
}

/// Parse a function header, or return `None` where Python raises for its shape.
#[pyfunction]
fn parse_function_header_values(
    header_values: Bound<'_, PyDict>,
    python: bool,
) -> PyResult<Option<HeaderRow>> {
    compiler_guard(|| {
        let mut header: Vec<(String, HeaderValue)> = Vec::with_capacity(header_values.len());
        for (key, value) in header_values.iter() {
            if value.is_none() {
                continue;
            }
            let Some(name) = text_value(&key) else {
                return Ok(None);
            };
            header.push((name, header_value(&value)?));
        }
        let language: FunctionLanguage = if python {
            FunctionLanguage::Python
        } else {
            FunctionLanguage::Sql
        };
        Ok(parse_function_header(&header, language).map(header_row))
    })
}

/// Python's physical, logical and fingerprint database and schema of one function.
#[pyfunction]
fn resolve_function_namespace_values(inputs: NamespaceInput) -> PyResult<NamespaceRow> {
    compiler_guard(|| {
        let namespace: FunctionNamespace = resolve_function_namespace(&NamespaceInputs {
            header_database: inputs.header_database,
            header_schema: inputs.header_schema,
            default_database: inputs.default_database,
            default_schema: inputs.default_schema,
            target_database: inputs.target_database,
            target_schema: inputs.target_schema,
            language: if inputs.python {
                FunctionLanguage::Python
            } else {
                FunctionLanguage::Sql
            },
            inherit_default_namespace: inputs.inherit_default_namespace,
        });
        Ok([
            namespace.database,
            namespace.schema,
            namespace.logical_database,
            namespace.logical_schema,
            namespace.fingerprint_database,
            namespace.fingerprint_schema,
            namespace.fingerprint_logical_database,
            namespace.fingerprint_logical_schema,
        ])
    })
}

fn header_value(value: &Bound<'_, PyAny>) -> PyResult<HeaderValue> {
    if value.is_instance_of::<PyString>() {
        return Ok(text_value(value).map_or(HeaderValue::Other, HeaderValue::Text));
    }
    if let Ok(mapping) = value.downcast::<PyDict>() {
        let mut entries: Vec<(HeaderValue, HeaderValue)> = Vec::with_capacity(mapping.len());
        for (key, item) in mapping.iter() {
            entries.push((header_value(&key)?, header_value(&item)?));
        }
        return Ok(HeaderValue::Map(entries));
    }
    if let Ok(list) = value.downcast::<PyList>() {
        let mut items: Vec<HeaderValue> = Vec::with_capacity(list.len());
        for item in list.iter() {
            items.push(header_value(&item)?);
        }
        return Ok(HeaderValue::Sequence(items));
    }
    if let Ok(tuple) = value.downcast::<PyTuple>() {
        let mut items: Vec<HeaderValue> = Vec::with_capacity(tuple.len());
        for item in tuple.iter() {
            items.push(header_value(&item)?);
        }
        return Ok(HeaderValue::Sequence(items));
    }
    Ok(HeaderValue::Other)
}

/// A `str` (or subclass) as text; text Rust cannot hold, such as lone surrogates, is `None`.
fn text_value(value: &Bound<'_, PyAny>) -> Option<String> {
    if !value.is_instance_of::<PyString>() {
        return None;
    }
    if let Ok(text) = value.extract::<String>() {
        return Some(text);
    }
    None
}

fn header_row(header: FunctionHeader) -> HeaderRow {
    let (scalar, table): (Option<String>, Option<Pairs>) = match header.returns {
        FunctionReturns::Type(text) => (Some(text), None),
        FunctionReturns::Table(columns) => (None, Some(rows(columns))),
    };
    (
        rows(header.arguments),
        scalar,
        table,
        header.tags,
        header.description,
        header.runtime_version,
        header.entry_point,
        header.packages,
    )
}

fn rows(named: Vec<NamedType>) -> Pairs {
    let mut rows: Pairs = Vec::with_capacity(named.len());
    for item in named {
        rows.push((item.raw_name, item.name, item.type_text));
    }
    rows
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_function_header_values, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_function_namespace_values, module)?)?;
    Ok(())
}
