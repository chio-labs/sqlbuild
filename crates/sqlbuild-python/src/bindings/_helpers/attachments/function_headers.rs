//! SQL and Python function header parsing and namespaces for the preview compile attachments.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{
    PyDict, PyDictMethods, PyList, PyListMethods, PyString, PyStringMethods, PyTuple,
    PyTupleMethods,
};
use pyo3::{FromPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_attachments::functions::main::parse_function_header::parse_function_header;
use sqlbuild_attachments::functions::main::resolve_function_namespace::resolve_function_namespace;
use sqlbuild_attachments::functions::models::{
    FunctionHeader, FunctionLanguage, FunctionNamespace, FunctionReturns, HeaderStage, HeaderValue,
    NamedType, NamespaceInputs,
};

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// `(authored name, name, type)` rows.
type Pairs = Vec<(String, String, String)>;
/// Parsed header fields in Python's order, then its first error as `(stage, message)`.
type HeaderRow = (
    Pairs,
    Option<String>,
    Option<Pairs>,
    Vec<String>,
    Option<String>,
    Option<String>,
    Option<String>,
    Vec<String>,
    Option<(&'static str, String)>,
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

/// Parse one function file's header with its first error; non-string keys are never read.
#[pyfunction]
fn parse_function_header_values(
    header_values: Bound<'_, PyDict>,
    python: bool,
    relative_path: &str,
) -> PyResult<HeaderRow> {
    compiler_guard(|| {
        let mut header: Vec<(String, HeaderValue)> = Vec::with_capacity(header_values.len());
        for (key, value) in header_values.iter() {
            let Some(name) = text_value(&key) else {
                continue;
            };
            if value.is_none() {
                continue;
            }
            header.push((name, header_value(&value)));
        }
        let language: FunctionLanguage = if python {
            FunctionLanguage::Python
        } else {
            FunctionLanguage::Sql
        };
        Ok(header_row(parse_function_header(
            &header,
            language,
            relative_path,
        )))
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

/// One header value.
fn header_value(value: &Bound<'_, PyAny>) -> HeaderValue {
    if let Some(text) = text_value(value) {
        return HeaderValue::Text(text);
    }
    if let Ok(mapping) = value.downcast::<PyDict>() {
        return HeaderValue::Map(
            mapping
                .iter()
                .map(|(key, item)| (header_value(&key), header_value(&item)))
                .collect(),
        );
    }
    if let Ok(list) = value.downcast::<PyList>() {
        return HeaderValue::Sequence(list.iter().map(|item| header_value(&item)).collect());
    }
    if let Ok(tuple) = value.downcast::<PyTuple>() {
        return HeaderValue::Sequence(tuple.iter().map(|item| header_value(&item)).collect());
    }
    HeaderValue::Other
}

/// A `str` (or subclass) as text; lone surrogates, rejected where text enters a compile, read as
/// U+FFFD.
fn text_value(value: &Bound<'_, PyAny>) -> Option<String> {
    value
        .downcast::<PyString>()
        .ok()
        .map(|text| text.to_string_lossy().into_owned())
}

fn header_row(header: FunctionHeader) -> HeaderRow {
    let (scalar, table): (Option<String>, Option<Pairs>) = match header.returns {
        Some(FunctionReturns::Type(text)) => (Some(text), None),
        Some(FunctionReturns::Table(columns)) => (None, Some(rows(columns))),
        None => (None, None),
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
        header
            .failure
            .map(|failure| (stage_name(failure.stage), failure.message)),
    )
}

fn stage_name(stage: HeaderStage) -> &'static str {
    match stage {
        HeaderStage::Start => "start",
        HeaderStage::Arguments => "arguments",
        HeaderStage::Returns => "returns",
        HeaderStage::PythonValues => "python_values",
        HeaderStage::Metadata => "metadata",
    }
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
