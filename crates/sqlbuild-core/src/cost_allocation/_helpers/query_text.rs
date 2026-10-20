//! The `QUERY_TEXT` column of a query-history read, selected by the run's query tag.

use crate::cost_allocation::constants::{
    HOOK_TAG_FRAGMENT, NULL_QUERY_TEXT, SQLBUILD_TAG_FRAGMENT,
};

/// One run's query-tag fragment as `json.dumps` writes it, else the SQLBuild app fragment.
fn run_tag_fragment(run_id: &str) -> String {
    let plain: bool = run_id
        .chars()
        .all(|character| character.is_ascii_graphic() && character != '"' && character != '\\');
    if plain && !run_id.is_empty() {
        format!("\"run_id\":\"{run_id}\"")
    } else {
        SQLBUILD_TAG_FRAGMENT.to_owned()
    }
}

fn like_contains(fragment: &str) -> String {
    format!("'%{}%'", fragment.replace('\'', "''"))
}

/// CREATE text of the run's non-hook statements, selected by query tag, or masked text.
pub(crate) fn query_text_expression(run_id: Option<&str>) -> String {
    let Some(run_id) = run_id else {
        return NULL_QUERY_TEXT.to_owned();
    };
    format!(
        "CASE WHEN (QUERY_TYPE = 'CREATE' OR QUERY_TYPE LIKE 'CREATE_%') \
AND QUERY_TAG LIKE {} AND QUERY_TAG NOT LIKE {} THEN QUERY_TEXT END AS QUERY_TEXT",
        like_contains(&run_tag_fragment(run_id)),
        like_contains(HOOK_TAG_FRAGMENT),
    )
}
