use std::collections::HashMap;

pub(crate) fn edges(rows: &[(&str, &[&str])]) -> HashMap<String, Vec<String>> {
    rows.iter()
        .map(|(name, upstream)| {
            (
                (*name).to_owned(),
                upstream.iter().map(|value| (*value).to_owned()).collect(),
            )
        })
        .collect()
}
