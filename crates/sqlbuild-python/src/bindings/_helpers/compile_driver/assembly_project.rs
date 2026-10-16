//! Compiled project assembly: the project's models, resources, checks and semantic diagnostics.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyString, PyStringMethods, PyTuple};

use sqlbuild_analysis::assembly::project::main::configured_namespace::configured_namespace;

use crate::bindings::_helpers::compile_driver::assembly::AssemblyRequest;
use crate::bindings::_helpers::compile_driver::assembly_analysis::{
    AnalysisContext, analysis_context, and_not,
};
use crate::bindings::_helpers::compile_driver::assembly_checks::compiled_sql_scenarios;
use crate::bindings::_helpers::compile_driver::assembly_facts::native_project_facts;
use crate::bindings::_helpers::compile_driver::assembly_models::{
    binding_rows, compiled_models, project_binding_diagnostics,
};
use crate::bindings::_helpers::compile_driver::assembly_sql_tests::assembled_sql_tests;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, keywords};
use crate::bindings::_helpers::compiled_project::compiled_model_view::NativeCompiledModel;
use crate::bindings::_helpers::contracts::spec_resolution::{
    resolve_effective_adapter_name, resolve_effective_scenario_config,
};
use crate::bindings::_helpers::model_config::template_data::early_model_templates;
use crate::bindings::_helpers::native_host::adapter::AdapterHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::scopes::scope_errors::report_scope_index_errors;
use crate::bindings::_helpers::scopes::scope_validation::scope_index_with_compile_usages;
use pyo3::IntoPyObjectExt;

const SOURCE_SLOT: &str = "source";
const SEED_SLOT: &str = "seed";
const AUDIT_SLOT: &str = "audit";

/// One native resource kind: its inputs, recorded facts, slot and the owner's methods.
struct ResourceKind<'a> {
    inputs: &'a str,
    facts: &'a str,
    slot: Option<&'a str>,
    record: &'a str,
    compiled: &'a str,
}

const SOURCES: ResourceKind<'static> = ResourceKind {
    inputs: "source_inputs",
    facts: "source_namespaces",
    slot: Some(SOURCE_SLOT),
    record: "record_source_namespaces",
    compiled: "compiled_source",
};
const SEEDS: ResourceKind<'static> = ResourceKind {
    inputs: "seed_inputs",
    facts: "seed_namespaces",
    slot: Some(SEED_SLOT),
    record: "record_seed_namespaces",
    compiled: "compiled_seed",
};
const FUNCTIONS: ResourceKind<'static> = ResourceKind {
    inputs: "sql_function_inputs",
    facts: "function_deps",
    slot: None,
    record: "record_function_deps",
    compiled: "compiled_function",
};
const AUDITS: ResourceKind<'static> = ResourceKind {
    inputs: "audit_inputs",
    facts: "audit_scope_deps",
    slot: Some(AUDIT_SLOT),
    record: "record_audit_scope_deps",
    compiled: "compiled_audit",
};

/// Convert attached compile inputs into the planner-ready project view.
pub(crate) fn assembled_project<'py>(
    py: Python<'py>,
    request: &AssemblyRequest,
) -> PyResult<Bound<'py, PyAny>> {
    let inputs: &Bound<'py, PyAny> = request.inputs.bind(py);
    let names: &Bound<'py, PyAny> = request.analysis_model_names.bind(py);
    let context: AnalysisContext<'py> = analysis_context(py, request)?;
    let native_session: Bound<'py, PyAny> = context
        .analyses
        .as_ref()
        .and_then(|analyses| analyses.session.as_ref())
        .map_or_else(
            || py.None().into_bound(py),
            |session| session.clone().into_any(),
        );
    let native: Bound<'py, PyAny> = native_project_facts(inputs, &context, names, &native_session)?;
    let resources: Bound<'py, PyAny> = native.getattr("resources")?;
    let scope_index: Bound<'py, PyAny> = scope_index_with_compile_usages(inputs)?;
    report_scope_index_errors(&scope_index)?;
    let target_values: Bound<'py, PyAny> = effective_target_values(inputs)?;
    let models: Bound<'py, PyTuple> =
        compiled_models(inputs, &context, (&native.getattr("models")?, names))?;
    let fields: Bound<'py, PyDict> = project_fields(
        inputs,
        &context,
        (&models, &resources, &scope_index),
        &target_values,
    )?;
    let project: Bound<'py, PyAny> = project_view(inputs, &fields, &models)?;
    let binding_results: Bound<'py, PyDict> = binding_rows(py, context.analyses.as_ref())?;
    call_with(
        &registry::native(py, NativeAttr::CompleteSemanticProject)?,
        &[
            ("project", project),
            ("profile", context.profile.clone()),
            (
                "resource_sql_analysis",
                and_not(
                    &context.sql_analysis_enabled,
                    &inputs.getattr("no_sql_validation")?,
                )?,
            ),
            ("session", native_session),
            ("binding_results", binding_results.into_any()),
        ],
    )
}

