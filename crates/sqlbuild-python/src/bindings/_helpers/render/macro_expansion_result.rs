//! Expand one authored SQL string's macros into a `MacroExpansionResult`.

use pyo3::IntoPyObject;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyDictMethods, PyList, PyString, PyStringMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, keywords,
};
use crate::bindings::_helpers::render::declaration_values::resolved_declaration_context;
use crate::bindings::_helpers::render::macro_call_rows::span_row;
use crate::bindings::_helpers::render::macro_expansion::{
    ExpansionOutput, NativeMacroExpansion, expanded,
};
use crate::bindings::_helpers::sqltext::sql_references::extract_references;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const COMPILE_EXCEPTIONS_MODULE: &str = "sqlbuild._native";
const FRONTIER_EXCEPTIONS_MODULE: &str = "sqlbuild._native";
const SCOPES_MODELS_MODULE: &str = "sqlbuild._native";
const SCOPES_TYPES_MODULE: &str = "sqlbuild._native";
const REF_MODELS_MODULE: &str = "sqlbuild.python_nodes.models";
const REF_TYPES_MODULE: &str = "sqlbuild.python_nodes.types";
const TYPED_REFERENCE_FUNCTIONS: [(&str, &str); 3] = [
    ("model", "__ref"),
    ("source", "__source"),
    ("seed", "__seed"),
];
const USER_MACROS_MODULE: &str = "sqlbuild.compiler.compile._helpers.render.user_macros";
const ACTIVE_BRIDGE_MODULE: &str = "sqlbuild.compiler.macro_bridge.main.active_macro_bridge";
/// The call prefix of every reference function, in `SqlReferenceKind` order.
const GENERATED_REFERENCE_MARKERS: [&str; 6] = [
    "__ref(",
    "__seed(",
    "__source(",
    "__dbt_ref(",
    "__udf(",
    "__table_fn(",
];
const DIAGNOSTICS_MODULE: &str = "sqlbuild._native";
const CONTRACT_MODELS_MODULE: &str = "sqlbuild._native";
const SQL_ANALYSIS_MODELS_MODULE: &str = "sqlbuild._native";
const BUILTINS_MODULE: &str = "builtins";
const MACRO_TOKEN: &str = "@";
const GENERATED_ALLOWED: &str = "macro-generated references";

static EXPANSION_CLASSES: PyOnceLock<Py<PyDict>> = PyOnceLock::new();

/// One expansion's inputs, as Python's `expand_sql_macros_result` takes them.
struct ExpansionRequest<'py> {
    sql: Bound<'py, PyString>,
    file_path: Bound<'py, PyAny>,
    loaded_macros: Bound<'py, PyDict>,
    macro_overrides: Option<Bound<'py, PyDict>>,
    macro_context: Bound<'py, PyAny>,
    declaration_resolver: Option<Bound<'py, PyAny>>,
    declarations: Option<Bound<'py, PyAny>>,
    consumer: Option<Bound<'py, PyAny>>,
}

fn generated_classes(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let native: Bound<'_, PyAny> = py.import(NATIVE_MODULE)?.into_any();
    let help: Bound<'_, PyAny> = native.getattr("explicit_references_help")?.call(
        (),
        Some(&keywords(
            py,
            &[("allowed", PyString::new(py, GENERATED_ALLOWED).into_any())],
        )?),
    )?;
    let markers: Bound<'_, PyAny> = PyList::new(py, GENERATED_REFERENCE_MARKERS)?.into_any();
    keywords(
        py,
        &[
            (
                "compiler_diagnostic",
                imported(py, COMPILE_MODELS_MODULE, "CompilerDiagnostic")?,
            ),
            (
                "report_diagnostic",
                imported(py, DIAGNOSTICS_MODULE, "report_compile_diagnostic")?,
            ),
            (
                "source_location",
                imported(py, CONTRACT_MODELS_MODULE, "SourceLocation")?,
            ),
            (
                "resource_identity",
                imported(py, SCOPES_MODELS_MODULE, "ResourceIdentity")?,
            ),
            (
                "generic_syntax",
                imported(py, SQL_ANALYSIS_MODELS_MODULE, "SqlLexicalSyntax")?
                    .call0()?
                    .getattr("native_mapping")?,
            ),
            ("generated_help", help),
            ("all_markers", markers),
        ],
    )
}

