use crate::semantic_validation::_helpers::truth_tests::truth_tests;

/// Byte spans of every `IS [NOT] TRUE|FALSE` in `sql`, outside comments and quoted text.
pub(crate) fn truth_test_spans(sql: &str) -> Vec<(usize, usize)> {
    truth_tests(sql)
        .into_iter()
        .map(|test| (test.start, test.end))
        .collect()
}
