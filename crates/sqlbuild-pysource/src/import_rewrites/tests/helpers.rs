use crate::import_rewrites::models::ImportEdit;

/// `contents` with `edits` applied back to front.
pub(crate) fn applied(contents: &str, edits: &[&ImportEdit]) -> String {
    let mut text: String = contents.to_owned();
    let mut ordered: Vec<&&ImportEdit> = edits.iter().collect();
    ordered.sort_by_key(|edit| std::cmp::Reverse(edit.start));
    for edit in ordered {
        text.replace_range(edit.start..edit.end, &edit.replacement);
    }
    text
}
