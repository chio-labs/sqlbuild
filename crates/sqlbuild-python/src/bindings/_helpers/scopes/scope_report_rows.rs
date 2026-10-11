//! Rows of scope report requests and results, in both directions across the boundary.

use pyo3::IntoPyObjectExt;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{
    PyBool, PyBoolMethods, PyDict, PyDictMethods, PyFloat, PyInt, PyList, PyString, PyTuple,
    PyTypeMethods,
};
use sqlbuild_core::json::models::{JsonInteger, JsonValue};
use sqlbuild_scopes::scope_index::main::format_identity::format_identity;
use sqlbuild_scopes::scope_index::models::QualifiedIdentity;
use sqlbuild_scopes::scope_report::models::{
    BrowseResult, Completeness, ConstantValues, DeclarationReport, DeclarationTarget,
    DeclarationValues, DiagnosticFacts, EnumValues, Explanation, ListResult, MacroValues,
    MovePreview, Provenance, QueryTarget, ReportDiagnostic, ReportFilters, ResourceReport,
    ScopeChainEntry, ScopeFolder, ScopeReport, ScopeSection, SourceLocation,
};

use crate::bindings::_helpers::scopes::placement::{
    IdentityRow, QualifiedRow, declaration_identity, qualified_identity, resource_identity,
};

type PyObject = Py<PyAny>;

/// A query target: an identity row, else text, and whether the text came from a `PurePath`.
pub(crate) type TargetRow = (Option<QualifiedRow>, String, bool);
/// Every `ScopeReportFilters` field in order.
pub(crate) type FiltersRow = (
    Vec<String>,
    bool,
    Option<String>,
    Vec<String>,
    Option<String>,
    bool,
    i64,
    String,
    Option<String>,
    i64,
    i64,
    String,
);
/// Parameters, dependencies and source digest.
type MacroRow = (Vec<String>, Vec<QualifiedRow>, String);
/// Member names and scalar type.
type EnumRow = (Vec<String>, String);
/// Logical type, collection kind, item count, nullable and render-as.
type ConstantRow = (String, Option<String>, Option<i64>, bool, Option<String>);
pub(crate) type ValuesRow = (Option<MacroRow>, Option<EnumRow>, Option<ConstantRow>);
pub(crate) type CompletenessRow = (bool, bool, bool, bool, bool, bool);
/// Code, message, severity, path, line, column, declaration and resource identities.
pub(crate) type DiagnosticInRow = (
    String,
    String,
    String,
    Option<String>,
    Option<i64>,
    Option<i64>,
    Option<QualifiedRow>,
    Option<IdentityRow>,
);
/// An index diagnostic's canonical position, else a raised `(code, message, path)`.
type DiagnosticOutRow = (Option<usize>, Option<(String, String, Option<String>)>);
/// Identity, kind, name, owner, definition, scope and owning path.
type HeadRow = (
    String,
    String,
    String,
    Option<String>,
    (String, i64, i64),
    String,
    Option<String>,
);
/// Visibility, inaccessible reason and metadata entries.
type StandingRow<M> = (
    Option<(String, Option<String>)>,
    Option<String>,
    Vec<(String, M)>,
);
/// Consumers, dependencies, grants, required scope, required path and promotion impact.
type LinksRow = (
    Vec<String>,
    Vec<String>,
    Vec<String>,
    Option<String>,
    Option<String>,
    Vec<String>,
);
pub(crate) type DeclarationRow<M> = (HeadRow, StandingRow<M>, LinksRow);
type SectionRow = (
    String,
    i64,
    i64,
    bool,
    i64,
    bool,
    bool,
    Option<String>,
    Option<String>,
    i64,
);
type ResourceReportRow = (String, Option<String>, Option<String>, bool, bool, i64);
type ChainRow = (String, String, i64);
type ExplanationRow<M> = (Option<DeclarationRow<M>>, bool);
/// Every `MovePreview` field in order.
type MoveRow<M> = (
    String,
    String,
    Option<String>,
    Vec<DeclarationRow<M>>,
    Vec<DeclarationRow<M>>,
    Vec<DeclarationRow<M>>,
    Vec<String>,
    Vec<DeclarationRow<M>>,
    Vec<DeclarationRow<M>>,
    bool,
);
type FolderRow = (String, String, i64, i64, i64, Vec<(String, i64)>);
/// Every `ScopeReport` field in order.
pub(crate) type ReportRow<M, D> = (
    ResourceReportRow,
    Vec<ChainRow>,
    Vec<DeclarationRow<M>>,
    Vec<DeclarationRow<M>>,
    Vec<DeclarationRow<M>>,
    Vec<DeclarationRow<M>>,
    FiltersRow,
    Vec<SectionRow>,
    Option<ExplanationRow<M>>,
    Option<MoveRow<M>>,
    Vec<D>,
    bool,
);
pub(crate) type BrowseRow<D> = (String, Vec<FolderRow>, Vec<D>, bool);
pub(crate) type ListRow<M, D> = (String, Vec<DeclarationRow<M>>, SectionRow, Vec<D>);
pub(crate) type ExplanationOutRow = (ExplanationRow<PyObject>, Vec<DiagnosticOutRow>);
pub(crate) type MoveOutRow = (Option<MoveRow<PyObject>>, Vec<DiagnosticOutRow>);
pub(crate) type ReportOutRow = ReportRow<PyObject, DiagnosticOutRow>;
pub(crate) type BrowseOutRow = BrowseRow<DiagnosticOutRow>;
pub(crate) type ListOutRow = ListRow<PyObject, DiagnosticOutRow>;

