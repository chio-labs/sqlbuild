use std::cell::RefCell;

use crate::templates::errors::TemplateError;
use crate::templates::main::expand_template_string::expand_template_string;
use crate::templates::models::{StringExpansion, TemplateFailure, TemplateOptions};
use crate::templates::tests::helpers::{text, value};
use crate::templates::tests::test_types::{TemplateTestCase, TestHost, Value};

#[test]
fn given_template_strings_when_expanding_then_values_and_reads_match_python() {
    let test_cases = [
        TemplateTestCase {
            description: "a whole-string variable keeps its value",
            text: "${flag}",
            expected: value(Value::Bool(true)),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "embedded templates render as text",
            text: "orders_${env}_${flag}_${null}",
            expected: text("orders_prod_true_"),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "coalesce skips a missing environment variable and re-reads the last",
            text: "${coalesce(ENV:MISSING, ENV:SCHEMA_NAME, 'fallback')}",
            expected: value(Value::Text("analytics".to_owned())),
            expected_reads: &["ENV:MISSING", "ENV:SCHEMA_NAME"],
        },
        TemplateTestCase {
            description: "coalesce returns the last argument when none is truthy",
            text: "${coalesce(ENV:MISSING, ' False ', ENV:EMPTY)}",
            expected: value(Value::Text(String::new())),
            expected_reads: &["ENV:MISSING", "ENV:EMPTY", "ENV:EMPTY"],
        },
        TemplateTestCase {
            description: "if, eq and ne compare rendered text",
            text: "${if(eq(CTX:run.target, 'prod'), 'p', ne(flag, true))}",
            expected: value(Value::Text("p".to_owned())),
            expected_reads: &["CTX:run.target"],
        },
        TemplateTestCase {
            description: "escapes and nested quotes inside strings",
            text: r#"${"a\"b)c"}"#,
            expected: value(Value::Text("a\"b)c".to_owned())),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "an unknown context key is preserved",
            text: "${CTX:model.alias}",
            expected: value(Value::Text("${CTX:model.alias}".to_owned())),
            expected_reads: &["CTX:model.alias"],
        },
        TemplateTestCase {
            description: "a string without a complete template is unchanged",
            text: "${} and ${a{b}",
            expected: Ok(StringExpansion::Unchanged),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "a context key without a value is missing",
            text: "${CTX:model.schema}",
            expected: Err(TemplateFailure::Missing(
                TemplateError::UnavailableContextKey("model.schema".to_owned()),
            )),
            expected_reads: &["CTX:model.schema"],
        },
        TemplateTestCase {
            description: "a missing variable after a coalesce names itself",
            text: "${coalesce(missing, '')}_${ENV:UNSET}",
            expected: Err(TemplateFailure::Missing(
                TemplateError::MissingEnvironmentVariable("UNSET".to_owned()),
            )),
            expected_reads: &["ENV:UNSET"],
        },
        TemplateTestCase {
            description: "an unexpected token reports its unquoted value and position",
            text: "${coalesce(a,,b)}",
            expected: Err(TemplateFailure::Invalid(TemplateError::UnexpectedToken(
                ",".to_owned(),
                11,
            ))),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "a trailing token after the expression",
            text: "${env 'x y'}",
            expected: Err(TemplateFailure::Invalid(TemplateError::UnexpectedToken(
                "x y".to_owned(),
                4,
            ))),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "an unclosed call expects its parenthesis at the end",
            text: "${if(flag, env",
            expected: Ok(StringExpansion::Unchanged),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "an unclosed call inside a template expects its parenthesis",
            text: "${eq(flag env)}",
            expected: Err(TemplateFailure::Invalid(TemplateError::ExpectedSymbol(
                ')', 8,
            ))),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "an unterminated string reports where it opens",
            text: "${'abc}",
            expected: Err(TemplateFailure::Invalid(TemplateError::UnterminatedString(
                "single", 0,
            ))),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "an escape at the end of the expression",
            text: "${\"ab\\}",
            expected: Err(TemplateFailure::Invalid(TemplateError::UnterminatedEscape(
                3,
            ))),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "argument counts are checked before arguments are evaluated",
            text: "${ne(missing)}",
            expected: Err(TemplateFailure::Invalid(TemplateError::ArgumentCount(
                "ne", 2,
            ))),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "an unsupported function is invalid",
            text: "${upper(env)}",
            expected: Err(TemplateFailure::Invalid(
                TemplateError::UnsupportedFunction("upper".to_owned()),
            )),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "an unsupported namespace is invalid",
            text: "${VAR:env}",
            expected: Err(TemplateFailure::Invalid(
                TemplateError::UnsupportedNamespace("VAR".to_owned()),
            )),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "rendering an opaque value is left to Python",
            text: "x_${opaque}",
            expected: Err(TemplateFailure::Unsupported),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "non-ASCII outside quotes is left to Python's whitespace rules",
            text: "${coalesce(\u{a0}env)}",
            expected: Err(TemplateFailure::Unsupported),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "Python separators are whitespace between tokens",
            text: "${coalesce(\u{1f}env\t)}",
            expected: value(Value::Text("prod".to_owned())),
            expected_reads: &[],
        },
    ];

    for test_case in test_cases {
        let host = TestHost {
            variables: vec![
                ("flag", Value::Bool(true)),
                ("env", Value::Text("prod".to_owned())),
                ("opaque", Value::Opaque),
            ],
            environment: vec![("SCHEMA_NAME", "analytics"), ("EMPTY", "")],
            context: vec![("run.target", Some("prod")), ("model.schema", None)],
            reads: RefCell::new(Vec::new()),
        };
        let options = TemplateOptions {
            allow_context: true,
            preserve_context_tokens: false,
            preserve_unknown_context: true,
        };
        let expansion = expand_template_string(&host, test_case.text, options);
        assert_eq!(
            (expansion, host.reads.into_inner()),
            (
                test_case.expected,
                test_case
                    .expected_reads
                    .iter()
                    .map(|read| (*read).to_owned())
                    .collect::<Vec<_>>()
            ),
            "{}",
            test_case.description
        );
    }
}
