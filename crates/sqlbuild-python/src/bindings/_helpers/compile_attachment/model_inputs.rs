//! Every discovered model file attached as a model input by the native model loop.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyCFunction, PyDict, PyDictMethods, PyFrozenSet, PyList, PyString, PyTuple};
use sqlbuild_analysis::assembly::project::main::sql_analysis_opt_out_help::sql_analysis_opt_out_help;

use crate::bindings::_helpers::attachments::cursor_intrinsics::reserved_cursor_markers;
use crate::bindings::_helpers::compile_attachment::model_config::native_model_config_session;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::compiled_project::loop_classes::model_loop_classes;
use crate::bindings::_helpers::render::declaration_values::constant_declaration_sql;
use crate::bindings::_helpers::render::macro_expansion_result::macro_expansion_classes;

const NATIVE_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const COMPILE_ERRORS_MODULE: &str = "sqlbuild.compiler.compile.exceptions";
const COMPILE_CONSTANTS_MODULE: &str = "sqlbuild.compiler.compile.constants";
const DISCOVERY_MODELS_MODULE: &str = "sqlbuild.compiler.discovery.models";
const DISCOVERY_CONSTANTS_MODULE: &str = "sqlbuild.compiler.discovery.constants";
const SCOPE_MODELS_MODULE: &str = "sqlbuild.compiler.scopes.models";
const SCOPE_TYPES_MODULE: &str = "sqlbuild.compiler.scopes.types";
const COLLECTOR_MODULE: &str = "sqlbuild.compiler.compile._helpers.diagnostics.collector";
const UNICODE_ENVIRONMENT_MODULE: &str = "sqlbuild.compiler.compile.classes.unicode_environment";
const PROJECT_VARS_MODULE: &str = "sqlbuild._native";
const MACRO_BRIDGE_MODULE: &str = "sqlbuild.compiler.macro_bridge.main.active_macro_bridge";
const CONTRACT_CLASSES_MODULE: &str =
    "sqlbuild.compiler.model_config.main._native_contract_classes";
const SQL_ANALYSIS_MODELS_MODULE: &str = "sqlbuild.compiler.sql_analysis.models";
const PYTHON_NODE_MODELS_MODULE: &str = "sqlbuild.python_nodes.models";

fn dict<'py>(
    py: Python<'py>,
    entries: Vec<(&str, Bound<'py, PyAny>)>,
) -> PyResult<Bound<'py, PyDict>> {
    let built: Bound<'py, PyDict> = PyDict::new(py);
    for (key, value) in entries {
        built.set_item(key, value)?;
    }
    Ok(built)
}

/// The parser opt-out help as a Python string.
fn opt_out_help(py: Python<'_>, model_owned: bool) -> PyResult<Bound<'_, PyAny>> {
    Ok(PyString::new(py, &sql_analysis_opt_out_help(model_owned)).into_any())
}

/// The host the loop calls back into: `constant_text(*, declaration, file_path)`.
fn loop_host<'py>(context: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = context.py();
    let context: Py<PyAny> = context.clone().unbind();
    let constant_text = move |arguments: &Bound<'_, PyTuple>,
                              keywords: Option<&Bound<'_, PyDict>>|
          -> PyResult<Py<PyAny>> {
        let py: Python<'_> = arguments.py();
        let context: &Bound<'_, PyAny> = context.bind(py);
        let passed: Bound<'_, PyDict> =
            keywords.map_or_else(|| PyDict::new(py), |keywords| keywords.clone());
        let file_path: Bound<'_, PyAny> = passed.as_any().get_item("file_path")?;
        let rendered: String = constant_declaration_sql(
            &passed.as_any().get_item("declaration")?,
            &context.getattr("value_renderer")?,
            (&context.getattr("collection_rendering")?, Some(&file_path)),
        )?;
        Ok(PyString::new(py, &rendered).into_any().unbind())
    };
    let keywords: Bound<'py, PyDict> = PyDict::new(py);
    keywords.set_item(
        "constant_text",
        PyCFunction::new_closure(py, None, None, constant_text)?,
    )?;
    imported(py, "types", "SimpleNamespace")?.call((), Some(&keywords))
}

