use std::collections::HashMap;

use sqlbuild_cache::digest::types::ContentDigest;
use sqlbuild_cache::store::models::NativeStore;

use crate::assembly::analysis_session::models::{
    AnalysisCacheStats, DynamicFamily, ModelReference, SessionRequest,
};
use crate::assembly::analysis_session::tests::helpers::{
    CachedRun, cached_run, damaged, model_keys, model_requests, orders_request, pairs,
    session_lines, shapes, started, uncached_catalog,
};
use crate::assembly::analysis_session::tests::test_types::{
    CacheEditTestCase, CacheKeyTestCase, CacheReuseTestCase, ModelSpec, RelationDigestTestCase,
};

const STG_ORDERS: ModelSpec = (
    "stg_orders",
    "SELECT order_id, amount * 2 AS doubled FROM __source(\"raw_orders\")",
    &["raw_orders"],
    &[],
);
const ORDERS_MART: ModelSpec = (
    "orders_mart",
    "SELECT doubled, order_id + 1 AS next_id FROM __ref(\"stg_orders\")",
    &[],
    &["stg_orders"],
);
const ORDERS_STAR: ModelSpec = (
    "orders_star",
    "SELECT * FROM __ref(\"stg_orders\")",
    &[],
    &["stg_orders"],
);
const ORDERS_BAD: ModelSpec = (
    "orders_bad",
    "SELECT missing_column FROM __source(\"raw_orders\")",
    &["raw_orders"],
    &[],
);
const EVENTS: ModelSpec = (
    "events",
    "SELECT event_id FROM __source(\"raw_events\")",
    &["raw_events"],
    &[],
);
const EVENTS_MART: ModelSpec = (
    "events_mart",
    "SELECT event_id, 1 AS one FROM __ref(\"events\")",
    &[],
    &["events"],
);
const ORDERS: &[ModelSpec] = &[STG_ORDERS, ORDERS_MART, ORDERS_STAR, ORDERS_BAD];

fn stats(run: &CachedRun) -> (usize, usize, usize) {
    let AnalysisCacheStats {
        hits,
        misses,
        stored,
    } = run.stats;
    (hits, misses, stored)
}