/// `value.strip()` when `value` is a string with non-blank text, else `None`.
fn str_or_none<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = value.py();
    if let Ok(text) = value.downcast::<PyString>()
        && let Some(stripped) = configured_namespace(&text.to_cow()?)
    {
        return Ok(PyString::new(py, &stripped).into_any());
    }
    Ok(py.None().into_bound(py))
}

/// The selected target's `field`, or `None` without a selected target.
fn target_field<'py>(inputs: &Bound<'py, PyAny>, field: &str) -> PyResult<Bound<'py, PyAny>> {
    let target: Bound<'py, PyAny> = inputs.getattr("effective_target")?;
    if target.is_none() {
        return Ok(target);
    }
    target.getattr(field)
}

/// The target database and schema, with connection fallbacks, resolved as early model templates.
fn effective_target_values<'py>(inputs: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = inputs.py();
    let connection: Bound<'py, PyAny> = inputs.getattr("effective_connection")?;
    let database: Bound<'py, PyAny> = target_field(inputs, "database")?;
    let database: Bound<'py, PyAny> = if database.is_truthy()? {
        database
    } else {
        connection_database_fallback(inputs, &connection)?
    };
    let schema: Bound<'py, PyAny> = target_field(inputs, "schema")?;
    let schema: Bound<'py, PyAny> = if schema.is_truthy()? {
        schema
    } else {
        str_or_none(&connection.call_method1("get", ("schema",))?)?
    };
    early_model_templates(
        keywords(py, &[("database", database), ("schema", schema)])?.as_any(),
        &inputs.getattr("effective_vars")?,
        (
            &inputs.getattr("effective_target_name")?,
            &inputs.getattr("run_id")?,
        ),
    )
}

/// The connection's database, except under DuckDB, whose database is a file.
fn connection_database_fallback<'py>(
    inputs: &Bound<'py, PyAny>,
    connection: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = inputs.py();
    let adapter_name: Bound<'py, PyAny> = resolve_effective_adapter_name(
        &inputs.getattr("project_config")?,
        &inputs.getattr("local_config")?,
    )
    .and_then(|value| value.into_bound_py_any(py))?;
    if adapter_name.eq(host::entry(py, AdapterHost::BuiltinAdapter)?.getattr("DUCKDB")?)? {
        return Ok(py.None().into_bound(py));
    }
    str_or_none(&connection.call_method1("get", ("database",))?)
}

/// The compiled project's fields, in the order Python's assembly built them.
fn project_fields<'py>(
    inputs: &Bound<'py, PyAny>,
    context: &AnalysisContext<'py>,
    (models, resources, scope_index): (
        &Bound<'py, PyTuple>,
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
    ),
    target_values: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = inputs.py();
    let discovered: Bound<'py, PyAny> = inputs.getattr("discovered_inputs")?;
    let project_config: Bound<'py, PyAny> = inputs.getattr("project_config")?;
    let fields: Bound<'py, PyDict> = keywords(
        py,
        &[
            (
                "binding_catalog",
                context.profile.getattr("binding_catalog")?,
            ),
            ("run_id", inputs.getattr("run_id")?),
            (
                "effective_target_name",
                inputs.getattr("effective_target_name")?,
            ),
            (
                "effective_connection",
                inputs.getattr("effective_connection")?,
            ),
            ("effective_vars", inputs.getattr("effective_vars")?),
            (
                "effective_target_database",
                str_or_none(&target_values.call_method1("get", ("database",))?)?,
            ),
            (
                "effective_target_schema",
                str_or_none(&target_values.call_method1("get", ("schema",))?)?,
            ),
            (
                "sql_analysis_dialect",
                context.profile.getattr("sql_analysis_dialect")?,
            ),
            ("sql_lexical_syntax", inputs.getattr("sql_lexical_syntax")?),
            ("compile_cache_dir", inputs.getattr("compile_cache_dir")?),
            ("settings", inputs.getattr("effective_settings")?),
            (
                "scenario",
                resolve_effective_scenario_config(
                    &project_config,
                    &inputs.getattr("local_config")?,
                )?,
            ),
            ("models", models.clone().into_any()),
        ],
    )?;
    for (name, kind) in [
        ("sources", &SOURCES),
        ("seeds", &SEEDS),
        ("functions", &FUNCTIONS),
        ("audits", &AUDITS),
    ] {
        fields.set_item(name, compiled_resources(inputs, resources, kind)?)?;
    }
    fields.set_item("sql_tests", assembled_sql_tests(inputs)?)?;
    fields.set_item("sql_scenarios", compiled_sql_scenarios(inputs)?)?;
    for name in ["loader_functions", "hook_functions"] {
        fields.set_item(name, discovered.getattr(name)?)?;
    }
    fields.set_item(
        "enforce_explicit_references",
        project_config
            .getattr("references")?
            .getattr("enforce_explicit")?,
    )?;
    for name in ["sql_hook_files", "materialization_files"] {
        fields.set_item(name, discovered.getattr(name)?)?;
    }
    for name in ["public_enums", "public_constants", "loaded_macros"] {
        fields.set_item(name, inputs.getattr(name)?)?;
    }
    let mut diagnostics: Vec<Bound<'py, PyAny>> = inputs
        .getattr("diagnostics")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    diagnostics.extend(project_binding_diagnostics(
        models,
        context.analyses.as_ref(),
    )?);
    fields.set_item("diagnostics", PyTuple::new(py, diagnostics)?)?;
    fields.set_item(
        "external_sql_reference_resolver",
        inputs.getattr("external_sql_reference_resolver")?,
    )?;
    fields.set_item("scope_index", scope_index)?;
    Ok(fields)
}

