//! The compile-input model loop: models it can finish natively go straight into the owned project.

use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyRefMut, PyResult, Python,
};
use pyo3::types::{
    PyBool, PyBoolMethods, PyDict, PyDictMethods, PyInt, PyString, PyStringMethods, PyTuple,
};
use pyo3::{IntoPyObject, pyclass, pymethods};
use sqlbuild_analysis::compiled_project::main::calls_macros::calls_macros;
use sqlbuild_analysis::compiled_project::main::enum_member_literal::enum_member_literal;
use sqlbuild_analysis::compiled_project::main::header_column_blocker::header_column_blocker;
use sqlbuild_analysis::compiled_project::main::header_metadata_keys::is_header_metadata_key;
use sqlbuild_analysis::compiled_project::main::merge_call_site_references::merge_call_site_references;
use sqlbuild_analysis::compiled_project::main::plain_model_blocker::plain_model_blocker;
use sqlbuild_analysis::compiled_project::main::plain_model_facts::plain_model_facts;
use sqlbuild_analysis::compiled_project::main::splice_declarations::splice_declarations;
use sqlbuild_analysis::compiled_project::models::{
    AnalysisOverride, CompiledModelFacts, DeclarationSplice, DescriptionShape, HeaderColumnShape,
    ModelConfigFacts, ModelLoopSettings, ModelReferenceFact, ModelSchemaFact, PlainModel,
    PlainModelCheck, SchemaColumnFact, SplicedSql,
};
use sqlbuild_attachments::cursor_intrinsics::main::validated_model_intrinsics::validated_model_intrinsics;
use sqlbuild_attachments::cursor_intrinsics::models::IntrinsicModel;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_model_config::header_metadata::main::parse_header_metadata::parse_header_metadata;
use sqlbuild_model_config::header_metadata::models::{ParsedAudit, ParsedColumn};
use sqlbuild_sqltext::sql_references::main::extract_sql_references::extract_sql_references;
use sqlbuild_sqltext::sql_references::models::{ReferenceExtraction, SqlReference};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::bindings::_helpers::compiled_project::project::{
    DeclarationPy, ModelInputPy, NativeCompiledProject, config_values, declarations, model_facts,
};
use crate::bindings::_helpers::discovery::project_files::python_semantics;
use crate::bindings::_helpers::model_config::authored_nodes::PyNode;
use crate::bindings::_helpers::model_config::header_metadata::{
    ContractClasses, audit_tuple, column_tuple,
};
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;

const DESCRIPTION_KEY: &str = "description";
const COLUMNS_KEY: &str = "columns";
const AUDITS_KEY: &str = "audits";
const SQL_ANALYSIS_KEY: &str = "sql_analysis";
const SQL_VALIDATION_KEY: &str = "sql_validation";
const MATERIALIZED_KEY: &str = "materialized";
const CURSOR_KEY: &str = "cursor";
const INCREMENTAL_MATERIALIZATION: &str = "incremental";
const DBT_REF_KIND: &str = "dbt_ref";
const VALUES_ATTRIBUTE: &str = "values";
const HEADER_KEYS_ATTRIBUTE: &str = "model_header_keys";
const LAYER_SCHEMA_ATTRIBUTE: &str = "layer_schema";
const RETENTION_ATTRIBUTE: &str = "time_travel_retention";
const UNMANAGED_ATTRIBUTE: &str = "unmanaged";
const TABLE_TYPE_ATTRIBUTE: &str = "table_type";
const DECLARED_ATTRIBUTE: &str = "declared";
const STRIP_METHOD: &str = "strip";
const VALIDATE_METHOD: &str = "validate";
const CONFIG_CALLBACK: &str = "config";
const PLAIN_INPUT_CALLBACK: &str = "plain_input";
const FALLBACK_CALLBACK: &str = "fallback";
const MODEL_ROW_CALLBACK: &str = "model_row";
const INDEX_ARGUMENT: &str = "index";
const MODEL_INPUT_ARGUMENT: &str = "model_input";
const VALUES_ARGUMENT: &str = "values";
const REFERENCES_ARGUMENT: &str = "references";
const QUERY_SQL_ARGUMENT: &str = "query_sql";
const DESCRIPTION_ARGUMENT: &str = "description";
const SCHEMA_ARGUMENT: &str = "schema";
const DECLARATIONS_ARGUMENT: &str = "declarations";
const EXPAND_MACROS_CALLBACK: &str = "expand_macros";
const SQL_ARGUMENT: &str = "sql";
const SPANS_ARGUMENT: &str = "spans";
const DECLARATION_ARGUMENT: &str = "declaration";
const CONSTANT_TEXT_CALLBACK: &str = "constant_text";
const ENUMS_ATTRIBUTE: &str = "enums";
const CONSTANTS_ATTRIBUTE: &str = "constants";
const ENUM_VISIBILITY_ATTRIBUTE: &str = "enum_visibility";
const CONSTANT_VISIBILITY_ATTRIBUTE: &str = "constant_visibility";
const MEMBERS_ATTRIBUTE: &str = "members";
const NAME_ATTRIBUTE: &str = "name";
const VALUE_ATTRIBUTE: &str = "value";
const DECLARATION_FIELD: &str = "declaration";
const THROUGH_FIELD: &str = "through";
const CONSUMER_FIELD: &str = "consumer";
const ENUM_MEMBER_FIELD: &str = "enum_member";
const ENUM_REFERENCE_KIND: u8 = 0;

