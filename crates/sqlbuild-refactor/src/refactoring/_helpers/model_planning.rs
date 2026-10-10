//! Resolve a model rename or move, find what blocks it, and decide its migrations, as
//! `model_planning.py` does.

use std::path::Path;

use crate::refactoring::_helpers::header_edits::{header_tokens, is_value};
use crate::refactoring::_helpers::model_references::{
    macro_reference_locations, model_reference_edits,
};
use crate::refactoring::_helpers::paths::{
    join, name, parent, relative_posix, resolve, stem, suffix, with_name,
};
use crate::refactoring::_helpers::project_files::{ProjectSqlFile, project_sql_files, yaml_files};
use crate::refactoring::_helpers::scan_context::ScanContext;
use crate::refactoring::_helpers::text_edits::{RefactorParts, manual_at};
use crate::refactoring::_helpers::yaml_edits::yaml_model_edits;
use crate::refactoring::constants::{
    HISTORY_MATERIALIZATIONS, MIGRATABLE_MATERIALIZATIONS, MIGRATE_FROM_KEY, SQL_SUFFIX,
};
use crate::refactoring::models::{
    DeclarationMoves, ManualLocation, ModelFacts, RefactorError, RefactorFacts, RefactorOperation,
    RefactorRequest,
};

/// Works out which declaration files a model move takes along: `(model, source, destination)`.
pub type DeclarationMoveHost<'a> =
    dyn FnMut(&str, &str, &str) -> Result<DeclarationMoves, RefactorError> + 'a;

/// The model a request names, and the request with its name and destination resolved.
pub(crate) struct ModelTarget<'a> {
    pub(crate) model: &'a ModelFacts,
    pub(crate) request: RefactorRequest,
    pub(crate) source_path: String,
}

impl ModelTarget<'_> {
    pub(crate) fn destination(&self) -> String {
        self.request
            .destination
            .clone()
            .filter(|destination| !destination.is_empty())
            .unwrap_or_else(|| self.source_path.clone())
    }
}

/// Whether a migration is needed, and why, or why none can be written.
pub(crate) struct ModelMigrationDecision {
    pub(crate) needed: bool,
    pub(crate) reason: String,
    pub(crate) blocked: bool,
}

/// The compiled model a target names.
pub(crate) fn find_model<'a>(
    models: &'a [ModelFacts],
    name: &str,
) -> Result<&'a ModelFacts, RefactorError> {
    models
        .iter()
        .find(|model| model.name == name)
        .ok_or_else(|| {
            RefactorError::input(
                "C951",
                format!("no model named '{name}' in this project"),
                Some("list models with sqb dag --json or sqb scope --browse models"),
            )
        })
}

/// `IDENTIFIER_PATTERN.match`: `^[A-Za-z_][A-Za-z0-9_]*$`, where `$` also matches before a
/// trailing newline.
fn is_identifier(name: &str) -> bool {
    let name = name.strip_suffix('\n').unwrap_or(name);
    let mut characters = name.chars();
    characters
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == '_')
        && characters.all(|character| character.is_ascii_alphanumeric() || character == '_')
}

/// Refuse a new name that is not a plain SQL identifier.
pub(crate) fn validate_identifier(name: &str, noun: &str) -> Result<(), RefactorError> {
    if is_identifier(name) {
        return Ok(());
    }
    Err(RefactorError::input(
        "C952",
        format!("'{name}' is not a valid {noun} name"),
        Some("use letters, digits, and underscores, starting with a letter or underscore"),
    ))
}

/// Resolve the model, its new name, and its destination file.
pub(crate) fn model_target<'a>(
    facts: &'a RefactorFacts,
    request: &RefactorRequest,
) -> Result<ModelTarget<'a>, RefactorError> {
    let model = find_model(&facts.models, &request.model_name)?;
    let source_path = model.path.clone();
    let is_move = request.operation == RefactorOperation::MoveModel;
    let destination = if is_move {
        resolve_destination(
            Path::new(&facts.project_dir),
            request.destination.as_deref().unwrap_or_default(),
            name(&source_path),
        )?
    } else {
        with_name(&source_path, &format!("{}{SQL_SUFFIX}", request.new_name))
    };
    let new = if is_move {
        stem(&destination).to_owned()
    } else {
        request.new_name.clone()
    };
    validate_identifier(&new, "model")?;
    if new == model.name && destination == source_path {
        return Err(RefactorError::input(
            "C953",
            format!("model:{} already has that name and location", model.name),
            None,
        ));
    }
    Ok(ModelTarget {
        model,
        request: RefactorRequest {
            new_name: new,
            destination: Some(destination),
            ..request.clone()
        },
        source_path,
    })
}

