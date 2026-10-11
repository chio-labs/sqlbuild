//! Python's `get_resource_sql_diagnostics`: bind resource SQL against the closed model shapes.

use std::collections::{BTreeSet, HashMap, HashSet};

use sqlbuild_attachments::cursor_intrinsics::main::replace_intrinsics::replace_intrinsics;
use sqlbuild_core::text::main::active_python_text::active_python_text;

use crate::semantic_checks::_helpers::explanation::opt_outs::unneeded_opt_out;
use crate::semantic_checks::_helpers::resource_sql::help::{HelpContext, resource_sql_help};
use crate::semantic_checks::_helpers::resource_sql::locations::{
    Finding, line_at, location, text_from,
};
use crate::semantic_checks::_helpers::resource_sql::resources::{ResourceSql, resources};
use crate::semantic_checks::models::{
    ResourceSqlDiagnostic, ResourceSqlFailure, ResourceSqlKind, ResourceSqlRequest, SemanticFailure,
};
use crate::semantic_validation::main::normalize::normalize_analysis_sql;
use crate::semantic_validation::models::{Columns, NormalizationInput, ProjectCatalog};
use crate::semantic_validation::types::{BindingRequest, Relations};

const UNKNOWN_TABLE_CODE: &str = "B000";
const UNKNOWN_TABLE_PREFIX: &str = "Unknown table ";
const SYNTAX_ERROR_CODE: &str = "P001";
const OPT_OUT_CODE: &str = "P009";
const ERROR_SEVERITY: &str = "error";
const CURSOR_CONTEXT: &str = "Model SQL";
const ANALYSIS_CURSOR_LITERAL: &str = "CAST('2000-01-01 00:00:00' AS TIMESTAMP)";
const GENERIC_DIALECT: &str = "generic";

type Key = (String, String, String, i64, i64, i64);

fn kind_label(kind: ResourceSqlKind) -> &'static str {
    match kind {
        ResourceSqlKind::Audit => "audit",
        ResourceSqlKind::SqlTest => "SQL test",
        ResourceSqlKind::Model => "model",
    }
}

fn semantic(failure: SemanticFailure) -> ResourceSqlFailure {
    ResourceSqlFailure::Internal(format!("{failure:?}"))
}

/// Python's `normalize_analysis_sql(cursor_intrinsics_analysis_sql(sql))`.
fn cleaned_sql(sql: &str, dialect: Option<&str>) -> Result<String, ResourceSqlFailure> {
    let (analysis_sql, _) = replace_intrinsics(active_python_text(), sql, CURSOR_CONTEXT, |_| {
        ANALYSIS_CURSOR_LITERAL.to_owned()
    })
    .map_err(ResourceSqlFailure::CursorIntrinsic)?;
    normalize_analysis_sql(NormalizationInput {
        sql: analysis_sql,
        dialect: dialect.unwrap_or(GENERIC_DIALECT).to_owned(),
        stubs: HashMap::new(),
        placeholders: HashMap::new(),
    })
    .map_err(ResourceSqlFailure::Normalization)
}

/// The binding request for `sql` over `relations`, with each closed shape as an override.
fn binding_request(
    sql: &str,
    relations: &BTreeSet<String>,
    shapes: &HashMap<&str, &[(String, String)]>,
) -> BindingRequest {
    let mut references: Vec<(String, bool)> = Vec::with_capacity(relations.len());
    let mut overrides: Relations = Relations::new();
    for name in relations {
        let columns = shapes.get(name.as_str()).copied().unwrap_or(&[]);
        references.push((name.clone(), !columns.is_empty()));
        if !columns.is_empty() {
            overrides.insert(
                name.clone(),
                Columns(
                    columns
                        .iter()
                        .map(|(column, data_type)| (column.clone(), Some(data_type.clone())))
                        .collect(),
                ),
            );
        }
    }
    (sql.to_owned(), references, overrides)
}

/// Python's `_reported_diagnostic`: drop open-relation lookups, make parser rejections P001.
fn reported(resource: &ResourceSql, finding: &Finding) -> Option<Finding> {
    if finding.0 != UNKNOWN_TABLE_CODE {
        return Some(finding.clone());
    }
    if finding.1.starts_with(UNKNOWN_TABLE_PREFIX) {
        return None;
    }
    Some((
        SYNTAX_ERROR_CODE.to_owned(),
        format!(
            "SQL syntax error in {} '{}': {}",
            kind_label(resource.kind),
            resource.name,
            finding.1
        ),
        finding.2,
        finding.3,
        finding.4,
        finding.5,
        ERROR_SEVERITY.to_owned(),
    ))
}

/// What one resource's findings are checked against.
struct Checking<'a> {
    request: &'a ResourceSqlRequest,
    cleaned_sql: &'a str,
}