/// Identity, header column locations, authored query, contents, interpolation, declaration refs.
#[derive(pyo3::FromPyObject)]
struct ModelLoopRow(
    (String, String, String),
    Py<PyDict>,
    String,
    String,
    Option<String>,
    Option<DeclarationScan>,
);
/// `(kind, name, member, start, end)` per scanned reference, and the code the scan stopped on.
type DeclarationScan = (Vec<(u8, String, Option<String>, usize, usize)>, Option<u8>);
/// `(source start, source end, output start, output end)`.
type SpanRow = (usize, usize, usize, usize);
/// `(kind, name, package, call argument count)`.
type ReferenceRow = (String, String, Option<String>, Option<usize>);
/// The Python view of the model and its visible local enum and constant declarations.
type PlainInputPy<'py> = (
    Bound<'py, PyAny>,
    (Vec<DeclarationPy<'py>>, Vec<DeclarationPy<'py>>),
);

/// The ordered model loop of one compile-input stage.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeModelLoop {
    validator: Py<PyAny>,
    syntax: LexicalSyntax,
    reserved_markers: Vec<String>,
    python: PythonText,
    settings: ModelLoopSettings,
    contract_classes: Py<PyDict>,
    usage_record: Py<PyAny>,
}

/// One model as the loop finishes it: its row, effective config and visible enum names.
struct LoopModel<'a, 'py> {
    index: usize,
    row: &'a ModelLoopRow,
    config: Bound<'py, PyAny>,
    visible: &'a VisibleDeclarations<'py>,
    classes: &'a ContractClasses<'py>,
}

/// The declarations a model sees, the identity its usages are recorded for, and the host.
struct VisibleDeclarations<'py> {
    declarations: Bound<'py, PyAny>,
    consumer: Bound<'py, PyAny>,
    enum_names: Vec<String>,
    host: Bound<'py, PyAny>,
}

/// The declaration-expanded query, its spans and the usage records it adds.
struct ExpandedDeclarations<'py> {
    spliced: SplicedSql,
    usages: Vec<Bound<'py, PyAny>>,
}

/// What a model's header schema entry is attached from.
struct HeaderSource<'a, 'py> {
    values: &'a Bound<'py, PyDict>,
    locations: &'a Bound<'py, PyDict>,
    relative_path: &'a str,
    classes: &'a ContractClasses<'py>,
    enum_names: &'a [String],
    described: bool,
}

/// A header schema entry's Python columns and audits, type enforcement and retained fact.
struct HeaderSchema<'py> {
    columns: Bound<'py, PyTuple>,
    audits: Bound<'py, PyTuple>,
    type_enforcement: bool,
    fact: ModelSchemaFact,
}

