//! The first attached compile input snapshot: target, vars, macros, scopes, models and resources.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, keywords, within,
};
use crate::bindings::_helpers::model_config::template_data::run_id;

const CALL_STORE_MODULE: &str = "sqlbuild.compiler.compile._helpers.macro_bridge.call_store";
const ATTACHMENT_MODULE: &str = "sqlbuild._native";
const DECLARATION_SCOPE_MODULE: &str = "sqlbuild._native";
const COLLECTOR_MODULE: &str = "sqlbuild._native";
const MACROS_MODULE: &str = "sqlbuild.compiler.compile._helpers.render.user_macros";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const ATTACH_CHECKS_MODULE: &str = "sqlbuild._native";
const ATTACH_RESOURCES_MODULE: &str = "sqlbuild._native";
const INPUTS_VIEW_MODULE: &str = "sqlbuild._native";
const INPUTS_WITH_MODULE: &str = "sqlbuild._native";
const ADAPTER_NAME_MODULE: &str = "sqlbuild._native";
const NATIVE_MODULE: &str = "sqlbuild._native";

const REQUIRED: [&str; 2] = ["discovered_inputs", "adapter_context"];
const OPTIONAL: [&str; 8] = [
    "selected_target",
    "cli_vars",
    "run_id",
    "no_sql_validation",
    "defer_model_sql_validation",
    "external_sql_reference_resolver",
    "resolved_connection",
    "no_cache",
];

/// The effective target, vars, settings and macro context every later stage shares.
struct TargetContext<'py> {
    target_name: Bound<'py, PyAny>,
    target: Bound<'py, PyAny>,
    compile_cache_dir: Bound<'py, PyAny>,
    vars: Bound<'py, PyAny>,
    settings: Bound<'py, PyAny>,
    macro_context: Bound<'py, PyAny>,
}

/// The attached models with the native project that owns them and their declarations.
struct ModelBuild<'py> {
    inputs: Bound<'py, PyAny>,
    native_project: Bound<'py, PyAny>,
    enums: Bound<'py, PyAny>,
    constants: Bound<'py, PyAny>,
    context: Bound<'py, PyAny>,
}

/// Seeds, functions and sources, and `(tests, scenarios, audits, diagnostics)` as attached.
struct AttachedResources<'py> {
    seeds: Bound<'py, PyAny>,
    functions: Bound<'py, PyAny>,
    sources: Bound<'py, PyAny>,
    checks: Bound<'py, PyAny>,
}

/// Attach discovered metadata into the first compile input snapshot.
#[pyfunction]
#[pyo3(signature = (**options))]
fn build_compile_inputs<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> =
        KeywordArguments::read(py, "build_compile_inputs", options, (&REQUIRED, &OPTIONAL))?;
    let collector: Bound<'py, PyAny> =
        imported(py, COLLECTOR_MODULE, "collect_compile_diagnostics")?.call0()?;
    let (built, violations): (Bound<'py, PyAny>, Bound<'py, PyAny>) =
        within(&collector, |violations| {
            Ok((compile_inputs(py, &arguments)?, violations.clone()))
        })?;
    let collected: Bound<'py, PyAny> = violations.getattr("diagnostics")?;
    if !collected.is_truthy()? {
        return Ok(built);
    }
    let diagnostics: Bound<'py, PyTuple> = PyTuple::new(
        py,
        built
            .getattr("diagnostics")?
            .try_iter()?
            .chain(collected.try_iter()?)
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    call_with(
        &imported(py, INPUTS_WITH_MODULE, "inputs_with")?,
        &[("inputs", built), ("diagnostics", diagnostics.into_any())],
    )
}