fn resolve_destination(
    project_dir: &Path,
    raw: &str,
    file_name: &str,
) -> Result<String, RefactorError> {
    let path = Path::new(raw);
    let mut absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        project_dir.join(path)
    };
    if raw.ends_with('/') || absolute.is_dir() {
        absolute = absolute.join(file_name);
    }
    let resolved = resolve(&absolute);
    let Some(relative) = relative_posix(&resolved, project_dir) else {
        return Err(RefactorError::input(
            "C955",
            format!("destination '{raw}' is outside the project"),
            None,
        ));
    };
    if suffix(name(&relative)) != SQL_SUFFIX || relative == "." {
        return Err(RefactorError::input(
            "C955",
            format!("destination '{raw}' must be a .sql file or a folder ending in /"),
            None,
        ));
    }
    Ok(relative)
}

/// Every edit, manual location, and blocker of one model rename or move.
pub(crate) fn model_parts(
    facts: &RefactorFacts,
    target: &ModelTarget<'_>,
    context: &ScanContext,
    host: &mut DeclarationMoveHost<'_>,
) -> Result<RefactorParts, RefactorError> {
    let files = project_sql_files(facts);
    let old = target.model.name.as_str();
    let new = target.request.new_name.as_str();
    let declaration = declaration_moves(target, host)?;
    let mut edits = Vec::new();
    if new != old {
        edits.extend(model_reference_edits(&files, (old, new), context)?);
        edits.extend(yaml_model_edits(&yaml_files(facts), old, new)?);
    }
    let mut manual = macro_reference_locations(&facts.models, &files, old, context);
    manual.extend(facts.python_locations.iter().cloned());
    let mut blocking = collisions(facts, target);
    blocking.extend(declaration.blocking);
    blocking.extend(pending_migration(&files, target)?);
    Ok(RefactorParts {
        edits,
        manual,
        blocking,
        moves: declaration.moves,
        ..RefactorParts::default()
    })
}

fn collisions(facts: &RefactorFacts, target: &ModelTarget<'_>) -> Vec<ManualLocation> {
    let new = &target.request.new_name;
    let mut found: Vec<ManualLocation> = facts
        .models
        .iter()
        .filter(|other| {
            other.name.to_lowercase() == new.to_lowercase() && other.name != target.model.name
        })
        .map(|other| ManualLocation {
            path: other.path.clone(),
            line: None,
            column: None,
            reason: format!("model:{new} already exists"),
        })
        .collect();
    let destination = target.destination();
    if destination != target.source_path
        && join(Path::new(&facts.project_dir), &destination).exists()
    {
        found.push(ManualLocation {
            path: destination,
            line: None,
            column: None,
            reason: "destination file already exists".to_owned(),
        });
    }
    found
}

fn declaration_moves(
    target: &ModelTarget<'_>,
    host: &mut DeclarationMoveHost<'_>,
) -> Result<DeclarationMoves, RefactorError> {
    let destination = target.destination();
    if parent(&destination) == parent(&target.source_path) {
        return Ok(DeclarationMoves::default());
    }
    host(&target.model.name, &target.source_path, &destination)
}