/// What the native validator reads for one model.
struct Validation<'a, 'py> {
    config: &'a Bound<'py, PyAny>,
    values: &'a Bound<'py, PyDict>,
    model: (&'a str, &'a str, &'a str),
    references: &'a [ReferenceRow],
}

/// One model the native loop finished, before the host builds its Python view.
struct FinishedModel<'py> {
    config: Bound<'py, PyAny>,
    stripped: Bound<'py, PyDict>,
    query_sql: String,
    description: Option<String>,
    schema: Option<HeaderSchema<'py>>,
    references: Vec<ReferenceRow>,
    declarations: ExpandedDeclarations<'py>,
}

/// Where the header attachment stands for one model.
enum HeaderOutcome<'py> {
    Attached(Option<HeaderSchema<'py>>),
    NeedsAttachment,
}

#[pymethods]
impl NativeModelLoop {
    #[new]
    fn new(
        checks: (Py<PyAny>, Py<PyDict>, Py<PyAny>),
        syntax: LexicalSyntaxInput,
        cursor: (Vec<String>, ((u8, u8), String)),
        settings: (bool, bool, bool, bool),
    ) -> PyResult<Self> {
        let (validator, contract_classes, usage_record) = checks;
        let (reserved_markers, (python_version, unicode_version)) = cursor;
        let (sql_analysis, no_sql_validation, defer_sql_validation, legacy_schema_files) = settings;
        Ok(Self {
            validator,
            syntax: syntax.into(),
            reserved_markers,
            python: python_semantics(python_version, &unicode_version)?,
            settings: ModelLoopSettings {
                sql_analysis,
                no_sql_validation,
                defer_sql_validation,
                legacy_schema_files,
            },
            contract_classes,
            usage_record,
        })
    }

    /// Build every model in order into `project`; return the Python views and the native count.
    fn run<'py>(
        &self,
        py: Python<'py>,
        mut project: PyRefMut<'py, NativeCompiledProject>,
        host: Bound<'py, PyAny>,
        models: Vec<ModelLoopRow>,
    ) -> PyResult<(Vec<Bound<'py, PyAny>>, usize)> {
        let classes: ContractClasses<'py> = self.contract_classes.bind(py).extract()?;
        let mut inputs: Vec<Bound<'py, PyAny>> = Vec::with_capacity(models.len());
        let mut finished_natively: usize = 0;
        for (index, row) in models.into_iter().enumerate() {
            let index_argument = [(INDEX_ARGUMENT, index.into_pyobject(py)?.into_any())];
            let (config, declarations, consumer): (
                Bound<'py, PyAny>,
                Bound<'py, PyAny>,
                Bound<'py, PyAny>,
            ) = callback(&host, CONFIG_CALLBACK, &index_argument)?.extract()?;
            let visible: VisibleDeclarations<'py> = VisibleDeclarations {
                enum_names: declarations
                    .getattr(ENUMS_ATTRIBUTE)?
                    .downcast_into::<PyDict>()?
                    .keys()
                    .extract()?,
                declarations,
                consumer,
                host: host.clone(),
            };
            let model: LoopModel<'_, 'py> = LoopModel {
                index,
                row: &row,
                config,
                visible: &visible,
                classes: &classes,
            };
            let (input, facts) = match self.finish(py, model)? {
                Some(finished) => {
                    finished_natively += 1;
                    plain_input(&host, index, row, finished)?
                }
                None => attached_input(&host, &index_argument)?,
            };
            project.retain(facts);
            inputs.push(input);
        }
        Ok((inputs, finished_natively))
    }
}

