use std::cell::RefCell;

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
            expected: Err(TemplateFailure::Missing),
            expected_reads: &["CTX:model.schema"],
        },
        TemplateTestCase {
            description: "parse errors are invalid",
            text: "${coalesce(a,,b)}",
            expected: Err(TemplateFailure::Invalid),
            expected_reads: &[],
        },
        TemplateTestCase {
            description: "an unsupported function or namespace is invalid",
            text: "${upper(env)}",
            expected: Err(TemplateFailure::Invalid),
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