pub(crate) fn target(row: TargetRow) -> PyResult<QueryTarget> {
    let (identity, text, path) = row;
    Ok(match (identity, path) {
        (Some(identity), _) => QueryTarget::Identity(qualified_identity(identity)?),
        (None, true) => QueryTarget::Path(text),
        (None, false) => QueryTarget::Text(text),
    })
}

pub(crate) fn declaration_target(
    (identity, text): (Option<QualifiedRow>, String),
) -> PyResult<DeclarationTarget> {
    Ok(match identity {
        Some(identity) => DeclarationTarget::Identity(declaration_identity(identity)?),
        None => DeclarationTarget::Text(text),
    })
}

pub(crate) fn filters(row: FiltersRow) -> ReportFilters {
    let (
        sections,
        include_nearby,
        defined_under,
        kinds,
        glob,
        used_only,
        dependency_depth,
        sort,
        cursor,
        page_size,
        nearby_depth,
        globals,
    ) = row;
    ReportFilters {
        sections,
        include_nearby,
        defined_under,
        kinds,
        glob,
        used_only,
        dependency_depth,
        sort,
        cursor,
        page_size,
        nearby_depth,
        globals,
    }
}

fn filters_row(filters: &ReportFilters) -> FiltersRow {
    (
        filters.sections.clone(),
        filters.include_nearby,
        filters.defined_under.clone(),
        filters.kinds.clone(),
        filters.glob.clone(),
        filters.used_only,
        filters.dependency_depth,
        filters.sort.clone(),
        filters.cursor.clone(),
        filters.page_size,
        filters.nearby_depth,
        filters.globals.clone(),
    )
}

pub(crate) fn declaration_values(row: ValuesRow) -> PyResult<DeclarationValues> {
    let (macro_row, enum_row, constant_row) = row;
    Ok(DeclarationValues {
        macro_values: match macro_row {
            Some((parameters, dependencies, source_digest)) => Some(MacroValues {
                parameters,
                dependencies: dependencies
                    .into_iter()
                    .map(declaration_identity)
                    .collect::<PyResult<_>>()?,
                source_digest,
            }),
            None => None,
        },
        enum_values: enum_row.map(|(members, scalar_type)| EnumValues {
            members,
            scalar_type,
        }),
        constant_values: constant_row.map(
            |(logical_type, collection_kind, item_count, nullable, render_as)| ConstantValues {
                logical_type,
                collection_kind,
                item_count,
                nullable,
                render_as,
            },
        ),
    })
}

