//! The Python classes, project declarations and callbacks the native model loop builds with.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyList, PyTuple};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::imported;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
const COMPILE_ERRORS_MODULE: &str = "sqlbuild._native";
const AUDITING_TYPES_MODULE: &str = "sqlbuild.compiler.auditing.types";
const DISCOVERY_MODELS_MODULE: &str = "sqlbuild._native";
const LINEAGE_TYPES_MODULE: &str = "sqlbuild.compiler.lineage.types";
const PLANNER_TYPES_MODULE: &str = "sqlbuild._native";
const REFERENCE_TYPES_MODULE: &str = "sqlbuild._native";
const SCOPE_ERRORS_MODULE: &str = "sqlbuild._native";
const SCOPE_MODELS_MODULE: &str = "sqlbuild._native";
const SCOPE_TYPES_MODULE: &str = "sqlbuild._native";
const CONTRACT_MODELS_MODULE: &str = "sqlbuild._native";
const CONTRACT_TYPES_MODULE: &str = "sqlbuild._native";
const NATIVE_MODULE: &str = "sqlbuild._native";
/// The materializations a model's storage policies are inherited for, besides none.
const TABLE_BACKED_MATERIALIZATIONS: [&str; 3] = ["TABLE", "INCREMENTAL", "SNAPSHOT"];
/// The declaration kinds whose project-owned records the loop names.
const NAMED_KINDS: [&str; 4] = ["AUDIT", "SCHEMA", "SQL_HOOK", "PYTHON_HOOK"];

fn class<'py>(py: Python<'py>, module: &str, name: &str) -> PyResult<Bound<'py, PyAny>> {
    imported(py, module, name)
}

fn member<'py>(
    py: Python<'py>,
    module: &str,
    (enum_class, name): (&str, &str),
) -> PyResult<Bound<'py, PyAny>> {
    imported(py, module, enum_class)?.getattr(name)
}

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

/// The values of a table-backed `MaterializationType`, as text.
pub(crate) fn table_backed<'py>(py: Python<'py>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    TABLE_BACKED_MATERIALIZATIONS
        .iter()
        .map(|name| member(py, PLANNER_TYPES_MODULE, ("MaterializationType", name)))
        .collect()
}

/// The builder, storage defaults and classes a model's `CompileModelConfig` is made of.
pub(crate) fn native_config_classes<'py>(
    session: &Bound<'py, PyAny>,
    record_template_reads: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = session.py();
    let table_backed: Vec<Bound<'py, PyAny>> = table_backed(py)?
        .iter()
        .map(|materialization| Ok(materialization.str()?.into_any()))
        .collect::<PyResult<_>>()?;
    dict(
        py,
        vec![
            ("builder", session.getattr("builder")?),
            ("inherited_storage", session.getattr("inherited_storage")?),
            ("table_backed", PyTuple::new(py, table_backed)?.into_any()),
            (
                "compile_model_config",
                class(py, NATIVE_RECORDS_MODULE, "CompileModelConfig")?,
            ),
            (
                "resolved_retention",
                class(py, CONTRACT_MODELS_MODULE, "ResolvedTimeTravelRetention")?,
            ),
            (
                "retention_source",
                member(
                    py,
                    CONTRACT_TYPES_MODULE,
                    ("TimeTravelRetentionSource", "MODEL"),
                )?,
            ),
            (
                "resolved_table_type",
                class(py, CONTRACT_MODELS_MODULE, "ResolvedTableType")?,
            ),
            ("table_type", class(py, CONTRACT_TYPES_MODULE, "TableType")?),
            (
                "table_type_source",
                member(py, CONTRACT_TYPES_MODULE, ("TableTypeSource", "MODEL"))?,
            ),
            ("record_template_reads", record_template_reads.clone()),
        ],
    )
}