impl NativeModelLoop {
    /// The model finished natively, or `None` when the Python attachment must finish it.
    fn finish<'py>(
        &self,
        py: Python<'py>,
        model: LoopModel<'_, 'py>,
    ) -> PyResult<Option<FinishedModel<'py>>> {
        let LoopModel {
            index,
            row,
            config,
            visible,
            classes,
        } = model;
        let ModelLoopRow(
            (name, _, relative_path),
            locations,
            _,
            _,
            interpolated_sql,
            declaration_scan,
        ) = row;
        let values: Bound<'py, PyDict> = config.getattr(VALUES_ATTRIBUTE)?.downcast_into()?;
        let check: PlainModelCheck = PlainModelCheck {
            config_keys: config_keys(&values)?,
            description: description_shape(&values)?,
            analysis_override: analysis_override(&values)?,
            interpolated_sql: interpolated_sql.clone(),
            declaration_scan_failed: declaration_scan
                .as_ref()
                .is_some_and(|(_, stop)| stop.is_some()),
            settings: self.settings,
        };
        let (None, Some(sql)) = (plain_model_blocker(&check), interpolated_sql) else {
            return Ok(None);
        };
        let references = declaration_scan
            .as_ref()
            .map_or(&[][..], |(refs, _)| refs.as_slice());
        let Some(declarations) = self.expand_declarations(py, visible, sql, references)? else {
            return Ok(None);
        };
        let (macro_sql, argument_references): (String, Vec<ReferenceRow>) =
            if calls_macros(&declarations.spliced.sql) {
                expand_macros(visible, index, &declarations.spliced)?
            } else {
                (declarations.spliced.sql.clone(), Vec::new())
            };
        let Ok(query_sql) = self.canonical_query(name, &macro_sql, &values)? else {
            return Ok(None);
        };
        let ReferenceExtraction::Extracted(scan) = extract_sql_references(&query_sql, &self.syntax)
        else {
            return Ok(None);
        };
        if !scan.invalid_calls.is_empty()
            || scan
                .references
                .iter()
                .any(|reference| reference.kind == DBT_REF_KIND)
        {
            return Ok(None);
        }
        let references: Vec<ReferenceRow> = merge_call_site_references(
            scan.references.iter().map(reference_row).collect(),
            argument_references,
        );
        let validation: Validation<'_, 'py> = Validation {
            config: &config,
            values: &values,
            model: (name, &query_sql, relative_path),
            references: &references,
        };
        if !self.validates(py, &validation)? {
            return Ok(None);
        }
        let description: Option<String> = match check.description {
            DescriptionShape::Text(description) => Some(description),
            DescriptionShape::Absent | DescriptionShape::Invalid => None,
        };
        let header: HeaderSource<'_, 'py> = HeaderSource {
            values: &values,
            locations: locations.bind(py),
            relative_path,
            classes,
            enum_names: &visible.enum_names,
            described: description.is_some(),
        };
        let HeaderOutcome::Attached(schema) = header_schema(py, &header)? else {
            return Ok(None);
        };
        Ok(Some(FinishedModel {
            stripped: stripped_values(py, &values)?,
            config,
            query_sql,
            description,
            schema,
            references,
            declarations,
        }))
    }

    /// Splice the scanned enum and constant references; `None` when the attachment reports one.
    fn expand_declarations<'py>(
        &self,
        py: Python<'py>,
        visible: &VisibleDeclarations<'py>,
        sql: &str,
        references: &[(u8, String, Option<String>, usize, usize)],
    ) -> PyResult<Option<ExpandedDeclarations<'py>>> {
        let mut splices: Vec<DeclarationSplice> = Vec::with_capacity(references.len());
        let mut usages: Vec<Bound<'py, PyAny>> = Vec::new();
        for (kind, name, member, start, end) in references {
            let resolved: Option<(String, Bound<'py, PyAny>)> = if *kind == ENUM_REFERENCE_KIND {
                enum_text(visible, name, member.as_deref())?
            } else {
                constant_text(visible, name)?
            };
            let Some((replacement, visibility)) = resolved else {
                return Ok(None);
            };
            for record in visibility.try_iter()? {
                usages.push(self.usage(py, visible, &record?, member.as_deref())?);
            }
            splices.push(DeclarationSplice {
                start: *start,
                end: *end,
                replacement,
            });
        }
        Ok(Some(ExpandedDeclarations {
            spliced: splice_declarations(sql, &splices),
            usages,
        }))
    }

    /// The usage a resolved reference records for one visibility record of the declaration.
    fn usage<'py>(
        &self,
        py: Python<'py>,
        visible: &VisibleDeclarations<'py>,
        record: &Bound<'py, PyAny>,
        member: Option<&str>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let fields: Bound<'py, PyDict> = PyDict::new(py);
        fields.set_item(CONSUMER_FIELD, &visible.consumer)?;
        fields.set_item(DECLARATION_FIELD, record.getattr(DECLARATION_FIELD)?)?;
        fields.set_item(THROUGH_FIELD, record.getattr(THROUGH_FIELD)?)?;
        fields.set_item(ENUM_MEMBER_FIELD, member)?;
        self.usage_record.bind(py).call((), Some(&fields))
    }

    /// The query with canonical cursor intrinsics, or the message the attachment raises.
    fn canonical_query(
        &self,
        name: &str,
        sql: &str,
        values: &Bound<'_, PyDict>,
    ) -> PyResult<Result<String, String>> {
        let incremental: bool = values
            .get_item(MATERIALIZED_KEY)?
            .is_some_and(|value| is_text(&value, INCREMENTAL_MATERIALIZATION));
        let cursor: Option<String> = match values.get_item(CURSOR_KEY)? {
            Some(value) => match value.downcast::<PyString>() {
                Ok(text) => Some(text.to_string_lossy().into_owned()),
                Err(_) => None,
            },
            None => None,
        };
        let model: IntrinsicModel<'_> = IntrinsicModel {
            name,
            incremental,
            cursor: cursor.as_deref(),
        };
        Ok(validated_model_intrinsics(
            self.python,
            sql,
            &self.reserved_markers,
            &model,
        ))
    }

    /// Whether the native validator accepts the model; a rejection is reported by Python.
    fn validates(&self, py: Python<'_>, validation: &Validation<'_, '_>) -> PyResult<bool> {
        let rows: Vec<(&str, &str, bool)> = validation
            .references
            .iter()
            .map(|(kind, name, _, _)| (kind.as_str(), name.as_str(), false))
            .collect();
        let unmanaged: Bound<'_, PyAny> = validation
            .config
            .getattr(RETENTION_ATTRIBUTE)?
            .getattr(UNMANAGED_ATTRIBUTE)?;
        let declared: Bound<'_, PyAny> = validation
            .config
            .getattr(TABLE_TYPE_ATTRIBUTE)?
            .getattr(DECLARED_ATTRIBUTE)?;
        let outcome: Bound<'_, PyAny> = self.validator.bind(py).call_method1(
            VALIDATE_METHOD,
            (
                validation.values.clone(),
                validation.model,
                (rows, py.None(), unmanaged, declared),
            ),
        )?;
        Ok(outcome.is_none())
    }
}

