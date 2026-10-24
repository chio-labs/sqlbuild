//! Enum and constant references expanded natively, for model queries and every other caller.

use crate::bindings::_helpers::render::macro_call_rows::SpanRow;
use pyo3::FromPyObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyInt, PyTuple};
use sqlbuild_analysis::compiled_project::errors::DeclarationError;
use sqlbuild_analysis::compiled_project::main::declaration_error_message::declaration_error_message;
use sqlbuild_analysis::compiled_project::main::enum_member_literal::enum_member_literal;
use sqlbuild_analysis::compiled_project::main::splice_declarations::splice_declarations;
use sqlbuild_analysis::compiled_project::models::{
    DeclarationSplice, InaccessibleDeclaration, SplicedSql,
};
use sqlbuild_analysis::sql_macros::models::{ExpandedText, SqlMacroCheck, TypedCall};

use crate::bindings::_helpers::render::declaration_values::ConstantRendering;
use crate::bindings::_helpers::render::sql_macro_host::{
    SqlMacroSource, expanded_sql_macro_calls, is_sql_macro_reference, reject_bare_macro_calls,
};
use crate::bindings::_helpers::sqltext::declaration_references::ScannedReference;

const ENUM_REFERENCE_KIND: u8 = 0;
const ENUM_KIND: &str = "enum";
const CONSTANT_KIND: &str = "constant";
const ENUMS: &str = "enums";
const CONSTANTS: &str = "constants";
const INACCESSIBLE_ENUMS: &str = "inaccessible_enums";
const INACCESSIBLE_CONSTANTS: &str = "inaccessible_constants";
const ENUM_VISIBILITY: &str = "enum_visibility";
const CONSTANT_VISIBILITY: &str = "constant_visibility";
const MEMBERS: &str = "members";
const NAME: &str = "name";
const VALUE: &str = "value";
const KIND: &str = "kind";
const PATH: &str = "path";
const LINE: &str = "line";
const COLUMN: &str = "column";
const SCOPE: &str = "scope";
const OWNING_PATH: &str = "owning_path";
const OWNERSHIP_ROOT: &str = "ownership_root";
const IDENTITY: &str = "identity";
const OWNER: &str = "owner";
const DECLARATION: &str = "declaration";
const THROUGH: &str = "through";
const CONSUMER: &str = "consumer";
const ENUM_MEMBER: &str = "enum_member";

/// The Python classes expansion builds usages and errors from.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
pub(crate) struct ExpansionClasses<'py> {
    pub(crate) usage_record: Bound<'py, PyAny>,
    pub(crate) compile_error: Bound<'py, PyAny>,
}

/// Who reads the declarations, whether it prefers relationship visibility, and its error path.
#[derive(Clone)]
pub(crate) struct ExpansionConsumer<'a, 'py> {
    pub(crate) identity: Option<Bound<'py, PyAny>>,
    pub(crate) relationship_visibility: bool,
    pub(crate) path: &'a str,
}

/// One expansion: the SQL, its scan, the visible declarations and the adapter's constant rendering.
pub(crate) struct DeclarationExpansion<'a, 'py> {
    pub(crate) sql: &'a str,
    pub(crate) references: &'a [ScannedReference],
    pub(crate) stop: Option<u8>,
    pub(crate) context: &'a Bound<'py, PyAny>,
    pub(crate) consumer: ExpansionConsumer<'a, 'py>,
    pub(crate) rendering: &'a ConstantRendering,
    pub(crate) classes: &'a ExpansionClasses<'py>,
    /// What SQL macro calls read beyond the context; `None` where SQL macros are not expanded.
    pub(crate) sql_macros: Option<SqlMacroSource<'a, 'py>>,
}

/// The expanded SQL with its spans, and the usage records it adds in reference order.
pub(crate) struct ExpandedDeclarations<'py> {
    pub(crate) spliced: SplicedSql,
    pub(crate) usages: Vec<Bound<'py, PyAny>>,
    /// The SQL macros the SQL called, top-level and nested, once each.
    pub(crate) sql_macros: Vec<String>,
    /// What the analysed SQL must show for each top-level call's arguments to fit.
    pub(crate) sql_macro_checks: Vec<SqlMacroCheck>,
    /// Each expression macro call in the spliced SQL, by byte range.
    pub(crate) typed_calls: Vec<TypedCall>,
}