/// Each project-owned generic audit's, schema's and hook's first record, by `(kind, name)`.
fn named_records<'py>(resolver: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = resolver.py();
    let records: Bound<'py, PyDict> = PyDict::new(py);
    if resolver.is_none() {
        return Ok(records);
    }
    let kinds: Vec<Bound<'py, PyAny>> = NAMED_KINDS
        .iter()
        .map(|name| member(py, SCOPE_TYPES_MODULE, ("DeclarationKind", name)))
        .collect::<PyResult<_>>()?;
    let declarations: Bound<'py, PyAny> = resolver.getattr("lookup")?.getattr("declarations")?;
    for pair in declarations.call_method0("items")?.try_iter()? {
        let (identity, records_of): (Bound<'py, PyAny>, Bound<'py, PyAny>) = pair?.extract()?;
        let kind: Bound<'py, PyAny> = identity.getattr("kind")?;
        if kinds.iter().any(|named| kind.is(named))
            && identity.getattr("owner")?.is_none()
            && records_of.is_truthy()?
        {
            records.set_item(
                (kind.getattr("value")?, identity.getattr("name")?),
                records_of.get_item(0)?,
            )?;
        }
    }
    Ok(records)
}

/// Project-owned enums by name, as `model_schema_enum_declarations` resolves column types.
fn schema_enums<'py>(resolver: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = resolver.py();
    let enums: Bound<'py, PyDict> = PyDict::new(py);
    if resolver.is_none() {
        return Ok(enums);
    }
    let enum_kind: Bound<'py, PyAny> = member(py, SCOPE_TYPES_MODULE, ("DeclarationKind", "ENUM"))?;
    let enum_class: Bound<'py, PyAny> = class(py, DISCOVERY_MODELS_MODULE, "EnumDeclaration")?;
    let declarations: Bound<'py, PyAny> =
        resolver.getattr("projection")?.getattr("declarations")?;
    for pair in declarations.call_method0("items")?.try_iter()? {
        let (identity, value): (Bound<'py, PyAny>, Bound<'py, PyAny>) = pair?.extract()?;
        if identity.getattr("kind")?.is(&enum_kind)
            && identity.getattr("owner")?.is_none()
            && value.is_instance(&enum_class)?
        {
            enums.set_item(identity.getattr("name")?, value)?;
        }
    }
    Ok(enums)
}

/// A hook function's parameters as `inspect.signature` reads them: name, kind, default.
#[pyfunction]
fn hook_signature<'py>(function: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyList>> {
    let py: Python<'py> = function.py();
    let inspect: Bound<'py, PyAny> = py.import("inspect")?.into_any();
    let empty: Bound<'py, PyAny> = inspect.getattr("Parameter")?.getattr("empty")?;
    let mut parameters: Vec<(String, i64, bool)> = Vec::new();
    for parameter in inspect
        .call_method1("signature", (function,))?
        .getattr("parameters")?
        .call_method0("values")?
        .try_iter()?
    {
        let parameter: Bound<'py, PyAny> = parameter?;
        parameters.push((
            parameter.getattr("name")?.extract()?,
            parameter
                .getattr("kind")?
                .call_method0("__int__")?
                .extract()?,
            !parameter.getattr("default")?.is(&empty),
        ));
    }
    PyList::new(py, parameters)
}

/// What the loop resolves each model's visible declarations from.
fn visibility_classes<'py>(
    context: &Bound<'py, PyAny>,
    visible_declarations: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = context.py();
    let resolver: Bound<'py, PyAny> = context.getattr("declaration_resolver")?;
    let (projects, resource_specific) = if resolver.is_none() {
        (false, PyFrozenSet::empty(py)?)
    } else {
        let lookup: Bound<'py, PyAny> = resolver.getattr("lookup")?;
        let declarations: Bound<'py, PyAny> = lookup.getattr("index")?.getattr("declarations")?;
        let private: Bound<'py, PyAny> = member(py, SCOPE_TYPES_MODULE, ("ScopeKind", "PRIVATE"))?;
        let mut owners: Vec<Bound<'py, PyAny>> = Vec::new();
        for declaration in declarations.try_iter()? {
            let declaration: Bound<'py, PyAny> = declaration?;
            let owner: Bound<'py, PyAny> = declaration.getattr("identity")?.getattr("owner")?;
            if declaration.getattr("scope")?.is(&private) && !owner.is_none() {
                owners.push(owner);
            }
        }
        for resource in lookup.getattr("grants_by_resource")?.try_iter()? {
            owners.push(resource?);
        }
        (declarations.is_truthy()?, PyFrozenSet::new(py, &owners)?)
    };
    dict(
        py,
        vec![
            ("resolver", resolver),
            ("projects", projects.into_bound_py_any(py)?),
            ("resource_specific", resource_specific.into_any()),
            ("public_enums", context.getattr("public_enums")?),
            ("public_constants", context.getattr("public_constants")?),
            ("visible_declarations", visible_declarations.clone()),
            (
                "resource_identity",
                class(py, SCOPE_MODELS_MODULE, "ResourceIdentity")?,
            ),
            (
                "declaration_identity",
                class(py, SCOPE_MODELS_MODULE, "DeclarationIdentity")?,
            ),
            (
                "model_kind",
                member(py, SCOPE_TYPES_MODULE, ("ResourceKind", "MODEL"))?,
            ),
            (
                "enum_kind",
                member(py, SCOPE_TYPES_MODULE, ("DeclarationKind", "ENUM"))?,
            ),
            (
                "constant_kind",
                member(py, SCOPE_TYPES_MODULE, ("DeclarationKind", "CONSTANT"))?,
            ),
            (
                "private_owner",
                member(
                    py,
                    SCOPE_TYPES_MODULE,
                    ("VisibilityReason", "PRIVATE_OWNER"),
                )?,
            ),
            (
                "visibility_record",
                class(py, SCOPE_MODELS_MODULE, "VisibilityRecord")?,
            ),
        ],
    )
}