fn macro_inputs<'py>(context: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = context.py();
    dict(
        py,
        vec![
            ("loaded_macros", context.getattr("loaded_macros")?),
            ("macro_context", context.getattr("macro_context")?),
            (
                "bridge",
                imported(py, MACRO_BRIDGE_MODULE, "active_macro_bridge")?.call0()?,
            ),
            (
                "scoped",
                pyo3::types::PyBool::new(py, !context.getattr("declaration_resolver")?.is_none())
                    .to_owned()
                    .into_any(),
            ),
            (
                "declaration_context",
                imported(py, COMPILE_MODELS_MODULE, "DeclarationResolutionContext")?,
            ),
            (
                "macro_argument_error",
                imported(py, COMPILE_ERRORS_MODULE, "MacroArgumentError")?,
            ),
            ("expansion", macro_expansion_classes(py)?.into_any()),
            (
                "generic_syntax",
                imported(py, SQL_ANALYSIS_MODELS_MODULE, "SqlLexicalSyntax")?
                    .call0()?
                    .getattr("native_mapping")?,
            ),
        ],
    )
}

fn sql_hook_inputs<'py>(
    discovered: &Bound<'py, PyAny>,
    context: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = context.py();
    dict(
        py,
        vec![
            (
                "named_sql_hook_entry",
                imported(py, DISCOVERY_MODELS_MODULE, "NamedSqlHookEntry")?,
            ),
            (
                "python_hook_entry",
                imported(py, DISCOVERY_MODELS_MODULE, "PythonHookEntry")?,
            ),
            ("hook_files", discovered.getattr("sql_hook_files")?),
            ("effective_vars", context.getattr("effective_vars")?),
            (
                "environment",
                imported(py, UNICODE_ENVIRONMENT_MODULE, "UnicodeEnvironment")?.call0()?,
            ),
            (
                "render_project_var",
                imported(py, PROJECT_VARS_MODULE, "render_project_var_text")?,
            ),
            (
                "sql_resource_ref",
                imported(py, PYTHON_NODE_MODELS_MODULE, "SqlResourceRef")?,
            ),
            (
                "explicit_kinds",
                imported(py, COMPILE_CONSTANTS_MODULE, "EXPLICIT_REFERENCE_KINDS")?,
            ),
            (
                "declaration_identity",
                imported(py, SCOPE_MODELS_MODULE, "DeclarationIdentity")?,
            ),
            (
                "sql_hook_kind",
                imported(py, SCOPE_TYPES_MODULE, "DeclarationKind")?.getattr("SQL_HOOK")?,
            ),
        ],
    )
}

