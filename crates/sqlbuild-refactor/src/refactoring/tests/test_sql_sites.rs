use crate::refactoring::_helpers::chars::chars;
use crate::refactoring::_helpers::interpolation::interpolation_sites;
use crate::refactoring::_helpers::sql_sites::{
    ModelBody, analysis_sql, authored_offset, authored_span, embedded_ref_spans, resource_sites,
};
use crate::refactoring::models::ExpansionSpan;
use crate::refactoring::tests::helpers::{context, python, span_texts};
use crate::refactoring::tests::test_types::{
    AnalysisSqlTestCase, InterpolationSitesTestCase, ResourceSitesTestCase,
};

#[test]
fn given_sql_when_scanning_interpolation_then_sites_outside_comments_and_strings_are_found() {
    let test_cases = [
        InterpolationSitesTestCase {
            description: "a reference call outside a comment",
            dialect: "duckdb",
            sql: "SELECT * FROM __ref('orders') -- __ref('ignored')\n",
            expected_sites: &["__ref('orders')"],
        },
        InterpolationSitesTestCase {
            description: "a doubled quote stays inside its string",
            dialect: "duckdb",
            sql: "SELECT '__ref(''x'')' AS a, __source('raw', 'orders')",
            expected_sites: &["__source('raw', 'orders')"],
        },
        InterpolationSitesTestCase {
            description: "macros, variables and templates",
            dialect: "duckdb",
            sql: "SELECT @cents(amount), @@limit_rows, ${var} FROM t",
            expected_sites: &["@cents(amount)", "@@limit_rows", "${var}"],
        },
        InterpolationSitesTestCase {
            description: "a backslash before a line break backtracks to the last doubled quote",
            dialect: "duckdb",
            sql: "SELECT 'it''s \\\n' , __ref('a')",
            expected_sites: &[],
        },
        InterpolationSitesTestCase {
            description: "dollar quotes hide calls, but not after an identifier character",
            dialect: "duckdb",
            sql: "SELECT $tag$__ref('x')$tag$, __ref('y'), x$y$__ref('z')",
            expected_sites: &["__ref('y')", "__ref('z')"],
        },
        InterpolationSitesTestCase {
            description: "backticks quote where the dialect quotes identifiers with them",
            dialect: "generic",
            sql: "SELECT `__ref('x')`, __ref('y')",
            expected_sites: &["__ref('y')"],
        },
        InterpolationSitesTestCase {
            description: "backticks are plain text in postgres",
            dialect: "postgres",
            sql: "SELECT `__ref('x')`, __ref('y')",
            expected_sites: &["__ref('x')", "__ref('y')"],
        },
        InterpolationSitesTestCase {
            description: "a call left open is not a site",
            dialect: "duckdb",
            sql: "SELECT __ref('x' FROM t",
            expected_sites: &[],
        },
    ];
    for test_case in test_cases {
        let scan = context(test_case.dialect);
        let sites: Vec<String> =
            interpolation_sites(&chars(test_case.sql), scan.backtick_identifiers, python())
                .into_iter()
                .map(|site| site.text)
                .collect();
        assert_eq!(sites, test_case.expected_sites, "{}", test_case.description);
    }
}

#[test]
fn given_sql_when_finding_resource_sites_then_single_name_calls_are_returned() {
    let test_cases = [
        ResourceSitesTestCase {
            description: "spaced and double-quoted reference",
            sql: "SELECT * FROM __ref( \"orders\" ) JOIN __seed('codes')",
            expected_sites: &[
                ("ref", "orders", "__ref( \"orders\" )", "orders"),
                ("seed", "codes", "__seed('codes')", "codes"),
            ],
        },
        ResourceSitesTestCase {
            description: "a two-argument source is not a resource site",
            sql: "SELECT * FROM __source('raw', 'orders')",
            expected_sites: &[],
        },
    ];
    for test_case in test_cases {
        let sites: Vec<(String, String, String, String)> =
            resource_sites(&chars(test_case.sql), &context("duckdb"))
                .into_iter()
                .map(|site| {
                    let texts = span_texts(
                        test_case.sql,
                        &[(site.start, site.end), (site.name_start, site.name_end)],
                    );
                    (site.kind, site.name, texts[0].clone(), texts[1].clone())
                })
                .collect();
        let expected: Vec<(String, String, String, String)> = test_case
            .expected_sites
            .iter()
            .map(|(kind, name, call, name_text)| {
                (
                    (*kind).to_owned(),
                    (*name).to_owned(),
                    (*call).to_owned(),
                    (*name_text).to_owned(),
                )
            })
            .collect();
        assert_eq!(sites, expected, "{}", test_case.description);
    }
}

#[test]
fn given_sql_when_building_analysis_sql_then_sites_become_same_length_placeholders() {
    let test_cases = [
        AnalysisSqlTestCase {
            description: "resource and macro sites",
            sql: "SELECT a FROM __ref('orders') o JOIN @m(x) m",
            expected_sql: "SELECT a FROM _qr0___________ o JOIN _qx1_ m",
            expected_tables: &[("ref", "orders", &["_qr0___________"])],
        },
        AnalysisSqlTestCase {
            description: "a site shorter than its placeholder base",
            sql: "SELECT @m FROM t",
            expected_sql: "SELECT _x FROM t",
            expected_tables: &[],
        },
    ];
    for test_case in test_cases {
        let analysis = analysis_sql(&chars(test_case.sql), &context("duckdb"));
        assert_eq!(
            analysis.sql, test_case.expected_sql,
            "{}",
            test_case.description
        );
        let tables: Vec<(String, String, Vec<String>)> = analysis
            .tables
            .iter()
            .map(|((kind, name), placeholders)| {
                (
                    kind.clone(),
                    name.clone(),
                    placeholders.iter().cloned().collect(),
                )
            })
            .collect();
        let expected: Vec<(String, String, Vec<String>)> = test_case
            .expected_tables
            .iter()
            .map(|(kind, name, placeholders)| {
                (
                    (*kind).to_owned(),
                    (*name).to_owned(),
                    placeholders.iter().map(|item| (*item).to_owned()).collect(),
                )
            })
            .collect();
        assert_eq!(tables, expected, "{}", test_case.description);
    }
}

#[test]
fn given_quoted_text_when_finding_embedded_refs_then_escaped_quotes_match() {
    let text = "x __ref(\\\"orders\\\") __ref('orders_v2') y";
    assert_eq!(
        span_texts(text, &embedded_ref_spans(&chars(text), "orders")),
        vec!["orders"]
    );
}

#[test]
fn given_expansion_passes_when_mapping_offsets_then_generated_text_is_flagged() {
    let body = ModelBody {
        body_start: 10,
        compiled_sql: "SELECT a + b FROM t".to_owned(),
        passes: vec![vec![ExpansionSpan {
            source_start: 7,
            source_end: 11,
            output_start: 7,
            output_end: 12,
        }]],
    };
    assert_eq!(authored_offset(&body, 3), (13, false));
    assert_eq!(authored_offset(&body, 8), (17, true));
    assert_eq!(authored_offset(&body, 13), (22, false));
    assert_eq!(authored_span(&body, 13, 17), Some((22, 26)));
    assert_eq!(authored_span(&body, 6, 9), None);
}
