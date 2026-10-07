use crate::errors::ConfigErrorKind;
use crate::models::ConfigValue;
use crate::yaml::main::safe_load::safe_load;
use crate::yaml::tests::helpers::{
    alias_chain, billion_laughs, date, datetime, deep_anchor_chain, mapping, merge_chain, text,
    under_a,
};
use crate::yaml::tests::test_types::{HostileYamlTestCase, SafeLoadTestCase};

#[test]
fn given_yaml_documents_when_loading_then_values_match_pyyaml_safe_load() {
    let test_cases = [
        SafeLoadTestCase {
            description: "YAML 1.1 booleans",
            text: "a: yes",
            expected_value: Ok(under_a(ConfigValue::Bool(true))),
        },
        SafeLoadTestCase {
            description: "mixed-case boolean is text",
            text: "a: yEs",
            expected_value: Ok(under_a(text("yEs"))),
        },
        SafeLoadTestCase {
            description: "off is false",
            text: "a: Off",
            expected_value: Ok(under_a(ConfigValue::Bool(false))),
        },
        SafeLoadTestCase {
            description: "octal integer",
            text: "a: 017",
            expected_value: Ok(under_a(ConfigValue::Integer(15))),
        },
        SafeLoadTestCase {
            description: "0o is not YAML 1.1 octal",
            text: "a: 0o17",
            expected_value: Ok(under_a(text("0o17"))),
        },
        SafeLoadTestCase {
            description: "binary integer",
            text: "a: 0b101",
            expected_value: Ok(under_a(ConfigValue::Integer(5))),
        },
        SafeLoadTestCase {
            description: "hexadecimal integer",
            text: "a: 0x1F",
            expected_value: Ok(under_a(ConfigValue::Integer(31))),
        },
        SafeLoadTestCase {
            description: "underscores in integers",
            text: "a: 1_000",
            expected_value: Ok(under_a(ConfigValue::Integer(1000))),
        },
        SafeLoadTestCase {
            description: "sexagesimal integer",
            text: "a: 190:20:30",
            expected_value: Ok(under_a(ConfigValue::Integer(685_230))),
        },
        SafeLoadTestCase {
            description: "sexagesimal float",
            text: "a: -190:20:30.5",
            expected_value: Ok(under_a(ConfigValue::Float(-685_230.5))),
        },
        SafeLoadTestCase {
            description: "eight is not octal",
            text: "a: 08",
            expected_value: Ok(under_a(text("08"))),
        },
        SafeLoadTestCase {
            description: "arbitrary precision integer",
            text: "a: 99999999999999999999999",
            expected_value: Ok(under_a(ConfigValue::BigInteger(
                "99999999999999999999999".to_owned(),
            ))),
        },
        SafeLoadTestCase {
            description: "exponent needs a dot and a sign",
            text: "a: 1e5",
            expected_value: Ok(under_a(text("1e5"))),
        },
        SafeLoadTestCase {
            description: "float with signed exponent",
            text: "a: 1.0e+5",
            expected_value: Ok(under_a(ConfigValue::Float(100_000.0))),
        },
        SafeLoadTestCase {
            description: "float with trailing dot",
            text: "a: 5.",
            expected_value: Ok(under_a(ConfigValue::Float(5.0))),
        },
        SafeLoadTestCase {
            description: "signed leading-dot float is text",
            text: "a: +.5",
            expected_value: Ok(under_a(text("+.5"))),
        },
        SafeLoadTestCase {
            description: "negative infinity",
            text: "a: -.Inf",
            expected_value: Ok(under_a(ConfigValue::Float(f64::NEG_INFINITY))),
        },
        SafeLoadTestCase {
            description: "tilde is null",
            text: "a: ~",
            expected_value: Ok(under_a(ConfigValue::Null)),
        },
        SafeLoadTestCase {
            description: "empty value is null",
            text: "a:",
            expected_value: Ok(under_a(ConfigValue::Null)),
        },
        SafeLoadTestCase {
            description: "quoted values stay text",
            text: "a: 'yes'",
            expected_value: Ok(under_a(text("yes"))),
        },
        SafeLoadTestCase {
            description: "non-specific tag resolves quoted scalars",
            text: "a: ! '123'",
            expected_value: Ok(under_a(ConfigValue::Integer(123))),
        },
        SafeLoadTestCase {
            description: "explicit string tag",
            text: "a: !!str 1",
            expected_value: Ok(under_a(text("1"))),
        },
        SafeLoadTestCase {
            description: "explicit integer tag parses hexadecimal text",
            text: "a: !!int '0x10'",
            expected_value: Ok(under_a(ConfigValue::Integer(16))),
        },
        SafeLoadTestCase {
            description: "date",
            text: "a: 2001-12-14",
            expected_value: Ok(under_a(date(2001, 12, 14))),
        },
        SafeLoadTestCase {
            description: "single-digit month is text",
            text: "a: 2001-1-4",
            expected_value: Ok(under_a(text("2001-1-4"))),
        },
        SafeLoadTestCase {
            description: "aware timestamp",
            text: "a: 2001-12-14t21:59:43.10-05:00",
            expected_value: Ok(under_a(datetime(
                [2001, 12, 14, 21, 59, 43, 100_000],
                Some(-18_000),
            ))),
        },
        SafeLoadTestCase {
            description: "spaced timestamp with short offset",
            text: "a: 2001-12-14 21:59:43.10 -5",
            expected_value: Ok(under_a(datetime(
                [2001, 12, 14, 21, 59, 43, 100_000],
                Some(-18_000),
            ))),
        },
        SafeLoadTestCase {
            description: "naive timestamp truncates to microseconds",
            text: "a: 2001-12-14 21:59:43.1234567",
            expected_value: Ok(under_a(datetime([2001, 12, 14, 21, 59, 43, 123_456], None))),
        },
        SafeLoadTestCase {
            description: "merge keys put merged entries first",
            text: "base: &b {x: 1, y: 2}\nother:\n  y: 3\n  <<: *b",
            expected_value: Ok(mapping(vec![
                (
                    text("base"),
                    mapping(vec![
                        (text("x"), ConfigValue::Integer(1)),
                        (text("y"), ConfigValue::Integer(2)),
                    ]),
                ),
                (
                    text("other"),
                    mapping(vec![
                        (text("x"), ConfigValue::Integer(1)),
                        (text("y"), ConfigValue::Integer(3)),
                    ]),
                ),
            ])),
        },
        SafeLoadTestCase {
            description: "merge list prefers earlier mappings",
            text: "a:\n  <<: [{k: 1}, {k: 2, j: 3}]",
            expected_value: Ok(under_a(mapping(vec![
                (text("k"), ConfigValue::Integer(1)),
                (text("j"), ConfigValue::Integer(3)),
            ]))),
        },
        SafeLoadTestCase {
            description: "equal numeric keys collapse to the first key",
            text: "{1: a, 1.0: b, true: c}",
            expected_value: Ok(mapping(vec![(ConfigValue::Integer(1), text("c"))])),
        },
        SafeLoadTestCase {
            description: "equals sign key is text",
            text: "=: 1",
            expected_value: Ok(mapping(vec![(text("="), ConfigValue::Integer(1))])),
        },
        SafeLoadTestCase {
            description: "empty stream is null",
            text: "",
            expected_value: Ok(ConfigValue::Null),
        },
        SafeLoadTestCase {
            description: "duplicate anchors are rejected",
            text: "a: &x 1\nb: &x 2",
            expected_value: Err(ConfigErrorKind::Construct),
        },
        SafeLoadTestCase {
            description: "equals sign value has no constructor",
            text: "a: =",
            expected_value: Err(ConfigErrorKind::Construct),
        },
        SafeLoadTestCase {
            description: "merge value outside a key has no constructor",
            text: "a: <<",
            expected_value: Err(ConfigErrorKind::Construct),
        },
        SafeLoadTestCase {
            description: "impossible date is rejected",
            text: "a: 2002-02-30",
            expected_value: Err(ConfigErrorKind::Construct),
        },
        SafeLoadTestCase {
            description: "unhashable key is rejected",
            text: "{[1, 2]: a}",
            expected_value: Err(ConfigErrorKind::Construct),
        },
        SafeLoadTestCase {
            description: "several documents are rejected",
            text: "--- 1\n--- 2",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        SafeLoadTestCase {
            description: "hexadecimal without digits is rejected",
            text: "a: 0x_",
            expected_value: Err(ConfigErrorKind::Construct),
        },
        SafeLoadTestCase {
            description: "unknown tags are rejected",
            text: "a: !custom 1",
            expected_value: Err(ConfigErrorKind::Construct),
        },
        SafeLoadTestCase {
            description: "sets are left to Python",
            text: "a: !!set {x}",
            expected_value: Err(ConfigErrorKind::Unsupported),
        },
        SafeLoadTestCase {
            description: "control characters are rejected",
            text: "a: \u{7}",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        SafeLoadTestCase {
            description: "YAML 1.1 line separators are left to Python",
            text: "a: b\u{2028}c",
            expected_value: Err(ConfigErrorKind::Unsupported),
        },
        SafeLoadTestCase {
            description: "recursive aliases are left to Python",
            text: "a: &x [*x]",
            expected_value: Err(ConfigErrorKind::Unsupported),
        },
        SafeLoadTestCase {
            description: "literal scalar at the end of input has no final line break",
            text: "a: |\n  x",
            expected_value: Ok(under_a(text("x"))),
        },
        SafeLoadTestCase {
            description: "folded scalar at the end of input has no final line break",
            text: "a: >\n  folded",
            expected_value: Ok(under_a(text("folded"))),
        },
        SafeLoadTestCase {
            description: "sequence entry literal at the end of input",
            text: "- |\n  x",
            expected_value: Ok(ConfigValue::List(vec![text("x")])),
        },
        SafeLoadTestCase {
            description: "trailing indentation without a line break is not content",
            text: "a: |\n  x\n  ",
            expected_value: Ok(under_a(text("x\n"))),
        },
        SafeLoadTestCase {
            description: "keep chomping counts only complete trailing lines",
            text: "a: |+\n  x\n\n ",
            expected_value: Ok(under_a(text("x\n\n"))),
        },
        SafeLoadTestCase {
            description: "strip chomping drops trailing lines",
            text: "a: |-\n  x\n\n",
            expected_value: Ok(under_a(text("x"))),
        },
        SafeLoadTestCase {
            description: "a literal of blank lines clips to empty text",
            text: "a: |\n   \n",
            expected_value: Ok(under_a(text(""))),
        },
        SafeLoadTestCase {
            description: "more-indented trailing spaces are content",
            text: "a: |\n  x\n    ",
            expected_value: Ok(under_a(text("x\n  "))),
        },
        SafeLoadTestCase {
            description: "explicit indentation under a nested sequence",
            text: "a:\n  - |2-\n     x\n    y\n",
            expected_value: Ok(under_a(ConfigValue::List(vec![text(" x\ny")]))),
        },
        SafeLoadTestCase {
            description: "a leading byte order mark is skipped",
            text: "\u{feff}a: 1",
            expected_value: Ok(under_a(ConfigValue::Integer(1))),
        },
        SafeLoadTestCase {
            description: "the non-specific tag keeps a quoted line break as text",
            text: "a: ! \"\\n\"",
            expected_value: Ok(under_a(text("\n"))),
        },
        SafeLoadTestCase {
            description: "sexagesimal digits may have leading zeros",
            text: "a: 1:05",
            expected_value: Ok(under_a(ConfigValue::Integer(65))),
        },
        SafeLoadTestCase {
            description: "a lone document end marker is rejected",
            text: "...",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        SafeLoadTestCase {
            description: "a document end marker after comments is rejected",
            text: "# c\n...",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        SafeLoadTestCase {
            description: "a flow key spanning lines is rejected",
            text: "{a\nb: 1}",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        SafeLoadTestCase {
            description: "a flow key with its value indicator on the next line is rejected",
            text: "{a\n: 1}",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        SafeLoadTestCase {
            description: "an anchor glued to a flow collection is left to Python",
            text: "&a{}",
            expected_value: Err(ConfigErrorKind::Unsupported),
        },
        SafeLoadTestCase {
            description: "a plain scalar cannot start with a block indicator",
            text: "{>-: 1}",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        SafeLoadTestCase {
            description: "a question mark ending a value is not an explicit key",
            text: "a: b?\n: c",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        SafeLoadTestCase {
            description: "question marks in flow scalars are left to Python",
            text: "[a?b]",
            expected_value: Err(ConfigErrorKind::Unsupported),
        },
        SafeLoadTestCase {
            description: "tabs are left to Python",
            text: "a: x\ty",
            expected_value: Err(ConfigErrorKind::Unsupported),
        },
        SafeLoadTestCase {
            description: "inner byte order marks are left to Python",
            text: "a: x\u{feff}",
            expected_value: Err(ConfigErrorKind::Unsupported),
        },
        SafeLoadTestCase {
            description: "directives are left to Python",
            text: "%YAML 1.1\n--- a",
            expected_value: Err(ConfigErrorKind::Unsupported),
        },
    ];
    for test_case in test_cases {
        let actual = safe_load(test_case.text).map_err(|error| error.kind);
        assert_eq!(
            actual, test_case.expected_value,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_hostile_yaml_when_loading_then_native_reader_defers_without_exhausting_resources() {
    let test_cases = [
        HostileYamlTestCase {
            description: "a ten thousand link alias chain",
            text: alias_chain(10_000),
            expected_error: ConfigErrorKind::Unsupported,
        },
        HostileYamlTestCase {
            description: "billion laughs with twelve levels",
            text: billion_laughs(12),
            expected_error: ConfigErrorKind::Unsupported,
        },
        HostileYamlTestCase {
            description: "merge keys doubling over thirty levels",
            text: merge_chain(30),
            expected_error: ConfigErrorKind::Unsupported,
        },
        HostileYamlTestCase {
            description: "anchors wrapping deep flow nesting",
            text: deep_anchor_chain(50, 200),
            expected_error: ConfigErrorKind::Unsupported,
        },
        HostileYamlTestCase {
            description: "a hundred thousand nested flow sequences",
            text: format!("a: {}{}", "[".repeat(100_000), "]".repeat(100_000)),
            expected_error: ConfigErrorKind::Syntax,
        },
        HostileYamlTestCase {
            description: "a hundred thousand nested block sequences",
            text: "- ".repeat(100_000),
            expected_error: ConfigErrorKind::Unsupported,
        },
        HostileYamlTestCase {
            description: "an integer beyond Python's string conversion limit",
            text: format!("a: {}", "9".repeat(4_301)),
            expected_error: ConfigErrorKind::Unsupported,
        },
    ];
    for test_case in test_cases {
        let actual = safe_load(&test_case.text).map_err(|error| error.kind);
        assert_eq!(
            actual,
            Err(test_case.expected_error),
            "{}",
            test_case.description
        );
    }
}
