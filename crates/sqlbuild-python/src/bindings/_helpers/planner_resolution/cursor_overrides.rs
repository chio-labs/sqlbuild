//! Selected-model inspection and untyped override conversion.

use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::model_config::config_values::config_str as authored_config_str;
use crate::bindings::_helpers::planner_resolution::values::{method, string};
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::PyDict;
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_cursor::planner::main::override_kind::override_kind;

#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn type_cursor_overrides<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "type_cursor_overrides",
        kwargs,
        (&["cursor_overrides"], &["selected_models"]),
    )?;
    let overrides = args.value("cursor_overrides")?;
    if overrides.is_none() || !overrides.getattr("has_untyped")?.is_truthy()? {
        return Ok(overrides);
    }
    let mut models: Vec<(String, String)> = Vec::new();
    let selected = if args.passed("selected_models")? {
        args.value("selected_models")?
    } else {
        pyo3::types::PyTuple::empty(py).into_any()
    };
    for model in selected.try_iter()? {
        let model = model?;
        let values = model.getattr("config")?.getattr("values")?;
        let config = |key: &str| -> PyResult<Bound<'_, PyAny>> {
            Ok(authored_config_str(&values, key)?.unwrap_or_else(|| py.None().into_bound(py)))
        };
        if !config("materialized")?.eq("incremental")? || config("cursor")?.is_none() {
            continue;
        }
        let kind = config("cursor_type")?;
        if kind.eq("integer")? || kind.eq("timestamp")? {
            models.push((model.getattr("name")?.extract()?, kind.extract()?));
        }
    }
    let mut integer_literals = true;
    if models.is_empty() {
        for field in ["start", "end"] {
            let value = overrides.getattr(field)?;
            if value.is_none() {
                continue;
            }
            let stripped = value.call_method0("strip")?;
            let text: String = stripped.extract()?;
            let digits = text.strip_prefix(['+', '-']).unwrap_or(&text);
            if !string(py, digits).call_method0("isdecimal")?.is_truthy()? {
                integer_literals = false;
                break;
            }
        }
    }
    let kind = override_kind(&models, integer_literals).map_err(|message| {
        match registry::error(py, ErrorId::PlannerInput).and_then(|class| call_with(&class, &[
            ("message", string(py, &message)), ("code", string(py, "S303")),
            ("help", string(py, "select models with one cursor type, or set each type explicitly with --start-cursor-ts/--end-cursor-ts and --start-cursor-int/--end-cursor-int")),
        ])) { Ok(error) => PyErr::from_value(error), Err(error) => error }
    })?;
    let kind = registry::class(py, RecordId::CursorType)?.call1((kind,))?;
    method(&overrides, "typed_as", &[("cursor_type", kind)])
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(type_cursor_overrides, module)?)
}
