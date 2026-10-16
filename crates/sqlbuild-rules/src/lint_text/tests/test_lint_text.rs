use crate::lint_text::_helpers::sites::site_pattern;
use crate::lint_text::constants::{
    FORBIDDEN_FIX_REASON, FORBIDDEN_MESSAGE, FORBIDDEN_REMEDIATION, INVALID_MESSAGE,
    INVALID_REMEDIATION, REASON_REQUIRED_FIX_REASON, SITE_START_BYTES, UNUSED_REMEDIATION,
};
use crate::lint_text::errors::LintTextError;
use crate::lint_text::main::apply_suppressions::apply_suppressions;
use crate::lint_text::main::format_sql_bodies::format_sql_bodies;
use crate::lint_text::main::interpolation_text_at::interpolation_text_at;
use crate::lint_text::main::lint_sql_bodies::lint_sql_bodies;
use crate::lint_text::main::neutralize_audit_parameters::neutralize_audit_parameters;
use crate::lint_text::main::neutralize_context_interpolation::neutralize_context_interpolation;
use crate::lint_text::main::neutralize_interpolation::neutralize_interpolation;
use crate::lint_text::main::restore_interpolation::restore_interpolation;
use crate::lint_text::models::{
    ExpansionSpan, FormatFile, LintSqlBody, LintSqlOptions, RetainedViolation,
    SuppressibleViolation, SuppressionFinding,
};
use crate::lint_text::tests::test_types::{
    Finding, FormatBodiesTestCase, LintBodiesTestCase, NeutralizeTestCase, ParameterTestCase,
    RestoreTestCase, SitePatternTestCase, SuppressionTestCase, TokenAtTestCase,
};

const SUPPRESSED_FILE: &str = "-- sqb: ignore SQBRSQL005 because kept\n\n-- note\nselect 1\n-- sqb: ignore X because y\n-- sqb: ignore nope\nselect 2\n";

