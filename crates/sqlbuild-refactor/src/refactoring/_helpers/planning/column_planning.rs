//! Walk a column rename through every downstream reader, as `column_planning.py` does.

use std::collections::{BTreeSet, HashSet, VecDeque};

use crate::refactoring::_helpers::edits::header_edits::{
    add_column_entry_edit, column_config_edits, column_entry_edits, consumer_column_header_edits,
    header_tokens, schema_column_edits, unhandled_word_offsets,
};
use crate::refactoring::_helpers::edits::text_edits::{
    RefactorParts, manual_at, merge_parts, path_edits,
};
use crate::refactoring::_helpers::edits::yaml_edits::yaml_column_edits;
use crate::refactoring::_helpers::files::project_files::{
    AuthoredBody, ProjectSqlFile, authored_bodies, project_sql_files, yaml_files,
};
use crate::refactoring::_helpers::planning::column_references::{
    BodyContext, BodyMapping, ColumnQuery, ResourceColumns, analyze_column, columns_of,
    consumer_edits, output_edits, resource_columns,
};
use crate::refactoring::_helpers::planning::model_planning::{
    find_model, needs_column_migration, validate_identifier,
};
use crate::refactoring::_helpers::scanning::chars::chars;
use crate::refactoring::_helpers::scanning::scan_context::ScanContext;
use crate::refactoring::_helpers::scanning::sql_sites::{analysis_sql, model_body};
use crate::refactoring::constants::{
    EXPECTED_FIXTURE_PREFIX, MIGRATE_FROM_KEY, MODEL_RESOURCE_TYPE, REF_FIXTURE_PREFIX, REF_KIND,
    ROOT_SCOPE,
};
use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::{
    DiscoveredFile, ManualLocation, MigrationDeclaration, ModelFacts, RefactorFacts,
    RefactorRequest, SqlFileRole, TextEdit,
};

/// Everything a column rename reads while it walks downstream models.
pub(crate) struct ColumnRenameContext<'a> {
    facts: &'a RefactorFacts,
    scan: &'a ScanContext,
    owner: &'a ModelFacts,
    columns: ResourceColumns,
    files: Vec<ProjectSqlFile>,
    bodies: Vec<AuthoredBody>,
    yaml_files: Vec<DiscoveredFile>,
    pub(crate) old: String,
    pub(crate) new: String,
    cascade: bool,
}

impl ColumnRenameContext<'_> {
    fn names(&self) -> (&str, &str) {
        (&self.old, &self.new)
    }

    fn file(&self, path: &str) -> Option<&ProjectSqlFile> {
        self.files.iter().find(|file| file.path == path)
    }

    fn output_names(&self) -> BTreeSet<String> {
        columns_of(&self.columns, REF_KIND, &self.owner.name)
            .iter()
            .map(|name| name.to_lowercase())
            .collect()
    }
}

/// Validate a column rename and collect everything its walk reads.
pub(crate) fn column_rename_context<'a>(
    facts: &'a RefactorFacts,
    request: &RefactorRequest,
    scan: &'a ScanContext,
) -> Result<ColumnRenameContext<'a>, RefactorError> {
    let owner = find_model(&facts.models, &request.model_name)?;
    let old = request.column_name.clone().unwrap_or_default();
    let new = request.new_name.clone();
    validate_identifier(&new, "column")?;
    let context = ColumnRenameContext {
        facts,
        scan,
        owner,
        columns: resource_columns(facts),
        files: project_sql_files(facts),
        bodies: authored_bodies(facts),
        yaml_files: yaml_files(facts),
        old,
        new,
        cascade: request.cascade,
    };
    if !context.output_names().contains(&context.old.to_lowercase()) {
        return Err(RefactorError::input(
            "C956",
            format!(
                "model:{} has no output column '{}'",
                owner.name, context.old
            ),
            Some("column names match case-insensitively; check the spelling"),
        ));
    }
    if context.old.to_lowercase() == context.new.to_lowercase() {
        return Err(RefactorError::input(
            "C953",
            format!("column {} already has that name", context.old),
            None,
        ));
    }
    Ok(context)
}

