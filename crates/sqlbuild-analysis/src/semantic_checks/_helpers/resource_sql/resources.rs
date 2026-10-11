//! Python's `_audit_resources`, `_sql_test_resources` and `_hook_resources`.

use std::collections::{BTreeSet, HashMap, HashSet};
use std::sync::Arc;

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::semantic_checks::_helpers::resource_sql::columns::resolve_binding_column;
use crate::semantic_checks::_helpers::resource_sql::fixtures::{
    prepared_test_sql, reference_names,
};
use crate::semantic_checks::_helpers::resource_sql::locations::offset_location;
use crate::semantic_checks::models::{
    AuditSqlInput, HookModelInput, ResourceSqlKind, ResourceSqlRequest, SqlTestSqlInput,
};

const COLUMN_ONLY_BUILT_IN_AUDITS: [&str; 2] = ["not_null", "unique"];
const SQL_ANALYSIS_KEY: &str = "sql_analysis";

/// One authored SQL body owned by a non-model resource, Python's `_ResourceSql`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub(crate) struct ResourceSql {
    pub(crate) kind: ResourceSqlKind,
    pub(crate) name: String,
    pub(crate) path: String,
    pub(crate) contents: Arc<str>,
    pub(crate) authored_body: String,
    pub(crate) sql: String,
    pub(crate) relations: BTreeSet<String>,
    pub(crate) label: Option<String>,
    pub(crate) audit_definition: Option<String>,
    /// `(line, column)` of the header `sql_analysis` key that opts the resource out.
    pub(crate) opt_out: Option<(i64, i64)>,
}

fn is_blank(text: &str) -> bool {
    python_strip(text).is_empty()
}

/// `str.find` in code points, or None.
pub(crate) fn find_code_points(text: &str, needle: &str) -> Option<usize> {
    text.find(needle).map(|byte| text[..byte].chars().count())
}

/// Python's `_header_opt_out`: where a TEST or AUDIT header turns SQL analysis off.
fn header_opt_out(opts_out: bool, contents: &str, body: &str) -> Option<(i64, i64)> {
    if !opts_out {
        return None;
    }
    let end = text_byte_end(contents, body);
    let key = contents[..end]
        .rfind(SQL_ANALYSIS_KEY)
        .map_or(0, |byte| contents[..byte].chars().count());
    Some(offset_location(contents, key))
}

/// The byte end `rfind` searches before: where `body` starts, or the whole text.
fn text_byte_end(contents: &str, body: &str) -> usize {
    contents.find(body).unwrap_or(contents.len())
}

fn audit_label(audit: &AuditSqlInput) -> String {
    let mut label = format!("audit '{}'", audit.definition_name);
    if let Some((kind, target)) = &audit.attached_target {
        label.push_str(&format!(" on {kind} '{target}'"));
    }
    if let Some(column) = &audit.attached_column {
        label.push_str(&format!(" column '{column}'"));
    }
    label
}

fn shape<'a>(request: &'a ResourceSqlRequest, name: &str) -> &'a [(String, String)] {
    request
        .shapes
        .iter()
        .find(|(shape_name, _)| shape_name == name)
        .map_or(&[], |(_, columns)| columns.as_slice())
}

/// Python's `_binds_cleanly`: a built-in single-column audit on a column its closed shape has.
fn binds_cleanly(audit: &AuditSqlInput, request: &ResourceSqlRequest) -> bool {
    let (Some((_, target)), Some(column)) = (&audit.attached_target, &audit.attached_column) else {
        return false;
    };
    if !COLUMN_ONLY_BUILT_IN_AUDITS.contains(&audit.definition_name.as_str()) || !audit.built_in {
        return false;
    }
    let columns = shape(request, target);
    !columns.is_empty()
        && resolve_binding_column(
            column,
            columns,
            request.dialect.as_deref(),
            request.quoted_ignore_case,
        )
        .is_some()
}

fn disabled_models(request: &ResourceSqlRequest) -> HashSet<&str> {
    request
        .models
        .iter()
        .filter(|model| model.analysis_disabled)
        .map(|model| model.name.as_str())
        .collect()
}