pub(crate) fn completeness(row: CompletenessRow) -> Completeness {
    let (discovery, static_visibility, runtime_usage, relationships, placement, promotion_impact) =
        row;
    Completeness {
        discovery,
        static_visibility,
        runtime_usage,
        relationships,
        placement,
        promotion_impact,
    }
}

/// A diagnostic row's facts, with its identities as qualified text.
pub(crate) fn diagnostic_facts(row: DiagnosticInRow) -> PyResult<DiagnosticFacts> {
    let (code, message, severity, path, line, column, declaration, resource) = row;
    Ok(DiagnosticFacts {
        code,
        message,
        severity,
        path,
        line,
        column,
        declaration: match declaration {
            Some(row) => Some(format_identity(&QualifiedIdentity::Declaration(
                declaration_identity(row)?,
            ))),
            None => None,
        },
        resource: match resource {
            Some(row) => Some(format_identity(&QualifiedIdentity::Resource(
                resource_identity(row)?,
            ))),
            None => None,
        },
    })
}

fn diagnostic_out(diagnostic: ReportDiagnostic) -> DiagnosticOutRow {
    match diagnostic {
        ReportDiagnostic::Index(position) => (Some(position), None),
        ReportDiagnostic::Raised(facts) => (None, Some((facts.code, facts.message, facts.path))),
    }
}

pub(crate) fn raised_out(diagnostics: Vec<DiagnosticFacts>) -> Vec<DiagnosticOutRow> {
    diagnostics
        .into_iter()
        .map(|facts| diagnostic_out(ReportDiagnostic::Raised(facts)))
        .collect()
}

/// A JSON value as Python builds it; arrays become tuples or lists.
pub(crate) fn json_to_python(py: Python<'_>, value: JsonValue, tuples: bool) -> PyResult<PyObject> {
    match value {
        JsonValue::Null => Ok(py.None()),
        JsonValue::Bool(flag) => flag.into_py_any(py),
        JsonValue::Integer(integer) => match integer.to_i128() {
            Some(number) => number.into_py_any(py),
            None => Ok(py
                .import("builtins")?
                .getattr("int")?
                .call1((integer.as_str(),))?
                .unbind()),
        },
        JsonValue::Float(number) => number.into_py_any(py),
        JsonValue::String(text) => text.into_py_any(py),
        JsonValue::Utf16(units) => String::from_utf16_lossy(&units).into_py_any(py),
        JsonValue::Array(items) => {
            let values: Vec<PyObject> = items
                .into_iter()
                .map(|item| json_to_python(py, item, tuples))
                .collect::<PyResult<_>>()?;
            if tuples {
                PyTuple::new(py, values)?.into_py_any(py)
            } else {
                PyList::new(py, values)?.into_py_any(py)
            }
        }
        JsonValue::Object(entries) => {
            let dictionary: Bound<'_, PyDict> = PyDict::new(py);
            for (key, item) in entries {
                dictionary.set_item(key, json_to_python(py, item, tuples)?)?;
            }
            dictionary.into_py_any(py)
        }
    }
}

