//! Lines of the human refactoring output.

use sqlbuild_core::cli_text::main::format_count_noun::format_count_noun;
use sqlbuild_core::cli_text::models::CliStyle;

use crate::refactor_command::_helpers::text::{
    excerpt, first_line, left_justified, tree_connector,
};
use crate::refactor_command::constants::{
    BLANK_PREFIX, CONTINUE_PREFIX, FOLDER_PLACEHOLDER, KIND_WIDTH, POSITION_WIDTH,
};
use crate::refactor_command::models::{LayerMove, RefactorDiagnostic, RefactorStatus};
use crate::refactoring::models::{
    FileChange, ManualLocation, MigrationDeclaration, RefactorOperation, RefactorPlan, TextEdit,
};

/// `model:<name>` or `column:<model>.<column>`.
pub(crate) fn refactor_target(plan: &RefactorPlan) -> String {
    let request = &plan.request;
    if request.operation == RefactorOperation::RenameColumn {
        return format!(
            "column:{}.{}",
            request.model_name,
            request.column_name.as_deref().unwrap_or("None")
        );
    }
    format!("model:{}", request.model_name)
}

pub(crate) fn heading(plan: &RefactorPlan) -> String {
    let request = &plan.request;
    match request.operation {
        RefactorOperation::RenameColumn => format!(
            "Rename column  {}.{} -> {}",
            request.model_name,
            request.column_name.as_deref().unwrap_or("None"),
            request.new_name
        ),
        RefactorOperation::MoveModel => format!(
            "Move model  {} -> {}",
            request.model_name,
            request.destination.as_deref().unwrap_or("None")
        ),
        RefactorOperation::RenameModel => {
            format!(
                "Rename model  {} -> {}",
                request.model_name, request.new_name
            )
        }
    }
}

pub(crate) fn verb(plan: &RefactorPlan) -> &'static str {
    if plan.request.operation == RefactorOperation::MoveModel {
        "move"
    } else {
        "rename"
    }
}

/// Edits ordered by start offset, as both outputs list them.
pub(crate) fn sorted_edits(change: &FileChange) -> Vec<&TextEdit> {
    let mut edits: Vec<&TextEdit> = change.edits.iter().collect();
    edits.sort_by_key(|edit| edit.start);
    edits
}

pub(crate) fn change_lines(style: CliStyle, changes: &[FileChange]) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    for (index, change) in changes.iter().enumerate() {
        let last: bool = index + 1 == changes.len();
        let moved: String = if change.moved() {
            style.muted(&format!("  (moved from {})", change.original_path))
        } else {
            String::new()
        };
        lines.push(format!(
            "{} {}{moved}",
            tree_connector(style, last),
            change.path
        ));
        let prefix: String = style.muted(if last { BLANK_PREFIX } else { CONTINUE_PREFIX });
        let edits: Vec<&TextEdit> = sorted_edits(change);
        for (edit_index, edit) in edits.iter().enumerate() {
            let connector: String = tree_connector(style, edit_index + 1 == edits.len());
            let position: String =
                left_justified(&format!("{}:{}", edit.line, edit.column), POSITION_WIDTH);
            let kind: String = left_justified(edit.kind.value(), KIND_WIDTH);
            lines.push(if edit.before.is_empty() {
                format!(
                    "{prefix}{connector} {position}{kind}+ {}",
                    excerpt(&edit.after)
                )
            } else {
                format!(
                    "{prefix}{connector} {position}{kind}{}  ->  {}",
                    excerpt(&edit.before),
                    excerpt(&edit.after)
                )
            });
        }
    }
    lines
}

pub(crate) fn migration_lines(style: CliStyle, migrations: &[MigrationDeclaration]) -> Vec<String> {
    migrations
        .iter()
        .enumerate()
        .map(|(index, item)| {
            format!(
                "{} {}  {}  {}",
                tree_connector(style, index + 1 == migrations.len()),
                style.object_name(&item.model_name),
                item.declaration,
                style.muted(&item.reason)
            )
        })
        .collect()
}

pub(crate) fn position(location: &ManualLocation) -> String {
    match location.line {
        None => location.path.clone(),
        Some(line) => format!(
            "{}:{line}:{}",
            location.path,
            location.column.filter(|column| *column != 0).unwrap_or(1)
        ),
    }
}

pub(crate) fn location_lines(style: CliStyle, locations: &[&ManualLocation]) -> Vec<String> {
    locations
        .iter()
        .enumerate()
        .map(|(index, item)| {
            format!(
                "{} {}  {}",
                tree_connector(style, index + 1 == locations.len()),
                position(item),
                item.reason
            )
        })
        .collect()
}

pub(crate) fn diagnostic_lines(style: CliStyle, diagnostics: &[RefactorDiagnostic]) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    for (index, diagnostic) in diagnostics.iter().enumerate() {
        let mut location: String = String::new();
        if let Some(path) = &diagnostic.path {
            let line: String = match diagnostic.line {
                Some(line) if line != 0 => line.to_string(),
                _ => String::new(),
            };
            location = format!("{path}:{line}  ");
        }
        lines.push(format!(
            "{} {}  {location}{}",
            tree_connector(style, index + 1 == diagnostics.len()),
            diagnostic.code,
            first_line(&diagnostic.message)
        ));
    }
    lines
}

pub(crate) fn layer_move_lines(style: CliStyle, layer_move: &LayerMove) -> Vec<String> {
    let folder: String = match (&layer_move.folder, &layer_move.layer_folder) {
        (Some(folder), _) => format!("under {folder}/"),
        (None, Some(layer_folder)) => format!("under a layer folder named {layer_folder}/"),
        (None, None) => "under another layer's folder".to_owned(),
    };
    let note: String = if layer_move.folder.is_some() {
        "(change the folder if you want it somewhere else)".to_owned()
    } else {
        format!("(replace {FOLDER_PLACEHOLDER}/ with the folder the model should live in)")
    };
    vec![
        format!(
            "{} belongs {folder}",
            style.object_name(&layer_move.new_name)
        ),
        "  Rename and move in one step:".to_owned(),
        format!("    {}", style.command(&layer_move.command)),
        format!("  {}", style.muted(&note)),
    ]
}

pub(crate) fn status_line(style: CliStyle, plan: &RefactorPlan, status: RefactorStatus) -> String {
    let files: String = format_count_noun(
        i64::try_from(plan.changes.len()).unwrap_or(i64::MAX),
        "file",
        None,
    );
    match status {
        RefactorStatus::Applied => style.success_strong(&format!("Compiled: ok, {files} changed")),
        RefactorStatus::DryRun => style.success_strong(&format!(
            "Dry run: compiles, {files} would change; nothing written"
        )),
        RefactorStatus::CompileFailed => style.error_strong("Compiled: failed; no files changed"),
        RefactorStatus::Refused => style.error_strong("Refused; no files changed"),
    }
}
