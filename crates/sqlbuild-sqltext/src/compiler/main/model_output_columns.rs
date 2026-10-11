//! Authored locations of a model's simple top-level SELECT output columns.

use crate::compiler::_helpers::model_headers::matching::match_one;
use crate::compiler::_helpers::select_items::scanning::{
    insert_named, line_starts, select_item_output_name, select_list_bounds, span_location,
    split_select_items, trimmed_item,
};
use crate::compiler::models::TextLocation;

/// Python's `model_output_column_locations`: each simple output name and where it is authored.
pub fn model_output_columns(contents: &str, implicit_aliases: bool) -> Vec<(String, TextLocation)> {
    let Some((_, _, sql_start)) = match_one(contents) else {
        return Vec::new();
    };
    let characters: Vec<char> = contents.chars().collect();
    let sql = &characters[sql_start..];
    let Some((start, end)) = select_list_bounds(sql) else {
        return Vec::new();
    };
    let starts = line_starts(&characters);
    let mut locations: Vec<(String, TextLocation)> = Vec::new();
    for range in split_select_items(sql, start, end) {
        let Some(name) = select_item_output_name(&sql[range.0..range.1], implicit_aliases) else {
            continue;
        };
        if let Some((item_start, item_end)) = trimmed_item(sql, range) {
            let location = span_location(&starts, sql_start + item_start, sql_start + item_end);
            locations = insert_named(locations, name, location);
        }
    }
    locations
}