/// `_value` of one metadata value; an unsupported type is the error Python's serializer raises.
pub(crate) fn python_to_json(value: &Bound<'_, PyAny>) -> PyResult<JsonValue> {
    if value.is_none() {
        return Ok(JsonValue::Null);
    }
    if let Ok(flag) = value.downcast::<PyBool>() {
        return Ok(JsonValue::Bool(flag.is_true()));
    }
    let py: Python<'_> = value.py();
    if py
        .import("enum")?
        .getattr("Enum")
        .and_then(|enum_type| value.is_instance(&enum_type))?
    {
        return python_to_json(&value.getattr("value")?);
    }
    if value.is_instance_of::<PyInt>() {
        let decimal: String = value.str()?.extract()?;
        return JsonInteger::parse(&decimal)
            .map(JsonValue::Integer)
            .ok_or_else(|| PyValueError::new_err("Unsupported scope report value: int"));
    }
    if value.is_instance_of::<PyFloat>() {
        return Ok(JsonValue::Float(value.extract::<f64>()?));
    }
    if value.is_instance_of::<PyString>() {
        return Ok(JsonValue::String(value.extract()?));
    }
    let pure_path = py.import("pathlib")?.getattr("PurePath")?;
    if value.is_instance(&pure_path)? {
        return Ok(JsonValue::String(
            value.call_method0("as_posix")?.extract()?,
        ));
    }
    if value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>() {
        let mut items: Vec<JsonValue> = Vec::new();
        for item in value.try_iter()? {
            items.push(python_to_json(&item?)?);
        }
        return Ok(JsonValue::Array(items));
    }
    if let Ok(mapping) = value.downcast::<PyDict>() {
        let mut entries: Vec<(String, JsonValue)> = Vec::new();
        for (key, item) in mapping.iter() {
            entries.push((key.str()?.extract()?, python_to_json(&item)?));
        }
        return Ok(JsonValue::Object(entries));
    }
    let name: String = value.get_type().name()?.extract()?;
    Err(PyValueError::new_err(format!(
        "Unsupported scope report value: {name}"
    )))
}

/// `{str(key): value}` with later duplicate keys replacing earlier values in place.
fn unique_entries(entries: Vec<(String, JsonValue)>) -> Vec<(String, JsonValue)> {
    let mut unique: Vec<(String, JsonValue)> = Vec::with_capacity(entries.len());
    for (key, value) in entries {
        match unique.iter_mut().find(|(existing, _)| *existing == key) {
            Some(entry) => entry.1 = value,
            None => unique.push((key, value)),
        }
    }
    unique
}

pub(crate) fn declaration_out(
    py: Python<'_>,
    report: DeclarationReport,
) -> PyResult<DeclarationRow<PyObject>> {
    let metadata: Vec<(String, PyObject)> = report
        .metadata
        .into_iter()
        .map(|(key, value)| Ok((key, json_to_python(py, value, true)?)))
        .collect::<PyResult<_>>()?;
    Ok((
        (
            report.identity,
            report.kind,
            report.name,
            report.owner,
            (
                report.definition.path,
                report.definition.line,
                report.definition.column,
            ),
            report.scope,
            report.owning_path,
        ),
        (
            report
                .visibility
                .map(|provenance| (provenance.reason, provenance.through)),
            report.inaccessible_reason,
            metadata,
        ),
        (
            report.consumers,
            report.dependencies,
            report.grants,
            report.required_scope,
            report.required_path,
            report.promotion_impact,
        ),
    ))
}

pub(crate) fn declaration_in(row: DeclarationRow<Bound<'_, PyAny>>) -> PyResult<DeclarationReport> {
    let (
        (identity, kind, name, owner, (path, line, column), scope, owning_path),
        (visibility, inaccessible_reason, metadata),
        (consumers, dependencies, grants, required_scope, required_path, promotion_impact),
    ) = row;
    let metadata: Vec<(String, JsonValue)> = metadata
        .into_iter()
        .map(|(key, value)| Ok((key, python_to_json(&value)?)))
        .collect::<PyResult<_>>()?;
    Ok(DeclarationReport {
        identity,
        kind,
        name,
        owner,
        definition: SourceLocation { path, line, column },
        scope,
        owning_path,
        visibility: visibility.map(|(reason, through)| Provenance { reason, through }),
        inaccessible_reason,
        metadata: unique_entries(metadata),
        consumers,
        dependencies,
        grants,
        required_scope,
        required_path,
        promotion_impact,
    })
}

