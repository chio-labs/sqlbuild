use std::convert::Infallible;

use crate::rule_results::main::duplicate_literal_hints::duplicate_literal_hints;
use crate::rule_results::main::format_result::format_result;
use crate::rule_results::models::{ResultCounts, RuleFinding};
use crate::rule_results::tests::test_types::{HintTestCase, ResultTestCase};

const SUFFIX: &str = " and reference it with `@const` in each file. R.";

#[test]
fn given_repeated_long_literals_when_hinting_then_matches_python_wording() {
    let test_cases = [
        HintTestCase {
            description: "two files in one folder share a local constants folder",
            paths: vec!["models/a/x.sql", "models/a/y.sql"],
            expected_hint: Some(
                "The identical literal also appears in models/a/y.sql; their nearest common folder is `models/a`, so declare it once in `models/a/_sqlbuild/_constants/`",
            ),
        },
        HintTestCase {
            description: "a declaration group file and subfolders inherit constants",
            paths: vec![
                "models/a/_sqlbuild/x.sql",
                "models/a/b/y.sql",
                "models/a/c/z.sql",
            ],
            expected_hint: Some(
                "The identical literal also appears in models/a/b/y.sql, models/a/c/z.sql; their nearest common folder is `models/a`, so declare it once in `models/a/_sqlbuild/constants/`",
            ),
        },
        HintTestCase {
            description: "paths sort by parts and only five are listed",
            paths: vec![
                "models/a-b/x.sql",
                "models/a/b/x.sql",
                "models/a/y.sql",
                "m/1.sql",
                "m/2.sql",
                "m/3.sql",
                "m/4.sql",
            ],
            expected_hint: Some(
                "The identical literal also appears in m/1.sql, m/2.sql, m/3.sql, m/4.sql, models/a/b/x.sql and 1 more; no folder below the project roots holds every use, so declare it once in top-level `constants/`",
            ),
        },
        HintTestCase {
            description: "a literal in one file gets no hint",
            paths: vec!["models/a/x.sql"],
            expected_hint: None,
        },
    ];

    for test_case in test_cases {
        let findings: Vec<RuleFinding> = test_case
            .paths
            .iter()
            .map(|path| RuleFinding {
                code: "SQBRSQL044".to_owned(),
                path: (*path).to_owned(),
                line: 1,
                column: 8,
                remediation: "R.".to_owned(),
                ..RuleFinding::default()
            })
            .collect();
        let Ok(hinted) = duplicate_literal_hints(&findings, |_| {
            Ok::<Vec<String>, Infallible>(vec!["SELECT '\u{e9} long literal'".to_owned()])
        });

        assert_eq!(
            hinted[0],
            test_case
                .expected_hint
                .map(|hint| format!("{hint}{SUFFIX}")),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_rules_result_when_formatting_then_matches_python_text_and_json() {
    let test_cases = [
        ResultTestCase {
            description: "text lists affected rules, the fix note and unevaluated resources",
            json_output: false,
            expected_text: "models/o.sql:3:4 [SQBRSQL001] bad \u{e9}\n  Remediation: Fix it.\n  Affected Rules: A, B\n  Fix available: `sqb format --fix` applies it after compiler verification\nFound 1 Rules findings\n2 models evaluated, 1 resources could not be evaluated",
        },
        ResultTestCase {
            description: "JSON is indented, key-sorted and ASCII-escaped",
            json_output: true,
            expected_text: "{\n  \"cache_hits\": 1,\n  \"cache_misses\": 1,\n  \"evaluated_models\": 2,\n  \"finding_count\": 1,\n  \"findings\": [\n    {\n      \"affected_rules\": [\n        \"A\",\n        \"B\"\n      ],\n      \"code\": \"SQBRSQL001\",\n      \"column\": 4,\n      \"fixable\": true,\n      \"line\": 3,\n      \"message\": \"bad \\u00e9\",\n      \"path\": \"models/o.sql\",\n      \"remediation\": \"Fix it.\"\n    }\n  ],\n  \"unevaluated_resources\": 1\n}",
        },
    ];
    let finding = RuleFinding {
        code: "SQBRSQL001".to_owned(),
        path: "models/o.sql".to_owned(),
        line: 3,
        column: 4,
        message: "bad \u{e9}".to_owned(),
        remediation: "Fix it.".to_owned(),
        unevaluated: false,
        affected_rules: vec!["A".to_owned(), "B".to_owned()],
        fixable: true,
    };
    let counts = ResultCounts {
        evaluated_models: 2,
        unevaluated_resources: 1,
        cache_hits: 1,
        cache_misses: 1,
    };

    for test_case in test_cases {
        let rendered: String = format_result(
            std::slice::from_ref(&finding),
            counts,
            test_case.json_output,
        );

        assert_eq!(
            rendered, test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
