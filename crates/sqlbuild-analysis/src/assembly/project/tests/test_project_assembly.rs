use crate::assembly::project::models::InputRead;
use crate::assembly::project::tests::helpers::{deps, namespace, seed, seed_reads, source, valid};
use crate::assembly::project::tests::test_types::{
    DepsTestCase, EnvironmentTestCase, SeedTestCase, SourceTestCase, SyntaxTestCase, keys,
};

#[test]
fn given_references_when_deriving_deps_then_matches_python_keys() {
    let test_cases = [
        DepsTestCase {
            description: "each kind maps to its resource and repeats keep the first key",
            references: &[
                ("ref", "orders", None),
                ("source", "raw_orders", None),
                ("ref", "orders", None),
                ("dbt_ref", "customers", Some("upstream")),
                ("dbt_ref", "products", None),
                ("udf", "tax", None),
                ("table_fn", "series", None),
                ("seed", "countries", None),
            ],
            attached: Some(("model", "orders")),
            expected_deps: Some(&[
                ("model", "orders"),
                ("source", "raw_orders"),
                ("dbt_ref", "upstream.customers"),
                ("dbt_ref", "products"),
                ("udf", "tax"),
                ("table_fn", "series"),
                ("seed", "countries"),
            ]),
        },
        DepsTestCase {
            description: "an attached target joins the references",
            references: &[("ref", "orders", None)],
            attached: Some(("seed", "countries")),
            expected_deps: Some(&[("model", "orders"), ("seed", "countries")]),
        },
        DepsTestCase {
            description: "an attached kind Python rejects",
            references: &[],
            attached: Some(("function", "tax")),
            expected_deps: None,
        },
    ];
    for test_case in test_cases {
        let derived = deps(test_case.references, test_case.attached);

        assert_eq!(
            derived,
            test_case.expected_deps.map(keys),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_seeds_when_resolving_targets_then_matches_python_or_defers() {
    let test_cases = [
        SeedTestCase {
            description: "defaults and the seed's templates read variables and updated context",
            seed: (
                "countries",
                Some("${n}"),
                Some("seeds_${env_name}_${CTX:model.database}"),
            ),
            defaults: (Some("db_${env_name}"), None, None, Some("raw")),
            target: None,
            expected_namespace: Some((
                Some("3"),
                Some("seeds_prod_3"),
                Some("3"),
                Some("seeds_prod_3"),
            )),
        },
        SeedTestCase {
            description: "a target overrides the schema and preserves the database",
            seed: ("countries", None, None),
            defaults: (Some("analytics"), Some("main"), None, None),
            target: Some((Some("preserve"), Some("dev_${env_name}"), None)),
            expected_namespace: Some((
                Some("analytics"),
                Some("dev_prod"),
                Some("analytics"),
                Some("main"),
            )),
        },
        SeedTestCase {
            description: "the qualified destination context",
            seed: ("countries", None, Some("${CTX:destination.qualified}_x")),
            defaults: (Some("analytics"), Some("main"), None, None),
            target: None,
            expected_namespace: Some((
                Some("analytics"),
                Some("analytics.main.countries_x"),
                Some("analytics"),
                Some("analytics.main.countries_x"),
            )),
        },
        SeedTestCase {
            description: "a whole-template boolean renders as Python's str",
            seed: ("countries", None, Some("${flag}")),
            defaults: (None, None, None, None),
            target: None,
            expected_namespace: Some((None, Some("True"), None, Some("True"))),
        },
        SeedTestCase {
            description: "a preserved schema the seed does not own raises in Python",
            seed: ("countries", None, None),
            defaults: (None, None, None, None),
            target: Some((None, Some("preserve"), None)),
            expected_namespace: None,
        },
        SeedTestCase {
            description: "environment reads stay with Python",
            seed: ("countries", None, Some("${ENV:SEED_SCHEMA}")),
            defaults: (None, None, None, None),
            target: None,
            expected_namespace: None,
        },
        SeedTestCase {
            description: "a variable only Python renders",
            seed: ("countries", None, Some("${tags}")),
            defaults: (None, None, None, None),
            target: None,
            expected_namespace: None,
        },
    ];
    for test_case in test_cases {
        let resolved = seed(test_case.seed, test_case.defaults, test_case.target);

        assert_eq!(
            resolved,
            test_case.expected_namespace.map(namespace),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_sources_when_resolving_managed_targets_then_matches_python() {
    let test_cases = [
        SourceTestCase {
            description: "an empty loader schema falls back to the target schema",
            source: (true, None, None),
            target: Some((Some("wh_${env_name}"), Some("main"), Some(""))),
            expected_namespace: Some(Some((Some("wh_prod"), Some("main")))),
        },
        SourceTestCase {
            description: "an authored schema wins over the loader schema",
            source: (true, None, Some("landing")),
            target: Some((Some("wh"), None, Some("loaders"))),
            expected_namespace: Some(Some((Some("wh"), Some("landing")))),
        },
        SourceTestCase {
            description: "an unmanaged source stays as authored",
            source: (false, None, None),
            target: Some((Some("wh"), Some("main"), None)),
            expected_namespace: Some(None),
        },
    ];
    for test_case in test_cases {
        let resolved = source(test_case.source, test_case.target);

        assert_eq!(
            resolved,
            test_case.expected_namespace.map(|namespace| {
                namespace.map(|(database, schema)| {
                    (database.map(str::to_owned), schema.map(str::to_owned))
                })
            }),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_model_sql_when_validating_syntax_then_matches_python_or_defers() {
    let test_cases = [
        SyntaxTestCase {
            dialect: "duckdb",
            description: "markers and placeholder defaults parse",
            sql: "SELECT @@@x AS a FROM __ref(\"orders\")",
            placeholders: &[("x", "1")],
            expected_valid: Some(true),
        },
        SyntaxTestCase {
            dialect: "duckdb",
            description: "a syntax error",
            sql: "SELECT FROM WHERE (",
            placeholders: &[],
            expected_valid: Some(false),
        },
        SyntaxTestCase {
            dialect: "duckdb",
            description: "a placeholder run retried one character later, as re.sub does",
            sql: "SELECT @@@@@abc AS a",
            placeholders: &[("abc", "version")],
            expected_valid: Some(true),
        },
        SyntaxTestCase {
            dialect: "duckdb",
            description: "a placeholder followed by text Python's \\w may extend",
            sql: "SELECT @@@x\u{e9} AS a",
            placeholders: &[("x", "1")],
            expected_valid: None,
        },
        SyntaxTestCase {
            dialect: "trino",
            description: "a dialect this parser build does not carry",
            sql: "SELECT 1 AS a FROM t QUALIFY a = 1",
            placeholders: &[],
            expected_valid: None,
        },
    ];
    for test_case in test_cases {
        let checked = valid(test_case.sql, test_case.placeholders, test_case.dialect);

        assert_eq!(
            checked, test_case.expected_valid,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_environment_templates_when_resolving_seeds_then_matches_python_values_and_reads() {
    let test_cases = [
        EnvironmentTestCase {
            description: "a coalesced unset variable, a set variable and a context key",
            seed: (
                "countries",
                None,
                Some(
                    "${coalesce(ENV:SQB_UNSET_SCHEMA, 'main')}_${ENV:SQB_SET_SCHEMA}_${CTX:model.name}",
                ),
            ),
            environment: &[
                ("SQB_UNSET_SCHEMA", None),
                ("SQB_SET_SCHEMA", Some("landing")),
            ],
            expected_schema: Some("main_landing_countries"),
            expected_reads: vec![
                InputRead::Environment("SQB_UNSET_SCHEMA".to_owned()),
                InputRead::Environment("SQB_SET_SCHEMA".to_owned()),
                InputRead::Context("model.name".to_owned()),
            ],
        },
        EnvironmentTestCase {
            description: "an unset variable Python raises for",
            seed: ("countries", None, Some("${ENV:SQB_UNSET_SCHEMA}")),
            environment: &[("SQB_UNSET_SCHEMA", None)],
            expected_schema: None,
            expected_reads: vec![InputRead::Environment("SQB_UNSET_SCHEMA".to_owned())],
        },
        EnvironmentTestCase {
            description: "a name Python did not resolve stays with Python",
            seed: (
                "countries",
                None,
                Some("${coalesce(ENV:app_schema, 'main')}"),
            ),
            environment: &[("APP_SCHEMA", Some("landing"))],
            expected_schema: None,
            expected_reads: vec![InputRead::Environment("app_schema".to_owned())],
        },
    ];
    for test_case in test_cases {
        let environment: Vec<(String, Option<String>)> = test_case
            .environment
            .iter()
            .map(|(name, value)| ((*name).to_owned(), value.map(str::to_owned)))
            .collect();

        let (resolved, reads) = seed_reads(test_case.seed, &environment);

        assert_eq!(
            resolved.and_then(|namespace| namespace.schema),
            test_case.expected_schema.map(str::to_owned),
            "{}",
            test_case.description
        );
        assert_eq!(reads, test_case.expected_reads, "{}", test_case.description);
    }
}
