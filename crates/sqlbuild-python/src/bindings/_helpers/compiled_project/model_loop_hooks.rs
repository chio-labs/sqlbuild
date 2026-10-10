//! A model's hooks, expanded by the project's hook code and checked natively.

use pyo3::IntoPyObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyList, PyTuple};
use sqlbuild_attachments::cursor_intrinsics::main::intrinsic_free::intrinsic_free;
use sqlbuild_attachments::cursor_intrinsics::models::IntrinsicCheck;

use crate::bindings::_helpers::compiled_project::model_loop::{
    LoopContext, NativeModelLoop, compile_error, config_error,
};
use crate::bindings::_helpers::compiled_project::model_loop_host::{ReferenceRow, callback};
use crate::bindings::_helpers::compiled_project::model_loop_inputs::{HOOK_KEYS, present};

const EXPAND_HOOKS_CALLBACK: &str = "expand_hooks";
const INDEX_ARGUMENT: &str = "index";
const REFERENCES_METHOD: &str = "references";
const STATEMENT_ATTRIBUTE: &str = "statement";
const DBT_REF_KIND: &str = "dbt_ref";

/// The hook-expanded config values and SQL hook count; `None` when a hook references dbt.
pub(crate) fn expanded_hooks<'py>(
    model_loop: &NativeModelLoop,
    context: &LoopContext<'_, 'py>,
    index: usize,
    model: (&str, &str),
) -> PyResult<Option<(Bound<'py, PyDict>, usize)>> {
    let py: Python<'py> = context.host.py();
    let (values, references): (Bound<'py, PyDict>, Vec<ReferenceRow>) = callback(
        context.host,
        EXPAND_HOOKS_CALLBACK,
        &[(INDEX_ARGUMENT, index.into_pyobject(py)?.into_any())],
    )?
    .extract()?;
    if references
        .iter()
        .any(|(kind, _, _, _)| kind == DBT_REF_KIND)
    {
        return Ok(None);
    }
    let rows: Vec<(&str, &str, bool)> = references
        .iter()
        .map(|(kind, name, _, _)| (kind.as_str(), name.as_str(), false))
        .collect();
    let outcome: Bound<'py, PyAny> = model_loop
        .validator
        .bind(py)
        .call_method1(REFERENCES_METHOD, (model, rows))?;
    if !outcome.is_none() {
        return Err(config_error(
            context.classes,
            &outcome,
            Some(&PyDict::new(py)),
        ));
    }
    let statements: usize = reject_hook_intrinsics(model_loop, context, model.0, &values)?;
    Ok(Some((values, statements)))
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
