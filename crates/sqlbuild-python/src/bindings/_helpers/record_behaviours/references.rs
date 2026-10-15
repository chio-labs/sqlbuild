//! Reference call spellings of the natively hosted `SqlReferenceKind`.

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyTuple, PyTupleMethods};

fn function_name(kind: &Bound<'_, PyAny>) -> PyResult<String> {
    let value: String = kind.str()?.extract()?;
    Ok(format!("__{value}"))
}

/// `SqlReferenceKind.function_name`: the reference function, such as `__ref`.
pub(crate) fn reference_function_name(kind: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    function_name(kind)?.into_py_any(kind.py())
}

/// `SqlReferenceKind.fixture_cte_prefix`: the prefix of fixture CTEs for this kind.
pub(crate) fn reference_fixture_cte_prefix(kind: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    format!("{}__", function_name(kind)?).into_py_any(kind.py())
}

/// `SqlReferenceKind.example_call(*args, quote="'")`: a call with quoted arguments.
pub(crate) fn reference_example_call(
    kind: &Bound<'_, PyAny>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Py<PyAny>> {
    let quote: String = match kwargs {
        Some(kwargs) => match kwargs.get_item("quote")? {
            Some(quote) => quote.extract()?,
            None => "'".to_owned(),
        },
        None => "'".to_owned(),
    };
    let doubled: String = format!("{quote}{quote}");
    let mut quoted: Vec<String> = Vec::with_capacity(args.len());
    for argument in args.iter() {
        let text: String = argument.extract()?;
        quoted.push(format!("{quote}{}{quote}", text.replace(&quote, &doubled)));
    }
    format!("{}({})", function_name(kind)?, quoted.join(", ")).into_py_any(kind.py())
}

/// `SqlReferenceKind.placeholder_call(placeholder="")`.
pub(crate) fn reference_placeholder_call(
    kind: &Bound<'_, PyAny>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Py<PyAny>> {
    let placeholder: String = match kwargs
        .map(|kwargs| kwargs.get_item("placeholder"))
        .transpose()?
    {
        Some(Some(value)) => value.extract()?,
        _ if !args.is_empty() => args.get_item(0)?.extract()?,
        _ => String::new(),
    };
    format!("{}({placeholder})", function_name(kind)?).into_py_any(kind.py())
}