fn input_view_classes<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
    let compiled: Vec<(&str, Bound<'py, PyAny>)> = vec![
        (
            "object_key",
            class(py, COMPILE_MODELS_MODULE, "CompiledObjectKey")?,
        ),
        (
            "relation_location",
            class(py, COMPILE_MODELS_MODULE, "CompiledRelationLocation")?,
        ),
        (
            "inferred_column",
            class(py, COMPILE_MODELS_MODULE, "InferredColumn")?,
        ),
        (
            "nullability",
            class(py, LINEAGE_TYPES_MODULE, "InferredNullability")?,
        ),
        (
            "compiler_diagnostic",
            class(py, COMPILE_MODELS_MODULE, "CompilerDiagnostic")?,
        ),
        (
            "source_location",
            class(py, CONTRACT_MODELS_MODULE, "SourceLocation")?,
        ),
        (
            "compact_lineage_facts",
            class(py, COMPILE_MODELS_MODULE, "CompactLineageFacts")?,
        ),
        (
            "lineage_column_fact",
            class(py, NATIVE_RECORDS_MODULE, "CompiledLineageColumnFact")?,
        ),
        (
            "lineage_source_fact",
            class(py, COMPILE_MODELS_MODULE, "CompiledLineageSourceFact")?,
        ),
        (
            "contract_proof",
            class(py, NATIVE_RECORDS_MODULE, "DynamicColumnContractProof")?,
        ),
        (
            "family_proof",
            class(py, NATIVE_RECORDS_MODULE, "DynamicColumnFamilyProof")?,
        ),
    ];
    dict(
        py,
        vec![
            (
                "sql_reference",
                class(py, COMPILE_MODELS_MODULE, "CompileSqlReference")?,
            ),
            (
                "reference_kind",
                class(py, REFERENCE_TYPES_MODULE, "SqlReferenceKind")?,
            ),
            (
                "schema_model_entry",
                class(py, CONTRACT_MODELS_MODULE, "SchemaModelEntry")?,
            ),
            (
                "sql_expansion",
                class(py, NATIVE_RECORDS_MODULE, "CompiledSqlExpansion")?,
            ),
            (
                "expansion_span",
                class(py, NATIVE_RECORDS_MODULE, "ExpansionSpan")?,
            ),
            (
                "audits",
                dict(
                    py,
                    vec![
                        (
                            "audit_severity",
                            class(py, AUDITING_TYPES_MODULE, "AuditSeverity")?,
                        ),
                        (
                            "attached_target_kind",
                            class(py, COMPILE_TYPES_MODULE, "AttachedAuditTargetKind")?,
                        ),
                    ],
                )?
                .into_any(),
            ),
            (
                "functions",
                dict(
                    py,
                    vec![
                        (
                            "function_argument",
                            class(py, NATIVE_RECORDS_MODULE, "FunctionArgument")?,
                        ),
                        (
                            "function_return_column",
                            class(py, NATIVE_RECORDS_MODULE, "FunctionReturnColumn")?,
                        ),
                        (
                            "function_language",
                            class(py, COMPILE_TYPES_MODULE, "FunctionLanguage")?,
                        ),
                    ],
                )?
                .into_any(),
            ),
            ("compiled", dict(py, compiled)?.into_any()),
        ],
    )
}

