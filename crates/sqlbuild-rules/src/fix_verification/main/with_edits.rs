use crate::fix_verification::models::FixEdit;

/// Apply nonoverlapping authored edits in reverse character-offset order.
pub fn with_edits(contents: &str, mut edits: Vec<FixEdit>) -> String {
    edits.sort_by_key(|edit| std::cmp::Reverse(edit.start));
    let mut result = contents.to_owned();
    for edit in edits {
        let start = result
            .char_indices()
            .nth(edit.start)
            .map_or(result.len(), |(index, _)| index);
        let end = result
            .char_indices()
            .nth(edit.end)
            .map_or(result.len(), |(index, _)| index);
        result.replace_range(start..end, &edit.replacement);
    }
    result
}