/// Every edit of the rename; `cascaded` lists each model whose column is renamed.
pub(crate) fn column_rename_parts(
    context: &ColumnRenameContext<'_>,
) -> Result<RefactorParts, RefactorError> {
    let mut parts: Vec<RefactorParts> = vec![collision(context), owner_output(context)?];
    let mut queue: VecDeque<&ModelFacts> = VecDeque::from([context.owner]);
    let mut seen: HashSet<String> = HashSet::new();
    while let Some(model) = queue.pop_front() {
        if !seen.insert(model.name.clone()) {
            continue;
        }
        let (consumers, cascaded) = consumers(context, model)?;
        let mut declared_edits =
            yaml_column_edits(&context.yaml_files, &model.name, &context.old, &context.new)?;
        declared_edits.extend(schema_edits(context, model)?);
        parts.push(RefactorParts {
            cascaded: vec![model.name.clone()],
            ..RefactorParts::default()
        });
        parts.push(declarations(context, model)?);
        parts.push(consumers);
        parts.push(authored_body_parts(context, model)?);
        parts.push(RefactorParts {
            edits: declared_edits,
            ..RefactorParts::default()
        });
        queue.extend(cascaded);
    }
    let merged = merge_parts(parts);
    let edited: HashSet<&str> = merged.edits.iter().map(|(path, _)| path.as_str()).collect();
    let python = RefactorParts {
        manual: context
            .facts
            .python_locations
            .iter()
            .filter(|location| !edited.contains(location.path.as_str()))
            .cloned()
            .collect(),
        ..RefactorParts::default()
    };
    Ok(merge_parts(vec![merged, python]))
}

fn schema_edits(
    context: &ColumnRenameContext<'_>,
    model: &ModelFacts,
) -> Result<Vec<(String, TextEdit)>, RefactorError> {
    let mut edits: Vec<(String, TextEdit)> = Vec::new();
    for file in context
        .files
        .iter()
        .filter(|file| file.role == SqlFileRole::Schema)
    {
        edits.extend(path_edits(
            &file.path,
            schema_column_edits(
                &file.contents,
                &file.text,
                (&model.name, context.names()),
                context.scan.python,
            )?,
        ));
    }
    Ok(edits)
}

fn collision(context: &ColumnRenameContext<'_>) -> RefactorParts {
    if !context.output_names().contains(&context.new.to_lowercase()) {
        return RefactorParts::default();
    }
    RefactorParts {
        blocking: vec![ManualLocation {
            path: context.owner.path.clone(),
            line: None,
            column: None,
            reason: format!(
                "model:{} already has a column named {}",
                context.owner.name, context.new
            ),
        }],
        ..RefactorParts::default()
    }
}

fn owner_output(context: &ColumnRenameContext<'_>) -> Result<RefactorParts, RefactorError> {
    let (body, compiled_sql, unmapped) = model_context(context, context.owner);
    let Some(body) = body else {
        return Ok(RefactorParts {
            manual: unmapped,
            ..RefactorParts::default()
        });
    };
    let scopes = BTreeSet::from([ROOT_SCOPE.to_owned()]);
    let facts = analyze_column(
        &analysis_sql(&chars(&compiled_sql), context.scan),
        &context.facts.dialect,
        &context.columns,
        &ColumnQuery {
            column: &context.old,
            target_tables: BTreeSet::new(),
            target_ctes: BTreeSet::new(),
            output_scopes: scopes.clone(),
        },
    )?;
    let result = output_edits(&facts, &body, &scopes, context.names());
    let mut manual = result.manual;
    if result.edits.is_empty() && manual.is_empty() {
        manual.push(ManualLocation {
            path: body.path.to_owned(),
            line: None,
            column: None,
            reason: format!(
                "cannot find where model:{} produces {}",
                context.owner.name, context.old
            ),
        });
    }
    Ok(RefactorParts {
        edits: path_edits(body.path, result.edits),
        manual,
        ..RefactorParts::default()
    })
}