fn declarations_out(
    py: Python<'_>,
    reports: Vec<DeclarationReport>,
) -> PyResult<Vec<DeclarationRow<PyObject>>> {
    reports
        .into_iter()
        .map(|report| declaration_out(py, report))
        .collect()
}

fn declarations_in(
    rows: Vec<DeclarationRow<Bound<'_, PyAny>>>,
) -> PyResult<Vec<DeclarationReport>> {
    rows.into_iter().map(declaration_in).collect()
}

fn section_row(section: ScopeSection) -> SectionRow {
    (
        section.name,
        section.total,
        section.returned,
        section.collapsed,
        section.collapsed_count,
        section.truncated,
        section.complete,
        section.next_cursor,
        section.cursor,
        section.page_size,
    )
}

fn section_in(row: SectionRow) -> ScopeSection {
    let (
        name,
        total,
        returned,
        collapsed,
        collapsed_count,
        truncated,
        complete,
        next_cursor,
        cursor,
        page_size,
    ) = row;
    ScopeSection {
        name,
        total,
        returned,
        collapsed,
        collapsed_count,
        truncated,
        complete,
        next_cursor,
        cursor,
        page_size,
    }
}

fn folder_row(folder: ScopeFolder) -> FolderRow {
    (
        folder.path,
        folder.name,
        folder.descendant_count,
        folder.child_count,
        folder.used_count,
        folder.kind_counts,
    )
}

fn folder_in(row: FolderRow) -> ScopeFolder {
    let (path, name, descendant_count, child_count, used_count, kind_counts) = row;
    let mut unique: Vec<(String, i64)> = Vec::with_capacity(kind_counts.len());
    for (kind, count) in kind_counts {
        match unique.iter_mut().find(|(existing, _)| *existing == kind) {
            Some(entry) => entry.1 = count,
            None => unique.push((kind, count)),
        }
    }
    ScopeFolder {
        path,
        name,
        descendant_count,
        child_count,
        used_count,
        kind_counts: unique,
    }
}

pub(crate) fn explanation_out(
    py: Python<'_>,
    explanation: Explanation,
) -> PyResult<ExplanationRow<PyObject>> {
    Ok((
        explanation
            .declaration
            .map(|report| declaration_out(py, report))
            .transpose()?,
        explanation.complete,
    ))
}

fn explanation_in(row: ExplanationRow<Bound<'_, PyAny>>) -> PyResult<Explanation> {
    Ok(Explanation {
        declaration: row.0.map(declaration_in).transpose()?,
        complete: row.1,
    })
}

pub(crate) fn move_out(py: Python<'_>, preview: MovePreview) -> PyResult<MoveRow<PyObject>> {
    Ok((
        preview.resource,
        preview.destination,
        preview.new_ownership_root,
        declarations_out(py, preview.retained)?,
        declarations_out(py, preview.gained)?,
        declarations_out(py, preview.lost)?,
        preview.invalidated_usages,
        declarations_out(py, preview.private_retained)?,
        declarations_out(py, preview.relationship_retained)?,
        preview.complete,
    ))
}

fn move_in(row: MoveRow<Bound<'_, PyAny>>) -> PyResult<MovePreview> {
    let (
        resource,
        destination,
        new_ownership_root,
        retained,
        gained,
        lost,
        invalidated_usages,
        private_retained,
        relationship_retained,
        complete,
    ) = row;
    Ok(MovePreview {
        resource,
        destination,
        new_ownership_root,
        retained: declarations_in(retained)?,
        gained: declarations_in(gained)?,
        lost: declarations_in(lost)?,
        invalidated_usages,
        private_retained: declarations_in(private_retained)?,
        relationship_retained: declarations_in(relationship_retained)?,
        complete,
    })
}

fn resource_row(resource: ResourceReport) -> ResourceReportRow {
    (
        resource.target,
        resource.identity,
        resource.path,
        resource.prospective,
        resource.directory,
        resource.duplicate_count,
    )
}