fn audit_resources(request: &ResourceSqlRequest, disabled: &HashSet<&str>) -> Vec<ResourceSql> {
    let mut resources: Vec<ResourceSql> = Vec::new();
    for audit in &request.audits {
        let target_disabled = audit
            .attached_target
            .as_ref()
            .is_some_and(|(_, target)| disabled.contains(&target.as_str()));
        if target_disabled || binds_cleanly(audit, request) {
            continue;
        }
        for (sql, authored) in &audit.bodies {
            let Some(sql) = sql.as_deref().filter(|sql| !is_blank(sql)) else {
                continue;
            };
            let body = authored
                .as_deref()
                .filter(|authored| !authored.is_empty())
                .unwrap_or(sql);
            resources.push(ResourceSql {
                kind: ResourceSqlKind::Audit,
                name: audit.name.clone(),
                path: audit.path.clone(),
                contents: audit.contents.clone(),
                authored_body: body.to_owned(),
                sql: sql.to_owned(),
                relations: audit.relations.iter().cloned().collect(),
                label: Some(audit_label(audit)),
                audit_definition: Some(audit.definition_name.clone()),
                opt_out: header_opt_out(audit.opts_out, &audit.contents, body),
            });
        }
    }
    resources
}

fn test_resource(test: &SqlTestSqlInput, prepared: &(String, Vec<String>)) -> ResourceSql {
    ResourceSql {
        kind: ResourceSqlKind::SqlTest,
        name: test.name.clone(),
        path: test.path.clone(),
        contents: test.contents.clone(),
        authored_body: test.authored_body.clone(),
        sql: prepared.0.clone(),
        relations: prepared.1.iter().cloned().collect(),
        label: Some(format!("SQL test '{}'", test.name)),
        audit_definition: None,
        opt_out: header_opt_out(test.opts_out, &test.contents, &test.authored_body),
    }
}

fn sql_test_resources(request: &ResourceSqlRequest, disabled: &HashSet<&str>) -> Vec<ResourceSql> {
    let mut prepared: HashMap<&str, (String, Vec<String>)> = HashMap::new();
    let mut resources: Vec<ResourceSql> = Vec::new();
    for test in &request.sql_tests {
        let expects_disabled = test
            .expected_model_names
            .iter()
            .any(|name| disabled.contains(&name.as_str()));
        if is_blank(&test.sql_body) || expects_disabled {
            continue;
        }
        let sql = prepared
            .entry(&test.sql_body)
            .or_insert_with(|| prepared_test_sql(&test.sql_body));
        resources.push(test_resource(test, sql));
    }
    resources
}

fn hook_resources_of(model: &HookModelInput, request: &ResourceSqlRequest) -> Vec<ResourceSql> {
    let mut resources: Vec<ResourceSql> = Vec::new();
    for hook in model.hooks.iter().filter(|hook| !is_blank(&hook.statement)) {
        let named_file = hook.hook_path.as_ref().and_then(|path| {
            request
                .hook_files
                .iter()
                .rev()
                .find(|(file, _)| file == path)
                .map(|(file, contents)| (file.clone(), contents.clone()))
        });
        let statement: Vec<char> = hook.statement.chars().collect();
        let mut relations: BTreeSet<String> = hook.relations.iter().cloned().collect();
        relations.extend(reference_names(&statement));
        let authored_body = match (&named_file, &hook.definition) {
            (Some(_), Some(definition)) => definition.clone(),
            _ => hook.statement.clone(),
        };
        let (path, contents) =
            named_file.unwrap_or_else(|| (model.path.clone(), model.authored_sql.clone()));
        resources.push(ResourceSql {
            kind: ResourceSqlKind::Model,
            name: model.name.clone(),
            path,
            contents,
            authored_body,
            sql: hook.statement.clone(),
            relations,
            label: Some(format!("{}[{}] SQL hook", hook.key, hook.index)),
            audit_definition: None,
            opt_out: None,
        });
    }
    resources
}

/// Every checked resource body, deduplicated in first-seen order and filtered by the opt-out policy.
pub(crate) fn resources(request: &ResourceSqlRequest) -> Vec<ResourceSql> {
    let disabled = disabled_models(request);
    let mut all = audit_resources(request, &disabled);
    all.extend(sql_test_resources(request, &disabled));
    for model in request
        .models
        .iter()
        .filter(|model| !model.analysis_disabled)
    {
        all.extend(hook_resources_of(model, request));
    }
    let mut seen: HashSet<ResourceSql> = HashSet::with_capacity(all.len());
    let mut unique: Vec<ResourceSql> = Vec::with_capacity(all.len());
    for resource in all {
        if seen.insert(resource.clone()) {
            unique.push(resource);
        }
    }
    unique.retain(|resource| resource.opt_out.is_none() || request.require_sql_analysis);
    unique
}
