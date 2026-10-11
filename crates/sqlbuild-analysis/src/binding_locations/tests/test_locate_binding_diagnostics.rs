use crate::binding_locations::main::locate_binding_diagnostics::locate_binding_diagnostics;
use crate::binding_locations::models::BindingSource;
use crate::binding_locations::tests::helpers::{
    MODEL, QUERY, one_missing_column, repeated_rows, unmapped_row,
};
use crate::binding_locations::tests::test_types::LocateBindingDiagnosticsTestCase;

#[test]
fn given_binding_rows_when_locating_then_python_locations_and_deduplication_hold() {
    let test_cases = [
        LocateBindingDiagnosticsTestCase {
            description: "a column error maps to its authored span below the header",
            authored: MODEL,
            query: QUERY,
            rows: one_missing_column,
            expected_located: &[("E201", Some(5), Some(20), Some((5, 20, Some(5), Some(25))))],
        },
        LocateBindingDiagnosticsTestCase {
            description: "internal codes drop, spanned error repeats drop, other repeats stay",
            authored: MODEL,
            query: QUERY,
            rows: repeated_rows,
            expected_located: &[
                ("E201", Some(5), Some(20), Some((5, 20, Some(5), Some(25)))),
                ("W1", Some(5), Some(1), Some((5, 1, None, None))),
                ("W1", Some(5), Some(1), Some((5, 1, None, None))),
            ],
        },
        LocateBindingDiagnosticsTestCase {
            description: "a query missing from the file keeps the raw line and column",
            authored: "SELECT 1",
            query: "absent query",
            rows: unmapped_row,
            expected_located: &[("E1", Some(2), Some(3), None)],
        },
    ];
    for test_case in test_cases {
        let source: BindingSource<'_> = BindingSource {
            authored: test_case.authored,
            query: test_case.query,
            cleaned: test_case.query,
            expansion: None,
        };

        let located = locate_binding_diagnostics(&(test_case.rows)(), &source)
            .expect("positions map")
            .into_iter()
            .map(|item| {
                (
                    item.code,
                    item.line,
                    item.column,
                    item.location
                        .map(|span| (span.line, span.column, span.end_line, span.end_column)),
                )
            })
            .collect::<Vec<_>>();

        assert_eq!(
            located,
            test_case
                .expected_located
                .iter()
                .map(|(code, line, column, span)| ((*code).to_owned(), *line, *column, *span))
                .collect::<Vec<_>>(),
            "{}",
            test_case.description
        );
    }
}