fn built_classes(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let native: Bound<'_, PyAny> = py.import(NATIVE_MODULE)?.into_any();
    let declaration_kind: Bound<'_, PyAny> = imported(py, SCOPES_TYPES_MODULE, "DeclarationKind")?;
    let ref_kind: Bound<'_, PyAny> = imported(py, REF_TYPES_MODULE, "SqlResourceRefKind")?;
    let ref_kinds: Bound<'_, PyDict> = PyDict::new(py);
    let ref_functions: Bound<'_, PyDict> = PyDict::new(py);
    for (kind, function) in TYPED_REFERENCE_FUNCTIONS {
        ref_kinds.set_item(function, ref_kind.call1((kind,))?)?;
        ref_functions.set_item(kind, function)?;
    }
    let store_tokens: Bound<'_, PyDict> = keywords(
        py,
        &[
            ("macro_token", native.getattr("macro_store_token")?),
            ("context_token", native.getattr("context_store_token")?),
        ],
    )?;
    keywords(
        py,
        &[
            (
                "compile_error",
                imported(py, COMPILE_EXCEPTIONS_MODULE, "CompileInputError")?,
            ),
            (
                "macro_argument_error",
                imported(py, COMPILE_EXCEPTIONS_MODULE, "MacroArgumentError")?,
            ),
            (
                "mismatch_error",
                imported(py, FRONTIER_EXCEPTIONS_MODULE, "NativeStageMismatchError")?,
            ),
            (
                "declaration_identity",
                imported(py, SCOPES_MODELS_MODULE, "DeclarationIdentity")?,
            ),
            ("macro_kind", declaration_kind.getattr("MACRO")?),
            ("declaration_kind", declaration_kind),
            (
                "usage_record",
                imported(py, SCOPES_MODELS_MODULE, "UsageRecord")?,
            ),
            (
                "runtime_usage",
                imported(py, SCOPES_TYPES_MODULE, "UsageKind")?.getattr("RUNTIME")?,
            ),
            (
                "resource_identity",
                imported(py, SCOPES_MODELS_MODULE, "ResourceIdentity")?,
            ),
            (
                "model_kind",
                imported(py, SCOPES_TYPES_MODULE, "ResourceKind")?.getattr("MODEL")?,
            ),
            (
                "resource_ref",
                imported(py, REF_MODELS_MODULE, "SqlResourceRef")?,
            ),
            ("ref_kinds", ref_kinds.into_any()),
            ("ref_functions", ref_functions.into_any()),
            ("store_tokens", store_tokens.into_any()),
            (
                "relation_renderer",
                imported(py, REF_MODELS_MODULE, "RELATION_RENDERER")?,
            ),
            (
                "invocation_context",
                imported(py, USER_MACROS_MODULE, "macro_invocation_context")?,
            ),
            ("generated", generated_classes(py)?.into_any()),
            ("int_type", imported(py, BUILTINS_MODULE, "int")?),
            ("float_type", imported(py, BUILTINS_MODULE, "float")?),
        ],
    )
}

/// The classes, enums and helpers the native expansion builds facts and errors from, built once.
pub(crate) fn macro_expansion_classes(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    EXPANSION_CLASSES
        .get_or_try_init(py, || built_classes(py).map(Bound::unbind))
        .map(|classes| classes.bind(py).clone())
}

/// `tuple(dict.fromkeys(items))`: the items without repeats, in first-seen order.
fn unique<'py>(py: Python<'py>, items: Vec<Py<PyAny>>) -> PyResult<Bound<'py, PyTuple>> {
    let seen: Bound<'py, PyDict> = PyDict::new(py);
    for item in items {
        seen.set_item(item, py.None())?;
    }
    PyTuple::new(py, seen.keys())
}

fn result_model<'py>(
    py: Python<'py>,
    pairs: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "MacroExpansionResult")?,
        pairs,
    )
}

