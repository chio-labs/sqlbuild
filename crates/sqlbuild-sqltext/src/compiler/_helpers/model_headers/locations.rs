//! Authored locations of the column names a MODEL header declares.

use crate::compiler::_helpers::model_headers::tokenization::parse_batch;
use crate::compiler::_helpers::select_items::scanning::{insert_named, line_starts};
use crate::compiler::models::TextLocation;

const NO_LOCATIONS: &str = "Native MODEL header parser returned no column locations";

/// Python's `header_column_locations` for `header` authored at code point `header_start`.
pub(crate) fn header_column_locations(
    contents: &str,
    header: &str,
    header_start: usize,
) -> Result<Vec<(String, TextLocation)>, String> {
    let (_, offsets, error) = parse_batch(&[header.to_owned()])?.pop().unwrap_or((
        None,
        None,
        Some(NO_LOCATIONS.to_owned()),
    ));
    if let Some(error) = error {
        return Err(error);
    }
    let offsets = offsets.ok_or_else(|| NO_LOCATIONS.to_owned())?;
    let characters: Vec<char> = contents.chars().collect();
    let starts = line_starts(&characters[..header_start.min(characters.len())]);
    let header_line = starts.len();
    let header_column = header_start - starts[starts.len() - 1] + 1;
    let header_characters: Vec<char> = header.chars().collect();
    let (mut line, mut column, mut cursor) = (1, 1, 0);
    let mut locations: Vec<(String, TextLocation)> = Vec::new();
    for (name, position, length) in offsets {
        while cursor < position {
            match header_characters[cursor..position]
                .iter()
                .position(|character| *character == '\n')
            {
                Some(newline) => {
                    line += 1;
                    column = 1;
                    cursor += newline + 1;
                }
                None => {
                    column += position - cursor;
                    cursor = position;
                }
            }
        }
        let start_column = column + if line == 1 { header_column - 1 } else { 0 };
        let location = TextLocation {
            line: header_line + line - 1,
            column: start_column,
            end_line: header_line + line - 1,
            end_column: start_column + length,
        };
        locations = insert_named(locations, name, location);
    }
    Ok(locations)
}
