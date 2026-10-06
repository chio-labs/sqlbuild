use crate::errors::ConfigErrorKind;
use crate::models::{ConfigDate, ConfigDateTime, ConfigTime, ConfigValue};
use crate::toml::main::load_toml::load_toml;
use crate::toml::tests::helpers::table;
use crate::toml::tests::test_types::{HostileTomlTestCase, LoadTomlTestCase};

#[test]
fn given_toml_documents_when_loading_then_values_match_tomllib() {
    let test_cases = [
        LoadTomlTestCase {
            description: "tables keep document order",
            text: "z = 1\n[b]\nx = true\n[a]\ny = 'q'",
            expected_value: Ok(ConfigValue::Map(vec![
                (ConfigValue::String("z".to_owned()), ConfigValue::Integer(1)),
                (
                    ConfigValue::String("b".to_owned()),
                    ConfigValue::Map(vec![(
                        ConfigValue::String("x".to_owned()),
                        ConfigValue::Bool(true),
                    )]),
                ),
                (
                    ConfigValue::String("a".to_owned()),
                    ConfigValue::Map(vec![(
                        ConfigValue::String("y".to_owned()),
                        ConfigValue::String("q".to_owned()),
                    )]),
                ),
            ])),
        },
        LoadTomlTestCase {
            description: "implicit parent tables are created where first named",
            text: "[a.b]\nx = 1\n[c]\n[a.d]\ny = 2",
            expected_value: Ok(ConfigValue::Map(vec![
                (
                    ConfigValue::String("a".to_owned()),
                    ConfigValue::Map(vec![
                        (
                            ConfigValue::String("b".to_owned()),
                            ConfigValue::Map(vec![(
                                ConfigValue::String("x".to_owned()),
                                ConfigValue::Integer(1),
                            )]),
                        ),
                        (
                            ConfigValue::String("d".to_owned()),
                            ConfigValue::Map(vec![(
                                ConfigValue::String("y".to_owned()),
                                ConfigValue::Integer(2),
                            )]),
                        ),
                    ]),
                ),
                (
                    ConfigValue::String("c".to_owned()),
                    ConfigValue::Map(vec![]),
                ),
            ])),
        },
        LoadTomlTestCase {
            description: "dotted keys and arrays of tables",
            text: "p.q = 1\n[[r]]\ns = 1.5\n[[r]]",
            expected_value: Ok(ConfigValue::Map(vec![
                (
                    ConfigValue::String("p".to_owned()),
                    ConfigValue::Map(vec![(
                        ConfigValue::String("q".to_owned()),
                        ConfigValue::Integer(1),
                    )]),
                ),
                (
                    ConfigValue::String("r".to_owned()),
                    ConfigValue::List(vec![
                        ConfigValue::Map(vec![(
                            ConfigValue::String("s".to_owned()),
                            ConfigValue::Float(1.5),
                        )]),
                        ConfigValue::Map(vec![]),
                    ]),
                ),
            ])),
        },
        LoadTomlTestCase {
            description: "offset datetime keeps its offset",
            text: "t = 1979-05-27T00:32:00.999999999-07:00",
            expected_value: Ok(ConfigValue::Map(vec![(
                ConfigValue::String("t".to_owned()),
                ConfigValue::DateTime(ConfigDateTime {
                    date: ConfigDate {
                        year: 1979,
                        month: 5,
                        day: 27,
                    },
                    time: ConfigTime {
                        hour: 0,
                        minute: 32,
                        second: 0,
                        microsecond: 999_999,
                    },
                    utc_offset_seconds: Some(-25_200),
                }),
            )])),
        },
        LoadTomlTestCase {
            description: "local date and time",
            text: "d = 1979-05-27\nt = 07:32:00",
            expected_value: Ok(ConfigValue::Map(vec![
                (
                    ConfigValue::String("d".to_owned()),
                    ConfigValue::Date(ConfigDate {
                        year: 1979,
                        month: 5,
                        day: 27,
                    }),
                ),
                (
                    ConfigValue::String("t".to_owned()),
                    ConfigValue::Time(ConfigTime {
                        hour: 7,
                        minute: 32,
                        second: 0,
                        microsecond: 0,
                    }),
                ),
            ])),
        },
        LoadTomlTestCase {
            description: "escaped backslash before e is TOML 1.0",
            text: "a = \"\\\\e\"",
            expected_value: Ok(ConfigValue::Map(vec![(
                ConfigValue::String("a".to_owned()),
                ConfigValue::String("\\e".to_owned()),
            )])),
        },
        LoadTomlTestCase {
            description: "multi-line array is TOML 1.0",
            text: "a = [\n1,\n]",
            expected_value: Ok(ConfigValue::Map(vec![(
                ConfigValue::String("a".to_owned()),
                ConfigValue::List(vec![ConfigValue::Integer(1)]),
            )])),
        },
        LoadTomlTestCase {
            description: "trailing comma in an inline table is TOML 1.1",
            text: "a = {x = 1,}",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "newline in an inline table is TOML 1.1",
            text: "a = {\nx = 1}",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "escape e is TOML 1.1",
            text: "a = \"\\e\"",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "escape x is TOML 1.1",
            text: "a = \"\\x41\"",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "time without seconds is TOML 1.1",
            text: "a = 07:32",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "leap second is rejected",
            text: "a = 1990-12-31T23:59:60Z",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "impossible date is rejected",
            text: "a = 2021-02-30",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "duplicate keys are rejected",
            text: "a = 1\na = 2",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "an implicit table declared later keeps the position where it was created",
            text: "[p.a.config]\nx = 1\n[p.b]\ny = 2\n[p.a]\nz = 3",
            expected_value: Ok(table(vec![(
                "p",
                table(vec![
                    (
                        "a",
                        table(vec![
                            ("config", table(vec![("x", ConfigValue::Integer(1))])),
                            ("z", ConfigValue::Integer(3)),
                        ]),
                    ),
                    ("b", table(vec![("y", ConfigValue::Integer(2))])),
                ]),
            )])),
        },
        LoadTomlTestCase {
            description: "a dotted key creates its table before a later header",
            text: "q.x = 1\n[r]\n[q.s]",
            expected_value: Ok(table(vec![
                (
                    "q",
                    table(vec![("x", ConfigValue::Integer(1)), ("s", table(vec![]))]),
                ),
                ("r", table(vec![])),
            ])),
        },
        LoadTomlTestCase {
            description: "a dotted key cannot reach into an array of tables",
            text: "[[a.b]]\n[a]\nb.c.d = 1",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "a two-segment dotted key cannot reach into an array of tables",
            text: "[[a.b]]\n[a]\nb.c = 1",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "a dotted key cannot reopen a table declared by a header",
            text: "[a.b]\n[a]\nb.c = 1",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "a header cannot redeclare a table created by a dotted key",
            text: "a.b = 1\n[a]",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "a header cannot extend a table opened by dotted keys in a section",
            text: "[a]\nb.c = 1\n[a.b]",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "a header cannot extend an inline table",
            text: "a = {b = 1}\n[a.c]",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "an inline table cannot be extended by a dotted key",
            text: "x = {a = {b = 1}, a.c = 2}",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "an array of tables cannot extend a static array",
            text: "a = [1]\n[[a]]",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "each array of tables element reopens its own sub-tables",
            text: "[[t]]\n[t.c]\nx = 1\n[[t]]\n[t.c]\ny = 2",
            expected_value: Ok(table(vec![(
                "t",
                ConfigValue::List(vec![
                    table(vec![("c", table(vec![("x", ConfigValue::Integer(1))]))]),
                    table(vec![("c", table(vec![("y", ConfigValue::Integer(2))]))]),
                ]),
            )])),
        },
        LoadTomlTestCase {
            description: "dotted keys may extend the tables they created",
            text: "a.b.c = 1\na.b.d = 2",
            expected_value: Ok(table(vec![(
                "a",
                table(vec![(
                    "b",
                    table(vec![
                        ("c", ConfigValue::Integer(1)),
                        ("d", ConfigValue::Integer(2)),
                    ]),
                )]),
            )])),
        },
        LoadTomlTestCase {
            description: "a byte order mark is rejected as tomllib rejects it",
            text: "\u{feff}a = 1",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        LoadTomlTestCase {
            description: "CRLF line endings are normalized inside multi-line strings",
            text: "a = \"\"\"x\r\ny\"\"\"",
            expected_value: Ok(table(vec![("a", ConfigValue::String("x\ny".to_owned()))])),
        },
    ];
    for test_case in test_cases {
        let actual = load_toml(test_case.text).map_err(|error| error.kind);
        assert_eq!(
            actual, test_case.expected_value,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_hostile_toml_when_loading_then_native_reader_rejects_without_exhausting_the_stack() {
    let test_cases = [
        HostileTomlTestCase {
            description: "ten thousand nested arrays",
            text: format!("a = {}{}", "[".repeat(10_000), "]".repeat(10_000)),
            expected_error: ConfigErrorKind::Syntax,
        },
        HostileTomlTestCase {
            description: "ten thousand nested inline tables",
            text: format!("a = {}{}", "{b = ".repeat(10_000), "}".repeat(10_000)),
            expected_error: ConfigErrorKind::Syntax,
        },
        HostileTomlTestCase {
            description: "a dotted key with a hundred thousand segments",
            text: format!("a{} = 1", ".a".repeat(100_000)),
            expected_error: ConfigErrorKind::Syntax,
        },
        HostileTomlTestCase {
            description: "a table header with a hundred thousand segments",
            text: format!("[a{}]", ".a".repeat(100_000)),
            expected_error: ConfigErrorKind::Syntax,
        },
    ];
    for test_case in test_cases {
        let actual = load_toml(&test_case.text).map_err(|error| error.kind);
        assert_eq!(
            actual,
            Err(test_case.expected_error),
            "{}",
            test_case.description
        );
    }
}