/// Attach schema metadata to discovered model files.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn build_model_inputs<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_model_inputs",
        options,
        (
            &["discovered_inputs", "context", "native_project"],
            &[
                "no_sql_validation",
                "defer_model_sql_validation",
                "external_sql_reference_resolver",
            ],
        ),
    )?;
    let discovered_inputs: &Bound<'py, PyAny> = &arguments.value("discovered_inputs")?;
    let context: &Bound<'py, PyAny> = &arguments.value("context")?;
    let native_project: &Bound<'py, PyAny> = &arguments.value("native_project")?;
    let no_sql_validation: bool = arguments.flag("no_sql_validation")?;
    let defer_model_sql_validation: bool = arguments.flag("defer_model_sql_validation")?;
    let external: Bound<'py, PyAny> = arguments.value("external_sql_reference_resolver")?;
    let settings: Bound<'py, PyAny> = context.getattr("effective_settings")?;
    let validator: Bound<'py, PyAny> = imported(py, NATIVE_MODULE, "NativeModelValidator")?
        .call_method1(
            "from_inputs",
            (
                discovered_inputs,
                settings.getattr("microbatch_concurrency")?,
            ),
        )?;
    if !external.is_none() {
        call_with(
            &external.getattr("validate_model_names")?,
            &[("known_model_names", validator.call_method0("model_names")?)],
        )?;
    }
    let project_dir: Bound<'py, PyAny> = discovered_inputs.getattr("project_dir")?;
    let root: Bound<'py, PyAny> = if project_dir.is_truthy()? {
        project_dir
    } else {
        imported(py, "pathlib", "Path")?.call0()?
    };
    let project_config_path: Bound<'py, PyAny> = root.div(imported(
        py,
        DISCOVERY_CONSTANTS_MODULE,
        "PROJECT_CONFIG_FILENAME",
    )?)?;
    let config_inputs: Bound<'py, PyAny> = call_with(
        &imported(py, COMPILE_MODELS_MODULE, "NativeModelConfigInputs")?,
        &[
            (
                "project_config",
                discovered_inputs.getattr("project_config")?,
            ),
            ("target_config", context.getattr("target_config")?),
            ("effective_vars", context.getattr("effective_vars")?),
            (
                "effective_target_name",
                context.getattr("effective_target_name")?,
            ),
            ("run_id", context.getattr("run_id")?),
            (
                "microbatch_concurrency",
                settings.getattr("microbatch_concurrency")?,
            ),
        ],
    )?;
    let session: Bound<'py, PyAny> = native_model_config_session(&config_inputs, &validator)?;
    let provider_names: Vec<Bound<'py, PyAny>> = discovered_inputs
        .getattr("providers")?
        .try_iter()?
        .map(|provider| provider?.getattr("name"))
        .collect::<PyResult<_>>()?;
    let host_inputs: Bound<'py, PyDict> = dict(
        py,
        vec![
            (
                "report_diagnostic",
                imported(py, COLLECTOR_MODULE, "report_compile_diagnostic")?,
            ),
            (
                "record_template_reads",
                imported(py, NATIVE_MODULE, "record_template_reads")?,
            ),
            (
                "visible_declarations",
                imported(py, COMPILE_MODELS_MODULE, "VisibleModelDeclarations")?,
            ),
            ("config_session", session),
            ("syntax_help", opt_out_help(py, true)?),
            ("source_syntax_help", opt_out_help(py, false)?),
            ("macros", macro_inputs(context)?.into_any()),
            (
                "sql_hooks",
                sql_hook_inputs(discovered_inputs, context)?.into_any(),
            ),
            (
                "hook_functions",
                discovered_inputs.getattr("hook_functions")?,
            ),
            (
                "provider_names",
                PyFrozenSet::new(py, &provider_names)?.into_any(),
            ),
        ],
    )?;
    let classes: Bound<'py, PyDict> = model_loop_classes(
        &discovered_inputs.getattr("audit_factories")?,
        context,
        &external,
        &host_inputs,
    )?;
    let syntax: Bound<'py, PyAny> = context.getattr("sql_lexical_syntax")?;
    let native_loop: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "NativeModelLoop")?.call1((
            (
                validator,
                imported(py, CONTRACT_CLASSES_MODULE, "native_contract_classes")?.call0()?,
                classes,
            ),
            syntax.getattr("native_mapping")?,
            reserved_cursor_markers(),
            (
                (
                    settings.getattr("sql_analysis")?,
                    no_sql_validation,
                    defer_model_sql_validation,
                    settings.getattr("require_sql_analysis")?,
                ),
                project_config_path.str()?,
            ),
        ))?;
    let files: Bound<'py, PyList> = PyList::new(
        py,
        discovered_inputs
            .getattr("model_files")?
            .try_iter()?
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    let inputs: Bound<'py, PyAny> =
        native_loop.call_method1("run", (native_project, loop_host(context)?, files))?;
    PyTuple::new(py, inputs.try_iter()?.collect::<PyResult<Vec<_>>>()?)
}
