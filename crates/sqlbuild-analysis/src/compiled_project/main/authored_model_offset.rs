//! `_authored_model_location`: an offset of expanded model SQL in the authored model file.

use crate::compiled_project::_helpers::locating::{map_through_passes, model_query_start};
use crate::compiled_project::models::SplicedSpan;

/// The authored file offset of `offset` in `sql`, when expansion did not generate it.
pub fn authored_model_offset(
    contents: &str,
    query_sql: &str,
    expanded: (&str, usize),
    passes: &[Vec<SplicedSpan>],
) -> Option<usize> {
    let (sql, offset) = expanded;
    let characters: Vec<char> = contents.chars().collect();
    let body_start: usize = model_query_start(contents, query_sql).or_else(|| {
        let leading: usize = characters
            .iter()
            .take_while(|character| char::is_whitespace(**character))
            .count();
        let query: Vec<char> = query_sql.chars().collect();
        characters[leading..].starts_with(&query).then_some(leading)
    })?;
    let sql_characters: Vec<char> = sql.chars().collect();
    let (mapped, generated) = map_through_passes(offset, passes);
    let authored: usize = body_start + mapped;
    if generated
        || offset >= sql_characters.len()
        || authored >= characters.len()
        || characters[authored] != sql_characters[offset]
    {
        return None;
    }
    Some(authored)
}
