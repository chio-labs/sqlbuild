use crate::cli_text::models::CliStyle;
use crate::seed_command::main::render_seed_completion::render_seed_completion;
use crate::seed_command::main::render_seed_ready::render_seed_ready;
use crate::seed_command::main::render_seed_row::render_seed_row;
use crate::seed_command::main::seed_exit_code::seed_exit_code;
use crate::seed_command::models::SeedRow;
use crate::seed_command::tests::test_types::{CompletionTestCase, ReadyTestCase, RowTestCase};

const PLAIN: CliStyle = CliStyle { use_color: false };

#[test]
fn given_selected_seeds_when_rendering_ready_then_lists_them_as_a_tree() {
    let test_cases = [
        ReadyTestCase {
            description: "two seeds end with the last branch",
            names: vec!["first_seed".to_owned(), "second_seed".to_owned()],
            expected_text: "\nSeed ready  2 selected\n\nSeeds (2)\n├── first_seed\n└── second_seed\n\n",
        },
        ReadyTestCase {
            description: "no seeds keep the header",
            names: Vec::new(),
            expected_text: "\nSeed ready  0 selected\n\nSeeds (0)\n\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_seed_ready(&test_case.names, PLAIN),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_finished_seed_when_rendering_row_then_pads_name_and_shows_error() {
    let test_cases = [
        RowTestCase {
            description: "a success shows its duration",
            row: SeedRow {
                name: "first_seed".to_owned(),
                ordinal: 1,
                total: 2,
                succeeded: true,
                duration_ms: Some(1234.0),
                ..SeedRow::default()
            },
            expected_text: "  1/2  seed      first_seed                     OK     1.23s\n",
        },
        RowTestCase {
            description: "a coded failure renders the labelled error and help",
            row: SeedRow {
                name: "bad_seed".to_owned(),
                ordinal: 2,
                total: 2,
                error_message: Some("bad value\ndetail".to_owned()),
                error_code: Some("S001".to_owned()),
                error_help: Some("fix the CSV".to_owned()),
                ..SeedRow::default()
            },
            expected_text: "  2/2  seed      bad_seed                       FAIL   \n    error[S001]: bad value\ndetail\n  = help: fix the CSV\n",
        },
        RowTestCase {
            description: "an uncoded failure shows the message",
            row: SeedRow {
                name: "bad_seed".to_owned(),
                ordinal: 1,
                total: 1,
                duration_ms: Some(5.0),
                error_message: Some("boom".to_owned()),
                ..SeedRow::default()
            },
            expected_text: "  1/1  seed      bad_seed                       FAIL   0.01s\n    boom\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_seed_row(&test_case.row, PLAIN),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_results_when_completing_then_summarizes_and_resolves_exit_code() {
    let test_cases = [
        CompletionTestCase {
            description: "all seeds loaded",
            counts: (2, 0, 2),
            expected_text: "\n✓ Completed successfully  PASS=2  WARN=0  FAIL=0  SKIP=0  TOTAL=2  (1.50s)\n",
            expected_exit_code: 0,
        },
        CompletionTestCase {
            description: "a failed seed fails the run",
            counts: (1, 1, 2),
            expected_text: "\n✗ Completed with errors  PASS=1  WARN=0  FAIL=1  SKIP=0  TOTAL=2  (1.50s)\n",
            expected_exit_code: 1,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_seed_completion(test_case.counts, 1.5, PLAIN),
            test_case.expected_text,
            "{}",
            test_case.description
        );
        assert_eq!(
            seed_exit_code(test_case.counts.1),
            test_case.expected_exit_code,
            "{}",
            test_case.description
        );
    }
}
