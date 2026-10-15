//! Seeds, functions, sources, SQL tests, scenarios and audits attached from discovered inputs.

use crate::bindings::_helpers::compiler_records::shape_classes::shape_class_at;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyCFunction, PyDict, PyDictMethods, PyTuple};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use std::collections::HashMap;

use sqlbuild_attachments::audits::constants::BUILTIN_AUDITS;

use crate::bindings::_helpers::compile_driver::compile_timings::record_compile_timing;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::compiled_project::audit_loop::{AuditBlockRow, AuditFileRow};
use crate::bindings::_helpers::compiled_project::function_loop::FunctionRow;
use crate::bindings::_helpers::compiled_project::project::NativeCompiledProject;
use crate::bindings::_helpers::compiled_project::resource_diagnostics::{
    DiagnosticSettings, LoaderRow, resource_diagnostics,
};
use crate::bindings::_helpers::compiled_project::scenario_loop::ScenarioRow;
use crate::bindings::_helpers::compiled_project::source_loop::SourceRow;
use crate::bindings::_helpers::compiled_project::sql_test_loop::{
    TestBlockRow, TestCaseRow, TestFileRow,
};
use crate::bindings::_helpers::sql_test_glue::constants::SQL_TEST_CTE_SCAN_ALGORITHM;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_RECORDS: &str = "sqlbuild._native";
const COMPILE_ERRORS_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
const SCOPE_TYPES_MODULE: &str = "sqlbuild._native";
const SCOPE_MODELS_MODULE: &str = "sqlbuild._native";
const AUDITING_TYPES_MODULE: &str = "sqlbuild.compiler.auditing.types";
const CONTRACT_MODELS_MODULE: &str = "sqlbuild._native";
const SQL_VALUE_ERRORS_MODULE: &str = "sqlbuild.sql_values.exceptions";
const YAML_FILE_SUFFIXES: [&str; 2] = [".yml", ".yaml"];
const PYTHON_RESOURCES_MODULE: &str =
    "sqlbuild.compiler.compile._helpers.diagnostics.python_resources";
const PATHLIB_MODULE: &str = "pathlib";
const TEST_TIMING_KEY: &str = "test_input_compile_ms";
const DESCRIPTION_KEY: &str = "description";
const MEASUREMENT_MODE: &str = "MEASUREMENT";

/// `getattr(value, name)` extracted.
fn attr<'py, T: pyo3::FromPyObject<'py>>(value: &Bound<'py, PyAny>, name: &str) -> PyResult<T> {
    value.getattr(name)?.extract()
}

/// `str(value.<name>)`.
fn text(value: &Bound<'_, PyAny>, name: &str) -> PyResult<String> {
    Ok(value.getattr(name)?.str()?.to_string())
}

/// `value.<path>.stem`.
fn stem(value: &Bound<'_, PyAny>, name: &str) -> PyResult<String> {
    attr(&value.getattr(name)?, "stem")
}

/// Each item of the iterable `value.<name>`.
fn items<'py>(value: &Bound<'py, PyAny>, name: &str) -> PyResult<Vec<Bound<'py, PyAny>>> {
    value.getattr(name)?.try_iter()?.collect()
}

fn enum_member<'py>(
    py: Python<'py>,
    (module, class, member): (&str, &str, &str),
) -> PyResult<Bound<'py, PyAny>> {
    imported(py, module, class)?.getattr(member)
}

/// `{member.value: member for member in enum_class}`.
fn by_value<'py>(py: Python<'py>, module: &str, class: &str) -> PyResult<Bound<'py, PyDict>> {
    let members: Bound<'py, PyDict> = PyDict::new(py);
    for member in imported(py, module, class)?.try_iter()? {
        let member: Bound<'py, PyAny> = member?;
        members.set_item(member.getattr("value")?, member)?;
    }
    Ok(members)
}