fn pending_migration(
    files: &[ProjectSqlFile],
    target: &ModelTarget<'_>,
) -> Result<Vec<ManualLocation>, RefactorError> {
    if !target.model.declares_migrate_from {
        return Ok(Vec::new());
    }
    let (contents, text) = files
        .iter()
        .find(|file| file.path == target.source_path)
        .map(|file| (file.contents.clone(), file.text.clone()))
        .unwrap_or_default();
    let offset = header_tokens(&contents, &text)?
        .unwrap_or_default()
        .iter()
        .find(|token| token.depth == 0 && is_value(token, MIGRATE_FROM_KEY))
        .map(|token| token.start);
    Ok(vec![manual_at(
        &target.source_path,
        &text,
        offset,
        format!(
            "model:{} still declares migrate_from; build it on every target and remove migrate_from before renaming it again",
            target.model.name
        ),
    )])
}

fn python_none(value: Option<&str>) -> String {
    value.map_or_else(|| "None".to_owned(), str::to_owned)
}

/// Declare `migrate_from` whenever the relation moves, unless migrations cannot follow it.
pub(crate) fn decide_model_migration(
    before: &[ModelFacts],
    after: Option<&[ModelFacts]>,
    names: (&str, &str),
) -> ModelMigrationDecision {
    let (old, new) = names;
    let decision = |needed: bool, reason: String| ModelMigrationDecision {
        needed,
        reason,
        blocked: false,
    };
    let Some(old_model) = before.iter().find(|model| model.name == old) else {
        return decision(false, "model not compiled".to_owned());
    };
    let new_model = after.and_then(|models| models.iter().find(|model| model.name == new));
    let materialized = new_model.unwrap_or(old_model).materialized.as_deref();
    if !materialized.is_some_and(|value| MIGRATABLE_MATERIALIZATIONS.contains(&value)) {
        return decision(
            false,
            format!(
                "'{}' models keep no warehouse data",
                python_none(materialized)
            ),
        );
    }
    let (Some(after), Some(new_model)) = (after, new_model) else {
        return decision(
            true,
            "keeps the relation's history; the destination could not be checked because the edited project does not compile"
                .to_owned(),
        );
    };
    if location_key(old_model) == location_key(new_model) {
        return decision(false, "relation name is unchanged".to_owned());
    }
    blocked_move(after, old_model, new_model).unwrap_or_else(|| {
        decision(
            true,
            "keeps the relation's history and its old name working".to_owned(),
        )
    })
}

fn blocked_move(
    after: &[ModelFacts],
    old_model: &ModelFacts,
    new_model: &ModelFacts,
) -> Option<ModelMigrationDecision> {
    let lowered = |value: &Option<String>| value.as_deref().unwrap_or_default().to_lowercase();
    let old_database = lowered(&old_model.destination.database);
    let new_database = lowered(&new_model.destination.database);
    if !old_database.is_empty() && !new_database.is_empty() && old_database != new_database {
        return Some(ModelMigrationDecision {
            needed: false,
            blocked: true,
            reason: format!(
                "moves from database {} to {}; migrations cannot cross databases",
                python_none(old_model.destination.database.as_deref()),
                python_none(new_model.destination.database.as_deref())
            ),
        });
    }
    let old_schema = lowered(&old_model.destination.schema);
    if after
        .iter()
        .any(|model| lowered(&model.destination.schema) == old_schema)
    {
        return None;
    }
    Some(ModelMigrationDecision {
        needed: false,
        blocked: true,
        reason: format!(
            "no model is left in schema {}, so migrate_from {} cannot find the old relation; add a schema-qualified migrate_from for each target",
            python_none(old_model.destination.schema.as_deref()),
            old_model.name
        ),
    })
}

/// Whether renaming a column of this model must declare `migrate_from`.
pub(crate) fn needs_column_migration(model: &ModelFacts) -> bool {
    let materialized = model.materialized.as_deref();
    if materialized.is_some_and(|value| HISTORY_MATERIALIZATIONS.contains(&value)) {
        return true;
    }
    materialized.is_some_and(|value| MIGRATABLE_MATERIALIZATIONS.contains(&value))
        && model.migrate_from_set
}

fn location_key(model: &ModelFacts) -> (String, String, String) {
    (
        model
            .destination
            .database
            .as_deref()
            .unwrap_or_default()
            .to_lowercase(),
        model
            .destination
            .schema
            .as_deref()
            .unwrap_or_default()
            .to_lowercase(),
        model.destination.name.to_lowercase(),
    )
}
