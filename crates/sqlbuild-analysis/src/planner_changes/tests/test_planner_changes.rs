use crate::planner_changes::main::detect_schema_changes::detect_schema_changes;
use crate::planner_changes::main::metadata_changes::metadata_changes;
use crate::planner_changes::main::model_backfill::model_backfill;
use crate::planner_changes::main::model_change_kind::model_change_kind;
use crate::planner_changes::main::origin_reference_names::origin_reference_names;
use crate::planner_changes::main::recorded_declared_columns_hash::recorded_declared_columns_hash;
use crate::planner_changes::main::replay_policy_needed::replay_policy_needed;
use crate::planner_changes::main::resolve_replay_on_change::resolve_replay_on_change;
use crate::planner_changes::main::with_declared_columns_hash::with_declared_columns_hash;
use crate::planner_changes::main::without_declared_columns_hash::without_declared_columns_hash;
use crate::planner_changes::models::{
    BackfillAction, BackfillFacts, ChangeKind, NameSpan, RenameCandidate, SchemaChangeKind,
    SchemaColumnSource, SchemaColumns, SchemaComparison,
};
use crate::planner_changes::tests::helpers::{backfill, finding, pairs, quoted_span, types_equal};
use crate::planner_changes::tests::test_types::{
    DecisionTestCase, MetadataChangesTestCase, MetadataTextTestCase, OriginTestCase,
    ReplayTestCase, SchemaTestCase,
};

