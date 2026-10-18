//! Python's P008 check of project relation names hard-coded in literal SQL in Python code.

use std::collections::HashSet;

use sqlbuild_core::text::main::python_casefold::python_casefold;

use crate::explicit_references::_helpers::relations::{
    ProjectRelation, matched, project_relations,
};
use crate::explicit_references::constants::HARD_CODED_RELATION_CODE;
use crate::explicit_references::errors::ReferenceFailure;
use crate::explicit_references::main::old_name_message::old_name_message;
use crate::explicit_references::main::relation_remedy::relation_remedy;
use crate::explicit_references::models::{
    LiteralSql, ReferenceDiagnostic, ReferenceReport, ReferenceRequest, Relation, SqlOwner,
    UnmatchedRelation,
};
use crate::explicit_references::types::ResourceKey;
use crate::relation_names::errors::RelationNamesFailure;
use crate::relation_names::main::extract_relation_names::extract_relation_names;
use crate::relation_names::models::ExtractedRelations;

/// A diagnostic's identity: owner label, line and the matched resource.
type FoundKey = (String, usize, ResourceKey);

/// What one relation of one literal yields.
enum Finding {
    Unmatched(UnmatchedRelation),
    Diagnostic(FoundKey, ReferenceDiagnostic),
}

/// One owner's literal SQL against the project-relation index.
struct OwnerScan<'a> {
    request: &'a ReferenceRequest,
    index: &'a [ProjectRelation],
    owner_index: usize,
    owner: &'a SqlOwner,
}

/// `python_sql_reference_diagnostics`: P008 errors sorted by path, line and owner, and unmatched.
pub(crate) fn python_sql_report(
    request: &ReferenceRequest,
) -> Result<ReferenceReport, ReferenceFailure> {
    if request.owners.is_empty() {
        return Ok(ReferenceReport::default());
    }
    let index: Vec<ProjectRelation> = project_relations(request);
    let mut findings: Vec<Finding> = Vec::new();
    for (owner_index, owner) in request.owners.iter().enumerate() {
        let scan = OwnerScan {
            request,
            index: &index,
            owner_index,
            owner,
        };
        findings.extend(scan.findings()?);
    }
    let mut keys: HashSet<FoundKey> = HashSet::new();
    let mut found: Vec<(FoundKey, ReferenceDiagnostic)> = Vec::new();
    let mut unmatched: Vec<UnmatchedRelation> = Vec::new();
    let mut seen: HashSet<UnmatchedRelation> = HashSet::new();
    for finding in findings {
        match finding {
            Finding::Diagnostic(key, diagnostic) => {
                if keys.insert(key.clone()) {
                    found.push((key, diagnostic));
                }
            }
            Finding::Unmatched(relation) => {
                if seen.insert(unmatched_identity(request, &relation)) {
                    unmatched.push(relation);
                }
            }
        }
    }
    found.sort_by_cached_key(|(key, diagnostic)| {
        let owner: usize = diagnostic.owner.unwrap_or_default();
        (
            request.owners[owner].path_order,
            key.1,
            key.0.clone(),
            key.2.clone(),
        )
    });
    Ok(ReferenceReport {
        diagnostics: found
            .into_iter()
            .map(|(_, diagnostic)| diagnostic)
            .collect(),
        unmatched,
    })
}