fn seed_declarations<'py>(discovered: &Bound<'py, PyAny>) -> PyResult<Vec<(Py<PyAny>, Py<PyAny>)>> {
    let mut declarations: Vec<(Py<PyAny>, Py<PyAny>)> = Vec::new();
    for schema_file in items(discovered, "schema_files")? {
        for entry in items(&schema_file, "seed_entries")? {
            declarations.push((entry.unbind(), schema_file.clone().unbind()));
        }
    }
    Ok(declarations)
}

/// The function rows of `field`; Python function files have no authored SQL contents.
fn function_rows(
    discovered: &Bound<'_, PyAny>,
    (field, body): (&str, &str),
    python: bool,
) -> PyResult<Vec<FunctionRow>> {
    items(discovered, field)?
        .into_iter()
        .map(|file| {
            Ok((
                text(&file, "file_path")?,
                text(&file, "relative_path")?,
                stem(&file, "file_path")?,
                file.clone().unbind(),
                attr(&file, "header_values")?,
                attr(&file, body)?,
                if python {
                    None
                } else {
                    Some(attr(&file, "contents")?)
                },
            ))
        })
        .collect()
}

/// `override if override is not None else fallback`.
fn either<'py>(
    defaults: &Bound<'py, PyAny>,
    (preferred, fallback): (&str, &str),
) -> PyResult<Option<String>> {
    let value: Bound<'py, PyAny> = defaults.getattr(preferred)?;
    if value.is_none() {
        return attr(defaults, fallback);
    }
    value.extract()
}

/// `(database, schema)` of a target config, or `None`.
fn target_namespace(
    target: &Bound<'_, PyAny>,
) -> PyResult<Option<(Option<String>, Option<String>)>> {
    if target.is_none() {
        return Ok(None);
    }
    Ok(Some((attr(target, "database")?, attr(target, "schema")?)))
}

/// Pair every seed, then attach every function and source, in that order.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn attach_resources<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "attach_resources",
        options,
        (
            &[
                "discovered_inputs",
                "native_project",
                "settings",
                "no_sql_validation",
                "python_functions_inherit_default_namespace",
            ],
            &[],
        ),
    )?;
    let discovered_inputs: &Bound<'py, PyAny> = &arguments.value("discovered_inputs")?;
    let native_project: &Bound<'py, NativeCompiledProject> =
        &arguments.value("native_project")?.downcast_into()?;
    let (effective_settings, target_config, adapter_name): (
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
        String,
    ) = arguments.value("settings")?.extract()?;
    let no_sql_validation: bool = arguments.flag("no_sql_validation")?;
    let python_functions_inherit_default_namespace: bool =
        arguments.flag("python_functions_inherit_default_namespace")?;
    let validate: bool = attr::<bool>(&effective_settings, "sql_analysis")? && !no_sql_validation;
    let seeds = NativeCompiledProject::attach_seeds(
        native_project,
        seed_declarations(discovered_inputs)?,
        items(discovered_inputs, "seed_files")?
            .into_iter()
            .map(Bound::unbind)
            .collect(),
        &imported(py, COMPILE_ERRORS_MODULE, "CompileInputError")?,
    )?;
    let defaults: Bound<'py, PyAny> = discovered_inputs
        .getattr("project_config")?
        .getattr("defaults")?;
    let function_kind: Bound<'py, PyAny> =
        enum_member(py, (SCOPE_TYPES_MODULE, "ResourceKind", "FUNCTION"))?;
    let functions = NativeCompiledProject::attach_functions(
        native_project,
        (
            function_rows(discovered_inputs, ("sql_function_files", "body_sql"), false)?,
            function_rows(
                discovered_inputs,
                ("python_function_files", "body_python"),
                true,
            )?,
        ),
        (
            adapter_name,
            validate,
            (
                either(&defaults, ("function_database", "database"))?,
                either(&defaults, ("function_schema", "schema"))?,
            ),
            target_namespace(&target_config)?,
            python_functions_inherit_default_namespace,
            function_kind.unbind(),
        ),
    )?;
    let mut source_rows: Vec<SourceRow> = Vec::new();
    for source_file in items(discovered_inputs, "source_files")? {
        let file_path: String = text(&source_file, "file_path")?;
        for entry in items(&source_file, "source_entries")? {
            source_rows.push((
                file_path.clone(),
                source_file.clone().unbind(),
                entry.unbind(),
            ));
        }
    }
    let sources = NativeCompiledProject::attach_sources(
        native_project,
        source_rows,
        (
            attr(&defaults, "contract")?,
            validate,
            enum_member(py, (SCOPE_TYPES_MODULE, "ResourceKind", "SOURCE"))?.unbind(),
        ),
    )?;
    PyTuple::new(
        py,
        [
            PyTuple::new(py, seeds)?.into_any(),
            PyTuple::new(py, functions)?.into_any(),
            PyTuple::new(py, sources)?.into_any(),
        ],
    )
}