/// The undecorated `build_compile_inputs`.
fn compile_inputs<'py>(
    py: Python<'py>,
    arguments: &KeywordArguments<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let discovered: Bound<'py, PyAny> = arguments.value("discovered_inputs")?;
    let adapter_context: Bound<'py, PyAny> = arguments.value("adapter_context")?;
    let target: TargetContext<'py> = target_context(arguments, &discovered, &adapter_context)?;
    let run_id: Bound<'py, PyAny> = run_id(&arguments.value("run_id")?)?;
    let loaded_macros: Bound<'py, PyAny> = imported(py, MACROS_MODULE, "load_project_macros")?
        .call1((discovered.getattr("macro_files")?,))?;
    let syntax: Bound<'py, PyAny> = adapter_context.getattr("sql_lexical_syntax")?;
    let declaration_scope: Bound<'py, PyAny> = call_with(
        &imported(py, DECLARATION_SCOPE_MODULE, "build_declaration_scope")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("loaded_macros", loaded_macros),
            ("sql_lexical_syntax", syntax.clone()),
            ("compile_cache_dir", target.compile_cache_dir.clone()),
        ],
    )?;
    let value_renderer: Bound<'py, PyAny> = adapter_context.getattr("value_renderer")?;
    let model_context: Bound<'py, PyAny> = call_with(
        &imported(py, COMPILE_MODELS_MODULE, "ModelInputBuildContext")?,
        &[
            ("effective_vars", target.vars.clone()),
            ("effective_settings", target.settings.clone()),
            ("target_config", target.target.clone()),
            ("effective_target_name", target.target_name.clone()),
            ("run_id", run_id.clone()),
            ("macro_context", target.macro_context.clone()),
            ("loaded_macros", declaration_scope.getattr("loaded_macros")?),
            ("value_renderer", value_renderer.clone()),
            (
                "collection_rendering",
                adapter_context.getattr("collection_rendering")?,
            ),
            ("sql_lexical_syntax", syntax.clone()),
            (
                "declaration_resolver",
                declaration_scope.getattr("resolver")?,
            ),
        ],
    )?;
    let models: ModelBuild<'py> = model_build(arguments, &discovered, &model_context)?;
    let attached: AttachedResources<'py> = attached_resources(
        arguments,
        &adapter_context,
        (&discovered, &declaration_scope),
        &models,
    )?;
    let fields: Bound<'py, PyDict> = keywords(
        py,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
            ("discovered_inputs", discovered.clone()),
            ("sql_lexical_syntax", syntax),
            ("run_id", run_id),
            ("effective_target_name", target.target_name.clone()),
            ("effective_target", target.target.clone()),
            ("compile_cache_dir", target.compile_cache_dir.clone()),
            (
                "effective_connection",
                effective_connection(arguments, &discovered, &target)?,
            ),
            ("effective_settings", target.settings.clone()),
            (
                "no_sql_validation",
                arguments.value_or_false("no_sql_validation")?,
            ),
            ("effective_vars", target.vars.clone()),
            ("macro_context", target.macro_context.clone()),
            ("loaded_macros", declaration_scope.getattr("loaded_macros")?),
            ("public_enums", models.enums.clone()),
            ("public_constants", models.constants.clone()),
            ("model_inputs", models.inputs.clone()),
            ("seed_inputs", attached.seeds),
            ("source_inputs", attached.sources),
            ("sql_function_inputs", attached.functions),
            ("test_inputs", attached.checks.get_item(0)?),
            ("scenario_inputs", attached.checks.get_item(1)?),
            ("audit_inputs", attached.checks.get_item(2)?),
            ("diagnostics", attached.checks.get_item(3)?),
            (
                "external_sql_reference_resolver",
                arguments.value("external_sql_reference_resolver")?,
            ),
            ("scope_index", declaration_scope.getattr("index")?),
            ("declaration_scope", declaration_scope),
        ],
    )?;
    call_with(
        &imported(py, INPUTS_VIEW_MODULE, "compile_inputs_view")?,
        &[
            ("fields", fields.into_any()),
            ("native_project", models.native_project),
        ],
    )
}

/// The selected target with the macro call store, and the effective vars, settings and macro context.
fn target_context<'py>(
    arguments: &KeywordArguments<'py>,
    discovered: &Bound<'py, PyAny>,
    adapter_context: &Bound<'py, PyAny>,
) -> PyResult<TargetContext<'py>> {
    let py: Python<'py> = discovered.py();
    let selected: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            CALL_STORE_MODULE,
            "target_context_with_macro_call_store",
        )?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("selected_target", arguments.value("selected_target")?),
            ("no_cache", arguments.value_or_false("no_cache")?),
        ],
    )?;
    let target_name: Bound<'py, PyAny> = selected.get_item(0)?;
    let target: Bound<'py, PyAny> = selected.get_item(1)?;
    let project_config: Bound<'py, PyAny> = discovered.getattr("project_config")?;
    let local_config: Bound<'py, PyAny> = discovered.getattr("local_config")?;
    let cli_vars: Bound<'py, PyAny> = arguments.value("cli_vars")?;
    let cli_vars: Bound<'py, PyAny> = if cli_vars.is_none() {
        PyDict::new(py).into_any()
    } else {
        cli_vars
    };
    let vars: Bound<'py, PyAny> = call_with(
        &imported(py, ATTACHMENT_MODULE, "build_effective_vars")?,
        &[
            ("project_config", project_config.clone()),
            ("local_config", local_config.clone()),
            ("target_config", target.clone()),
            ("cli_vars", cli_vars),
        ],
    )?;
    let settings: Bound<'py, PyAny> = call_with(
        &imported(py, ATTACHMENT_MODULE, "build_effective_settings")?,
        &[
            ("project_config", project_config.clone()),
            ("local_config", local_config.clone()),
        ],
    )?;
    let adapter_name: Bound<'py, PyAny> = call_with(
        &imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", project_config.clone()),
            ("local_config", local_config),
        ],
    )?;
    let macro_context: Bound<'py, PyAny> = call_with(
        &imported(py, COMPILE_MODELS_MODULE, "MacroContext")?,
        &[
            ("adapter_name", adapter_name),
            ("sql_analysis_enabled", settings.getattr("sql_analysis")?),
            ("target_name", target_name.clone()),
            ("vars", vars.clone()),
            (
                "_value_renderer",
                adapter_context.getattr("value_renderer")?,
            ),
            (
                "_collection_rendering",
                adapter_context.getattr("collection_rendering")?,
            ),
            (
                "_enforce_explicit_references",
                project_config
                    .getattr("references")?
                    .getattr("enforce_explicit")?,
            ),
        ],
    )?;
    Ok(TargetContext {
        target_name,
        target,
        compile_cache_dir: selected.get_item(2)?,
        vars,
        settings,
        macro_context,
    })
}