#[test]
fn given_site_patterns_when_text_opens_with_another_byte_then_no_site_starts_there()
-> Result<(), LintTextError> {
    let test_cases = [
        SitePatternTestCase {
            description: "lint sites",
            formatting: false,
            expected_other_start_bytes: Vec::new(),
        },
        SitePatternTestCase {
            description: "format sites",
            formatting: true,
            expected_other_start_bytes: Vec::new(),
        },
    ];
    for test_case in test_cases {
        let pattern = site_pattern(test_case.formatting)?;
        let other_start_bytes: Vec<u8> = (0..=127u8)
            .filter(|byte| !SITE_START_BYTES.contains(byte))
            .filter(|byte| {
                ["@@x", "@x", "${x}", "__ref(", "__REF (", "__udf("]
                    .iter()
                    .any(|site| pattern.is_match(&format!("{}{site}", char::from(*byte))))
            })
            .collect();
        assert_eq!(
            other_start_bytes, test_case.expected_other_start_bytes,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_authored_sql_when_neutralizing_then_sites_use_character_offsets()
-> Result<(), LintTextError> {
    let test_cases = [
        NeutralizeTestCase {
            description: "reference, macro call and template",
            body: "select @m(a, ')') from __ref('o') where x > ${v}",
            formatting: false,
            expected_text: "select __sqb_lint_0__ from __sqb_lint_1__ where x > __sqb_lint_2__",
            expected_sites: vec![
                ("@m(a, ')')", 7, 17),
                ("__ref('o')", 23, 33),
                ("${v}", 44, 48),
            ],
        },
        NeutralizeTestCase {
            description: "non-ASCII text before a site shifts character offsets only",
            body: "select 'é' as n, @@CTX:run.id",
            formatting: false,
            expected_text: "select 'é' as n, __sqb_lint_0__",
            expected_sites: vec![("@@CTX:run.id", 17, 29)],
        },
        NeutralizeTestCase {
            description: "comments and strings hide sites",
            body: "-- @x\nselect '@y', \"__ref(z)\" /* ${w} */",
            formatting: false,
            expected_text: "-- @x\nselect '@y', \"__ref(z)\" /* ${w} */",
            expected_sites: vec![],
        },
        NeutralizeTestCase {
            description: "lint leaves spaced and upper-case intrinsics alone",
            body: "select __REF('a'), __ref ('b'), __cursor_start()",
            formatting: false,
            expected_text: "select __REF('a'), __ref ('b'), __cursor_start()",
            expected_sites: vec![],
        },
        NeutralizeTestCase {
            description: "formatting protects every intrinsic spelling",
            body: "select __REF('a'), __ref ('b'), __cursor_start()",
            formatting: true,
            expected_text: "select __sqb_lint_0__, __sqb_lint_1__, __sqb_lint_2__",
            expected_sites: vec![
                ("__REF('a')", 7, 17),
                ("__ref ('b')", 19, 30),
                ("__cursor_start()", 32, 48),
            ],
        },
    ];

    for test_case in test_cases {
        let neutralized = neutralize_interpolation(test_case.body, "duckdb", test_case.formatting)?;
        let sites: Vec<(&str, usize, usize)> = neutralized
            .sites
            .iter()
            .map(|site| {
                (
                    site.original_text.as_str(),
                    site.original_start,
                    site.original_end,
                )
            })
            .collect();

        assert_eq!(
            neutralized.text, test_case.expected_text,
            "{}",
            test_case.description
        );
        assert_eq!(sites, test_case.expected_sites, "{}", test_case.description);
    }
    Ok(())
}

#[test]
fn given_generated_parameters_when_neutralizing_then_only_bare_parameters_are_replaced() {
    let test_cases = [
        ParameterTestCase {
            description: "quoted and raw audit parameters, but not calls or doubled at-signs",
            body: "select * from @this where @column < 0 and @'kind' = @f(1) and @@x",
            neutralize: neutralize_audit_parameters,
            expected_text: "select * from __sqlbuild_audit_parameter_0__ where __sqlbuild_audit_parameter_1__ < 0 and '__sqlbuild_audit_parameter_2__' = @f(1) and @@x",
        },
        ParameterTestCase {
            description: "context interpolation in hooks",
            body: "analyze @@CTX:relation; select @@CTX:a.b",
            neutralize: neutralize_context_interpolation,
            expected_text: "analyze __sqlbuild_context_parameter_0__; select __sqlbuild_context_parameter_1__",
        },
    ];

    for test_case in test_cases {
        let neutralized = (test_case.neutralize)(test_case.body);

        assert_eq!(
            neutralized.text, test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_formatted_sql_when_restoring_then_each_sentinel_must_appear_once()
-> Result<(), LintTextError> {
    let test_cases = [
        RestoreTestCase {
            description: "sentinels in any case restore to the original text",
            body: "select @m, ${v}",
            fixed: "SELECT __SQB_LINT_0__, __sqb_lint_1__",
            expected_restored: Ok("SELECT @m, ${v}".to_string()),
        },
        RestoreTestCase {
            description: "a duplicated sentinel is ambiguous",
            body: "select @m",
            fixed: "select __sqb_lint_0__, __SQB_LINT_0__",
            expected_restored: Err("formatted SQL contains 2 occurrences of sentinel '__sqb_lint_0__' standing in for '@m'; expected exactly 1".to_string()),
        },
    ];

    for test_case in test_cases {
        let neutralized = neutralize_interpolation(test_case.body, "duckdb", true)?;

        let restored = restore_interpolation(test_case.fixed, &neutralized.sites)
            .map_err(|error| error.to_string());

        assert_eq!(
            restored, test_case.expected_restored,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_character_offset_when_reading_token_then_only_site_starts_have_tokens() {
    let test_cases = [
        TokenAtTestCase {
            description: "a macro call after a multibyte character",
            body: "é @m(x) y",
            start: 2,
            expected_token: Some("@m(x)"),
        },
        TokenAtTestCase {
            description: "a plain character",
            body: "é @m(x) y",
            start: 0,
            expected_token: None,
        },
        TokenAtTestCase {
            description: "a spaced intrinsic call",
            body: "x __source ('a', 'b')",
            start: 2,
            expected_token: Some("__source ('a', 'b')"),
        },
    ];

    for test_case in test_cases {
        let token = interpolation_text_at(test_case.body, test_case.start, "duckdb");

        assert_eq!(
            token.as_deref(),
            test_case.expected_token,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_suppression_directives_when_applying_then_matching_findings_are_removed()
-> Result<(), LintTextError> {
    let test_cases = [
        SuppressionTestCase {
            description: "a used, an unused and an invalid directive",
            contents: SUPPRESSED_FILE,
            violations: vec![(4, "SQBRSQL005"), (7, "SQBRSQL034")],
            allow: true,
            expected_retained: vec![
                RetainedViolation::Existing(1),
                RetainedViolation::Added(SuppressionFinding {
                    file: 0,
                    line: 6,
                    message: INVALID_MESSAGE.to_string(),
                    remediation: INVALID_REMEDIATION,
                    fault: false,
                    fix: None,
                    fix_unavailable_reason: Some(REASON_REQUIRED_FIX_REASON),
                }),
                RetainedViolation::Added(SuppressionFinding {
                    file: 0,
                    line: 5,
                    message: "Unused suppression for X".to_string(),
                    remediation: UNUSED_REMEDIATION,
                    fault: false,
                    fix: Some((57, 84)),
                    fix_unavailable_reason: None,
                }),
            ],
        },
        SuppressionTestCase {
            description: "suppressions forbidden by the project",
            contents: "select 1\n-- sqb: ignore nope\n",
            violations: vec![(1, "SQBRSQL005")],
            allow: false,
            expected_retained: vec![
                RetainedViolation::Existing(0),
                RetainedViolation::Added(SuppressionFinding {
                    file: 0,
                    line: 2,
                    message: FORBIDDEN_MESSAGE.to_string(),
                    remediation: FORBIDDEN_REMEDIATION,
                    fault: true,
                    fix: None,
                    fix_unavailable_reason: Some(FORBIDDEN_FIX_REASON),
                }),
            ],
        },
    ];

    for test_case in test_cases {
        let violations: Vec<SuppressibleViolation> = test_case
            .violations
            .iter()
            .map(|(line, code)| SuppressibleViolation {
                file: 0,
                line: *line,
                code: (*code).to_string(),
                native: true,
            })
            .collect();

        let retained = apply_suppressions(&[test_case.contents], &violations, test_case.allow)?;

        assert_eq!(
            retained, test_case.expected_retained,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_sql_files_when_formatting_bodies_then_sites_and_fixture_ceremony_survive()
-> Result<(), LintTextError> {
    let test_cases = [
        FormatBodiesTestCase {
            description: "a model body with a reference and a macro",
            relative_parts: Some(vec!["models".to_string(), "orders.sql".to_string()]),
            contents: "MODEL (description \"d\");\nselect a, @m('x') as m from __ref('o')\n",
            expected_formatted: vec![(
                0,
                "MODEL (description \"d\");\nSELECT\n  a,\n  @m('x') AS m\nFROM __ref('o')\n"
                    .to_string(),
            )],
            expected_fault_lines: vec![],
        },
        FormatBodiesTestCase {
            description: "a fixture body keeps its omitted ceremonial select",
            relative_parts: Some(vec![
                "tests".to_string(),
                "unit".to_string(),
                "t.sql".to_string(),
            ]),
            contents: "TEST();\nwith __ref__o as (select 1 as a)\n",
            expected_formatted: vec![(
                0,
                "TEST();\nWITH __ref__o AS (\n  SELECT 1 AS a\n)\n".to_string(),
            )],
            expected_fault_lines: vec![],
        },
        FormatBodiesTestCase {
            description: "an unparseable body is a fault on its first line",
            relative_parts: None,
            contents: "MODEL ();\n\nSELECT FROM WHERE (((\n",
            expected_formatted: vec![],
            expected_fault_lines: vec![3],
        },
    ];

    for test_case in test_cases {
        let files = [FormatFile {
            relative_parts: test_case.relative_parts.clone(),
            contents: test_case.contents.to_string(),
        }];

        let result = format_sql_bodies(&files, "duckdb", 100)?;
        let fault_lines: Vec<usize> = result.faults.iter().map(|fault| fault.line).collect();

        assert_eq!(
            result.formatted, test_case.expected_formatted,
            "{}",
            test_case.description
        );
        assert_eq!(
            fault_lines, test_case.expected_fault_lines,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_expanded_bodies_when_linting_then_findings_map_to_authored_lines() {
    let test_cases = [
        LintBodiesTestCase {
            description: "an unused CTE after a header maps to its authored line",
            contents: "MODEL ();\nwith dead as (select 1 as y), live as (select 1 as a)\nselect a from live\n",
            body: LintSqlBody {
                body_start: 10,
                lint_text:
                    "with dead as (select 1 as y), live as (select 1 as a)\nselect a from live"
                        .to_string(),
                ..LintSqlBody::default()
            },
            expected_findings: vec![("SQBRSQL005", 2, 6, Some((2, 10)))],
        },
        LintBodiesTestCase {
            description: "a parse failure is a fault at the mapped parser position",
            contents: "MODEL ();\n\nselect a from from t\n",
            body: LintSqlBody {
                body_start: 11,
                lint_text: "select a from from t".to_string(),
                ..LintSqlBody::default()
            },
            expected_findings: vec![("L003", 3, 19, None)],
        },
        LintBodiesTestCase {
            description: "a finding inside generated SQL points at the interpolation token",
            contents: "select a from t where @isnull()\n",
            body: LintSqlBody {
                lint_text: "select a from t where a = null".to_string(),
                passes: vec![vec![ExpansionSpan {
                    source_start: 22,
                    source_end: 31,
                    output_start: 22,
                    output_end: 30,
                }]],
                ..LintSqlBody::default()
            },
            expected_findings: vec![("SQBRSQL001", 1, 23, Some((1, 32)))],
        },
    ];

    for test_case in test_cases {
        let options = LintSqlOptions {
            dialect: "duckdb".to_string(),
            enabled_rules: Some(vec!["SQBRSQL001".to_string(), "SQBRSQL005".to_string()]),
            max_literal_length: 100,
            max_ranking_order_by: 5,
            ..LintSqlOptions::default()
        };

        let result = lint_sql_bodies(&[test_case.body], &[test_case.contents], &options);
        let findings: Vec<Finding<'_>> = result
            .iter()
            .map(|finding| {
                (
                    finding.code.as_str(),
                    finding.line,
                    finding.column,
                    finding.end,
                )
            })
            .collect();

        assert_eq!(
            findings, test_case.expected_findings,
            "{}",
            test_case.description
        );
    }
}