fn test_case_row(case: Bound<'_, PyAny>) -> PyResult<TestCaseRow> {
    Ok((
        case.clone().unbind(),
        attr(&case, "name")?,
        items(&case, "values")?
            .into_iter()
            .map(|pair| pair.extract())
            .collect::<PyResult<_>>()?,
    ))
}

fn test_block_row(block: Bound<'_, PyAny>) -> PyResult<TestBlockRow> {
    Ok((
        block.clone().unbind(),
        attr(&block, "name")?,
        attr(&block, "sql_body")?,
        attr(&block.getattr("mode")?, "value")?,
        items(&block, "parameters")?
            .iter()
            .map(|parameter| attr(parameter, "name"))
            .collect::<PyResult<_>>()?,
        items(&block, "cases")?
            .into_iter()
            .map(test_case_row)
            .collect::<PyResult<_>>()?,
        attr(&block, "sql_body_span")?,
    ))
}

fn test_file_row(file: Bound<'_, PyAny>) -> PyResult<TestFileRow> {
    Ok((
        text(&file, "file_path")?,
        text(&file, "relative_path")?,
        stem(&file, "relative_path")?,
        file.clone().unbind(),
        attr(&file, "contents")?,
        items(&file, "blocks")?
            .into_iter()
            .map(test_block_row)
            .collect::<PyResult<_>>()?,
    ))
}

fn scenario_row(scenario: Bound<'_, PyAny>) -> PyResult<ScenarioRow> {
    Ok((
        text(&scenario, "file_path")?,
        text(&scenario, "relative_path")?,
        scenario.clone().unbind(),
        attr(&scenario, "contents")?,
        attr(&scenario, "sql_body")?,
        attr(&scenario, "name")?,
    ))
}

/// The adapter's typed scalar renderer as `(text, None)`, or `(None, error)` for a bad value.
fn parameter_renderer<'py>(value_renderer: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = value_renderer.py();
    let renderer: Py<PyAny> = value_renderer.clone().unbind();
    let errors: Py<PyAny> = PyTuple::new(
        py,
        [
            imported(py, SQL_VALUE_ERRORS_MODULE, "SqlValueRenderingError")?,
            imported(py, NATIVE_RECORDS, "SqlValueValidationError")?,
        ],
    )?
    .into_any()
    .unbind();
    let render = move |arguments: &Bound<'_, PyTuple>,
                       _: Option<&Bound<'_, PyDict>>|
          -> PyResult<(Option<String>, Option<String>)> {
        let py: Python<'_> = arguments.py();
        let keywords: Bound<'_, PyDict> = PyDict::new(py);
        keywords.set_item("value", arguments.get_item(0)?)?;
        match renderer
            .bind(py)
            .call_method("render_typed_scalar", (), Some(&keywords))
        {
            Ok(rendered) => Ok((Some(rendered.extract()?), None)),
            Err(error) if error.matches(py, errors.bind(py))? => {
                Ok((None, Some(error.value(py).str()?.to_string())))
            }
            Err(error) => Err(error),
        }
    };
    Ok(PyCFunction::new_closure(py, None, None, render)?.into_any())
}