impl OwnerScan<'_> {
    /// Each literal in line order, its created temporary tables hiding later unqualified names.
    fn findings(&self) -> Result<Vec<Finding>, ReferenceFailure> {
        let mut temporary: HashSet<String> = HashSet::new();
        let mut literals: Vec<&LiteralSql> = self.owner.literals.iter().collect();
        literals.sort_by_key(|literal| literal.line);
        let mut findings: Vec<Finding> = Vec::new();
        for literal in literals {
            let Some(extracted) = extracted(self.request, literal)? else {
                continue;
            };
            temporary.extend(extracted.temporary);
            for written in extracted.relations {
                let relation = Relation {
                    name: written.name,
                    schema: written.schema,
                    database: written.database,
                };
                findings.extend(self.finding(literal, &relation, &temporary));
            }
        }
        Ok(findings)
    }

    /// `_hard_coded_relations` for one relation of one literal.
    fn finding(
        &self,
        literal: &LiteralSql,
        relation: &Relation,
        temporary: &HashSet<String>,
    ) -> Option<Finding> {
        if joined(relation, "").contains(&self.request.placeholder) {
            return None;
        }
        if relation.schema.is_none() && temporary.contains(&python_casefold(&relation.name)) {
            return None;
        }
        let Some(found) = matched(self.index, relation) else {
            return Some(Finding::Unmatched(UnmatchedRelation {
                owner: self.owner_index,
                line: literal.line,
                method: literal.method.clone(),
                relation: relation.clone(),
            }));
        };
        if found.compatibility_for.is_none() && self.owner.own_refs.contains(&found.target) {
            return None;
        }
        let written: String = joined(relation, ".");
        Some(Finding::Diagnostic(
            (self.owner.label.clone(), literal.line, found.target.clone()),
            ReferenceDiagnostic {
                code: HARD_CODED_RELATION_CODE,
                message: self.message(literal, &written, found),
                help: self.help(relation, &written, found),
                path: None,
                owner: Some(self.owner_index),
                line: Some(literal.line),
                resource: None,
            },
        ))
    }

    fn message(&self, literal: &LiteralSql, written: &str, found: &ProjectRelation) -> String {
        match &found.compatibility_for {
            Some(model) => old_name_message(&self.owner.label, written, &literal.method, model),
            None => format!(
                "{} names {}:{} as '{written}' in SQL passed to ctx.{}()",
                self.owner.label, found.target.0, found.target.1, literal.method
            ),
        }
    }

    fn help(&self, relation: &Relation, written: &str, found: &ProjectRelation) -> String {
        let qualify: String = if relation.schema.is_none() {
            format!(
                "\n  = help: if '{written}' is an external table that shares the name, qualify \
                 it with its schema"
            )
        } else {
            String::new()
        };
        format!(
            "{}{qualify}\n  = help: {}",
            relation_remedy(
                &self.owner.kind,
                &found.target,
                &self.owner.upstream_loaders
            ),
            self.request.explicit_help
        )
    }
}

fn extracted(
    request: &ReferenceRequest,
    literal: &LiteralSql,
) -> Result<Option<ExtractedRelations>, ReferenceFailure> {
    extract_relation_names(&literal.sql, request.dialect.as_deref()).map_err(
        |failure| match failure {
            RelationNamesFailure::UnknownDialect(message) => {
                ReferenceFailure::UnknownDialect(message)
            }
            RelationNamesFailure::Internal(reason) => ReferenceFailure::Internal(reason),
        },
    )
}

/// The relation's non-empty database, schema and name parts joined by `separator`.
fn joined(relation: &Relation, separator: &str) -> String {
    let mut parts: Vec<&str> = Vec::new();
    for part in [&relation.database, &relation.schema].into_iter().flatten() {
        parts.push(part);
    }
    parts.push(&relation.name);
    parts.retain(|part| !part.is_empty());
    parts.join(separator)
}

/// `LiteralSqlRelation` equality: owner label, kind and path, line, method and relation.
fn unmatched_identity(request: &ReferenceRequest, item: &UnmatchedRelation) -> UnmatchedRelation {
    let owner: &SqlOwner = &request.owners[item.owner];
    let canonical: usize = request
        .owners
        .iter()
        .position(|other| {
            other.label == owner.label
                && other.kind == owner.kind
                && other.path_order == owner.path_order
        })
        .unwrap_or(item.owner);
    UnmatchedRelation {
        owner: canonical,
        ..item.clone()
    }
}
