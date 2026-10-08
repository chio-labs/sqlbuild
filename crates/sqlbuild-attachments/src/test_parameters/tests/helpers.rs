use crate::test_parameters::models::ParameterReference;

/// References as `(start, end, name)` tuples.
pub(super) fn spans(
    references: Option<Vec<ParameterReference>>,
) -> Option<Vec<(usize, usize, String)>> {
    let mut spans: Vec<(usize, usize, String)> = Vec::new();
    for reference in references? {
        spans.push((reference.start, reference.end, reference.name));
    }
    Some(spans)
}