/// Splice each reference in order, raising the attachment's error for the first bad one.
pub(crate) fn expand_declarations<'py>(
    request: &DeclarationExpansion<'_, 'py>,
) -> PyResult<ExpandedDeclarations<'py>> {
    reject_bare_macro_calls(request)?;
    let mut splices: Vec<DeclarationSplice> = Vec::with_capacity(request.references.len());
    let mut usages: Vec<Bound<'py, PyAny>> = Vec::new();
    let call_starts: Vec<usize> = request
        .references
        .iter()
        .filter(|reference| is_sql_macro_reference(reference.kind))
        .map(|reference| reference.start)
        .collect();
    let (mut call_texts, sql_macros, sql_macro_checks) = if call_starts.is_empty() {
        (
            Vec::<ExpandedText>::new().into_iter(),
            Vec::new(),
            Vec::new(),
        )
    } else {
        let (texts, facts) = expanded_sql_macro_calls(request, &call_starts)?;
        usages.extend(facts.usages);
        (texts.into_iter(), facts.names, facts.checks)
    };
    let mut call_splices: Vec<(usize, Vec<TypedCall>)> = Vec::new();
    for ScannedReference {
        kind,
        name,
        member,
        start,
        end,
    } in request.references
    {
        if is_sql_macro_reference(*kind) {
            let expanded: ExpandedText = call_texts.next().unwrap_or_default();
            if !expanded.calls.is_empty() {
                call_splices.push((splices.len(), expanded.calls));
            }
            splices.push(DeclarationSplice {
                start: *start,
                end: *end,
                replacement: expanded.sql,
            });
            continue;
        }
        let (replacement, visibility) = if *kind == ENUM_REFERENCE_KIND {
            enum_text(request, name, member.as_deref())?
        } else {
            constant_text(request, name)?
        };
        if let Some(consumer) = &request.consumer.identity {
            for record in usage_visibility(&visibility, request.consumer.relationship_visibility)? {
                usages.push(usage(
                    request.classes,
                    consumer,
                    &record,
                    member.as_deref(),
                )?);
            }
        }
        splices.push(DeclarationSplice {
            start: *start,
            end: *end,
            replacement,
        });
    }
    if let Some(code) = request.stop {
        return Err(compile_error(request, &DeclarationError::ScanStop(code)));
    }
    let spliced: SplicedSql = splice_declarations(request.sql, &splices);
    let typed_calls: Vec<TypedCall> = spliced_call_positions(&spliced, call_splices);
    Ok(ExpandedDeclarations {
        spliced,
        usages,
        sql_macros,
        sql_macro_checks,
        typed_calls,
    })
}

/// Each call text's typed calls moved to where its splice landed in `spliced`, by byte.
fn spliced_call_positions(
    spliced: &SplicedSql,
    call_splices: Vec<(usize, Vec<TypedCall>)>,
) -> Vec<TypedCall> {
    let mut typed: Vec<TypedCall> = Vec::new();
    if call_splices.is_empty() {
        return typed;
    }
    let ascii: bool = spliced.sql.is_ascii();
    let mut characters = spliced.sql.char_indices().map(|(offset, _)| offset);
    let mut seen: usize = 0;
    let mut last: usize = 0;
    for (index, calls) in call_splices {
        let Some(span) = spliced.spans.get(index) else {
            continue;
        };
        let offset: usize = if ascii {
            span.output_start
        } else {
            if span.output_start >= seen {
                last = characters
                    .nth(span.output_start - seen)
                    .unwrap_or(spliced.sql.len());
                seen = span.output_start + 1;
            }
            last
        };
        typed.extend(calls.into_iter().map(|call| TypedCall {
            start: call.start + offset,
            end: call.end + offset,
            ..call
        }));
    }
    typed
}

fn enum_text<'py>(
    request: &DeclarationExpansion<'_, 'py>,
    name: &str,
    member: Option<&str>,
) -> PyResult<(String, Bound<'py, PyAny>)> {
    let declaration: Bound<'py, PyAny> = visible_declaration(request, ENUM_KIND, name)?;
    let member: &str = member.unwrap_or_default();
    let mut members: Vec<String> = Vec::new();
    for candidate in declaration.getattr(MEMBERS)?.try_iter()? {
        let candidate: Bound<'py, PyAny> = candidate?;
        let candidate_name: String = candidate.getattr(NAME)?.extract()?;
        if candidate_name == member {
            let value: Bound<'py, PyAny> = candidate.getattr(VALUE)?;
            let literal: String =
                enum_member_literal(&value.str()?.to_string(), value.is_instance_of::<PyInt>());
            return Ok((literal, visibility(request, ENUM_VISIBILITY, name)?));
        }
        members.push(candidate_name);
    }
    Err(compile_error(
        request,
        &DeclarationError::UnknownMember {
            name: name.to_owned(),
            member: member.to_owned(),
            members,
        },
    ))
}

fn constant_text<'py>(
    request: &DeclarationExpansion<'_, 'py>,
    name: &str,
) -> PyResult<(String, Bound<'py, PyAny>)> {
    let declaration: Bound<'py, PyAny> = visible_declaration(request, CONSTANT_KIND, name)?;
    let rendered: String = request
        .rendering
        .render(&declaration, request.consumer.path)?;
    Ok((rendered, visibility(request, CONSTANT_VISIBILITY, name)?))
}