fn expansion_result<'py>(request: ExpansionRequest<'py>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.sql.py();
    if !request.sql.to_str()?.contains(MACRO_TOKEN) {
        return result_model(py, &[("sql", request.sql.into_any())]);
    }
    let declarations: Bound<'py, PyAny> = match (request.declarations, request.declaration_resolver)
    {
        (Some(declarations), _) => declarations,
        (None, Some(resolver)) => {
            resolved_declaration_context(&resolver, &request.file_path, None)?
        }
        (None, None) => py.None().into_bound(py),
    };
    let expansion: NativeMacroExpansion = NativeMacroExpansion::new(
        &request.file_path,
        (
            request.loaded_macros.unbind(),
            request
                .macro_overrides
                .unwrap_or_else(|| PyDict::new(py))
                .unbind(),
            request.macro_context.clone().unbind(),
            declarations.unbind(),
            request.consumer.map_or_else(|| py.None(), Bound::unbind),
        ),
        request
            .macro_context
            .getattr("_enforce_explicit_references")?
            .is_truthy()?,
        macro_expansion_classes(py)?.unbind(),
    )?;
    let expansion: Bound<'py, NativeMacroExpansion> = Bound::new(py, expansion)?;
    let bridge: Bound<'py, PyAny> =
        imported(py, ACTIVE_BRIDGE_MODULE, "active_macro_bridge")?.call0()?;
    let output: ExpansionOutput = expanded(&expansion, request.sql.to_str()?, &bridge)?;
    let span_class: Bound<'py, PyAny> = imported(py, NATIVE_RECORDS_MODULE, "ExpansionSpan")?;
    let mut spans: Vec<Bound<'py, PyAny>> = Vec::with_capacity(output.spans.len());
    for span in output.spans {
        let (source_start, source_end, output_start, output_end) = span_row(span);
        spans.push(call_with(
            &span_class,
            &[
                ("source_start", source_start.into_pyobject(py)?.into_any()),
                ("source_end", source_end.into_pyobject(py)?.into_any()),
                ("output_start", output_start.into_pyobject(py)?.into_any()),
                ("output_end", output_end.into_pyobject(py)?.into_any()),
            ],
        )?);
    }
    let argument_references: Bound<'py, PyAny> = if output.argument_references.is_empty() {
        PyTuple::empty(py).into_any()
    } else {
        let calls: Vec<String> = output
            .argument_references
            .iter()
            .map(|(kind, name)| format!("{}(\"{name}\")", typed_reference_function(kind)))
            .collect();
        let syntax: Bound<'py, PyAny> =
            imported(py, SQL_ANALYSIS_MODELS_MODULE, "SqlLexicalSyntax")?.call0()?;
        extract_references(&calls.join(" "), &syntax)?.into_any()
    };
    result_model(
        py,
        &[
            ("sql", PyString::new(py, &output.sql).into_any()),
            ("spans", PyTuple::new(py, spans)?.into_any()),
            ("argument_references", argument_references),
            ("dependencies", unique(py, output.dependencies)?.into_any()),
            ("usages", unique(py, output.usages)?.into_any()),
        ],
    )
}

/// The typed reference function naming a `SqlResourceRefKind` value, such as `__ref`.
fn typed_reference_function(kind: &str) -> &'static str {
    TYPED_REFERENCE_FUNCTIONS
        .iter()
        .find(|(typed, _)| *typed == kind)
        .map_or("", |(_, function)| function)
}

fn optional<'py>(value: Bound<'py, PyAny>) -> Option<Bound<'py, PyAny>> {
    (!value.is_none()).then_some(value)
}

/// Expand authored Python macros in one SQL string, keeping substitution spans and facts.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn expand_sql_macros<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "expand_sql_macros",
        options,
        (
            &["sql", "file_path", "loaded_macros", "macro_context"],
            &[
                "macro_overrides",
                "declaration_resolver",
                "declarations",
                "consumer",
            ],
        ),
    )?;
    expansion_result(ExpansionRequest {
        sql: arguments.value("sql")?.downcast_into()?,
        file_path: arguments.value("file_path")?,
        loaded_macros: arguments.value("loaded_macros")?.downcast_into()?,
        macro_overrides: optional(arguments.value("macro_overrides")?)
            .map(Bound::downcast_into)
            .transpose()?,
        macro_context: arguments.value("macro_context")?,
        declaration_resolver: optional(arguments.value("declaration_resolver")?),
        declarations: optional(arguments.value("declarations")?),
        consumer: optional(arguments.value("consumer")?),
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(expand_sql_macros, module)?)
}
