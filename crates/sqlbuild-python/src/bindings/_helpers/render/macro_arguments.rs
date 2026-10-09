//! Macro call arguments parsed natively into a value plan Python builds objects from.

use pyo3::prelude::{
    Bound, IntoPyObject, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyList, PyListMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_render::macro_arguments::main::parse_macro_arguments::parse_macro_arguments as parse;
use sqlbuild_render::macro_arguments::models::{ArgumentValue, MacroArguments};
use sqlbuild_render::macro_arguments::types::ArgumentHost;

/// `unicodedata` answers character names and identifier normalization as CPython does.
struct UnicodeHost<'py> {
    unicodedata: Bound<'py, PyModule>,
}

impl ArgumentHost for UnicodeHost<'_> {
    fn character_named(&self, name: &str) -> Option<char> {
        self.unicodedata
            .call_method1("lookup", (name,))
            .and_then(|found| found.extract::<char>())
            .ok()
    }

    fn identifier(&self, text: &str) -> Option<String> {
        let py: Python<'_> = self.unicodedata.py();
        let candidate = text.into_pyobject(py).ok()?;
        let valid: bool = candidate
            .call_method0("isidentifier")
            .and_then(|valid| valid.extract())
            .ok()?;
        if !valid {
            return None;
        }
        self.unicodedata
            .call_method1("normalize", ("NFKC", candidate))
            .and_then(|normalized| normalized.extract())
            .ok()
    }
}

/// `("ok", positional, keywords, typed references)` or `("error", detail, help, line, column)`.
#[pyfunction]
fn parse_macro_arguments(
    py: Python<'_>,
    text: &str,
    nested: Vec<(usize, usize)>,
) -> PyResult<Py<PyAny>> {
    let host = UnicodeHost {
        unicodedata: py.import("unicodedata")?,
    };
    match parse(&host, text, &nested) {
        Ok(arguments) => arguments_row(py, &arguments),
        Err(error) => Ok(
            ("error", error.detail, error.help, error.line, error.column)
                .into_pyobject(py)?
                .into_any()
                .unbind(),
        ),
    }
}

fn arguments_row(py: Python<'_>, arguments: &MacroArguments) -> PyResult<Py<PyAny>> {
    let positional = values_list(py, &arguments.positional)?;
    let keywords = PyList::empty(py);
    for (name, value) in &arguments.keywords {
        keywords.append((name, value_row(py, value)?))?;
    }
    Ok((
        "ok",
        positional,
        keywords,
        arguments.typed_references.clone(),
    )
        .into_pyobject(py)?
        .into_any()
        .unbind())
}

fn values_list<'py>(py: Python<'py>, values: &[ArgumentValue]) -> PyResult<Bound<'py, PyList>> {
    let list = PyList::empty(py);
    for value in values {
        list.append(value_row(py, value)?)?;
    }
    Ok(list)
}

/// One value as a tagged tuple: the tag, then its fields.
fn value_row<'py>(py: Python<'py>, value: &ArgumentValue) -> PyResult<Bound<'py, PyAny>> {
    let row: Bound<'py, PyTuple> = match value {
        ArgumentValue::Str(text) => ("s", text).into_pyobject(py)?,
        ArgumentValue::Int { radix, digits } => ("i", radix, digits).into_pyobject(py)?,
        ArgumentValue::Float(text) => ("f", text).into_pyobject(py)?,
        ArgumentValue::Bool(flag) => ("b", flag).into_pyobject(py)?,
        ArgumentValue::None => ("n",).into_pyobject(py)?,
        ArgumentValue::NestedCall(call) => ("c", call).into_pyobject(py)?,
        ArgumentValue::TypedReference { function, name } => {
            ("r", function, name).into_pyobject(py)?
        }
        ArgumentValue::List(items) => ("l", values_list(py, items)?).into_pyobject(py)?,
        ArgumentValue::Tuple(items) => ("t", values_list(py, items)?).into_pyobject(py)?,
        ArgumentValue::Dict(pairs) => {
            let rows = PyList::empty(py);
            for (key, item) in pairs {
                rows.append((value_row(py, key)?, value_row(py, item)?))?;
            }
            ("d", rows).into_pyobject(py)?
        }
        ArgumentValue::Negative(inner) => ("-", value_row(py, inner)?).into_pyobject(py)?,
        ArgumentValue::Positive(inner) => ("+", value_row(py, inner)?).into_pyobject(py)?,
    };
    Ok(row.into_any())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_macro_arguments, module)?)?;
    Ok(())
}
