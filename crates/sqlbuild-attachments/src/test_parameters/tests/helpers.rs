use crate::test_parameters::models::ParameterScan;

/// References as `(start, end, name)` tuples, and the error that stops the scan.
pub(super) fn spans(scan: ParameterScan) -> (Vec<(usize, usize, String)>, Option<String>) {
    let mut spans: Vec<(usize, usize, String)> = Vec::new();
    for reference in scan.references {
        spans.push((reference.start, reference.end, reference.name));
    }
    (spans, scan.error)
}
