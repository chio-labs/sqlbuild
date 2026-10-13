use crate::diff_selection::models::DiffGraph;

/// `orders` (0) reads source `raw_orders` (1) and feeds `revenue` (2); `customers` (3) stands apart.
pub(crate) fn orders_graph() -> DiffGraph {
    DiffGraph {
        names: vec![
            ("orders".to_owned(), 0),
            ("revenue".to_owned(), 2),
            ("customers".to_owned(), 3),
            ("raw_orders".to_owned(), 1),
        ],
        upstream: vec![vec![1], vec![], vec![0], vec![]],
        downstream: vec![vec![2], vec![0], vec![], vec![]],
        tags: vec![("finance".to_owned(), vec![2, 3])],
        paths: vec![
            (0, "staging".to_owned()),
            (2, "marts/finance".to_owned()),
            (3, "marts".to_owned()),
        ],
    }
}

pub(crate) fn owned(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}
