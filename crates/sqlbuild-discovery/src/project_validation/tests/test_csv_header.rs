use crate::project_validation::_helpers::csv_header::{HeaderError, csv_header};
use crate::project_validation::models::CsvSettings;

struct CsvHeaderTestCase {
    description: &'static str,
    text: &'static str,
    settings: CsvSettings,
    expected: &'static [&'static str],
}

fn quoted() -> CsvSettings {
    CsvSettings {
        quotechar: Some("\"".to_owned()),
        ..CsvSettings::default()
    }
}

/// Expectations recorded from Python's `next(csv.reader(...))` with the facade's arguments.
#[test]
fn given_seed_csv_text_when_reading_the_header_then_matches_python_csv_reader() {
    let test_cases = [
        CsvHeaderTestCase {
            description: "plain",
            text: "id,name\n1,a\n",
            settings: CsvSettings::default(),
            expected: &["id", "name"],
        },
        CsvHeaderTestCase {
            description: "crlf",
            text: "id,name\r\n1,a\r\n",
            settings: CsvSettings::default(),
            expected: &["id", "name"],
        },
        CsvHeaderTestCase {
            description: "bare cr",
            text: "id,name\r1,a\r",
            settings: CsvSettings::default(),
            expected: &["id", "name"],
        },
        CsvHeaderTestCase {
            description: "no terminator",
            text: "id,name",
            settings: CsvSettings::default(),
            expected: &["id", "name"],
        },
        CsvHeaderTestCase {
            description: "empty",
            text: "",
            settings: CsvSettings::default(),
            expected: &[],
        },
        CsvHeaderTestCase {
            description: "blank first line",
            text: "\nid\n",
            settings: CsvSettings::default(),
            expected: &[],
        },
        CsvHeaderTestCase {
            description: "unset quotechar keeps quotes",
            text: "\"a,x\",b\n",
            settings: CsvSettings::default(),
            expected: &["\"a", "x\"", "b"],
        },
        CsvHeaderTestCase {
            description: "quoted with quotechar",
            text: "\"a,x\",b\n",
            settings: quoted(),
            expected: &["a,x", "b"],
        },
        CsvHeaderTestCase {
            description: "doubled quote",
            text: "\"a\"\"b\",c\n",
            settings: quoted(),
            expected: &["a\"b", "c"],
        },
        CsvHeaderTestCase {
            description: "no doublequote",
            text: "\"a\"b,c\n",
            settings: CsvSettings {
                doublequote: Some(false),
                ..quoted()
            },
            expected: &["ab", "c"],
        },
        CsvHeaderTestCase {
            description: "quoted newline",
            text: "\"a\nb\",c\n",
            settings: quoted(),
            expected: &["a\nb", "c"],
        },
        CsvHeaderTestCase {
            description: "semicolon",
            text: "a;b;c\n",
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            expected: &["a", "b", "c"],
        },
        CsvHeaderTestCase {
            description: "skip initial space",
            text: "a, b,  c\n",
            settings: CsvSettings {
                skipinitialspace: Some(true),
                ..CsvSettings::default()
            },
            expected: &["a", "b", "c"],
        },
        CsvHeaderTestCase {
            description: "escape",
            text: "a\\,b,c\n",
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            expected: &["a,b", "c"],
        },
        CsvHeaderTestCase {
            description: "trailing delimiter",
            text: "a,b,\n",
            settings: CsvSettings::default(),
            expected: &["a", "b", ""],
        },
        CsvHeaderTestCase {
            description: "unterminated quote",
            text: "\"abc",
            settings: quoted(),
            expected: &["abc"],
        },
        CsvHeaderTestCase {
            description: "bom",
            text: "\u{feff}id,name\n",
            settings: CsvSettings::default(),
            expected: &["\u{feff}id", "name"],
        },
    ];
    for test_case in test_cases {
        let header: Vec<String> = csv_header(test_case.text.as_bytes(), &test_case.settings)
            .unwrap_or_else(|error| panic!("{}: {error:?}", test_case.description));
        assert_eq!(header, test_case.expected, "{}", test_case.description);
    }
}

#[test]
fn given_a_header_longer_than_one_decode_chunk_when_reading_then_reads_past_the_chunk() {
    let long_name: String = "c".repeat(10_000);
    let text: String = format!("{long_name},id\n1,2\n");

    let header: Vec<String> = csv_header(text.as_bytes(), &CsvSettings::default()).unwrap();

    assert_eq!(header, vec![long_name, "id".to_owned()]);
}

#[test]
fn given_csv_settings_python_rejects_when_reading_then_reports_its_type_error() {
    let settings = CsvSettings {
        quotechar: Some(String::new()),
        ..CsvSettings::default()
    };

    let error = csv_header(b"a,b\n", &settings).unwrap_err();

    assert!(
        matches!(&error, HeaderError::Setting(message) if message == "\"quotechar\" must be a 1-character string"),
        "{error:?}"
    );
}