/// The visible declaration, or the unknown or inaccessible error for it.
fn visible_declaration<'py>(
    request: &DeclarationExpansion<'_, 'py>,
    kind: &str,
    name: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let (visible_attribute, inaccessible_attribute) = if kind == ENUM_KIND {
        (ENUMS, INACCESSIBLE_ENUMS)
    } else {
        (CONSTANTS, INACCESSIBLE_CONSTANTS)
    };
    let visible: Bound<'py, PyDict> = request
        .context
        .getattr(visible_attribute)?
        .downcast_into()?;
    if let Some(declaration) = visible.get_item(name)? {
        return Ok(declaration);
    }
    let inaccessible: Bound<'py, PyDict> = request
        .context
        .getattr(inaccessible_attribute)?
        .downcast_into()?;
    let error: DeclarationError = match inaccessible.get_item(name)? {
        Some(record) => DeclarationError::Inaccessible {
            kind: kind.to_owned(),
            name: name.to_owned(),
            record: inaccessible_record(&record)?,
        },
        None => DeclarationError::Unknown {
            kind: kind.to_owned(),
            name: name.to_owned(),
            visible: visible.keys().extract()?,
        },
    };
    Err(compile_error(request, &error))
}

fn inaccessible_record(record: &Bound<'_, PyAny>) -> PyResult<InaccessibleDeclaration> {
    let owning_path: Bound<'_, PyAny> = record.getattr(OWNING_PATH)?;
    let owner: String = if owning_path.is_truthy()? {
        owning_path.str()?.to_string()
    } else {
        record
            .getattr(OWNERSHIP_ROOT)?
            .getattr(PATH)?
            .str()?
            .to_string()
    };
    let owner_resource: Bound<'_, PyAny> = record.getattr(IDENTITY)?.getattr(OWNER)?;
    let owner_identity: Option<(String, String)> = if owner_resource.is_none() {
        None
    } else {
        Some((
            owner_resource
                .getattr(KIND)?
                .getattr(VALUE)?
                .str()?
                .to_string(),
            owner_resource.getattr(NAME)?.str()?.to_string(),
        ))
    };
    Ok(InaccessibleDeclaration {
        path: record.getattr(PATH)?.str()?.to_string(),
        line: record.getattr(LINE)?.extract()?,
        column: record.getattr(COLUMN)?.extract()?,
        scope: record.getattr(SCOPE)?.getattr(VALUE)?.str()?.to_string(),
        owner,
        owner_identity,
    })
}

fn visibility<'py>(
    request: &DeclarationExpansion<'_, 'py>,
    attribute: &str,
    name: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let records: Bound<'py, PyDict> = request.context.getattr(attribute)?.downcast_into()?;
    Ok(records
        .get_item(name)?
        .unwrap_or_else(|| PyTuple::empty(records.py()).into_any()))
}

/// Tests and scenarios record relationship visibility when they have any; others record all.
pub(crate) fn usage_visibility<'py>(
    visibility: &Bound<'py, PyAny>,
    relationship_visibility: bool,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let records: Vec<Bound<'py, PyAny>> = visibility
        .try_iter()?
        .collect::<PyResult<Vec<Bound<'py, PyAny>>>>()?;
    if !relationship_visibility {
        return Ok(records);
    }
    let mut related: Vec<Bound<'py, PyAny>> = Vec::new();
    for record in &records {
        if !record.getattr(THROUGH)?.is_none() {
            related.push(record.clone());
        }
    }
    Ok(if related.is_empty() { records } else { related })
}

fn usage<'py>(
    classes: &ExpansionClasses<'py>,
    consumer: &Bound<'py, PyAny>,
    record: &Bound<'py, PyAny>,
    member: Option<&str>,
) -> PyResult<Bound<'py, PyAny>> {
    let fields: Bound<'py, PyDict> = PyDict::new(consumer.py());
    fields.set_item(CONSUMER, consumer)?;
    fields.set_item(DECLARATION, record.getattr(DECLARATION)?)?;
    fields.set_item(THROUGH, record.getattr(THROUGH)?)?;
    fields.set_item(ENUM_MEMBER, member)?;
    classes.usage_record.call((), Some(&fields))
}

fn compile_error(request: &DeclarationExpansion<'_, '_>, error: &DeclarationError) -> PyErr {
    let message: String = declaration_error_message(error, request.consumer.path);
    match request.classes.compile_error.call1((message,)) {
        Ok(instance) => PyErr::from_value(instance),
        Err(failure) => failure,
    }
}

pub(crate) fn span_rows(spliced: &SplicedSql) -> Vec<SpanRow> {
    spliced
        .spans
        .iter()
        .map(|span| SpanRow {
            source_start: span.source_start,
            source_end: span.source_end,
            output_start: span.output_start,
            output_end: span.output_end,
        })
        .collect()
}