fn sql_test_settings<'py>(
    py: Python<'py>,
    (value_renderer, syntax, scan_cache): (
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
    ),
) -> PyResult<Bound<'py, PyDict>> {
    let settings: Bound<'py, PyDict> = PyDict::new(py);
    for (key, class) in [
        ("test_input", "CompileSqlTestInput"),
        ("model_payload", "CompileModelSqlTestInputPayload"),
        ("direct_payload", "CompileDirectLogicSqlTestInputPayload"),
        ("test_cte", "CompileSqlTestCte"),
        ("scenario_input", "CompileSqlScenarioInput"),
        ("scenario_cte", "CompileSqlScenarioCte"),
    ] {
        settings.set_item(key, shape_class_at(py, COMPILE_MODELS_MODULE, class)?)?;
    }
    settings.set_item("modes", by_value(py, COMPILE_TYPES_MODULE, "SqlTestMode")?)?;
    settings.set_item(
        "test_kind",
        enum_member(py, (SCOPE_TYPES_MODULE, "ResourceKind", "TEST"))?,
    )?;
    settings.set_item(
        "scenario_kind",
        enum_member(py, (SCOPE_TYPES_MODULE, "ResourceKind", "SCENARIO"))?,
    )?;
    settings.set_item(
        "runtime_usage",
        enum_member(py, (SCOPE_TYPES_MODULE, "UsageKind", "RUNTIME"))?,
    )?;
    settings.set_item("render_parameter", parameter_renderer(value_renderer)?)?;
    settings.set_item("adapter_name", value_renderer.getattr("adapter_name")?)?;
    settings.set_item(
        "source_location",
        imported(py, CONTRACT_MODELS_MODULE, "SourceLocation")?,
    )?;
    settings.set_item("scan_store", scan_cache.call_method0("opened")?)?;
    settings.set_item(
        "scan_key",
        (SQL_TEST_CTE_SCAN_ALGORITHM, syntax.getattr("cache_key")?),
    )?;
    Ok(settings)
}

fn audit_block_row(block: Bound<'_, PyAny>) -> PyResult<AuditBlockRow> {
    let py: Python<'_> = block.py();
    let measurement: Bound<'_, PyAny> = enum_member(
        py,
        (
            AUDITING_TYPES_MODULE,
            "AuditEvaluationMode",
            MEASUREMENT_MODE,
        ),
    )?;
    Ok((
        block.clone().unbind(),
        attr(&block, "name")?,
        attr(&block, "sql_body")?,
        attr(&block, "evidence_sql")?,
        block.getattr("evaluation_mode")?.eq(measurement)?,
        attr(&block, "header_values")?,
    ))
}

fn audit_file_row(file: Bound<'_, PyAny>) -> PyResult<AuditFileRow> {
    let py: Python<'_> = file.py();
    let generic: Bound<'_, PyAny> =
        enum_member(py, (SCOPE_TYPES_MODULE, "DeclarationKind", "AUDIT"))?;
    Ok((
        text(&file, "file_path")?,
        text(&file, "relative_path")?,
        stem(&file, "file_path")?,
        file.clone().unbind(),
        file.getattr("declaration_kind")?.is(&generic),
        attr(&file, "contents")?,
        items(&file, "blocks")?
            .into_iter()
            .map(audit_block_row)
            .collect::<PyResult<_>>()?,
    ))
}

/// The discovered file of one built-in generic audit, as project discovery would describe it.
fn builtin_audit_file<'py>(
    py: Python<'py>,
    (name, sql_body): (&str, &str),
) -> PyResult<Bound<'py, PyAny>> {
    let path_class: Bound<'py, PyAny> = imported(py, PATHLIB_MODULE, "Path")?;
    let relative_path: Bound<'py, PyAny> =
        path_class.call1((format!("audits/generic/{name}.sql"),))?;
    let block: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "DiscoveredAuditBlock")?,
        &[
            ("audit_index", 0.into_bound_py_any(py)?),
            ("header_values", PyDict::new(py).into_any()),
            ("sql_body", sql_body.into_bound_py_any(py)?),
        ],
    )?;
    call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "DiscoveredAuditFile")?,
        &[
            (
                "file_path",
                path_class.call1(("<built-in>",))?.div(&relative_path)?,
            ),
            ("relative_path", relative_path),
            (
                "contents",
                format!("AUDIT ();\n\n{sql_body}\n").into_bound_py_any(py)?,
            ),
            ("blocks", PyTuple::new(py, [block])?.into_any()),
        ],
    )
}

