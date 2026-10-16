//! SQL test macro-mock model queries and compiled SQL scenarios of an assembled project.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyTuple};

use crate::bindings::_helpers::attachments::cursor_intrinsics::validated_model_cursor_sql;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};
use crate::bindings::_helpers::contracts::spec_resolution::resolve_effective_adapter_name;
use crate::bindings::_helpers::native_host::facade::FacadeHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::render::declaration_values::declaration_scope_resolver;
use pyo3::IntoPyObjectExt;

/// The `CompiledSqlScenario` fields copied from its input, in Python's keyword order.
const SCENARIO_FIELDS: [&str; 12] = [
    "sql_body",
    "authored_ctes",
    "expected_ctes",
    "assertion_ctes",
    "source_fixture_names",
    "ref_fixture_names",
    "seed_fixture_names",
    "dbt_ref_fixture_names",
    "expected_model_names",
    "assertion_names",
    "assertion_target_model_names",
    "target_model_names",
];

/// Re-expand each model from its pre-macro SQL with the test's macro mocks applied.
pub(crate) fn test_model_query_overrides<'py>(
    test_input: &Bound<'py, PyAny>,
    inputs: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = inputs.py();
    let overrides: Bound<'py, PyDict> = PyDict::new(py);
    let payload: Bound<'py, PyAny> = test_input.getattr("payload")?;
    if !payload.is_instance(&registry::class(
        py,
        RecordId::CompileModelSqlTestInputPayload,
    )?)? {
        return Ok(overrides);
    }
    let macro_mocks: Bound<'py, PyAny> = payload.getattr("macro_mocks")?;
    if !macro_mocks.is_truthy()? {
        return Ok(overrides);
    }
    let macro_context: Bound<'py, PyAny> = imported(py, "dataclasses", "replace")?.call(
        (model_macro_context(inputs)?,),
        Some(&keywords(
            py,
            &[(
                "_enforce_explicit_references",
                PyBool::new(py, false).to_owned().into_any(),
            )],
        )?),
    )?;
    let declaration_scope: Bound<'py, PyAny> = inputs.getattr("declaration_scope")?;
    let lookup: Bound<'py, PyAny> = if declaration_scope.is_none() {
        py.None().into_bound(py)
    } else {
        declaration_scope.getattr("resolver")?.getattr("lookup")?
    };
    let loaded_macros: Bound<'py, PyAny> = inputs.getattr("loaded_macros")?;
    let declaration_resolver: Bound<'py, PyAny> = declaration_scope_resolver(
        &inputs.getattr("discovered_inputs")?,
        &inputs.getattr("scope_index")?,
        (&loaded_macros, &lookup),
    )?;
    let expand: Bound<'py, PyAny> = registry::native(py, NativeAttr::ExpandSqlMacros)?;
    for model_input in inputs.getattr("model_inputs")?.try_iter()? {
        let model_input: Bound<'py, PyAny> = model_input?;
        let file_path: Bound<'py, PyAny> =
            model_input.getattr("model_file")?.getattr("file_path")?;
        let model_name: Bound<'py, PyAny> = file_path.getattr("stem")?;
        let macro_source_sql: Bound<'py, PyAny> = model_input.getattr("macro_source_sql")?;
        let macro_source_sql: Bound<'py, PyAny> = if macro_source_sql.is_truthy()? {
            macro_source_sql
        } else {
            model_input.getattr("query_sql")?
        };
        let expanded: Bound<'py, PyAny> = call_with(
            &expand,
            &[
                ("sql", macro_source_sql),
                ("file_path", file_path),
                ("loaded_macros", loaded_macros.clone()),
                ("macro_overrides", macro_mocks.clone()),
                ("macro_context", macro_context.clone()),
                ("declaration_resolver", declaration_resolver.clone()),
            ],
        )?
        .getattr("sql")?;
        let query: String = validated_model_cursor_sql(
            py,
            &expanded.extract::<String>()?,
            (
                &model_name.extract::<String>()?,
                &model_input.getattr("config")?.getattr("values")?,
            ),
        )?;
        overrides.set_item(model_name, query)?;
    }
    Ok(overrides)
}

/// The compile's macro context, or one built from the effective adapter, settings and target.
fn model_macro_context<'py>(inputs: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = inputs.py();
    let macro_context: Bound<'py, PyAny> = inputs.getattr("macro_context")?;
    if macro_context.is_truthy()? {
        return Ok(macro_context);
    }
    let adapter_name: Bound<'py, PyAny> = resolve_effective_adapter_name(
        &inputs.getattr("project_config")?,
        &inputs.getattr("local_config")?,
    )
    .and_then(|value| value.into_bound_py_any(py))?;
    call_with(
        &registry::class(py, RecordId::MacroContext)?,
        &[
            ("adapter_name", adapter_name),
            (
                "sql_analysis_enabled",
                inputs
                    .getattr("effective_settings")?
                    .getattr("sql_analysis")?,
            ),
            ("target_name", inputs.getattr("effective_target_name")?),
            ("vars", inputs.getattr("effective_vars")?),
        ],
    )
}

/// Each scenario input as a `CompiledSqlScenario`.
pub(crate) fn compiled_sql_scenarios<'py>(
    inputs: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = inputs.py();
    let scenario_class: Bound<'py, PyAny> = registry::class(py, RecordId::CompiledSqlScenario)?;
    let key_class: Bound<'py, PyAny> = registry::class(py, RecordId::CompiledObjectKey)?;
    let resource_type: Bound<'py, PyAny> =
        host::entry(py, FacadeHost::CompiledResourceType)?.getattr("SQL_SCENARIO")?;
    let mut scenarios: Vec<Bound<'py, PyAny>> = Vec::new();
    for scenario_input in inputs.getattr("scenario_inputs")?.try_iter()? {
        let scenario_input: Bound<'py, PyAny> = scenario_input?;
        let scenario_file: Bound<'py, PyAny> = scenario_input.getattr("scenario_file")?;
        let name: Bound<'py, PyAny> = scenario_file.getattr("name")?;
        let key: Bound<'py, PyAny> = call_with(
            &key_class,
            &[
                ("resource_type", resource_type.clone()),
                ("name", name.clone()),
            ],
        )?;
        let fields: Bound<'py, PyDict> = keywords(
            py,
            &[
                ("key", key),
                ("name", name),
                ("scenario_file", scenario_file.clone()),
            ],
        )?;
        for field in SCENARIO_FIELDS {
            fields.set_item(field, scenario_input.getattr(field)?)?;
        }
        fields.set_item("source_path", scenario_file.getattr("relative_path")?)?;
        fields.set_item("ownership_root", scenario_file.getattr("ownership_root")?)?;
        scenarios.push(scenario_class.call((), Some(&fields))?);
    }
    PyTuple::new(py, scenarios)
}