fn chain_row(entry: ScopeChainEntry) -> ChainRow {
    (entry.kind, entry.path, entry.declaration_count)
}

pub(crate) fn report_out(py: Python<'_>, report: ScopeReport) -> PyResult<ReportOutRow> {
    Ok((
        resource_row(report.resource),
        report.scope_chain.into_iter().map(chain_row).collect(),
        declarations_out(py, report.available)?,
        declarations_out(py, report.used)?,
        declarations_out(py, report.relationship_scope)?,
        declarations_out(py, report.nearby_unavailable)?,
        filters_row(&report.filters),
        report.sections.into_iter().map(section_row).collect(),
        report
            .explanation
            .map(|explanation| explanation_out(py, explanation))
            .transpose()?,
        report
            .move_preview
            .map(|preview| move_out(py, preview))
            .transpose()?,
        report.diagnostics.into_iter().map(diagnostic_out).collect(),
        report.complete,
    ))
}

pub(crate) fn report_in(
    row: ReportRow<Bound<'_, PyAny>, DiagnosticInRow>,
) -> PyResult<ScopeReport> {
    let (
        (target, identity, path, prospective, directory, duplicate_count),
        chain,
        available,
        used,
        relationship_scope,
        nearby_unavailable,
        filter_row,
        sections,
        explanation,
        move_preview,
        diagnostics,
        complete,
    ) = row;
    Ok(ScopeReport {
        resource: ResourceReport {
            target,
            identity,
            path,
            prospective,
            directory,
            duplicate_count,
        },
        scope_chain: chain
            .into_iter()
            .map(|(kind, path, declaration_count)| ScopeChainEntry {
                kind,
                path,
                declaration_count,
            })
            .collect(),
        available: declarations_in(available)?,
        used: declarations_in(used)?,
        relationship_scope: declarations_in(relationship_scope)?,
        nearby_unavailable: declarations_in(nearby_unavailable)?,
        filters: filters(filter_row),
        sections: sections.into_iter().map(section_in).collect(),
        explanation: explanation.map(explanation_in).transpose()?,
        move_preview: move_preview.map(move_in).transpose()?,
        diagnostics: diagnostics_in(diagnostics)?,
        complete,
    })
}

fn diagnostics_in(rows: Vec<DiagnosticInRow>) -> PyResult<Vec<ReportDiagnostic>> {
    rows.into_iter()
        .map(|row| Ok(ReportDiagnostic::Raised(diagnostic_facts(row)?)))
        .collect()
}

pub(crate) fn browse_out(result: BrowseResult) -> BrowseOutRow {
    (
        result.folder,
        result.folders.into_iter().map(folder_row).collect(),
        result.diagnostics.into_iter().map(diagnostic_out).collect(),
        result.complete,
    )
}

pub(crate) fn browse_in(row: BrowseRow<DiagnosticInRow>) -> PyResult<BrowseResult> {
    let (folder, folders, diagnostics, complete) = row;
    Ok(BrowseResult {
        folder,
        folders: folders.into_iter().map(folder_in).collect(),
        diagnostics: diagnostics_in(diagnostics)?,
        complete,
    })
}

pub(crate) fn list_out(py: Python<'_>, result: ListResult) -> PyResult<ListOutRow> {
    Ok((
        result.folder,
        declarations_out(py, result.declarations)?,
        section_row(result.section),
        result.diagnostics.into_iter().map(diagnostic_out).collect(),
    ))
}

pub(crate) fn list_in(row: ListRow<Bound<'_, PyAny>, DiagnosticInRow>) -> PyResult<ListResult> {
    let (folder, declarations, section, diagnostics) = row;
    Ok(ListResult {
        folder,
        declarations: declarations_in(declarations)?,
        section: section_in(section),
        diagnostics: diagnostics_in(diagnostics)?,
    })
}