fn declarations(
    context: &ColumnRenameContext<'_>,
    model: &ModelFacts,
) -> Result<RefactorParts, RefactorError> {
    let path = &model.path;
    let declared = model
        .schema_columns
        .iter()
        .flatten()
        .find(|column| column.name.to_lowercase() == context.old.to_lowercase());
    if declared.is_some_and(|column| column.migrate_from) {
        return Ok(RefactorParts {
            blocking: vec![ManualLocation {
                path: path.clone(),
                line: None,
                column: None,
                reason: format!(
                    "column {} of model:{} still declares migrate_from; build it on every target and remove migrate_from before renaming it again",
                    context.old, model.name
                ),
            }],
            ..RefactorParts::default()
        });
    }
    let shared: Vec<ManualLocation> = declared
        .and_then(|column| column.location.as_ref())
        .filter(|location| location.path != *path)
        .map(|location| ManualLocation {
            path: location.path.clone(),
            line: location.line,
            column: location.column,
            reason: format!(
                "column {} of model:{} is declared in a shared schema",
                context.old, model.name
            ),
        })
        .into_iter()
        .collect();
    Ok(merge_parts(vec![
        RefactorParts {
            manual: shared,
            ..RefactorParts::default()
        },
        header_parts(context, model)?,
    ]))
}

fn header_parts(
    context: &ColumnRenameContext<'_>,
    model: &ModelFacts,
) -> Result<RefactorParts, RefactorError> {
    let path = &model.path;
    let (contents, text) = context
        .file(path)
        .map(|file| (file.contents.clone(), file.text.clone()))
        .unwrap_or_default();
    let tokens = header_tokens(&contents, &text)?.unwrap_or_default();
    let migrate = needs_column_migration(model);
    let (old, new) = context.names();
    let entry_edits = column_entry_edits(&text, &tokens, (old, new), migrate);
    let added = if entry_edits.is_none() && migrate {
        add_column_entry_edit(&contents, &text, &tokens, (old, new))
    } else {
        None
    };
    let mut edits = column_config_edits(&text, &tokens, old, new);
    edits.extend(entry_edits.unwrap_or_default());
    edits.extend(added);
    let handled: Vec<usize> = edits.iter().map(|edit| edit.start).collect();
    let manual: Vec<ManualLocation> = unhandled_word_offsets(&text, &tokens, old, &handled)
        .into_iter()
        .map(|offset| {
            manual_at(
                path,
                &text,
                Some(offset),
                format!("the MODEL header mentions {old} here; update it by hand"),
            )
        })
        .collect();
    let migrations = if migrate {
        vec![MigrationDeclaration {
            model_name: model.name.clone(),
            declaration: format!("{new} ({MIGRATE_FROM_KEY} {old})"),
            reason: "keeps the column's history in place".to_owned(),
        }]
    } else {
        Vec::new()
    };
    Ok(RefactorParts {
        edits: path_edits(path, edits),
        manual,
        migrations,
        ..RefactorParts::default()
    })
}

fn consumers<'a>(
    context: &ColumnRenameContext<'a>,
    model: &ModelFacts,
) -> Result<(RefactorParts, Vec<&'a ModelFacts>), RefactorError> {
    let mut parts: Vec<RefactorParts> = Vec::new();
    let mut cascaded: Vec<&'a ModelFacts> = Vec::new();
    for consumer in &context.facts.models {
        if !consumer
            .deps
            .iter()
            .any(|dep| dep.resource_type == MODEL_RESOURCE_TYPE && dep.name == model.name)
        {
            continue;
        }
        let (consumer_parts, passes_through) = consumer_part(context, model, consumer)?;
        parts.push(consumer_parts);
        if passes_through {
            cascaded.push(consumer);
        }
    }
    Ok((merge_parts(parts), cascaded))
}

