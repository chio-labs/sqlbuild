use crate::refactoring::_helpers::scanning::chars::chars;
use crate::refactoring::_helpers::scanning::interpolation::interpolation_sites;
use crate::refactoring::_helpers::scanning::sql_sites::{
    authored_offset, authored_span, embedded_ref_spans,
};
use crate::refactoring::tests::helpers::{
    analysis_lines, context, expansion_body, python, resource_site_lines, span_texts,
};
use crate::refactoring::tests::test_types::{
    AnalysisSqlTestCase, AuthoredOffsetTestCase, AuthoredSpanTestCase, EmbeddedRefsTestCase,
    InterpolationSitesTestCase, ResourceSitesTestCase,
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
                "ref orders __ref( \"orders\" ) orders",
                "seed codes __seed('codes') codes",
            ],
        },
        ResourceSitesTestCase {
            description: "a two-argument source is not a resource site",
            sql: "SELECT * FROM __source('raw', 'orders')",
            expected_sites: &[],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            resource_site_lines(test_case.sql),
            test_case.expected_sites,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_sql_when_building_analysis_sql_then_sites_become_same_length_placeholders() {
    let test_cases = [
        AnalysisSqlTestCase {
            description: "resource and macro sites",
            sql: "SELECT a FROM __ref('orders') o JOIN @m(x) m",
            expected_sql: "SELECT a FROM _qr0___________ o JOIN _qx1_ m",
            expected_tables: &["ref orders _qr0___________"],
        },
        AnalysisSqlTestCase {
            description: "a site shorter than its placeholder base",
            sql: "SELECT @m FROM t",
            expected_sql: "SELECT _x FROM t",
            expected_tables: &[],
        },
    ];
    for test_case in test_cases {
        let (sql, tables): (String, Vec<String>) = analysis_lines(test_case.sql);
        assert_eq!(sql, test_case.expected_sql, "{}", test_case.description);
        assert_eq!(
            tables, test_case.expected_tables,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_quoted_text_when_finding_embedded_refs_then_escaped_quotes_match() {
    let test_cases = [EmbeddedRefsTestCase {
        description: "an escaped double-quoted reference matches, a longer name does not",
        text: "x __ref(\\\"orders\\\") __ref('orders_v2') y",
        name: "orders",
        expected_names: &["orders"],
    }];
    for test_case in test_cases {
        assert_eq!(
            span_texts(
                test_case.text,
                &embedded_ref_spans(&chars(test_case.text), test_case.name)
            ),
            test_case.expected_names,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_expansion_passes_when_mapping_offsets_then_generated_text_is_flagged() {
    let test_cases = [
        AuthoredOffsetTestCase {
            description: "an offset before the expansion",
            offset: 3,
            expected_offset: (13, false),
        },
        AuthoredOffsetTestCase {
            description: "an offset inside generated text",
            offset: 8,
            expected_offset: (17, true),
        },
        AuthoredOffsetTestCase {
            description: "an offset after the expansion shifts back",
            offset: 13,
            expected_offset: (22, false),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            authored_offset(&expansion_body(), test_case.offset),
            test_case.expected_offset,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_expansion_passes_when_mapping_spans_then_generated_spans_have_no_source() {
    let test_cases = [
        AuthoredSpanTestCase {
            description: "a span after the expansion",
            span: (13, 17),
            expected_span: Some((22, 26)),
        },
        AuthoredSpanTestCase {
            description: "a span crossing generated text",
            span: (6, 9),
            expected_span: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            authored_span(&expansion_body(), test_case.span.0, test_case.span.1),
            test_case.expected_span,
            "{}",
            test_case.description
        );
    }
}
