use crate::errors::ConfigErrorKind;
use crate::models::ConfigValue;
use crate::yaml::main::safe_load::safe_load;
use crate::yaml::tests::helpers::{
    alias_chain, billion_laughs, deep_anchor_chain, mapping, merge_chain, text, under_a,
};
use crate::yaml::tests::test_types::{HostileYamlTestCase, SafeLoadTestCase};

#[test]
fn given_yaml_documents_when_loading_then_values_follow_the_core_schema() {
    let test_cases = [
        SafeLoadTestCase {
            description: "lowercase, capitalized and uppercase booleans",
            text: "[true, False, TRUE]",
            expected_value: Ok(ConfigValue::List(vec![
                ConfigValue::Bool(true),
                ConfigValue::Bool(false),
                ConfigValue::Bool(true),
            ])),
        },
        SafeLoadTestCase {
            description: "YAML 1.1 boolean words are text",
            text: "[yes, No, on, OFF, y]",
            expected_value: Ok(ConfigValue::List(vec![
                text("yes"),
                text("No"),
                text("on"),
                text("OFF"),
                text("y"),
            ])),
        },
        SafeLoadTestCase {
            description: "mixed-case boolean is text",
            text: "a: tRue",
            expected_value: Ok(under_a(text("tRue"))),
        },
        SafeLoadTestCase {
            description: "a leading zero is decimal",
            text: "a: 017",
            expected_value: Ok(under_a(ConfigValue::Integer(17))),
        },
        SafeLoadTestCase {
            description: "0o octal integer",
            text: "a: 0o17",
            expected_value: Ok(under_a(ConfigValue::Integer(15))),
        },
        SafeLoadTestCase {
            description: "hexadecimal integer",
            text: "a: 0x1F",
            expected_value: Ok(under_a(ConfigValue::Integer(31))),
        },
        SafeLoadTestCase {
            description: "signed integer",
            text: "a: -42",
            expected_value: Ok(under_a(ConfigValue::Integer(-42))),
        },
        SafeLoadTestCase {
            description: "binary, underscored and base 60 numbers are text",
            text: "[0b101, 1_000, 190:20:30]",
            expected_value: Ok(ConfigValue::List(vec![
                text("0b101"),
                text("1_000"),
                text("190:20:30"),
            ])),
        },
        SafeLoadTestCase {
            description: "an integer beyond 64 bits stays exact",
            text: "a: -0099999999999999999999999",
            expected_value: Ok(under_a(ConfigValue::BigInteger(
                "-99999999999999999999999".to_owned(),
            ))),
        },
        SafeLoadTestCase {
            description: "an exponent needs no dot or sign",
            text: "a: 1e5",
            expected_value: Ok(under_a(ConfigValue::Float(100_000.0))),
        },
        SafeLoadTestCase {
            description: "trailing and leading dots",
            text: "[5., +.5, -1.5E-2]",
            expected_value: Ok(ConfigValue::List(vec![
                ConfigValue::Float(5.0),
                ConfigValue::Float(0.5),
                ConfigValue::Float(-0.015),
            ])),
        },
        SafeLoadTestCase {
            description: "negative infinity",
            text: "a: -.Inf",
            expected_value: Ok(under_a(ConfigValue::Float(f64::NEG_INFINITY))),
        },
        SafeLoadTestCase {
            description: "tilde, null words and an empty value are null",
            text: "[~, null, Null, NULL, ]",
            expected_value: Ok(ConfigValue::List(vec![ConfigValue::Null; 4])),
        },
        SafeLoadTestCase {
            description: "an empty mapping value is null",
            text: "a:",
            expected_value: Ok(under_a(ConfigValue::Null)),
        },
        SafeLoadTestCase {
            description: "quoted values stay text",
            text: "a: 'true'",
            expected_value: Ok(under_a(text("true"))),
        },
        SafeLoadTestCase {
            description: "the non-specific tag keeps a plain scalar as text",
            text: "a: ! 123",
            expected_value: Ok(under_a(text("123"))),
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
            description: "dates and timestamps are text",
            text: "[2001-12-14, 2001-12-14t21:59:43.10-05:00]",
            expected_value: Ok(ConfigValue::List(vec![
                text("2001-12-14"),
                text("2001-12-14t21:59:43.10-05:00"),
            ])),
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
            description: "a repeated key keeps its first position and its last value",
            text: "{a: 1, b: 2, a: 3}",
            expected_value: Ok(mapping(vec![
                (text("a"), ConfigValue::Integer(3)),
                (text("b"), ConfigValue::Integer(2)),
            ])),
        },
        SafeLoadTestCase {
            description: "a redefined anchor applies to later aliases",
            text: "a: &x 1\nb: &x 2\nc: *x",
            expected_value: Ok(mapping(vec![
                (text("a"), ConfigValue::Integer(1)),
                (text("b"), ConfigValue::Integer(2)),
                (text("c"), ConfigValue::Integer(2)),
            ])),
        },
        SafeLoadTestCase {
            description: "tabs separating words are content",
            text: "a: x\ty",
            expected_value: Ok(under_a(text("x\ty"))),
        },
        SafeLoadTestCase {
            description: "a leading byte order mark is skipped",
            text: "\u{feff}a: 1",
            expected_value: Ok(under_a(ConfigValue::Integer(1))),
        },
        SafeLoadTestCase {
            description: "a %YAML directive is accepted",
            text: "%YAML 1.2\n--- a",
            expected_value: Ok(text("a")),
        },
        SafeLoadTestCase {
            description: "literal and folded scalars at the end of input",
            text: "a: |\n  x\nb: >\n  folded\n  text",
            expected_value: Ok(mapping(vec![
                (text("a"), text("x\n")),
                (text("b"), text("folded text")),
            ])),
        },
        SafeLoadTestCase {
            description: "keep and strip chomping",
            text: "a: |+\n  x\n\nb: |-\n  y\n\n",
            expected_value: Ok(mapping(vec![
                (text("a"), text("x\n\n")),
                (text("b"), text("y")),
            ])),
        },
        SafeLoadTestCase {
            description: "a literal in a sequence at the end of input",
            text: "- |\n  x",
            expected_value: Ok(ConfigValue::List(vec![text("x")])),
        },
        SafeLoadTestCase {
            description: "keep chomping at the end of input",
            text: "a: |+\n  x\n\n",
            expected_value: Ok(under_a(text("x\n\n"))),
        },
        SafeLoadTestCase {
            description: "empty stream is null",
            text: "",
            expected_value: Ok(ConfigValue::Null),
        },
        SafeLoadTestCase {
            description: "a merge indicator outside a key is text",
            text: "a: <<",
            expected_value: Ok(under_a(text("<<"))),
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
            description: "a hexadecimal integer beyond 64 bits is rejected",
            text: "a: 0x10000000000000000",
            expected_value: Err(ConfigErrorKind::Construct),
        },
        SafeLoadTestCase {
            description: "an explicit integer tag on text that is not a number is rejected",
            text: "a: !!int abc",
            expected_value: Err(ConfigErrorKind::Construct),
        },
        SafeLoadTestCase {
            description: "an explicit integer tag on a lone sign is rejected",
            text: "a: !!int '-'",
            expected_value: Err(ConfigErrorKind::Construct),
        },
        SafeLoadTestCase {
            description: "unknown tags are unsupported",
            text: "a: !custom 1",
            expected_value: Err(ConfigErrorKind::Unsupported),
        },
        SafeLoadTestCase {
            description: "control characters are rejected",
            text: "a: \u{7}",
            expected_value: Err(ConfigErrorKind::Syntax),
        },
        SafeLoadTestCase {
            description: "recursive aliases are unsupported",
            text: "a: &x [*x]",
            expected_value: Err(ConfigErrorKind::Unsupported),
        },
        SafeLoadTestCase {
            description: "an undefined alias is rejected",
            text: "a: *missing",
            expected_value: Err(ConfigErrorKind::Syntax),
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
fn given_hostile_yaml_when_loading_then_reader_refuses_without_exhausting_resources() {
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
            description: "an integer beyond the 4300 digits Python converts",
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
