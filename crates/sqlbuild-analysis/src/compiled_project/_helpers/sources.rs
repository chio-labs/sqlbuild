//! Where a model's authored settings live: opt-out keys and legacy schema declarations.

use sqlbuild_core::text::main::is_word_char::is_word_char;

use crate::compiled_project::constants::{
    CURRENT_DIRECTORY, NEWLINE, OPT_OUT_KEYS, PATH_SEPARATOR,
};
use crate::compiled_project::models::{LegacySchemaFile, TextPosition};

/// `_text_location`: the first whole-word opt-out key at or after character `start`.
pub(crate) fn opt_out_position(text: &str, start: usize) -> TextPosition {
    let characters: Vec<char> = text.chars().collect();
    let mut offset: usize = 0;
    for index in start..characters.len() {
        if starts_key(&characters, index) {
            offset = index;
            break;
        }
    }
    char_position(&characters, offset)
}

/// The one-based line and column of character `offset`.
pub(crate) fn char_position(characters: &[char], offset: usize) -> TextPosition {
    let offset: usize = offset.min(characters.len());
    let mut line: usize = 1;
    let mut line_start: usize = 0;
    for (index, character) in characters[..offset].iter().enumerate() {
        if *character == NEWLINE {
            line += 1;
            line_start = index + 1;
        }
    }
    TextPosition {
        line,
        column: offset - line_start + 1,
    }
}

/// Whether an opt-out key starts at `index` with a word boundary on both sides.
fn starts_key(characters: &[char], index: usize) -> bool {
    if index > 0 && is_word_char(characters[index - 1]) {
        return false;
    }
    for key in OPT_OUT_KEYS {
        let end: usize = index + key.chars().count();
        if end > characters.len() || !characters[index..end].iter().copied().eq(key.chars()) {
            continue;
        }
        if characters.get(end).is_none_or(|&next| !is_word_char(next)) {
            return true;
        }
    }
    false
}

/// The error for a model a legacy schema file under its directory still declares.
pub(crate) fn legacy_schema_error(
    model: (&str, &str),
    schema_files: &[LegacySchemaFile],
) -> Option<String> {
    let (name, relative_path) = model;
    let model_parts: Vec<&str> = parts(relative_path);
    let mut matches: Vec<&str> = Vec::new();
    for file in schema_files {
        let directory: Vec<&str> = parts(&file.relative_path);
        if !model_parts.starts_with(&directory[..directory.len().saturating_sub(1)]) {
            continue;
        }
        for entry in &file.model_names {
            if entry == name {
                matches.push(&file.relative_path);
            }
        }
    }
    match matches.as_slice() {
        [] => None,
        [file] => Some(format!(
            "Schema file {file} declares model '{name}', but model metadata must live in \
             {relative_path} MODEL(...). Move description, columns, and audits into the model \
             header."
        )),
        files => Some(format!(
            "Model file {relative_path} matched multiple schema.yml declarations: {}",
            files.join(", ")
        )),
    }
}

/// A relative path's parts, as `PurePosixPath.parts` gives them (`.` has none).
fn parts(path: &str) -> Vec<&str> {
    path.split(PATH_SEPARATOR)
        .filter(|part| !part.is_empty() && *part != CURRENT_DIRECTORY)
        .collect()
}