/// An enum member's literal and the enum's visibility, or `None` for an unknown enum or member.
fn enum_text<'py>(
    visible: &VisibleDeclarations<'py>,
    name: &str,
    member: Option<&str>,
) -> PyResult<Option<(String, Bound<'py, PyAny>)>> {
    let enums: Bound<'py, PyDict> = visible
        .declarations
        .getattr(ENUMS_ATTRIBUTE)?
        .downcast_into()?;
    let (Some(declaration), Some(member)) = (enums.get_item(name)?, member) else {
        return Ok(None);
    };
    for candidate in declaration.getattr(MEMBERS_ATTRIBUTE)?.try_iter()? {
        let candidate: Bound<'py, PyAny> = candidate?;
        if candidate.getattr(NAME_ATTRIBUTE)?.extract::<String>()? != member {
            continue;
        }
        let value: Bound<'py, PyAny> = candidate.getattr(VALUE_ATTRIBUTE)?;
        let literal: String =
            enum_member_literal(&value.str()?.to_string(), value.is_instance_of::<PyInt>());
        return Ok(Some((
            literal,
            visibility(visible, ENUM_VISIBILITY_ATTRIBUTE, name)?,
        )));
    }
    Ok(None)
}

/// A constant rendered by the adapter and its visibility, or `None` for an unknown constant.
fn constant_text<'py>(
    visible: &VisibleDeclarations<'py>,
    name: &str,
) -> PyResult<Option<(String, Bound<'py, PyAny>)>> {
    let constants: Bound<'py, PyDict> = visible
        .declarations
        .getattr(CONSTANTS_ATTRIBUTE)?
        .downcast_into()?;
    let Some(declaration) = constants.get_item(name)? else {
        return Ok(None);
    };
    let rendered: String = callback(
        &visible.host,
        CONSTANT_TEXT_CALLBACK,
        &[(DECLARATION_ARGUMENT, declaration)],
    )?
    .extract()?;
    Ok(Some((
        rendered,
        visibility(visible, CONSTANT_VISIBILITY_ATTRIBUTE, name)?,
    )))
}