fn audit_settings<'py>(
    py: Python<'py>,
    effective_settings: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let settings: Bound<'py, PyDict> = PyDict::new(py);
    let severity: Bound<'py, PyAny> = effective_settings.getattr("default_audit_severity")?;
    settings.set_item(
        "default_severity",
        if severity.is_none() {
            None
        } else {
            Some(severity.str()?)
        },
    )?;
    settings.set_item(
        "default_run_scope",
        effective_settings.getattr("default_audit_run_scope")?,
    )?;
    let builtins: Vec<AuditFileRow> = BUILTIN_AUDITS
        .iter()
        .map(|definition| audit_file_row(builtin_audit_file(py, *definition)?))
        .collect::<PyResult<_>>()?;
    settings.set_item("builtins", builtins)?;
    settings.set_item(
        "declaration_identity",
        imported(py, SCOPE_MODELS_MODULE, "DeclarationIdentity")?,
    )?;
    settings.set_item(
        "singular_kind",
        enum_member(
            py,
            (SCOPE_TYPES_MODULE, "DeclarationKind", "SINGULAR_AUDIT"),
        )?,
    )?;
    settings.set_item(
        "audit_kind",
        enum_member(py, (SCOPE_TYPES_MODULE, "DeclarationKind", "AUDIT"))?,
    )?;
    settings.set_item(
        "resource_kinds",
        by_value(py, SCOPE_TYPES_MODULE, "ResourceKind")?,
    )?;
    Ok(settings)
}

/// Each loader's description, relative path and whether that path is a YAML file.
fn loader_rows<'py>(discovered: &Bound<'py, PyAny>) -> PyResult<HashMap<String, LoaderRow>> {
    let mut rows: HashMap<String, LoaderRow> = HashMap::new();
    for loader in items(discovered, "loader_functions")? {
        let relative_path: Bound<'py, PyAny> = loader.getattr("relative_path")?;
        rows.insert(
            attr(&loader, "name")?,
            (
                attr(&loader, DESCRIPTION_KEY)?,
                relative_path.str()?.to_string(),
                YAML_FILE_SUFFIXES.contains(
                    &relative_path
                        .getattr("suffix")?
                        .extract::<String>()?
                        .as_str(),
                ),
            ),
        );
    }
    Ok(rows)
}

