use crate::project_validation::models::CsvSettings;
use crate::project_validation::tests::helpers::read_header;
use crate::project_validation::tests::test_types::{CsvHeaderTestCase, LIMIT, csv_error, header};

/// Expectations recorded from CPython 3.12's `next(csv.reader(...))`, identical on 3.13 and 3.14.
#[test]
fn given_seed_csv_text_when_reading_the_header_then_matches_python_csv_reader() {
    let test_cases = [
        CsvHeaderTestCase {
            description: "bare cr",
            text: "id,name\r1,a\r".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "no terminator",
            text: "id,name".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "empty",
            text: "".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&[]),
        },
        CsvHeaderTestCase {
            description: "blank first line",
            text: "\nid\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&[]),
        },
        CsvHeaderTestCase {
            description: "trailing delimiter",
            text: "a,b,\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["a", "b", ""]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\n1,a\\n' read default",
            text: "id,name\n1,a\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\n1,a\\n' read quoted",
            text: "id,name\n1,a\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\n1,a\\n' read quoted without doublequote",
            text: "id,name\n1,a\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\n1,a\\n' read quoted skipping initial space",
            text: "id,name\n1,a\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\n1,a\\n' read escaped",
            text: "id,name\n1,a\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\n1,a\\n' read quoted and escaped",
            text: "id,name\n1,a\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\n1,a\\n' read semicolon",
            text: "id,name\n1,a\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["id,name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\r\\n' read default",
            text: "id,name\r\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\r\\n' read quoted",
            text: "id,name\r\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\r\\n' read quoted without doublequote",
            text: "id,name\r\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\r\\n' read quoted skipping initial space",
            text: "id,name\r\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\r\\n' read escaped",
            text: "id,name\r\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\r\\n' read quoted and escaped",
            text: "id,name\r\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'id,name\\r\\n' read semicolon",
            text: "id,name\r\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["id,name"]),
        },
        CsvHeaderTestCase {
            description: "'\"a,x\",b\\n' read default",
            text: "\"a,x\",b\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["\"a", "x\"", "b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a,x\",b\\n' read quoted",
            text: "\"a,x\",b\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a,x", "b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a,x\",b\\n' read quoted without doublequote",
            text: "\"a,x\",b\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a,x", "b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a,x\",b\\n' read quoted skipping initial space",
            text: "\"a,x\",b\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a,x", "b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a,x\",b\\n' read escaped",
            text: "\"a,x\",b\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\"a", "x\"", "b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a,x\",b\\n' read quoted and escaped",
            text: "\"a,x\",b\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a,x", "b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a,x\",b\\n' read semicolon",
            text: "\"a,x\",b\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\"a,x\",b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"\"b\",c\\n' read default",
            text: "\"a\"\"b\",c\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["\"a\"\"b\"", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"\"b\",c\\n' read quoted",
            text: "\"a\"\"b\",c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\"b", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"\"b\",c\\n' read quoted without doublequote",
            text: "\"a\"\"b\",c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\"b\"", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"\"b\",c\\n' read quoted skipping initial space",
            text: "\"a\"\"b\",c\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\"b", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"\"b\",c\\n' read escaped",
            text: "\"a\"\"b\",c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\"a\"\"b\"", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"\"b\",c\\n' read quoted and escaped",
            text: "\"a\"\"b\",c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\"b", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"\"b\",c\\n' read semicolon",
            text: "\"a\"\"b\",c\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\"a\"\"b\",c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"b,c\\n' read default",
            text: "\"a\"b,c\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["\"a\"b", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"b,c\\n' read quoted",
            text: "\"a\"b,c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["ab", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"b,c\\n' read quoted without doublequote",
            text: "\"a\"b,c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["ab", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"b,c\\n' read quoted skipping initial space",
            text: "\"a\"b,c\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["ab", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"b,c\\n' read escaped",
            text: "\"a\"b,c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\"a\"b", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"b,c\\n' read quoted and escaped",
            text: "\"a\"b,c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["ab", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"b,c\\n' read semicolon",
            text: "\"a\"b,c\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\"a\"b,c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\\nb\",c\\n' read default",
            text: "\"a\nb\",c\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["\"a"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\\nb\",c\\n' read quoted",
            text: "\"a\nb\",c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\nb", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\\nb\",c\\n' read quoted without doublequote",
            text: "\"a\nb\",c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\nb", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\\nb\",c\\n' read quoted skipping initial space",
            text: "\"a\nb\",c\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\nb", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\\nb\",c\\n' read escaped",
            text: "\"a\nb\",c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\"a"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\\nb\",c\\n' read quoted and escaped",
            text: "\"a\nb\",c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\nb", "c"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\\nb\",c\\n' read semicolon",
            text: "\"a\nb\",c\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\"a"]),
        },
        CsvHeaderTestCase {
            description: "'a, b,  c\\n' read default",
            text: "a, b,  c\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["a", " b", "  c"]),
        },
        CsvHeaderTestCase {
            description: "'a, b,  c\\n' read quoted",
            text: "a, b,  c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", " b", "  c"]),
        },
        CsvHeaderTestCase {
            description: "'a, b,  c\\n' read quoted without doublequote",
            text: "a, b,  c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", " b", "  c"]),
        },
        CsvHeaderTestCase {
            description: "'a, b,  c\\n' read quoted skipping initial space",
            text: "a, b,  c\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "b", "c"]),
        },
        CsvHeaderTestCase {
            description: "'a, b,  c\\n' read escaped",
            text: "a, b,  c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", " b", "  c"]),
        },
        CsvHeaderTestCase {
            description: "'a, b,  c\\n' read quoted and escaped",
            text: "a, b,  c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", " b", "  c"]),
        },
        CsvHeaderTestCase {
            description: "'a, b,  c\\n' read semicolon",
            text: "a, b,  c\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a, b,  c"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\,b,c\\n' read default",
            text: "a\\,b,c\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["a\\", "b", "c"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\,b,c\\n' read quoted",
            text: "a\\,b,c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\\", "b", "c"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\,b,c\\n' read quoted without doublequote",
            text: "a\\,b,c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\\", "b", "c"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\,b,c\\n' read quoted skipping initial space",
            text: "a\\,b,c\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\\", "b", "c"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\,b,c\\n' read escaped",
            text: "a\\,b,c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a,b", "c"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\,b,c\\n' read quoted and escaped",
            text: "a\\,b,c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a,b", "c"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\,b,c\\n' read semicolon",
            text: "a\\,b,c\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\\,b,c"]),
        },
        CsvHeaderTestCase {
            description: "'a,b,\\n' read default",
            text: "a,b,\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["a", "b", ""]),
        },
        CsvHeaderTestCase {
            description: "'a,b,\\n' read quoted",
            text: "a,b,\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "b", ""]),
        },
        CsvHeaderTestCase {
            description: "'a,b,\\n' read quoted without doublequote",
            text: "a,b,\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "b", ""]),
        },
        CsvHeaderTestCase {
            description: "'a,b,\\n' read quoted skipping initial space",
            text: "a,b,\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "b", ""]),
        },
        CsvHeaderTestCase {
            description: "'a,b,\\n' read escaped",
            text: "a,b,\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "b", ""]),
        },
        CsvHeaderTestCase {
            description: "'a,b,\\n' read quoted and escaped",
            text: "a,b,\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "b", ""]),
        },
        CsvHeaderTestCase {
            description: "'a,b,\\n' read semicolon",
            text: "a,b,\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a,b,"]),
        },
        CsvHeaderTestCase {
            description: "'\"abc' read default",
            text: "\"abc".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["\"abc"]),
        },
        CsvHeaderTestCase {
            description: "'\"abc' read quoted",
            text: "\"abc".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["abc"]),
        },
        CsvHeaderTestCase {
            description: "'\"abc' read quoted without doublequote",
            text: "\"abc".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["abc"]),
        },
        CsvHeaderTestCase {
            description: "'\"abc' read quoted skipping initial space",
            text: "\"abc".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["abc"]),
        },
        CsvHeaderTestCase {
            description: "'\"abc' read escaped",
            text: "\"abc".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\"abc"]),
        },
        CsvHeaderTestCase {
            description: "'\"abc' read quoted and escaped",
            text: "\"abc".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["abc"]),
        },
        CsvHeaderTestCase {
            description: "'\"abc' read semicolon",
            text: "\"abc".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\"abc"]),
        },
        CsvHeaderTestCase {
            description: "'\\ufeffid,name\\n' read default",
            text: "\u{feff}id,name\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["\u{feff}id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'\\ufeffid,name\\n' read quoted",
            text: "\u{feff}id,name\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\u{feff}id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'\\ufeffid,name\\n' read quoted without doublequote",
            text: "\u{feff}id,name\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\u{feff}id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'\\ufeffid,name\\n' read quoted skipping initial space",
            text: "\u{feff}id,name\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\u{feff}id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'\\ufeffid,name\\n' read escaped",
            text: "\u{feff}id,name\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\u{feff}id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'\\ufeffid,name\\n' read quoted and escaped",
            text: "\u{feff}id,name\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\u{feff}id", "name"]),
        },
        CsvHeaderTestCase {
            description: "'\\ufeffid,name\\n' read semicolon",
            text: "\u{feff}id,name\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\u{feff}id,name"]),
        },
        CsvHeaderTestCase {
            description: "' \"a\", b\\n' read default",
            text: " \"a\", b\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&[" \"a\"", " b"]),
        },
        CsvHeaderTestCase {
            description: "' \"a\", b\\n' read quoted",
            text: " \"a\", b\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&[" \"a\"", " b"]),
        },
        CsvHeaderTestCase {
            description: "' \"a\", b\\n' read quoted without doublequote",
            text: " \"a\", b\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&[" \"a\"", " b"]),
        },
        CsvHeaderTestCase {
            description: "' \"a\", b\\n' read quoted skipping initial space",
            text: " \"a\", b\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "b"]),
        },
        CsvHeaderTestCase {
            description: "' \"a\", b\\n' read escaped",
            text: " \"a\", b\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&[" \"a\"", " b"]),
        },
        CsvHeaderTestCase {
            description: "' \"a\", b\\n' read quoted and escaped",
            text: " \"a\", b\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&[" \"a\"", " b"]),
        },
        CsvHeaderTestCase {
            description: "' \"a\", b\\n' read semicolon",
            text: " \"a\", b\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&[" \"a\", b"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\\\nb,c\\n' read default",
            text: "a\\\nb,c\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["a\\"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\\\nb,c\\n' read quoted",
            text: "a\\\nb,c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\\"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\\\nb,c\\n' read quoted without doublequote",
            text: "a\\\nb,c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\\"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\\\nb,c\\n' read quoted skipping initial space",
            text: "a\\\nb,c\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\\"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\\\nb,c\\n' read escaped",
            text: "a\\\nb,c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\nb", "c"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\\\nb,c\\n' read quoted and escaped",
            text: "a\\\nb,c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\nb", "c"]),
        },
        CsvHeaderTestCase {
            description: "'a\\\\\\nb,c\\n' read semicolon",
            text: "a\\\nb,c\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a\\"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"  ,b\\n' read default",
            text: "\"a\"  ,b\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["\"a\"  ", "b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"  ,b\\n' read quoted",
            text: "\"a\"  ,b\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a  ", "b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"  ,b\\n' read quoted without doublequote",
            text: "\"a\"  ,b\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a  ", "b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"  ,b\\n' read quoted skipping initial space",
            text: "\"a\"  ,b\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a  ", "b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"  ,b\\n' read escaped",
            text: "\"a\"  ,b\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\"a\"  ", "b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"  ,b\\n' read quoted and escaped",
            text: "\"a\"  ,b\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a  ", "b"]),
        },
        CsvHeaderTestCase {
            description: "'\"a\"  ,b\\n' read semicolon",
            text: "\"a\"  ,b\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["\"a\"  ,b"]),
        },
        CsvHeaderTestCase {
            description: "'a,\"b\"c\\n' read default",
            text: "a,\"b\"c\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["a", "\"b\"c"]),
        },
        CsvHeaderTestCase {
            description: "'a,\"b\"c\\n' read quoted",
            text: "a,\"b\"c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "bc"]),
        },
        CsvHeaderTestCase {
            description: "'a,\"b\"c\\n' read quoted without doublequote",
            text: "a,\"b\"c\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "bc"]),
        },
        CsvHeaderTestCase {
            description: "'a,\"b\"c\\n' read quoted skipping initial space",
            text: "a,\"b\"c\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "bc"]),
        },
        CsvHeaderTestCase {
            description: "'a,\"b\"c\\n' read escaped",
            text: "a,\"b\"c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "\"b\"c"]),
        },
        CsvHeaderTestCase {
            description: "'a,\"b\"c\\n' read quoted and escaped",
            text: "a,\"b\"c\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "bc"]),
        },
        CsvHeaderTestCase {
            description: "'a,\"b\"c\\n' read semicolon",
            text: "a,\"b\"c\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a,\"b\"c"]),
        },
        CsvHeaderTestCase {
            description: "'\\n\\nid\\n' read default",
            text: "\n\nid\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&[]),
        },
        CsvHeaderTestCase {
            description: "'\\n\\nid\\n' read quoted",
            text: "\n\nid\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&[]),
        },
        CsvHeaderTestCase {
            description: "'\\n\\nid\\n' read quoted without doublequote",
            text: "\n\nid\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&[]),
        },
        CsvHeaderTestCase {
            description: "'\\n\\nid\\n' read quoted skipping initial space",
            text: "\n\nid\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&[]),
        },
        CsvHeaderTestCase {
            description: "'\\n\\nid\\n' read escaped",
            text: "\n\nid\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&[]),
        },
        CsvHeaderTestCase {
            description: "'\\n\\nid\\n' read quoted and escaped",
            text: "\n\nid\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&[]),
        },
        CsvHeaderTestCase {
            description: "'\\n\\nid\\n' read semicolon",
            text: "\n\nid\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&[]),
        },
        CsvHeaderTestCase {
            description: "'a,b\\rc\\n' read default",
            text: "a,b\rc\n".to_owned(),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&["a", "b"]),
        },
        CsvHeaderTestCase {
            description: "'a,b\\rc\\n' read quoted",
            text: "a,b\rc\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "b"]),
        },
        CsvHeaderTestCase {
            description: "'a,b\\rc\\n' read quoted without doublequote",
            text: "a,b\rc\n".to_owned(),
            settings: CsvSettings {
                quotechar: Some("\"".to_owned()),
                doublequote: Some(false),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "b"]),
        },
        CsvHeaderTestCase {
            description: "'a,b\\rc\\n' read quoted skipping initial space",
            text: "a,b\rc\n".to_owned(),
            settings: CsvSettings {
                skipinitialspace: Some(true),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "b"]),
        },
        CsvHeaderTestCase {
            description: "'a,b\\rc\\n' read escaped",
            text: "a,b\rc\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "b"]),
        },
        CsvHeaderTestCase {
            description: "'a,b\\rc\\n' read quoted and escaped",
            text: "a,b\rc\n".to_owned(),
            settings: CsvSettings {
                escapechar: Some("\\".to_owned()),
                quotechar: Some("\"".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a", "b"]),
        },
        CsvHeaderTestCase {
            description: "'a,b\\rc\\n' read semicolon",
            text: "a,b\rc\n".to_owned(),
            settings: CsvSettings {
                delimiter: Some(";".to_owned()),
                ..CsvSettings::default()
            },
            field_limit: LIMIT,
            expected_header: header(&["a,b"]),
        },
        CsvHeaderTestCase {
            description: "a header longer than one decode chunk",
            text: format!("{},id\n1,2\n", "c".repeat(10_000)),
            settings: CsvSettings::default(),
            field_limit: LIMIT,
            expected_header: header(&[&"c".repeat(10_000), "id"]),
        },
        CsvHeaderTestCase {
            description: "a field at the limit",
            text: format!("{},id\n", "c".repeat(10)),
            settings: CsvSettings::default(),
            field_limit: 10,
            expected_header: header(&[&"c".repeat(10), "id"]),
        },
        CsvHeaderTestCase {
            description: "a field over the limit",
            text: format!("{},id\n", "c".repeat(11)),
            settings: CsvSettings::default(),
            field_limit: 10,
            expected_header: csv_error("field larger than field limit (10)"),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            read_header(&test_case.text, &test_case.settings, test_case.field_limit),
            test_case.expected_header,
            "{}",
            test_case.description
        );
    }
}
