use std::path::PathBuf;

use crate::project_validation::main::at_most_one_csv_data_row::at_most_one_csv_data_row;
use crate::project_validation::models::CsvSettings;
use crate::project_validation::tests::test_types::OneDataRowTestCase;

#[test]
fn given_seed_csv_text_when_counting_data_rows_then_only_one_row_files_qualify() {
    let test_cases = [
        OneDataRowTestCase {
            description: "header and one row",
            text: "version,currency\n1,EUR\n".to_owned(),
            settings: CsvSettings::default(),
            expected_one_row: true,
        },
        OneDataRowTestCase {
            description: "header only",
            text: "version,currency\n".to_owned(),
            settings: CsvSettings::default(),
            expected_one_row: true,
        },
        OneDataRowTestCase {
            description: "one row without a final newline",
            text: "version,currency\n1,EUR".to_owned(),
            settings: CsvSettings::default(),
            expected_one_row: true,
        },
        OneDataRowTestCase {
            description: "blank lines are not rows",
            text: "version,currency\n\n1,EUR\n\n".to_owned(),
            settings: CsvSettings::default(),
            expected_one_row: true,
        },
        OneDataRowTestCase {
            description: "a quoted newline stays inside one row",
            text: "version,note\n1,\"first\nsecond\"\n".to_owned(),
            settings: CsvSettings::default(),
            expected_one_row: true,
        },
        OneDataRowTestCase {
            description: "two rows",
            text: "version,currency\n1,EUR\n2,USD\n".to_owned(),
            settings: CsvSettings::default(),
            expected_one_row: false,
        },
        OneDataRowTestCase {
            description: "two rows with a custom delimiter",
            text: "version;currency\n1;EUR\n2;USD\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            expected_one_row: false,
        },
        OneDataRowTestCase {
            description: "many rows past the first read",
            text: format!("id\n{}", "1\n".repeat(70_000)),
            settings: CsvSettings::default(),
            expected_one_row: false,
        },
        OneDataRowTestCase {
            description: "one row longer than the first read",
            text: format!("id\n\"{}\"\n", "x".repeat(200_000)),
            settings: CsvSettings::default(),
            expected_one_row: true,
        },
    ];
    let directory = tempfile::TempDir::new().unwrap_or_else(|error| panic!("{error}"));

    for test_case in test_cases {
        let path: PathBuf = directory.path().join("seed.csv");
        std::fs::write(&path, &test_case.text).unwrap_or_else(|error| panic!("{error}"));

        assert_eq!(
            at_most_one_csv_data_row(&path, &test_case.settings),
            test_case.expected_one_row,
            "{}",
            test_case.description
        );
    }
    assert!(!at_most_one_csv_data_row(
        &directory.path().join("missing.csv"),
        &CsvSettings::default()
    ));
}
