//! The SQL expansion inputs lint uses to expand authored SQL outside a compile.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyBool, PyDict, PyDictMethods};

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};

const NATIVE_MODULE: &str = "sqlbuild._native";
const USER_MACROS_MODULE: &str = "sqlbuild.compiler.compile._helpers.render.user_macros";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";

/// Build the declaration scope of `discovered`; a static scope lends only its index to macros.
fn declaration_scope<'py>(
    discovered: &Bound<'py, PyAny>,
    static_scope: Bound<'py, PyAny>,
    sql_lexical_syntax: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let loaded_macros: Bound<'py, PyAny> = imported(py, USER_MACROS_MODULE, "load_project_macros")?
        .call1((discovered.getattr("macro_files")?,))?;
    if !static_scope.is_none() {
        let rebound: Bound<'py, PyAny> = call_with(
            &imported(py, NATIVE_MODULE, "rebind_declaration_scope")?,
            &[
                ("scope", static_scope),
                ("discovered_inputs", discovered.clone()),
                ("loaded_macros", loaded_macros.clone()),
            ],
        )?;
        if !rebound.is_none() {
            return Ok(rebound);
        }
    }
    call_with(
        &imported(py, NATIVE_MODULE, "build_declaration_scope")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("loaded_macros", loaded_macros),
            ("sql_lexical_syntax", sql_lexical_syntax),
        ],
    )
}

/// Each model file's own enum and constant declarations, by file path.
fn local_declarations<'py>(discovered: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = discovered.py();
    let context: Bound<'py, PyAny> =
        imported(py, COMPILE_MODELS_MODULE, "DeclarationResolutionContext")?;
    let by_name = |declarations: Bound<'py, PyAny>| -> PyResult<Bound<'py, PyAny>> {
        let named: Bound<'py, PyDict> = PyDict::new(py);
        for declaration in declarations.try_iter()? {
            let declaration: Bound<'py, PyAny> = declaration?;
            named.set_item(declaration.getattr("name")?, declaration)?;
        }
        Ok(named.into_any())
    };
    let local: Bound<'py, PyDict> = PyDict::new(py);
    for model_file in discovered.getattr("model_files")?.try_iter()? {
        let model_file: Bound<'py, PyAny> = model_file?;
        local.set_item(
            model_file.getattr("file_path")?,
            call_with(
                &context,
                &[
                    ("enums", by_name(model_file.getattr("enum_declarations")?)?),
                    (
                        "constants",
                        by_name(model_file.getattr("constant_declarations")?)?,
                    ),
                ],
            )?,
        )?;
    }
    Ok(local)
}

/// Assemble SQL expansion inputs; a static scope lends only its index to private macros.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn build_sql_expansion_context<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_sql_expansion_context",
        options,
        (
            &["project_dir", "value_renderer"],
            &[
                "cli_vars",
                "discovered_inputs",
                "declaration_scope",
                "static_declaration_scope",
            ],
        ),
    )?;
    let value_renderer: Bound<'py, PyAny> = arguments.value("value_renderer")?;
    let mut discovered: Bound<'py, PyAny> = arguments.value("discovered_inputs")?;
    if discovered.is_none() {
        discovered = call_with(
            &imported(py, NATIVE_MODULE, "discover_project_inputs")?,
            &[
                ("project_dir", arguments.value("project_dir")?),
                (
                    "sql_analysis_enabled_override",
                    PyBool::new(py, false).to_owned().into_any(),
                ),
            ],
        )?;
    }
    let project_config: Bound<'py, PyAny> = discovered.getattr("project_config")?;
    let local_config: Bound<'py, PyAny> = discovered.getattr("local_config")?;
    let mut cli_vars: Bound<'py, PyAny> = arguments.value("cli_vars")?;
    if cli_vars.is_none() {
        cli_vars = PyDict::new(py).into_any();
    }
    let effective_vars: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "build_effective_vars")?,
        &[
            ("project_config", project_config.clone()),
            ("local_config", local_config.clone()),
            ("target_config", py.None().into_bound(py)),
            ("cli_vars", cli_vars),
        ],
    )?;
    let mut scope: Bound<'py, PyAny> = arguments.value("declaration_scope")?;
    if scope.is_none() {
        scope = declaration_scope(
            &discovered,
            arguments.value("static_declaration_scope")?,
            value_renderer.getattr("sql_lexical_syntax")?,
        )?;
    }
    let (enums, constants): (Bound<'py, PyAny>, Bound<'py, PyAny>) =
        imported(py, NATIVE_MODULE, "public_declaration_indexes")?
            .call1((&discovered,))?
            .extract()?;
    let collection_rendering: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "resolve_effective_collection_rendering")?,
        &[
            ("project_config", project_config.clone()),
            ("declaration_override", py.None().into_bound(py)),
        ],
    )?;
    let macro_context: Bound<'py, PyAny> = call_with(
        &imported(py, COMPILE_MODELS_MODULE, "MacroContext")?,
        &[
            (
                "adapter_name",
                call_with(
                    &imported(py, NATIVE_MODULE, "resolve_effective_adapter_name")?,
                    &[
                        ("project_config", project_config.clone()),
                        ("local_config", local_config),
                    ],
                )?,
            ),
            (
                "sql_analysis_enabled",
                PyBool::new(py, false).to_owned().into_any(),
            ),
            ("target_name", project_config.getattr("default_target")?),
            ("vars", effective_vars.clone()),
            ("_value_renderer", value_renderer.clone()),
            ("_collection_rendering", collection_rendering.clone()),
            (
                "_enforce_explicit_references",
                project_config
                    .getattr("references")?
                    .getattr("enforce_explicit")?,
            ),
        ],
    )?;
    call_with(
        &imported(py, COMPILE_MODELS_MODULE, "SqlExpansionContext")?,
        &[
            ("effective_vars", effective_vars),
            ("loaded_macros", scope.getattr("loaded_macros")?),
            ("macro_context", macro_context),
            ("enums", enums),
            ("constants", constants),
            ("value_renderer", value_renderer),
            ("collection_rendering", collection_rendering),
            (
                "local_declarations",
                local_declarations(&discovered)?.into_any(),
            ),
            ("declaration_resolver", scope.getattr("resolver")?),
        ],
    )
}