fn diagnostic_settings<'py>(
    discovered: &Bound<'py, PyAny>,
    source_inputs: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = discovered.py();
    let settings: Bound<'py, PyDict> = PyDict::new(py);
    settings.set_item(
        "compiler_diagnostic",
        imported(py, COMPILE_MODELS_MODULE, "CompilerDiagnostic")?,
    )?;
    settings.set_item(
        "compile_error",
        imported(py, COMPILE_ERRORS_MODULE, "CompileInputError")?,
    )?;
    settings.set_item(
        "source_location",
        imported(py, CONTRACT_MODELS_MODULE, "SourceLocation")?,
    )?;
    settings.set_item("path_class", imported(py, PATHLIB_MODULE, "Path")?)?;
    settings.set_item("model_files", items(discovered, "model_files")?)?;
    let factories: Vec<(String, String, usize)> = items(discovered, "audit_factories")?
        .iter()
        .map(|factory| {
            Ok((
                attr(factory, "name")?,
                text(factory, "relative_path")?,
                attr(factory, "line")?,
            ))
        })
        .collect::<PyResult<_>>()?;
    settings.set_item("audit_factories", factories)?;
    let scenarios: Vec<Bound<'py, PyTuple>> = items(discovered, "scenario_files")?
        .iter()
        .map(|scenario| {
            PyTuple::new(
                py,
                [
                    scenario.getattr("name")?,
                    text(scenario, "relative_path")?.into_bound_py_any(py)?,
                    scenario.getattr("contents")?,
                    scenario
                        .getattr("header_values")?
                        .call_method1("get", (DESCRIPTION_KEY,))?,
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    settings.set_item("scenarios", scenarios)?;
    let hooks: Vec<Bound<'py, PyTuple>> = items(discovered, "sql_hook_files")?
        .iter()
        .map(|hook| {
            PyTuple::new(
                py,
                [
                    hook.getattr("name")?,
                    text(hook, "relative_path")?.into_bound_py_any(py)?,
                    hook.getattr("contents")?,
                    hook.getattr(DESCRIPTION_KEY)?,
                ],
            )
        })
        .collect::<PyResult<_>>()?;
    settings.set_item("sql_hooks", hooks)?;
    settings.set_item("loaders", loader_rows(discovered)?)?;
    settings.set_item(
        "python_resources",
        call_with(
            &imported(py, PYTHON_RESOURCES_MODULE, "python_resource_rows")?,
            &[
                ("discovered_inputs", discovered.clone()),
                ("source_inputs", source_inputs.clone()),
            ],
        )?,
    )?;
    Ok(settings)
}

/// Attach every SQL test case, scenario and audit, then report every resource diagnostic.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn attach_checks<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "attach_checks",
        options,
        (
            &[
                "discovered_inputs",
                "native_project",
                "settings",
                "scan_cache",
                "source_inputs",
            ],
            &[],
        ),
    )?;
    let discovered_inputs: &Bound<'py, PyAny> = &arguments.value("discovered_inputs")?;
    let native_project: &Bound<'py, NativeCompiledProject> =
        &arguments.value("native_project")?.downcast_into()?;
    let (effective_settings, value_renderer, syntax): (
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
    ) = arguments.value("settings")?.extract()?;
    let scan_cache: &Bound<'py, PyAny> = &arguments.value("scan_cache")?;
    let source_inputs: &Bound<'py, PyAny> = &arguments.value("source_inputs")?;
    let (tests, scenarios) = record_compile_timing(TEST_TIMING_KEY, || {
        let attached = NativeCompiledProject::attach_sql_tests(
            native_project,
            items(discovered_inputs, "test_files")?
                .into_iter()
                .map(test_file_row)
                .collect::<PyResult<_>>()?,
            items(discovered_inputs, "scenario_files")?
                .into_iter()
                .map(scenario_row)
                .collect::<PyResult<_>>()?,
            sql_test_settings(py, (&value_renderer, &syntax, scan_cache))?.extract()?,
        )?;
        scan_cache.call_method0("save")?;
        Ok(attached)
    })?;
    let (audits, audit_diagnostics) = NativeCompiledProject::attach_audits(
        native_project,
        items(discovered_inputs, "audit_files")?
            .into_iter()
            .map(audit_file_row)
            .collect::<PyResult<_>>()?,
        audit_settings(py, &effective_settings)?.extract()?,
    )?;
    let settings: DiagnosticSettings =
        diagnostic_settings(discovered_inputs, source_inputs)?.extract()?;
    let (orphans, descriptions, cursors) =
        resource_diagnostics(&native_project.borrow(), py, &settings)?;
    let diagnostics: Vec<Bound<'py, PyAny>> = audit_diagnostics
        .into_iter()
        .chain(orphans)
        .chain(descriptions)
        .chain(cursors)
        .collect();
    PyTuple::new(
        py,
        [
            PyTuple::new(py, tests)?.into_any(),
            PyTuple::new(py, scenarios)?.into_any(),
            PyTuple::new(py, audits)?.into_any(),
            PyTuple::new(py, diagnostics)?.into_any(),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(attach_resources, module)?)?;
    module.add_function(wrap_pyfunction!(attach_checks, module)?)
}
