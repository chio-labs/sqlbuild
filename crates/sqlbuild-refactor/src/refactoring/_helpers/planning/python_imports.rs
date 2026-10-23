//! Python imports of the Python modules a refactoring moves.

use std::path::Path;

use sqlbuild_core::text::errors::TextDecodeError;
use sqlbuild_pysource::import_rewrites::main::python_import_rewrites::python_import_rewrites;
use sqlbuild_pysource::import_rewrites::models::{ImportRewrites, ModuleMove, PythonSource};

use crate::refactoring::_helpers::edits::text_edits::text_edit;
use crate::refactoring::_helpers::files::paths::{name, suffix};
use crate::refactoring::_helpers::files::workspace::project_files_with_suffix;
use crate::refactoring::_helpers::scanning::chars::chars;
use crate::refactoring::constants::{PYTHON_SUFFIX, UNREADABLE_PYTHON_REASON};
use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::{EditKind, ManualLocation, TextEdit};

/// Import edits by path, and the imports that cannot be rewritten.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct ImportParts {
    pub(crate) edits: Vec<(String, TextEdit)>,
    pub(crate) blocking: Vec<ManualLocation>,
}

/// Import edits for the Python files `moves` moves, and a blocker for each unsafe import.
pub(crate) fn python_import_parts(
    project_dir: &Path,
    moves: &[(String, String)],
) -> Result<ImportParts, RefactorError> {
    let modules: Vec<ModuleMove> = moves
        .iter()
        .filter(|(source, destination)| {
            source != destination
                && suffix(name(source)) == PYTHON_SUFFIX
                && suffix(name(destination)) == PYTHON_SUFFIX
        })
        .map(|(source, destination)| ModuleMove {
            from: source.clone(),
            to: destination.clone(),
        })
        .collect();
    let mut parts = ImportParts::default();
    if modules.is_empty() {
        return Ok(parts);
    }
    let mut sources: Vec<PythonSource> = Vec::new();
    for (path, text) in project_files_with_suffix(project_dir, PYTHON_SUFFIX)? {
        match text {
            Ok(contents) => sources.push(PythonSource { path, contents }),
            Err(TextDecodeError { .. }) => parts.blocking.push(ManualLocation {
                path,
                line: None,
                column: None,
                reason: UNREADABLE_PYTHON_REASON.to_owned(),
            }),
        }
    }
    let rewrites: ImportRewrites = python_import_rewrites(&sources, &modules);
    for edit in rewrites.edits {
        let Some(source) = sources.iter().find(|source| source.path == edit.path) else {
            continue;
        };
        let start: usize = source.contents[..edit.start].chars().count();
        let end: usize = start + source.contents[edit.start..edit.end].chars().count();
        parts.edits.push((
            edit.path,
            text_edit(
                &chars(&source.contents),
                (start, end),
                edit.replacement,
                EditKind::Import,
            ),
        ));
    }
    parts
        .blocking
        .extend(rewrites.refusals.into_iter().map(|refusal| ManualLocation {
            path: refusal.path,
            line: Some(refusal.line),
            column: Some(refusal.column),
            reason: refusal.reason,
        }));
    Ok(parts)
}
