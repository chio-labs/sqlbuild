use sqlbuild_cache::store::models::NativeStore;

use crate::assembly::analysis_session::models::SessionRequest;
use crate::assembly::analysis_session::tests::helpers::{
    cached_run, completed, described, model_requests, orders_request, shapes, started,
};
use crate::assembly::analysis_session::tests::test_types::{
    CachedRun, ModelSpec, TypedMarkerTestCase,
};

const STAGED: ModelSpec = (
    "staged",
    "SELECT * FROM __source(\"raw_orders\")",
    &["raw_orders"],
    &[],
);

/// The orders request over `sql` reading `staged`, as a fast-lineage compile of a contract sends it.
fn request(sql: &'static str) -> SessionRequest {
    let mut requests = model_requests(&[("typed", sql, &[], &["staged"]), STAGED]);
    requests[0].recover_cte_facts = true;
    let mut request: SessionRequest = orders_request(requests);
    request.rich_type_inference = false;
    let own = shapes(&[("typed", &[("v", "VARCHAR")])]);
    request.column_types.extend(own.clone());
    request.complete_schemas.extend(own);
    request
}

/// The described line of the first model's column `v`.
fn column_v(lines: &[Vec<String>]) -> String {
    lines[0]
        .iter()
        .find(|line| line.starts_with("v "))
        .cloned()
        .unwrap_or_else(|| format!("no v in {:?}", lines[0]))
}

const CASES: [TypedMarkerTestCase; 6] = [
    TypedMarkerTestCase {
        description: "an unknown body takes the asserted type",
        sql: "SELECT __polyglot_typed(bar(amount, 0, 10), 'VARCHAR') AS v FROM __ref(\"staged\")",
        expected_column: "v TEXT",
    },
    TypedMarkerTestCase {
        description: "a known body keeps its inferred type",
        sql: "SELECT __polyglot_typed(order_id, 'VARCHAR') AS v FROM __ref(\"staged\")",
        expected_column: "v INT ",
    },
    TypedMarkerTestCase {
        description: "a later set-operation branch types the union",
        sql: "SELECT CAST(NULL AS VARCHAR) AS v FROM __ref(\"staged\") UNION ALL \
              SELECT __polyglot_typed(bar(amount, 0, 10), 'VARCHAR') AS v FROM __ref(\"staged\")",
        expected_column: "v TEXT",
    },
    TypedMarkerTestCase {
        description: "a NULL body takes the asserted type in a union",
        sql: "SELECT CAST(NULL AS BIGINT) AS v FROM __ref(\"staged\") AS o UNION ALL \
              SELECT __polyglot_typed(NULL, 'BIGINT') AS v FROM __ref(\"staged\") AS o",
        expected_column: "v BIGINT",
    },
    TypedMarkerTestCase {
        description: "a CTE read by name",
        sql: "WITH c AS (SELECT __polyglot_typed(bar(amount, 0, 10), 'VARCHAR') AS v \
              FROM __ref(\"staged\")) SELECT v FROM c",
        expected_column: "v TEXT",
    },
    TypedMarkerTestCase {
        description: "an operand of a larger expression",
        sql: "SELECT COALESCE(__polyglot_typed(bar(amount, 0, 10), 'VARCHAR'), 'x') AS v \
              FROM __ref(\"staged\")",
        expected_column: "v TEXT",
    },
];

#[test]
fn given_typed_markers_when_analysing_then_each_call_has_its_asserted_or_inferred_type() {
    for test_case in CASES {
        let (_, outcomes, _) = completed(started(request(test_case.sql)));
        let lines: Vec<Vec<String>> = outcomes.iter().map(described).collect();
        assert!(
            column_v(&lines).starts_with(test_case.expected_column),
            "{}: {}",
            test_case.description,
            column_v(&lines)
        );
    }
}

#[test]
fn given_typed_markers_when_rerunning_from_the_cache_then_the_hit_matches_the_cold_run() {
    for test_case in CASES {
        let cold: CachedRun = cached_run(request(test_case.sql), NativeStore::default());
        let warm: CachedRun = cached_run(request(test_case.sql), cold.store);
        assert_eq!(warm.lines, cold.lines, "{}", test_case.description);
        assert!(
            warm.hits.iter().all(|hit| *hit),
            "{}: {:?}",
            test_case.description,
            warm.hits
        );
    }
}
