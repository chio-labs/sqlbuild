use crate::cli_text::models::CliStyle;
use crate::load_command::main::load_counts::load_counts;
use crate::load_command::main::load_exit_code::load_exit_code;
use crate::load_command::main::load_reference_loaders::load_reference_loaders;
use crate::load_command::main::render_load_footer::render_load_footer;
use crate::load_command::main::render_load_result::render_load_result;
use crate::load_command::main::select_load_entries::select_load_entries;
use crate::load_command::models::{LoadResultText, LoadStatus};
use crate::load_command::tests::helpers::{chained_graph, loader, result, selectors, source};
use crate::load_command::tests::test_types::{
    FooterTestCase, ReferenceTestCase, ResultLineTestCase, SelectionTestCase,
};

#[test]
fn given_selectors_when_selecting_then_orders_loaders_before_sources() {
    let test_cases = [
        SelectionTestCase {
            description: "no selectors load every source with its upstream loaders",
            select: &[],
            exclude: &[],
            expected_entries: Ok(vec![
                loader("fetch_events"),
                loader("fetch_prices"),
                source("raw_orders"),
                source("raw_customers"),
                source("raw_regions"),
            ]),
        },
        SelectionTestCase {
            description: "a bare source runs only its own loader",
            select: &["raw_orders"],
            exclude: &[],
            expected_entries: Ok(vec![source("raw_orders")]),
        },
        SelectionTestCase {
            description: "a loader name selects all its sources",
            select: &["load_customers"],
            exclude: &[],
            expected_entries: Ok(vec![source("raw_customers"), source("raw_regions")]),
        },
        SelectionTestCase {
            description: "a trailing plus adds downstream loaders and sources",
            select: &[" fetch_prices+ "],
            exclude: &[],
            expected_entries: Ok(vec![loader("fetch_prices"), source("raw_orders")]),
        },
        SelectionTestCase {
            description: "excluding a dependency prunes loaders that need it",
            select: &[],
            exclude: &["fetch_events"],
            expected_entries: Ok(vec![source("raw_customers"), source("raw_regions")]),
        },
        SelectionTestCase {
            description: "excluding one of a loader's sources keeps the loader for the other",
            select: &["load_customers"],
            exclude: &["raw_regions"],
            expected_entries: Ok(vec![source("raw_customers")]),
        },
        SelectionTestCase {
            description: "an unknown name is rejected",
            select: &["+nope"],
            exclude: &[],
            expected_entries: Err("nope"),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            select_load_entries(
                &chained_graph(),
                (&selectors(test_case.select), &selectors(test_case.exclude)),
            )
            .map_err(|error| error.name),
            test_case.expected_entries.map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_selected_sources_when_resolving_references_then_returns_unselected_upstream_loaders() {
    let test_cases = [
        ReferenceTestCase {
            description: "a terminal source references every upstream loader in order",
            selected: vec![("raw_orders".to_owned(), Some("raw_orders".to_owned()))],
            expected_loaders: &["fetch_events", "fetch_prices"],
        },
        ReferenceTestCase {
            description: "selected loaders and sources without loaders are not references",
            selected: vec![
                ("fetch_prices".to_owned(), Some("fetch_prices".to_owned())),
                ("raw_orders".to_owned(), Some("raw_orders".to_owned())),
                ("raw_static".to_owned(), None),
            ],
            expected_loaders: &["fetch_events"],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            load_reference_loaders(&chained_graph(), &test_case.selected),
            selectors(test_case.expected_loaders),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_result_when_rendering_then_shows_status_rows_logs_and_error() {
    let test_cases = [
        ResultLineTestCase {
            description: "a failed loader groups rows and shows its error",
            result: LoadResultText {
                resource_kind: "loader".to_owned(),
                rows_loaded: 1_234_567,
                duration_ms: Some(1500.0),
                error_message: Some("boom".to_owned()),
                ..result("fetch_b", LoadStatus::Failed)
            },
            use_color: false,
            expected_text: "  2/3  loader    fetch_b                        FAIL   1.50s  rows=1,234,567\n    boom\n",
        },
        ResultLineTestCase {
            description: "logs render as dim blocks and colour keeps the status unpadded",
            result: LoadResultText {
                log_messages: vec!["one\r\ntwo".to_owned()],
                ..result("raw_a", LoadStatus::Skipped)
            },
            use_color: true,
            expected_text: "  2/3  source    raw_a                          \u{1b}[2mSKIP\u{1b}[0m   rows=0\n\n\
                \u{1b}[2m    log  \u{1b}[0m\u{1b}[2mone\u{1b}[0m\n\u{1b}[2m         two\u{1b}[0m\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_load_result(
                &test_case.result,
                (2, 3),
                test_case.result.duration_ms,
                CliStyle {
                    use_color: test_case.use_color
                },
            ),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_results_when_completing_then_reports_warnings_counts_and_exit_code() {
    let test_cases = [
        FooterTestCase {
            description: "warnings are listed and make the run complete with warnings",
            results: vec![
                LoadResultText {
                    warning_messages: vec!["[P008] named raw".to_owned()],
                    loader_name: "load_a".to_owned(),
                    ..result("raw_a", LoadStatus::Success)
                },
                result("raw_b", LoadStatus::Success),
                result("raw_c", LoadStatus::Skipped),
            ],
            expected_text: "\nWarnings:\n\n  raw_a  (loader load_a)\n    [P008] named raw\n\n\
                \u{2713} Completed with warnings  PASS=1  WARN=1  FAIL=0  SKIP=1  TOTAL=3  (1.25s)\n",
            expected_exit_code: 0,
        },
        FooterTestCase {
            description: "a failure completes with errors and exits 1",
            results: vec![result("raw_a", LoadStatus::Failed)],
            expected_text: "\n\u{2717} Completed with errors  PASS=0  WARN=0  FAIL=1  SKIP=0  TOTAL=1  (1.25s)\n",
            expected_exit_code: 1,
        },
    ];

    for test_case in test_cases {
        let counts = load_counts(&test_case.results);
        assert_eq!(
            (
                render_load_footer(
                    &test_case.results,
                    (counts, 1.25),
                    CliStyle { use_color: false }
                ),
                load_exit_code(counts),
            ),
            (
                test_case.expected_text.to_owned(),
                test_case.expected_exit_code
            ),
            "{}",
            test_case.description
        );
    }
}