/// `{item.<attribute>: item for item in items}`.
pub(crate) fn by_attribute<'py>(
    items: &Bound<'py, PyAny>,
    attribute: &str,
) -> PyResult<Bound<'py, PyDict>> {
    let keyed: Bound<'py, PyDict> = PyDict::new(items.py());
    for item in items.try_iter()? {
        let item: Bound<'py, PyAny> = item?;
        keyed.set_item(item.getattr(attribute)?, item)?;
    }
    Ok(keyed)
}

/// The classes, error factories and project declarations the model loop reads.
pub(crate) fn model_loop_classes<'py>(
    audit_factories: &Bound<'py, PyAny>,
    context: &Bound<'py, PyAny>,
    external_resolver: &Bound<'py, PyAny>,
    host_inputs: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = context.py();
    let host = |key: &str| -> PyResult<Bound<'py, PyAny>> { host_inputs.as_any().get_item(key) };
    let resolver: Bound<'py, PyAny> = context.getattr("declaration_resolver")?;
    let mut provider_names: Vec<String> = host("provider_names")?
        .try_iter()?
        .map(|name| name?.extract())
        .collect::<PyResult<_>>()?;
    provider_names.sort();
    let hooks: Bound<'py, PyDict> = dict(
        py,
        vec![
            (
                "functions",
                by_attribute(&host("hook_functions")?, "name")?.into_any(),
            ),
            ("provider_names", provider_names.into_bound_py_any(py)?),
            (
                "python_hook_entry",
                class(py, DISCOVERY_MODELS_MODULE, "PythonHookEntry")?,
            ),
            (
                "signature",
                wrap_pyfunction!(hook_signature, py)?.into_any(),
            ),
        ],
    )?;
    let record: Bound<'py, PyDict> = dict(
        py,
        vec![
            ("replace", imported(py, "dataclasses", "replace")?),
            (
                "declaration_rows",
                imported(py, NATIVE_MODULE, "declaration_rows")?,
            ),
        ],
    )?;
    dict(
        py,
        vec![
            (
                "usage_record",
                class(py, SCOPE_MODELS_MODULE, "UsageRecord")?,
            ),
            (
                "compile_error",
                class(py, COMPILE_ERRORS_MODULE, "CompileInputError")?,
            ),
            ("syntax_help", host("syntax_help")?),
            ("source_syntax_help", host("source_syntax_help")?),
            ("macros", host("macros")?),
            ("sql_hooks", host("sql_hooks")?),
            (
                "scope_path_error",
                class(py, SCOPE_ERRORS_MODULE, "InvalidScopePathError")?,
            ),
            (
                "sql_hook_entry",
                class(py, DISCOVERY_MODELS_MODULE, "SqlHookEntry")?,
            ),
            (
                "audit_factories",
                by_attribute(audit_factories, "name")?.into_any(),
            ),
            (
                "generated_usage",
                member(py, SCOPE_TYPES_MODULE, ("UsageKind", "GENERATED"))?,
            ),
            (
                "contract_enforced",
                member(py, PLANNER_TYPES_MODULE, ("ContractPolicy", "ENFORCED"))?,
            ),
            ("model_schemas", context.getattr("public_model_schemas")?),
            ("named_records", named_records(&resolver)?.into_any()),
            ("schema_enums", schema_enums(&resolver)?.into_any()),
            (
                "compiler_diagnostic",
                class(py, COMPILE_MODELS_MODULE, "CompilerDiagnostic")?,
            ),
            ("report_diagnostic", host("report_diagnostic")?),
            ("path_class", imported(py, "pathlib", "Path")?),
            ("external_resolver", external_resolver.clone()),
            (
                "reference_kind",
                class(py, REFERENCE_TYPES_MODULE, "SqlReferenceKind")?,
            ),
            ("partial", imported(py, "functools", "partial")?),
            (
                "config",
                native_config_classes(&host("config_session")?, &host("record_template_reads")?)?
                    .into_any(),
            ),
            ("hooks", hooks.into_any()),
            (
                "visibility",
                visibility_classes(context, &host("visible_declarations")?)?.into_any(),
            ),
            ("record", record.into_any()),
            ("input_view", input_view_classes(py)?.into_any()),
        ],
    )
}