fn visibility<'py>(
    visible: &VisibleDeclarations<'py>,
    attribute: &str,
    name: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let records: Bound<'py, PyDict> = visible.declarations.getattr(attribute)?.downcast_into()?;
    Ok(records
        .get_item(name)?
        .unwrap_or_else(|| PyTuple::empty(records.py()).into_any()))
}

/// The header's schema entry, parsed by the native header parser the attachment uses.
fn header_schema<'py>(
    py: Python<'py>,
    header: &HeaderSource<'_, 'py>,
) -> PyResult<HeaderOutcome<'py>> {
    let columns: Option<Bound<'py, PyAny>> = present(header.values, COLUMNS_KEY)?;
    let audits: Option<Bound<'py, PyAny>> = present(header.values, AUDITS_KEY)?;
    if !header.described && columns.is_none() && audits.is_none() {
        return Ok(HeaderOutcome::Attached(None));
    }
    let none: Bound<'py, PyAny> = py.None().into_bound(py);
    let columns_node: PyNode<'py> = PyNode(columns.unwrap_or_else(|| none.clone()));
    let audits_node: PyNode<'py> = PyNode(audits.unwrap_or(none));
    let metadata = parse_header_metadata(&columns_node, &audits_node, header.relative_path);
    let (Ok(parsed_columns), Ok(parsed_audits)) = (metadata.columns, metadata.audits) else {
        return Ok(HeaderOutcome::NeedsAttachment);
    };
    let shapes: Vec<HeaderColumnShape> = parsed_columns
        .iter()
        .map(column_shape)
        .collect::<PyResult<_>>()?;
    if header_column_blocker(&shapes, header.enum_names).is_some() {
        return Ok(HeaderOutcome::NeedsAttachment);
    }
    let fact: ModelSchemaFact = schema_fact(&parsed_columns, &parsed_audits)?;
    Ok(HeaderOutcome::Attached(Some(HeaderSchema {
        columns: column_tuple(py, header.classes, &parsed_columns, header.locations)?,
        audits: audit_tuple(py, header.classes, &parsed_audits)?,
        type_enforcement: shapes.iter().any(|shape| shape.column_type.is_some()),
        fact,
    })))
}

fn schema_fact(
    columns: &[ParsedColumn<PyNode<'_>>],
    audits: &[ParsedAudit<PyNode<'_>>],
) -> PyResult<ModelSchemaFact> {
    Ok(ModelSchemaFact {
        audit_count: u32::try_from(audits.len()).unwrap_or(u32::MAX),
        columns: columns.iter().map(column_fact).collect::<PyResult<_>>()?,
        dynamic_columns: Vec::new(),
    })
}

fn column_fact(column: &ParsedColumn<PyNode<'_>>) -> PyResult<SchemaColumnFact> {
    Ok(SchemaColumnFact {
        name: column.name.0.str()?.to_string(),
        data_type: optional_text(column.column_type.as_ref())?,
        nullable: match &column.nullable {
            Some(node) if !node.0.is_none() => Some(node.0.is_truthy()?),
            _ => None,
        },
        audit_count: u32::try_from(column.audits.len()).unwrap_or(u32::MAX),
    })
}

fn column_shape(column: &ParsedColumn<PyNode<'_>>) -> PyResult<HeaderColumnShape> {
    Ok(HeaderColumnShape {
        column_type: optional_text(column.column_type.as_ref())?,
        migrates: column
            .migrate_from
            .as_ref()
            .is_some_and(|node| !node.0.is_none()),
    })
}

fn optional_text(node: Option<&PyNode<'_>>) -> PyResult<Option<String>> {
    match node {
        Some(node) if !node.0.is_none() => Ok(Some(node.0.str()?.to_string())),
        _ => Ok(None),
    }
}

/// The schema argument the host builds its `SchemaModelEntry` from.
fn schema_argument<'py>(
    py: Python<'py>,
    schema: Option<&HeaderSchema<'py>>,
) -> PyResult<Bound<'py, PyAny>> {
    match schema {
        Some(schema) => Ok((
            schema.columns.clone(),
            schema.audits.clone(),
            schema.type_enforcement,
        )
            .into_pyobject(py)?
            .into_any()),
        None => Ok(py.None().into_bound(py)),
    }
}