fn consumer_part(
    context: &ColumnRenameContext<'_>,
    upstream: &ModelFacts,
    consumer: &ModelFacts,
) -> Result<(RefactorParts, bool), RefactorError> {
    let (body, compiled_sql, unmapped) = model_context(context, consumer);
    let Some(body) = body else {
        return Ok((
            RefactorParts {
                manual: unmapped,
                ..RefactorParts::default()
            },
            false,
        ));
    };
    let analysis = analysis_sql(&chars(&compiled_sql), context.scan);
    let facts = analyze_column(
        &analysis,
        &context.facts.dialect,
        &context.columns,
        &ColumnQuery {
            column: &context.old,
            target_tables: analysis.placeholders(REF_KIND, &upstream.name),
            target_ctes: BTreeSet::new(),
            output_scopes: BTreeSet::new(),
        },
    )?;
    let result = consumer_edits(
        &facts,
        &body,
        context.names(),
        (context.cascade, context.cascade),
    );
    let file = context.file(body.path);
    let header = match file {
        Some(file) => consumer_column_header_edits(
            &file.contents,
            &file.text,
            &upstream.name,
            context.names(),
        )?,
        None => Vec::new(),
    };
    let mut edits = result.edits;
    edits.extend(header);
    Ok((
        RefactorParts {
            edits: path_edits(body.path, edits),
            manual: result.manual,
            ..RefactorParts::default()
        },
        result.passes_through,
    ))
}

fn authored_body_parts(
    context: &ColumnRenameContext<'_>,
    model: &ModelFacts,
) -> Result<RefactorParts, RefactorError> {
    let lowered_name = model.name.to_lowercase();
    let mut parts: Vec<RefactorParts> = Vec::new();
    for body in &context.bodies {
        if body.body.to_lowercase().contains(&lowered_name) {
            parts.push(authored_body(context, model, body)?);
        }
    }
    Ok(merge_parts(parts))
}

fn authored_body(
    context: &ColumnRenameContext<'_>,
    model: &ModelFacts,
    body: &AuthoredBody,
) -> Result<RefactorParts, RefactorError> {
    let lowered = body.body.to_lowercase();
    let analysis = analysis_sql(&body.text, context.scan);
    let targets = analysis.placeholders(REF_KIND, &model.name);
    let fixture_scopes: BTreeSet<String> =
        if matches!(body.role, SqlFileRole::Test | SqlFileRole::Scenario) {
            [
                format!("{EXPECTED_FIXTURE_PREFIX}{}", model.name),
                format!("{REF_FIXTURE_PREFIX}{}", model.name),
            ]
            .into_iter()
            .filter(|name| lowered.contains(&name.to_lowercase()))
            .collect()
        } else {
            BTreeSet::new()
        };
    if targets.is_empty() && fixture_scopes.is_empty() {
        return Ok(RefactorParts::default());
    }
    let facts = analyze_column(
        &analysis,
        &context.facts.dialect,
        &context.columns,
        &ColumnQuery {
            column: &context.old,
            target_tables: targets,
            target_ctes: fixture_scopes
                .iter()
                .filter(|name| name.starts_with(REF_FIXTURE_PREFIX))
                .cloned()
                .collect(),
            output_scopes: fixture_scopes.clone(),
        },
    )?;
    let located = BodyContext {
        path: &body.path,
        contents: &body.contents,
        mapping: BodyMapping::Authored(body.start),
        fallback_offset: body.start,
    };
    let outputs = output_edits(&facts, &located, &fixture_scopes, context.names());
    let consumers = consumer_edits(&facts, &located, context.names(), (false, true));
    let mut edits = outputs.edits;
    edits.extend(consumers.edits);
    let mut manual = outputs.manual;
    manual.extend(consumers.manual);
    Ok(RefactorParts {
        edits: path_edits(&body.path, edits),
        manual,
        ..RefactorParts::default()
    })
}

type ModelContext<'a> = (Option<BodyContext<'a>>, String, Vec<ManualLocation>);

fn model_context<'a>(
    context: &'a ColumnRenameContext<'_>,
    model: &'a ModelFacts,
) -> ModelContext<'a> {
    let Some(file) = context.file(&model.path) else {
        return (None, String::new(), Vec::new());
    };
    let Some(body) = model_body(model, &file.text) else {
        return (
            None,
            String::new(),
            vec![ManualLocation {
                path: model.path.clone(),
                line: None,
                column: None,
                reason: "the compiled SQL of this model cannot be mapped back to the file"
                    .to_owned(),
            }],
        );
    };
    let fallback_offset = body.body_start;
    let compiled_sql = body.compiled_sql.clone();
    (
        Some(BodyContext {
            path: &model.path,
            contents: &file.text,
            mapping: BodyMapping::Model(body),
            fallback_offset,
        }),
        compiled_sql,
        Vec::new(),
    )
}
