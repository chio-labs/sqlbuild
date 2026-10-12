//! SQL test macro-mock model queries and compiled SQL scenarios of an assembled project.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyTuple};

use crate::bindings::_helpers::compile_driver::assembly_project::ADAPTER_NAME_MODULE;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};

const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
const DECLARATIONS_MODULE: &str = "sqlbuild.compiler.compile._helpers.render.declarations";
const MACROS_MODULE: &str = "sqlbuild.compiler.compile._helpers.render.macros";
const CURSOR_INTRINSICS_MODULE: &str =
    "sqlbuild.compiler.compile._helpers.render.cursor_intrinsics";
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
    if !payload.is_instance(&imported(
        py,
        COMPILE_MODELS_MODULE,
        "CompileModelSqlTestInputPayload",
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
    let declaration_resolver: Bound<'py, PyAny> = call_with(
        &imported(py, DECLARATIONS_MODULE, "build_declaration_scope_resolver")?,
        &[
            ("discovered_inputs", inputs.getattr("discovered_inputs")?),
            ("scope_index", inputs.getattr("scope_index")?),
            ("loaded_macros", loaded_macros.clone()),
            ("lookup", lookup),
        ],
    )?;
    let expand: Bound<'py, PyAny> = imported(py, MACROS_MODULE, "expand_sql_macros")?;
    let intrinsics: Bound<'py, PyAny> = imported(
        py,
        CURSOR_INTRINSICS_MODULE,
        "get_validated_model_cursor_intrinsics",
    )?;
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
        )?;
        let query: Bound<'py, PyAny> = call_with(
            &intrinsics,
            &[
                ("sql", expanded),
                (
                    "config_values",
                    model_input.getattr("config")?.getattr("values")?,
                ),
                ("model_name", model_name.clone()),
            ],
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
    let adapter_name: Bound<'py, PyAny> = call_with(
        &imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", inputs.getattr("project_config")?),
            ("local_config", inputs.getattr("local_config")?),
        ],
    )?;
    call_with(
        &imported(py, COMPILE_MODELS_MODULE, "MacroContext")?,
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
    let scenario_class: Bound<'py, PyAny> =
        imported(py, COMPILE_MODELS_MODULE, "CompiledSqlScenario")?;
    let key_class: Bound<'py, PyAny> = imported(py, COMPILE_MODELS_MODULE, "CompiledObjectKey")?;
    let resource_type: Bound<'py, PyAny> =
        imported(py, COMPILE_TYPES_MODULE, "CompiledResourceType")?.getattr("SQL_SCENARIO")?;
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