/// Python's `_resource_diagnostics`: located findings keyed for deduplication.
fn resource_diagnostics(
    resource: &ResourceSql,
    findings: &[Finding],
    checking: &Checking<'_>,
) -> Result<Vec<(Key, ResourceSqlDiagnostic)>, ResourceSqlFailure> {
    let mut found: Vec<(Key, ResourceSqlDiagnostic)> = Vec::new();
    for (index, native) in findings.iter().enumerate() {
        let Some(finding) = reported(resource, native) else {
            continue;
        };
        let span = location(resource, checking.cleaned_sql, &finding)?;
        let key: Key = (
            resource.path.clone(),
            finding.0.clone(),
            finding.1.clone(),
            span.0,
            span.1,
            if finding.4.is_none() {
                index as i64
            } else {
                -1
            },
        );
        if found.iter().any(|(existing, _)| *existing == key) {
            continue;
        }
        let authored_text = text_from(resource, span);
        let authored_line = line_at(resource, span);
        let help = resource_sql_help(
            &finding.0,
            &finding.1,
            &HelpContext {
                kind: resource.kind,
                authored_text: &authored_text,
                authored_line: &authored_line,
                column: span.1,
                authored_body: &resource.authored_body,
                audit_definition: resource.audit_definition.as_deref(),
                shapes: &checking.request.shapes,
                relations: &resource.relations,
                dialect: checking.request.dialect.as_deref(),
            },
        )
        .map_err(semantic)?;
        let message = match &resource.label {
            Some(label) if finding.0 != SYNTAX_ERROR_CODE => format!("{label}: {}", finding.1),
            _ => finding.1.clone(),
        };
        found.push((
            key,
            ResourceSqlDiagnostic {
                kind: resource.kind,
                resource_name: resource.name.clone(),
                is_error: finding.6 == ERROR_SEVERITY,
                code: finding.0.clone(),
                message,
                path: resource.path.clone(),
                span,
                note: None,
                help,
            },
        ));
    }
    Ok(found)
}

fn opt_out_diagnostic(
    resource: &ResourceSql,
    (line, column): (i64, i64),
    hidden: &[(Key, ResourceSqlDiagnostic)],
) -> Result<ResourceSqlDiagnostic, ResourceSqlFailure> {
    let codes: Vec<&str> = hidden.iter().map(|(_, item)| item.code.as_str()).collect();
    let (message, note, help) =
        unneeded_opt_out(kind_label(resource.kind), &resource.name, false, &codes)
            .map_err(semantic)?;
    Ok(ResourceSqlDiagnostic {
        kind: resource.kind,
        resource_name: resource.name.clone(),
        is_error: true,
        code: OPT_OUT_CODE.to_owned(),
        message,
        path: resource.path.clone(),
        span: (line, column, None, None),
        note: Some(note),
        help: Some(help),
    })
}

/// Every audit, SQL test and SQL hook finding, in Python's first-seen order.
pub(crate) fn resource_sql_findings(
    request: &ResourceSqlRequest,
    catalog: &ProjectCatalog,
) -> Result<Vec<ResourceSqlDiagnostic>, ResourceSqlFailure> {
    let checked = resources(request);
    if checked.is_empty() {
        return Ok(Vec::new());
    }
    let dialect = request.dialect.as_deref();
    let mut normalized: HashMap<&str, String> = HashMap::new();
    for resource in &checked {
        if !normalized.contains_key(resource.sql.as_str()) {
            normalized.insert(&resource.sql, cleaned_sql(&resource.sql, dialect)?);
        }
    }
    let shapes: HashMap<&str, &[(String, String)]> = request
        .shapes
        .iter()
        .map(|(name, columns)| (name.as_str(), columns.as_slice()))
        .collect();
    let mut request_index: HashMap<(&str, &BTreeSet<String>), usize> = HashMap::new();
    let mut requests: Vec<BindingRequest> = Vec::new();
    for resource in &checked {
        let cleaned = normalized[resource.sql.as_str()].as_str();
        request_index
            .entry((cleaned, &resource.relations))
            .or_insert_with(|| {
                requests.push(binding_request(cleaned, &resource.relations, &shapes));
                requests.len() - 1
            });
    }
    let results = catalog
        .binding_results(requests)
        .map_err(ResourceSqlFailure::Internal)?;
    let mut keys: HashSet<Key> = HashSet::new();
    let mut opt_out_keys: HashSet<(String, i64, i64)> = HashSet::new();
    let mut diagnostics: Vec<ResourceSqlDiagnostic> = Vec::new();
    for resource in &checked {
        let cleaned = normalized[resource.sql.as_str()].as_str();
        let findings = &results[request_index[&(cleaned, &resource.relations)]];
        let checking = Checking {
            request,
            cleaned_sql: cleaned,
        };
        let found = resource_diagnostics(resource, findings, &checking)?;
        match resource.opt_out {
            None => {
                for (key, diagnostic) in found {
                    if keys.insert(key) {
                        diagnostics.push(diagnostic);
                    }
                }
            }
            Some(position) => {
                let parses = !found.iter().any(|(_, item)| item.code == SYNTAX_ERROR_CODE);
                if parses && opt_out_keys.insert((resource.path.clone(), position.0, position.1)) {
                    diagnostics.push(opt_out_diagnostic(resource, position, &found)?);
                }
            }
        }
    }
    Ok(diagnostics)
}
