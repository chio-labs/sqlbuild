//! A model's hooks, expanded by the project's hook code and checked natively.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyList, PyTuple};
use sqlbuild_attachments::cursor_intrinsics::main::intrinsic_free::intrinsic_free;
use sqlbuild_attachments::cursor_intrinsics::models::IntrinsicCheck;

use crate::bindings::_helpers::compiled_project::model_loop::{
    LoopContext, NativeModelLoop, compile_error, validation_outcome,
};
use crate::bindings::_helpers::compiled_project::model_loop_external::external_errors;
use crate::bindings::_helpers::compiled_project::model_loop_host::{ReferenceRow, callback};
use crate::bindings::_helpers::compiled_project::model_loop_inputs::{HOOK_KEYS, present};

const EXPAND_HOOKS_CALLBACK: &str = "expand_hooks";
const REFERENCES_METHOD: &str = "references";
const STATEMENT_ATTRIBUTE: &str = "statement";

/// The hook-expanded config values and SQL hook count, after checking the hooks' references.
pub(crate) fn expanded_hooks<'py>(
    model_loop: &NativeModelLoop,
    context: &LoopContext<'_, 'py>,
    arguments: &[(&str, Bound<'py, PyAny>)],
    model: (&str, &str),
) -> PyResult<(Bound<'py, PyDict>, usize)> {
    let py: Python<'py> = context.host.py();
    let (values, references): (Bound<'py, PyDict>, Vec<ReferenceRow>) =
        callback(context.host, EXPAND_HOOKS_CALLBACK, arguments)?.extract()?;
    let external: Vec<Option<PyErr>> = external_errors(context, &references, model.1)?;
    let rows: Vec<(&str, &str, bool)> = references
        .iter()
        .zip(&external)
        .map(|((kind, name, _, _), error)| (kind.as_str(), name.as_str(), error.is_some()))
        .collect();
    let outcome: Bound<'py, PyAny> = model_loop
        .validator
        .bind(py)
        .call_method1(REFERENCES_METHOD, (model, rows))?;
    validation_outcome(context, &outcome, external, &PyDict::new(py))?;
    let statements: usize = reject_hook_intrinsics(model_loop, context, model.0, &values)?;
    Ok((values, statements))
}

/// Reject cursor intrinsics in each SQL hook statement; return how many statements were checked.
fn reject_hook_intrinsics(
    model_loop: &NativeModelLoop,
    context: &LoopContext<'_, '_>,
    name: &str,
    values: &Bound<'_, PyDict>,
) -> PyResult<usize> {
    let mut statements: usize = 0;
    for key in HOOK_KEYS {
        let Some(hooks) = present(values, key)? else {
            continue;
        };
        if !(hooks.is_instance_of::<PyList>() || hooks.is_instance_of::<PyTuple>()) {
            continue;
        }
        let hook_context: String = format!("Model '{name}' {key}");
        for entry in hooks.try_iter()? {
            let entry: Bound<'_, PyAny> = entry?;
            if !entry.is_instance(&context.classes.sql_hook_entry)? {
                continue;
            }
            statements += 1;
            let statement: String = entry.getattr(STATEMENT_ATTRIBUTE)?.extract()?;
            if let IntrinsicCheck::Rejected(message) = intrinsic_free(
                model_loop.python,
                &statement,
                &model_loop.reserved_markers,
                &hook_context,
            ) {
                return Err(compile_error(context.classes, &message, None));
            }
        }
    }
    Ok(statements)
}
