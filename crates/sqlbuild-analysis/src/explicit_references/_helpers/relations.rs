//! Python's compiled project-relation index and its qualifier-tolerant matcher.

use std::collections::HashSet;

use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::python_casefold::python_casefold;
use sqlbuild_core::text::main::python_strip::python_strip;

use crate::explicit_references::constants::{
    MIGRATE_FROM_QUOTES, MODEL_TYPE, SCHEMA_QUALIFIED_PARTS, SEED_TYPE, SOURCE_TYPE,
};
use crate::explicit_references::models::{ReferenceRequest, Relation, SourceRelation};
use crate::explicit_references::types::ResourceKey;

/// A relation SQLBuild manages for one resource, or a model's retained old name.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub(crate) struct ProjectRelation {
    pub(crate) target: ResourceKey,
    pub(crate) relation: Relation,
    /// The model an old-name compatibility view keeps this name for.
    pub(crate) compatibility_for: Option<String>,
}

/// `compiled_project_relations_impl`: models, seeds and table sources, then retained old names.
pub(crate) fn project_relations(request: &ReferenceRequest) -> Vec<ProjectRelation> {
    let mut declared: Vec<ProjectRelation> = request
        .models
        .iter()
        .map(|model| relation(MODEL_TYPE, &model.name, model.destination.clone()))
        .collect();
    declared.extend(
        request
            .seeds
            .iter()
            .map(|seed| relation(SEED_TYPE, &seed.name, seed.relation.clone())),
    );
    declared.extend(
        request
            .sources
            .iter()
            .filter(|source| !source.expression)
            .map(source_relation),
    );
    let declared: Vec<ProjectRelation> = deduplicated(declared);
    let old_names: Vec<ProjectRelation> = old_names(request, &declared);
    deduplicated(declared.into_iter().chain(old_names).collect())
}

/// `match_project_relation_impl` without default qualifiers: the first relation that matches.
pub(crate) fn matched<'a>(
    index: &'a [ProjectRelation],
    relation: &Relation,
) -> Option<&'a ProjectRelation> {
    let name: String = folded(&relation.name);
    index.iter().find(|candidate| {
        folded(&candidate.relation.name) == name
            && compatible(relation.schema.as_ref(), candidate.relation.schema.as_ref())
            && compatible(
                relation.database.as_ref(),
                candidate.relation.database.as_ref(),
            )
    })
}

fn folded(text: &str) -> String {
    python_casefold(active_python_text(), text)
}

/// `_parts_compatible`: either part missing, or equal casefolded.
fn compatible(left: Option<&String>, right: Option<&String>) -> bool {
    match (left, right) {
        (Some(left), Some(right)) => folded(left) == folded(right),
        _ => true,
    }
}

/// `_declared_old_names`: `migrate_from` names not already a declared relation.
fn old_names(request: &ReferenceRequest, declared: &[ProjectRelation]) -> Vec<ProjectRelation> {
    let model_names: HashSet<&str> = request
        .models
        .iter()
        .map(|model| model.name.as_str())
        .collect();
    let mut found: Vec<ProjectRelation> = Vec::new();
    for model in &request.models {
        let Some(raw) = &model.migrate_from else {
            continue;
        };
        let parts: Vec<&str> = raw
            .split('.')
            .map(|part| python_strip(part).trim_matches(MIGRATE_FROM_QUOTES))
            .collect();
        if parts.len() == 1 && model_names.contains(parts[0]) {
            continue;
        }
        let count: usize = parts.len();
        let old = Relation {
            name: parts[count - 1].to_owned(),
            schema: if count > 1 {
                Some(parts[count - 2].to_owned())
            } else {
                model.destination.schema.clone()
            },
            database: if count > SCHEMA_QUALIFIED_PARTS {
                Some(parts[count - 3].to_owned())
            } else {
                model.destination.database.clone()
            },
        };
        if matched(declared, &old).is_some() {
            continue;
        }
        found.push(ProjectRelation {
            target: (MODEL_TYPE.to_owned(), model.name.clone()),
            relation: old,
            compatibility_for: Some(model.name.clone()),
        });
    }
    found
}

/// A table source's relation: its table, or its name where the table is unset or empty.
fn source_relation(source: &SourceRelation) -> ProjectRelation {
    let name: String = match &source.table {
        Some(table) if !table.is_empty() => table.clone(),
        _ => source.name.clone(),
    };
    relation(
        SOURCE_TYPE,
        &source.name,
        Relation {
            name,
            schema: source.schema.clone(),
            database: source.database.clone(),
        },
    )
}

fn relation(kind: &str, name: &str, relation: Relation) -> ProjectRelation {
    ProjectRelation {
        target: (kind.to_owned(), name.to_owned()),
        relation,
        compatibility_for: None,
    }
}

fn deduplicated(relations: Vec<ProjectRelation>) -> Vec<ProjectRelation> {
    let mut seen: HashSet<ProjectRelation> = HashSet::new();
    relations
        .into_iter()
        .filter(|relation| seen.insert(relation.clone()))
        .collect()
}