/// Each resource's view over the compile's native project, raising assembly's error there.
fn compiled_resources<'py>(
    inputs: &Bound<'py, PyAny>,
    resources: &Bound<'py, PyAny>,
    kind: &ResourceKind<'_>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = inputs.py();
    let count: usize = inputs.getattr(kind.inputs)?.len()?;
    if count == 0 {
        return Ok(PyTuple::empty(py));
    }
    let owner: Bound<'py, PyAny> = inputs.getattr("native_project")?;
    let facts: Bound<'py, PyAny> = resources.getattr(kind.facts)?;
    owner.call_method1(
        kind.record,
        (PyList::new(
            py,
            facts.try_iter()?.collect::<PyResult<Vec<_>>>()?,
        )?,),
    )?;
    let mut compiled: Vec<Bound<'py, PyAny>> = Vec::with_capacity(count);
    for index in 0..count {
        if let Some(slot) = kind.slot {
            native_resource(resources, (slot, &facts), index)?;
        }
        compiled.push(owner.call_method1(kind.compiled, (index,))?);
    }
    PyTuple::new(py, compiled)
}

/// Resource `index` of `slot`, raising the error Python's assembly raises there.
fn native_resource<'py>(
    resources: &Bound<'py, PyAny>,
    (slot, items): (&str, &Bound<'py, PyAny>),
    index: usize,
) -> PyResult<Bound<'py, PyAny>> {
    let failure: Bound<'py, PyAny> = resources.getattr("failure")?;
    if !failure.is_none()
        && failure.getattr("slot")?.eq(slot)?
        && failure.getattr("index")?.eq(index)?
    {
        return Err(PyErr::from_value(failure.getattr("error")?));
    }
    items.get_item(index)
}

/// The native owner's project view when it holds every model; else a `CompiledProject`.
fn project_view<'py>(
    inputs: &Bound<'py, PyAny>,
    fields: &Bound<'py, PyDict>,
    models: &Bound<'py, PyTuple>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = inputs.py();
    let owner: Bound<'py, PyAny> = inputs.getattr("native_project")?;
    let mut all_native: bool = true;
    for model in models.as_any().try_iter()? {
        if !model?.is_instance_of::<NativeCompiledModel>() {
            all_native = false;
            break;
        }
    }
    if !owner.is_none() && all_native {
        let view_fields: Bound<'py, PyDict> = fields.copy()?;
        view_fields.set_item("unmatched_literal_sql_relations", PyTuple::empty(py))?;
        view_fields.set_item("native_session", py.None())?;
        return owner.call_method1("project_view", (view_fields,));
    }
    let sql_expansions: Bound<'py, PyDict> = PyDict::new(py);
    for model_input in inputs.getattr("model_inputs")?.try_iter()? {
        let model_input: Bound<'py, PyAny> = model_input?;
        let expansion: Bound<'py, PyAny> = model_input.getattr("sql_expansion")?;
        if !expansion.is_none() {
            sql_expansions.set_item(
                model_input.getattr("model_file")?.getattr("file_path")?,
                expansion,
            )?;
        }
    }
    let arguments: Bound<'py, PyDict> = fields.copy()?;
    arguments.set_item("sql_expansions", sql_expansions)?;
    registry::class(py, RecordId::CompiledProject)?.call((), Some(&arguments))
}