/// The host's Python view of a natively finished model, and the facts the project retains.
fn plain_input<'py>(
    host: &Bound<'py, PyAny>,
    index: usize,
    row: ModelLoopRow,
    finished: FinishedModel<'py>,
) -> PyResult<(Bound<'py, PyAny>, CompiledModelFacts)> {
    let py: Python<'py> = host.py();
    let ModelLoopRow((name, relative_path, _), _, authored_query_sql, authored_sql, _, _) = row;
    let arguments = [
        (INDEX_ARGUMENT, index.into_pyobject(py)?.into_any()),
        (VALUES_ARGUMENT, finished.stripped.clone().into_any()),
        (
            REFERENCES_ARGUMENT,
            finished.references.clone().into_pyobject(py)?,
        ),
        (
            QUERY_SQL_ARGUMENT,
            finished.query_sql.as_str().into_pyobject(py)?.into_any(),
        ),
        (
            DESCRIPTION_ARGUMENT,
            finished.description.as_deref().into_pyobject(py)?,
        ),
        (
            SCHEMA_ARGUMENT,
            schema_argument(py, finished.schema.as_ref())?,
        ),
        (
            DECLARATIONS_ARGUMENT,
            (
                finished.declarations.spliced.sql.as_str(),
                span_rows(&finished.declarations.spliced),
                finished.declarations.usages,
            )
                .into_pyobject(py)?
                .into_any(),
        ),
    ];
    let (input, (enums, constants)): PlainInputPy<'py> =
        callback(host, PLAIN_INPUT_CALLBACK, &arguments)?.extract()?;
    let (values, encoding_error) = config_values(&finished.stripped);
    let facts: CompiledModelFacts = plain_model_facts(PlainModel {
        name,
        relative_path,
        query_sql: finished.query_sql,
        authored_query_sql,
        authored_sql,
        config: ModelConfigFacts {
            values,
            encoding_error,
            header_keys: finished.config.getattr(HEADER_KEYS_ATTRIBUTE)?.extract()?,
            layer_schema: finished.config.getattr(LAYER_SCHEMA_ATTRIBUTE)?.extract()?,
        },
        schema: finished.schema.map(|schema| schema.fact),
        references: finished
            .references
            .into_iter()
            .map(reference_fact)
            .collect(),
        enum_declarations: declarations(enums)?,
        constant_declarations: declarations(constants)?,
    });
    Ok((input, facts))
}

/// The attachment's model input, after all its callbacks ran, and the facts read from it.
fn attached_input<'py>(
    host: &Bound<'py, PyAny>,
    index_argument: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<(Bound<'py, PyAny>, CompiledModelFacts)> {
    let input: Bound<'py, PyAny> = callback(host, FALLBACK_CALLBACK, index_argument)?;
    let row: ModelInputPy<'_> = callback(
        host,
        MODEL_ROW_CALLBACK,
        &[(MODEL_INPUT_ARGUMENT, input.clone())],
    )?
    .extract()?;
    Ok((input, model_facts(row)?))
}

/// Call a host callback with keyword arguments, as its keyword-only signature requires.
fn callback<'py>(
    host: &Bound<'py, PyAny>,
    name: &str,
    arguments: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    let keywords: Bound<'py, PyDict> = PyDict::new(host.py());
    for (key, value) in arguments {
        keywords.set_item(*key, value)?;
    }
    host.call_method(name, (), Some(&keywords))
}