/// `_build_models_with_declarations`: attach every model with the public declaration indexes.
fn model_build<'py>(
    arguments: &KeywordArguments<'py>,
    discovered: &Bound<'py, PyAny>,
    context: &Bound<'py, PyAny>,
) -> PyResult<ModelBuild<'py>> {
    let py: Python<'py> = discovered.py();
    let native: Bound<'py, PyModule> = py.import(NATIVE_MODULE)?;
    let declarations: Bound<'py, PyAny> = native
        .getattr("public_declaration_indexes")?
        .call1((discovered,))?;
    let enums: Bound<'py, PyAny> = declarations.get_item(0)?;
    let constants: Bound<'py, PyAny> = declarations.get_item(1)?;
    let schemas: Bound<'py, PyAny> = native
        .getattr("public_model_schema_index")?
        .call1((discovered,))?;
    let native_project: Bound<'py, PyAny> = native.getattr("NativeCompiledProject")?.call0()?;
    let replace: Bound<'py, PyAny> = imported(py, "dataclasses", "replace")?;
    let model_context: Bound<'py, PyAny> = replace.call(
        (context,),
        Some(&keywords(
            py,
            &[
                ("public_enums", enums.clone()),
                ("public_constants", constants.clone()),
                ("public_model_schemas", schemas),
            ],
        )?),
    )?;
    let inputs: Bound<'py, PyAny> = call_with(
        &imported(py, ATTACHMENT_MODULE, "build_model_inputs")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("context", model_context),
            (
                "no_sql_validation",
                arguments.value_or_false("no_sql_validation")?,
            ),
            (
                "defer_model_sql_validation",
                arguments.value_or_false("defer_model_sql_validation")?,
            ),
            (
                "external_sql_reference_resolver",
                arguments.value("external_sql_reference_resolver")?,
            ),
            ("native_project", native_project.clone()),
        ],
    )?;
    let context: Bound<'py, PyAny> = replace.call(
        (context,),
        Some(&keywords(
            py,
            &[
                ("public_enums", enums.clone()),
                ("public_constants", constants.clone()),
            ],
        )?),
    )?;
    Ok(ModelBuild {
        inputs,
        native_project,
        enums,
        constants,
        context,
    })
}

/// The seeds, functions, sources and checks attached to the models.
fn attached_resources<'py>(
    arguments: &KeywordArguments<'py>,
    adapter_context: &Bound<'py, PyAny>,
    (discovered, declaration_scope): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    models: &ModelBuild<'py>,
) -> PyResult<AttachedResources<'py>> {
    let py: Python<'py> = discovered.py();
    let context: &Bound<'py, PyAny> = &models.context;
    let settings: Bound<'py, PyAny> = context.getattr("effective_settings")?;
    let resources: Bound<'py, PyAny> = call_with(
        &imported(py, ATTACH_RESOURCES_MODULE, "attach_resources")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("native_project", models.native_project.clone()),
            (
                "settings",
                PyTuple::new(
                    py,
                    [
                        settings.clone(),
                        context.getattr("target_config")?,
                        context.getattr("macro_context")?.getattr("adapter_name")?,
                    ],
                )?
                .into_any(),
            ),
            (
                "no_sql_validation",
                arguments.value_or_false("no_sql_validation")?,
            ),
            (
                "python_functions_inherit_default_namespace",
                adapter_context.getattr("python_functions_inherit_default_namespace")?,
            ),
        ],
    )?;
    let sources: Bound<'py, PyAny> = resources.get_item(2)?;
    let checks: Bound<'py, PyAny> = call_with(
        &imported(py, ATTACH_CHECKS_MODULE, "attach_checks")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("native_project", models.native_project.clone()),
            (
                "settings",
                PyTuple::new(
                    py,
                    [
                        settings,
                        adapter_context.getattr("value_renderer")?,
                        context.getattr("sql_lexical_syntax")?,
                    ],
                )?
                .into_any(),
            ),
            ("scan_cache", declaration_scope.getattr("sql_test_scans")?),
            ("source_inputs", sources.clone()),
        ],
    )?;
    Ok(AttachedResources {
        seeds: resources.get_item(0)?,
        functions: resources.get_item(1)?,
        sources,
        checks,
    })
}

/// The resolved connection when given, otherwise the configured one for the target.
fn effective_connection<'py>(
    arguments: &KeywordArguments<'py>,
    discovered: &Bound<'py, PyAny>,
    target: &TargetContext<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let resolved: Bound<'py, PyAny> = arguments.value("resolved_connection")?;
    if !resolved.is_none() {
        return Ok(resolved);
    }
    call_with(
        &imported(
            discovered.py(),
            ATTACHMENT_MODULE,
            "build_effective_connection",
        )?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
            ("target_config", target.target.clone()),
            ("effective_vars", target.vars.clone()),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_compile_inputs, module)?)
}
