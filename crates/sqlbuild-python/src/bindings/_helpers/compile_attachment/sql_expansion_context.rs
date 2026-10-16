//! The SQL expansion inputs lint uses to expand authored SQL outside a compile.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyBool, PyDict, PyDictMethods};

use crate::bindings::_helpers::compile_attachment::declaration_scope::rebind_declaration_scope;
use crate::bindings::_helpers::compile_attachment::effective_config::build_effective_vars;
use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::contracts::spec_resolution::resolve_effective_adapter_name;
use crate::bindings::_helpers::contracts::spec_resolution::resolve_effective_collection_rendering;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::native_host::user_code::UserCodeHost;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::IntoPyObjectExt;

/// Build the declaration scope of `discovered`; a static scope lends only its index to macros.
fn declaration_scope<'py>(
    discovered: &Bound<'py, PyAny>,
    static_scope: Bound<'py, PyAny>,
    sql_lexical_syntax: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let loaded_macros: Bound<'py, PyAny> = host::entry(py, UserCodeHost::LoadProjectMacros)?
        .call1((discovered.getattr("macro_files")?,))?;
    if !static_scope.is_none() {
        let rebound: Bound<'py, PyAny> =
            rebind_declaration_scope(&static_scope, &discovered.clone(), &loaded_macros.clone())
                .and_then(|value| value.into_bound_py_any(py))?;
        if !rebound.is_none() {
            return Ok(rebound);
        }
    }
    call_with(
        &registry::native(py, NativeAttr::BuildDeclarationScope)?,
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
    let context: Bound<'py, PyAny> = registry::class(py, RecordId::DeclarationResolutionContext)?;
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
            &registry::native(py, NativeAttr::DiscoverProjectInputs)?,
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
    let effective_vars: Bound<'py, PyAny> = build_effective_vars(
        &project_config.clone(),
        &local_config.clone(),
        &py.None().into_bound(py),
        &cli_vars,
    )
    .and_then(|value| value.into_bound_py_any(py))?;
    let mut scope: Bound<'py, PyAny> = arguments.value("declaration_scope")?;
    if scope.is_none() {
        scope = declaration_scope(
            &discovered,
            arguments.value("static_declaration_scope")?,
            value_renderer.getattr("sql_lexical_syntax")?,
        )?;
    }
    let (enums, constants): (Bound<'py, PyAny>, Bound<'py, PyAny>) =
        registry::native(py, NativeAttr::PublicDeclarationIndexes)?
            .call1((&discovered,))?
            .extract()?;
    let collection_rendering: Bound<'py, PyAny> =
        resolve_effective_collection_rendering(&project_config.clone(), &py.None().into_bound(py))
            .and_then(|value| value.into_bound_py_any(py))?;
    let macro_context: Bound<'py, PyAny> = call_with(
        &registry::class(py, RecordId::MacroContext)?,
        &[
            (
                "adapter_name",
                resolve_effective_adapter_name(&project_config.clone(), &local_config)
                    .and_then(|value| value.into_bound_py_any(py))?,
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
        &registry::class(py, RecordId::SqlExpansionContext)?,
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