fn span_rows(spliced: &SplicedSql) -> Vec<SpanRow> {
    spliced
        .spans
        .iter()
        .map(|span| {
            (
                span.source_start,
                span.source_end,
                span.output_start,
                span.output_end,
            )
        })
        .collect()
}

fn reference_row(reference: &SqlReference) -> ReferenceRow {
    (
        reference.kind.to_owned(),
        reference.name.clone(),
        reference.package.clone(),
        reference.call_argument_count,
    )
}

fn reference_fact((kind, name, package, _): ReferenceRow) -> ModelReferenceFact {
    ModelReferenceFact {
        kind,
        name,
        package,
    }
}

/// Expand the model's macro calls through the host, which runs the project's macros.
fn expand_macros(
    visible: &VisibleDeclarations<'_>,
    index: usize,
    spliced: &SplicedSql,
) -> PyResult<(String, Vec<ReferenceRow>)> {
    let py = visible.host.py();
    callback(
        &visible.host,
        EXPAND_MACROS_CALLBACK,
        &[
            (INDEX_ARGUMENT, index.into_pyobject(py)?.into_any()),
            (
                SQL_ARGUMENT,
                spliced.sql.as_str().into_pyobject(py)?.into_any(),
            ),
            (SPANS_ARGUMENT, span_rows(spliced).into_pyobject(py)?),
        ],
    )?
    .extract()
}

fn config_keys(values: &Bound<'_, PyDict>) -> PyResult<Vec<String>> {
    let mut keys: Vec<String> = Vec::with_capacity(values.len());
    for key in values.keys() {
        keys.push(key.str()?.to_string());
    }
    Ok(keys)
}

/// The config without header metadata, always a new dictionary as hook expansion leaves it.
fn stripped_values<'py>(
    py: Python<'py>,
    values: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let stripped: Bound<'py, PyDict> = PyDict::new(py);
    for (key, value) in values.iter() {
        if !is_header_metadata_key(&key.str()?.to_string()) {
            stripped.set_item(key, value)?;
        }
    }
    Ok(stripped)
}

/// Absent, a non-blank string by Python's `str.strip`, or anything the attachment rejects.
fn description_shape(values: &Bound<'_, PyDict>) -> PyResult<DescriptionShape> {
    let Some(value) = values.get_item(DESCRIPTION_KEY)? else {
        return Ok(DescriptionShape::Absent);
    };
    if value.is_none() {
        return Ok(DescriptionShape::Absent);
    }
    let Ok(text) = value.downcast::<PyString>() else {
        return Ok(DescriptionShape::Invalid);
    };
    if text.call_method0(STRIP_METHOD)?.is_truthy()? {
        Ok(DescriptionShape::Text(text.to_str()?.to_owned()))
    } else {
        Ok(DescriptionShape::Invalid)
    }
}

fn analysis_override(values: &Bound<'_, PyDict>) -> PyResult<AnalysisOverride> {
    let analysis: Option<Bound<'_, PyAny>> = present(values, SQL_ANALYSIS_KEY)?;
    let legacy: Option<Bound<'_, PyAny>> = present(values, SQL_VALIDATION_KEY)?;
    Ok(match (analysis, legacy) {
        (Some(_), Some(_)) => AnalysisOverride::Ambiguous,
        (Some(value), None) | (None, Some(value)) => match value.downcast::<PyBool>() {
            Ok(flag) if flag.is_true() => AnalysisOverride::Enabled,
            Ok(_) => AnalysisOverride::Disabled,
            Err(_) => AnalysisOverride::Inherit,
        },
        (None, None) => AnalysisOverride::Inherit,
    })
}

/// The value under `key`, treating an explicit `None` as absent.
fn present<'py>(values: &Bound<'py, PyDict>, key: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
    Ok(values.get_item(key)?.filter(|value| !value.is_none()))
}

fn is_text(value: &Bound<'_, PyAny>, expected: &str) -> bool {
    value
        .downcast::<PyString>()
        .is_ok_and(|text| text.to_string_lossy() == expected)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeModelLoop>()
}