#[test]
fn given_replay_policy_when_resolving_then_matches_python_parsing() {
    let test_cases = [
        ReplayTestCase {
            description: "absent",
            raw: None,
            expected_backfill: Ok(backfill(BackfillAction::ForwardOnly, None)),
        },
        ReplayTestCase {
            description: "forward",
            raw: Some("forward"),
            expected_backfill: Ok(backfill(BackfillAction::ForwardOnly, None)),
        },
        ReplayTestCase {
            description: "full",
            raw: Some("full"),
            expected_backfill: Ok(backfill(BackfillAction::Full, None)),
        },
        ReplayTestCase {
            description: "bounded with spaces",
            raw: Some("bounded- 7d "),
            expected_backfill: Ok(backfill(BackfillAction::Bounded, Some("7d"))),
        },
        ReplayTestCase {
            description: "bounded before a final newline",
            raw: Some("bounded-3d\n"),
            expected_backfill: Ok(backfill(BackfillAction::Bounded, Some("3d"))),
        },
        ReplayTestCase {
            description: "unknown",
            raw: Some("forward_only"),
            expected_backfill: Err("unknown replay_on_change 'forward_only'".to_owned()),
        },
        ReplayTestCase {
            description: "bounded without a duration",
            raw: Some("bounded-"),
            expected_backfill: Err("unknown replay_on_change 'bounded-'".to_owned()),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            resolve_replay_on_change(test_case.raw).map_err(|error| error.message()),
            test_case.expected_backfill,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_metadata_json_when_recording_declared_columns_then_writes_python_json() {
    let test_cases = [
        MetadataTextTestCase {
            description: "unsorted object with unicode and numbers",
            metadata_json: r#"{"model_name": "orders", "config": {"b": 1.0, "a": "café"}, "n": 10}"#,
            expected_with_hash: r#"{"config":{"a":"caf\u00e9","b":1.0},"declared_columns_hash":"h1","model_name":"orders","n":10}"#,
            expected_without_hash: r#"{"model_name": "orders", "config": {"b": 1.0, "a": "café"}, "n": 10}"#,
            expected_recorded_hash: None,
        },
        MetadataTextTestCase {
            description: "existing hash",
            metadata_json: r#"{"declared_columns_hash":"h0","x":[1,2]}"#,
            expected_with_hash: r#"{"declared_columns_hash":"h1","x":[1,2]}"#,
            expected_without_hash: r#"{"x":[1,2]}"#,
            expected_recorded_hash: Some("h0"),
        },
        MetadataTextTestCase {
            description: "not an object",
            metadata_json: "[1]",
            expected_with_hash: "[1]",
            expected_without_hash: "[1]",
            expected_recorded_hash: None,
        },
        MetadataTextTestCase {
            description: "not JSON",
            metadata_json: "{oops",
            expected_with_hash: "{oops",
            expected_without_hash: "{oops",
            expected_recorded_hash: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            (
                with_declared_columns_hash(test_case.metadata_json, "h1"),
                without_declared_columns_hash(test_case.metadata_json),
                recorded_declared_columns_hash(Some(test_case.metadata_json)),
            ),
            (
                test_case.expected_with_hash.to_owned(),
                test_case.expected_without_hash.to_owned(),
                test_case.expected_recorded_hash.map(str::to_owned),
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_recorded_metadata_when_comparing_then_reports_function_and_config_changes() {
    let test_cases = [
        MetadataChangesTestCase {
            description: "no recorded metadata",
            current: r#"{"config":{"materialized":"table"}}"#,
            recorded: None,
            origin_names: None,
            expected_functions: Vec::new(),
            expected_config_changed: false,
        },
        MetadataChangesTestCase {
            description: "audit gate and declared columns are ignored, numbers compare by value",
            current: r#"{"config":{"batch":1},"audit_gate":{"a":1},"declared_columns_hash":"x"}"#,
            recorded: Some(r#"{"config":{"batch":1.0},"declared_columns_hash":"y"}"#),
            origin_names: None,
            expected_functions: Vec::new(),
            expected_config_changed: false,
        },
        MetadataChangesTestCase {
            description: "config change",
            current: r#"{"config":{"materialized":"view"}}"#,
            recorded: Some(r#"{"config":{"materialized":"table"}}"#),
            origin_names: None,
            expected_functions: Vec::new(),
            expected_config_changed: true,
        },
        MetadataChangesTestCase {
            description: "only function hashes changed",
            current: r#"{"config":{},"local_function_hashes":{"zeta":"2","alpha":"2","new":"1"}}"#,
            recorded: Some(r#"{"config":{},"local_function_hashes":{"zeta":"1","alpha":"1"}}"#),
            origin_names: None,
            expected_functions: vec!["alpha".to_owned(), "zeta".to_owned()],
            expected_config_changed: false,
        },
        MetadataChangesTestCase {
            description: "renamed cursor input named by its origin",
            current: r#"{"config":{"cursor_inputs":{"orders_v2":"ordered_at"}}}"#,
            recorded: Some(r#"{"config":{"cursor_inputs":{"orders":"ordered_at"}}}"#),
            origin_names: Some(pairs(&[("orders_v2", "orders")])),
            expected_functions: Vec::new(),
            expected_config_changed: false,
        },
    ];
    for test_case in test_cases {
        let changes = metadata_changes(
            (test_case.current, test_case.recorded),
            test_case.origin_names.as_deref(),
            true,
        );
        assert_eq!(
            (changes.changed_functions, changes.config_changed),
            (
                test_case.expected_functions,
                test_case.expected_config_changed
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_change_facts_when_deciding_then_kind_and_backfill_follow_precedence() {
    let test_cases = [
        DecisionTestCase {
            description: "query change replays the policy",
            facts: BackfillFacts {
                query_changed: true,
                schema_changed: true,
                ..BackfillFacts::default()
            },
            replay_on_change: Some("bounded-2d"),
            expected_kind: ChangeKind::QueryChanged,
            expected_backfill: backfill(BackfillAction::Bounded, Some("2d")),
        },
        DecisionTestCase {
            description: "schema drift alone stays forward",
            facts: BackfillFacts {
                schema_changed: true,
                config_changed: false,
                ..BackfillFacts::default()
            },
            replay_on_change: Some("full"),
            expected_kind: ChangeKind::SchemaChanged,
            expected_backfill: backfill(BackfillAction::ForwardOnly, None),
        },
        DecisionTestCase {
            description: "schema findings with a config change replay",
            facts: BackfillFacts {
                schema_changed: true,
                config_changed: true,
                ..BackfillFacts::default()
            },
            replay_on_change: Some("full"),
            expected_kind: ChangeKind::SchemaChanged,
            expected_backfill: backfill(BackfillAction::Full, None),
        },
        DecisionTestCase {
            description: "config change alone",
            facts: BackfillFacts {
                config_changed: true,
                ..BackfillFacts::default()
            },
            replay_on_change: Some("full"),
            expected_kind: ChangeKind::ConfigChanged,
            expected_backfill: backfill(BackfillAction::ForwardOnly, None),
        },
        DecisionTestCase {
            description: "function change",
            facts: BackfillFacts {
                functions_changed: true,
                ..BackfillFacts::default()
            },
            replay_on_change: None,
            expected_kind: ChangeKind::FunctionChanged,
            expected_backfill: backfill(BackfillAction::ForwardOnly, None),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            (
                model_change_kind(test_case.facts),
                model_backfill(
                    test_case.facts,
                    replay_policy_needed(test_case.facts)
                        .then(|| resolve_replay_on_change(test_case.replay_on_change).ok())
                        .flatten(),
                )
            ),
            (test_case.expected_kind, test_case.expected_backfill),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_columns_when_comparing_schema_then_findings_keep_python_order() {
    let test_cases = [
        SchemaTestCase {
            description: "enforced declared columns, inferred extras and a removed column",
            columns: SchemaColumns {
                yml: pairs(&[("id", "INTEGER"), ("label", "TEXT")]),
                inferred: Some(vec![
                    ("id".to_owned(), Some("BIGINT".to_owned())),
                    ("amount".to_owned(), None),
                ]),
                warehouse: pairs(&[("id", "integer"), ("label", "INTEGER"), ("old", "TEXT")]),
            },
            comparison: SchemaComparison {
                type_enforcement: true,
                inferred_schema_complete: false,
                case_folding: false,
            },
            expected_findings: vec![
                finding(
                    (
                        SchemaChangeKind::ColumnTypeChanged,
                        "label",
                        SchemaColumnSource::Yml,
                    ),
                    Some("TEXT"),
                    Some("INTEGER"),
                ),
                finding(
                    (
                        SchemaChangeKind::ColumnAdded,
                        "amount",
                        SchemaColumnSource::SqlAnalysis,
                    ),
                    None,
                    None,
                ),
                finding(
                    (
                        SchemaChangeKind::ColumnRemoved,
                        "old",
                        SchemaColumnSource::Yml,
                    ),
                    None,
                    Some("TEXT"),
                ),
            ],
        },
        SchemaTestCase {
            description: "inferred columns first without enforcement, folded names",
            columns: SchemaColumns {
                yml: pairs(&[("ID", "INTEGER")]),
                inferred: Some(vec![("Label".to_owned(), Some("TEXT".to_owned()))]),
                warehouse: pairs(&[("id", "TEXT"), ("label", "TEXT"), ("extra_x", "INTEGER")]),
            },
            comparison: SchemaComparison {
                type_enforcement: false,
                inferred_schema_complete: true,
                case_folding: true,
            },
            expected_findings: vec![
                finding(
                    (
                        SchemaChangeKind::ColumnTypeChanged,
                        "id",
                        SchemaColumnSource::Yml,
                    ),
                    Some("INTEGER"),
                    Some("TEXT"),
                ),
                finding(
                    (
                        SchemaChangeKind::ColumnTypeChanged,
                        "extra_x",
                        SchemaColumnSource::Yml,
                    ),
                    Some("TEXT"),
                    Some("INTEGER"),
                ),
            ],
        },
    ];
    for test_case in test_cases {
        let mut equal = types_equal;
        let mut family = |name: &str| -> Result<Option<String>, ()> {
            Ok(name.starts_with("extra_").then(|| "TEXT".to_owned()))
        };
        let findings = detect_schema_changes(
            test_case.columns,
            test_case.comparison,
            (&mut equal, &mut family),
        );
        assert_eq!(
            findings,
            Ok(test_case.expected_findings),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_renamed_references_when_matching_then_returns_origin_mapping() {
    let test_cases = [
        OriginTestCase {
            description: "one renamed reference",
            query_sql: r#"SELECT * FROM __ref("orders_v2") JOIN __ref("customers")"#,
            recorded_query: r#"SELECT * FROM __ref("orders") JOIN __ref("customers")"#,
            renames: vec![("orders_v2", "orders", true)],
            span_names: vec!["orders_v2"],
            expected_mapping: Some(pairs(&[("orders_v2", "orders")])),
        },
        OriginTestCase {
            description: "chained renames reach the oldest name",
            query_sql: r#"SELECT * FROM __ref("orders_v3")"#,
            recorded_query: r#"SELECT * FROM __ref("orders")"#,
            renames: vec![
                ("orders_v3", "orders_v2", true),
                ("orders_v2", "orders", true),
            ],
            span_names: vec!["orders_v3"],
            expected_mapping: Some(pairs(&[("orders_v3", "orders")])),
        },
        OriginTestCase {
            description: "rename recorded after the build does not apply",
            query_sql: r#"SELECT * FROM __ref("orders_v2")"#,
            recorded_query: r#"SELECT * FROM __ref("orders")"#,
            renames: vec![("orders_v2", "orders", false)],
            span_names: vec!["orders_v2"],
            expected_mapping: None,
        },
        OriginTestCase {
            description: "other edits are not a rename",
            query_sql: r#"SELECT id FROM __ref("orders_v2")"#,
            recorded_query: r#"SELECT * FROM __ref("orders")"#,
            renames: vec![("orders_v2", "orders", true)],
            span_names: vec!["orders_v2"],
            expected_mapping: None,
        },
    ];
    for test_case in test_cases {
        let renames: Vec<RenameCandidate> = test_case
            .renames
            .iter()
            .map(|(new_name, origin_name, applies)| RenameCandidate {
                new_name: (*new_name).to_owned(),
                origin_name: (*origin_name).to_owned(),
                applies: *applies,
            })
            .collect();
        let found: Vec<NameSpan> = test_case
            .span_names
            .iter()
            .map(|name| quoted_span(test_case.query_sql, name))
            .collect();
        let mut spans = |_: &std::collections::BTreeSet<String>| -> Result<Vec<NameSpan>, ()> {
            Ok(found.clone())
        };
        let mut hash = |text: &str| -> Result<String, ()> { Ok(text.to_owned()) };
        assert_eq!(
            origin_reference_names(
                (test_case.query_sql, test_case.recorded_query),
                &renames,
                (&mut spans, &mut hash),
            ),
            Ok(test_case.expected_mapping),
            "{}",
            test_case.description
        );
    }
}