#[test]
fn given_a_filled_cache_when_rerunning_then_hits_match_the_uncached_session() {
    let test_cases = [
        CacheReuseTestCase {
            description: "typed chains, a star, a binding error and a native enrichment",
            models: ORDERS,
            expected_stats: [(0, 4, 4), (4, 0, 0)],
        },
        CacheReuseTestCase {
            description: "an open source's consumer takes the legacy analysis natively",
            models: &[EVENTS, EVENTS_MART],
            expected_stats: [(0, 2, 2), (2, 0, 0)],
        },
        CacheReuseTestCase {
            description: "a model Python analyses is never stored",
            models: &[
                (
                    "events",
                    "SELECT event_id AS \"gr\u{f6}\u{df}e\" FROM __source(\"raw_events\")",
                    &["raw_events"],
                    &[],
                ),
                (
                    "events_mart",
                    "SELECT \"gr\u{f6}\u{df}e\" FROM __ref(\"events\") \
                     WHERE \"gr\u{f6}\u{df}e\" IS NOT NULL",
                    &[],
                    &["events"],
                ),
            ],
            expected_stats: [(0, 2, 1), (1, 1, 0)],
        },
    ];
    for test_case in test_cases {
        let uncached = session_lines(test_case.models);
        let cold: CachedRun = cached_run(
            orders_request(model_requests(test_case.models)),
            NativeStore::default(),
        );
        let cold_stats: (usize, usize, usize) = stats(&cold);
        let cold_lines = cold.lines;
        let cold_catalog = cold.catalog;
        let warm: CachedRun =
            cached_run(orders_request(model_requests(test_case.models)), cold.store);

        assert_eq!(
            (&cold_lines, &warm.lines),
            (&uncached, &uncached),
            "{}",
            test_case.description
        );
        let uncached_changes = uncached_catalog(orders_request(model_requests(test_case.models)));
        assert_eq!(
            (&cold_catalog, &warm.catalog),
            (&uncached_changes, &uncached_changes),
            "{}",
            test_case.description
        );
        assert_eq!(
            [cold_stats, stats(&warm)],
            test_case.expected_stats,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_an_edit_when_rerunning_then_only_changed_analyses_miss_and_match_uncached() {
    let test_cases = [
        CacheEditTestCase {
            description: "a comment changes one query but no shape",
            models: ORDERS,
            edited: &[
                (
                    "stg_orders",
                    "SELECT order_id, amount * 2 AS doubled FROM __source(\"raw_orders\") -- edit",
                    &["raw_orders"],
                    &[],
                ),
                ORDERS_MART,
                ORDERS_STAR,
                ORDERS_BAD,
            ],
            expected_hits: &[false, true, true, true],
        },
        CacheEditTestCase {
            description: "a new upstream column reaches every consumer's key",
            models: ORDERS,
            edited: &[
                (
                    "stg_orders",
                    "SELECT order_id, amount * 2 AS doubled, amount FROM __source(\"raw_orders\")",
                    &["raw_orders"],
                    &[],
                ),
                ORDERS_MART,
                ORDERS_STAR,
                ORDERS_BAD,
            ],
            expected_hits: &[false, false, false, true],
        },
        CacheEditTestCase {
            description: "a legacy analysis misses when any relation it could read changes",
            models: &[EVENTS, STG_ORDERS, EVENTS_MART],
            edited: &[
                EVENTS,
                (
                    "stg_orders",
                    "SELECT order_id, amount FROM __source(\"raw_orders\")",
                    &["raw_orders"],
                    &[],
                ),
                EVENTS_MART,
            ],
            expected_hits: &[true, false, false],
        },
    ];
    for test_case in test_cases {
        let cold: CachedRun = cached_run(
            orders_request(model_requests(test_case.models)),
            NativeStore::default(),
        );
        let edited: CachedRun =
            cached_run(orders_request(model_requests(test_case.edited)), cold.store);

        assert_eq!(
            edited.lines,
            session_lines(test_case.edited),
            "{}",
            test_case.description
        );
        assert_eq!(
            edited.catalog,
            uncached_catalog(orders_request(model_requests(test_case.edited))),
            "{}",
            test_case.description
        );
        assert_eq!(
            edited.hits, test_case.expected_hits,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_damaged_entries_when_rerunning_then_every_model_is_analysed_again() {
    let cold: CachedRun = cached_run(
        orders_request(model_requests(ORDERS)),
        NativeStore::default(),
    );
    let keys = cold.keys.clone();
    let warm: CachedRun = cached_run(
        orders_request(model_requests(ORDERS)),
        damaged(cold.store, &keys),
    );

    assert_eq!(warm.lines, session_lines(ORDERS));
    assert_eq!(stats(&warm), (0, 4, 4));
}

fn mart(
    request: &mut SessionRequest,
) -> &mut crate::assembly::analysis_session::models::ModelRequest {
    &mut request.models[1]
}

#[test]
fn given_any_analysis_input_changed_when_keying_then_the_key_changes() {
    let test_cases = [
        CacheKeyTestCase {
            description: "model name",
            change: |request| mart(request).name = "orders_mart_v2".to_owned(),
        },
        CacheKeyTestCase {
            description: "query",
            change: |request| mart(request).query_sql.push(' '),
        },
        CacheKeyTestCase {
            description: "placeholders",
            change: |request| mart(request).placeholders = pairs(&[("region", "east")]),
        },
        CacheKeyTestCase {
            description: "reference analysis names",
            change: |request| {
                mart(request).references.push(ModelReference {
                    analysis_name: "raw_orders".to_owned(),
                    model_ref: false,
                })
            },
        },
        CacheKeyTestCase {
            description: "reference kinds",
            change: |request| mart(request).references[0].model_ref = false,
        },
        CacheKeyTestCase {
            description: "lineage references",
            change: |request| mart(request).lineage_references[0].1 = "seed".to_owned(),
        },
        CacheKeyTestCase {
            description: "required relation names",
            change: |request| mart(request).required_names.push("raw_orders".to_owned()),
        },
        CacheKeyTestCase {
            description: "CTE fact recovery",
            change: |request| mart(request).recover_cte_facts = true,
        },
        CacheKeyTestCase {
            description: "set operation",
            change: |request| mart(request).has_set_operation = true,
        },
        CacheKeyTestCase {
            description: "snapshot columns",
            change: |request| {
                mart(request).snapshot_columns =
                    Some(("valid_from".to_owned(), "valid_to".to_owned()))
            },
        },
        CacheKeyTestCase {
            description: "pivot SQL",
            change: |request| mart(request).pivot_sql.push(' '),
        },
        CacheKeyTestCase {
            description: "dynamic families",
            change: |request| mart(request).dynamic_families.push(family()),
        },
        CacheKeyTestCase {
            description: "dialect",
            change: |request| request.dialect = "postgres".to_owned(),
        },
        CacheKeyTestCase {
            description: "shape case sensitivity",
            change: |request| request.case_sensitive_shapes = true,
        },
        CacheKeyTestCase {
            description: "function return types",
            change: |request| request.function_return_types = pairs(&[("score", "DOUBLE")]),
        },
        CacheKeyTestCase {
            description: "nullability rules",
            change: |request| request.nullability_rules = None,
        },
        CacheKeyTestCase {
            description: "rich type inference",
            change: |request| request.rich_type_inference = false,
        },
        CacheKeyTestCase {
            description: "relation types",
            change: |request| {
                request.column_types = shapes(&[("raw_orders", &[("order_id", "BIGINT")])])
            },
        },
        CacheKeyTestCase {
            description: "relation nullability",
            change: |request| {
                request.column_nullability = shapes(&[(
                    "raw_orders",
                    &[("order_id", "unknown"), ("amount", "unknown")],
                )])
            },
        },
        CacheKeyTestCase {
            description: "complete binding schemas",
            change: |request| {
                request
                    .complete_schemas
                    .push(("raw_items".to_owned(), pairs(&[("id", "INTEGER")])))
            },
        },
        CacheKeyTestCase {
            description: "catalog schemas",
            change: |request| {
                request
                    .catalog_schemas
                    .push(("raw_items".to_owned(), pairs(&[("id", "INTEGER")])))
            },
        },
        CacheKeyTestCase {
            description: "dynamic families by table",
            change: |request| {
                request
                    .dynamic_families_by_table
                    .push(("raw_orders".to_owned(), vec![family()]))
            },
        },
    ];
    let base = model_keys(orders_request(model_requests(ORDERS)))[1];
    for test_case in test_cases {
        let mut request: SessionRequest = orders_request(model_requests(ORDERS));
        (test_case.change)(&mut request);

        assert_ne!(model_keys(request)[1], base, "{}", test_case.description);
    }
}

#[test]
fn given_any_relation_fact_changed_when_digesting_then_the_digest_changes() {
    let test_cases = [
        RelationDigestTestCase {
            description: "available types",
            change: |session| {
                session
                    .available_types
                    .set_default("raw_items", pairs(&[("id", "INTEGER")]))
            },
        },
        RelationDigestTestCase {
            description: "available nullability",
            change: |session| {
                session
                    .available_nullability
                    .set_default("raw_items", pairs(&[("id", "non_null")]))
            },
        },
        RelationDigestTestCase {
            description: "closed shape",
            change: |session| {
                session
                    .complete_shapes
                    .set_default("raw_items", pairs(&[("id", "INTEGER")]))
            },
        },
        RelationDigestTestCase {
            description: "catalog schema",
            change: |session| {
                let _ = session
                    .catalog
                    .prepare(&[("", &shapes(&[("raw_items", &[("id", "INTEGER")])]))]);
            },
        },
    ];
    for test_case in test_cases {
        let mut session = started(orders_request(model_requests(ORDERS)));
        let before = session.relation_digest("raw_items");
        (test_case.change)(&mut session);

        assert_ne!(
            session.relation_digest("raw_items"),
            before,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_read_relation_fact_changed_when_keying_then_the_reading_model_key_changes() {
    let mut session = started(orders_request(model_requests(ORDERS)));
    let key = |session: &crate::assembly::analysis_session::models::AnalysisSession| {
        let names: Vec<&str> = session.model_relation_names(1).into_iter().collect();
        let relations: HashMap<&str, ContentDigest> = names
            .iter()
            .map(|name| (*name, session.relation_digest(name)))
            .collect();
        session.model_key(&[0; 32], 1, &Vec::new(), &relations)
    };
    let before: ContentDigest = key(&session);
    session
        .available_nullability
        .set_default("stg_orders", pairs(&[("order_id", "non_null")]));

    assert_ne!(key(&session), before);
}

fn family() -> DynamicFamily {
    DynamicFamily {
        name: "amounts".to_owned(),
        pivot_column: "status".to_owned(),
        value_column: "amount".to_owned(),
        aggregate: "SUM".to_owned(),
        data_type: "DOUBLE".to_owned(),
        name_pattern: None,
    }
}
