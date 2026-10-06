use crate::compiler::_helpers::model_headers::tokenization::{
    MAX_TOKENIZER_WORKERS, TOKENIZER_WORKER_STACK_BYTES, build_tokenizer_pool, parse_batch,
};
use crate::compiler::_helpers::sql_interpolation::substitution::{
    FALLBACK, SUBSTITUTED, UNCHANGED, substitute_batch,
};
use crate::compiler::_helpers::sql_references::extraction::extract;
use crate::compiler::models::AuthoredValue;

pub(crate) fn scalar_variables_preserve_lexical_boundaries() -> bool {
    let sqls = vec![
        "SELECT @@revision, '@@status', @@@window_start".to_owned(),
        "-- @@revision\nSELECT /* @@status */ 1".to_owned(),
        "SELECT '@@revision''s'".to_owned(),
    ];
    substitute_batch(
        &sqls,
        &[
            ("revision".to_owned(), "7".to_owned()),
            ("status".to_owned(), "ready".to_owned()),
        ],
    ) == vec![
        (
            SUBSTITUTED,
            Some("SELECT 7, 'ready', @@@window_start".to_owned()),
        ),
        (UNCHANGED, None),
        (SUBSTITUTED, Some("SELECT '7''s'".to_owned())),
    ]
}

pub(crate) fn dynamic_or_malformed_sql_requests_fallback() -> bool {
    let sqls = vec![
        "SELECT @@ENV:USER".to_owned(),
        "SELECT @@missing".to_owned(),
        "SELECT @@revision, 'unterminated".to_owned(),
        "SELECT @@revision /* unterminated".to_owned(),
        "SELECT @@révision".to_owned(),
    ];
    substitute_batch(&sqls, &[("revision".to_owned(), "7".to_owned())])
        == vec![(FALLBACK, None); sqls.len()]
}

pub(crate) fn simple_references_preserve_authored_order() -> bool {
    extract(
        "SELECT * FROM __source('orders') UNION ALL SELECT * FROM __dbt_ref(\"shop\", \"customers\")",
    ) == Some(vec![
        ("source".to_owned(), "orders".to_owned(), None, None),
        (
            "dbt_ref".to_owned(),
            "customers".to_owned(),
            Some("shop".to_owned()),
            None,
        ),
    ])
}

pub(crate) fn comments_and_quoted_text_hide_references() -> bool {
    extract("-- __ref(\"ignored\")\nSELECT '__seed(\"also_ignored\")' FROM __ref(orders)")
        == Some(vec![("ref".to_owned(), "orders".to_owned(), None, None)])
}

pub(crate) fn dollar_quoted_text_hides_references() -> bool {
    extract(concat!(
        "SELECT $$Customer's order -- __ref(\"ignored\") $5$$ AS label, ",
        "$tag$ $$ __seed(\"also_ignored\") $tag$ AS note, price$1$ ",
        "FROM __ref(orders)"
    )) == Some(vec![("ref".to_owned(), "orders".to_owned(), None, None)])
}

pub(crate) fn complex_or_malformed_sql_requests_fallback() -> bool {
    [
        "SELECT * FROM __table_fn(\"orders\")(1)",
        "SELECT * FROM __ref(concat('ord', 'ers'))",
        "SELECT * FROM __ref(\"orders\"",
        "SELECT * FROM __ref(\"orders\") /* unterminated",
        "SELECT * FROM __ref(\"orders\") WHERE note = 'unterminated",
        "SELECT * FROM __ref(\"orders\") WHERE note = $$unterminated",
        "SELECT * FROM __ref(örders)",
    ]
    .into_iter()
    .all(|sql| extract(sql).is_none())
}

pub(crate) fn nested_authored_headers_preserve_values_and_offsets() -> bool {
    let headers = vec![
        " columns (café (type DECIMAL(10,2))), enabled true".to_owned(),
        "constants (_countries {FR, GB}, _size constant(value 2))".to_owned(),
    ];
    let results = parse_batch(&headers).expect("worker pool builds");
    assert_eq!(results[0].2, None);
    assert_eq!(
        results[0].1.as_ref().expect("column offsets"),
        &vec![("café".to_owned(), 10, 4)]
    );
    assert_eq!(
        results[0].0,
        Some(AuthoredValue::Map(vec![
            (
                "columns".to_owned(),
                AuthoredValue::Map(vec![(
                    "café".to_owned(),
                    AuthoredValue::Map(vec![(
                        "type".to_owned(),
                        AuthoredValue::String("DECIMAL(10,2)".to_owned()),
                    )]),
                )]),
            ),
            ("enabled".to_owned(), AuthoredValue::Boolean(true)),
        ]))
    );
    assert!(matches!(
        results[1].0,
        Some(AuthoredValue::Map(ref values)) if values.len() == 1
    ));
    true
}

pub(crate) fn invalid_headers_return_each_exact_error_in_order() -> bool {
    let headers = vec![
        "schema \"analytics".to_owned(),
        "schema analytics\"mart".to_owned(),
        "schema ${ENV".to_owned(),
    ];
    let results = parse_batch(&headers).expect("worker pool builds");
    assert_eq!(
        results
            .iter()
            .map(|result| result.2.as_deref())
            .collect::<Vec<_>>(),
        vec![
            Some("unterminated double-quoted string at position 7"),
            Some("unexpected double quote inside bare value at position 16; quote the whole value"),
            Some("unterminated template value at position 7"),
        ]
    );
    true
}

pub(crate) fn header_comments_are_skipped_without_shifting_offsets() -> bool {
    let headers = vec![
        "materialized table -- keep model metadata\n  columns (id ()) /* it's, (fine) */"
            .to_owned(),
        "materialized table--trailing note\n".to_owned(),
        "materialized table /* unclosed".to_owned(),
    ];

    let results = parse_batch(&headers).expect("worker pool builds");

    let AuthoredValue::Map(values) = results[0].0.as_ref().expect("header values") else {
        panic!("header values must be a map");
    };
    assert_eq!(
        values
            .iter()
            .map(|(key, _)| key.as_str())
            .collect::<Vec<_>>(),
        vec!["materialized", "columns"]
    );
    assert_eq!(
        results[0].1.as_ref().expect("column offsets"),
        &vec![("id".to_owned(), 53, 2)]
    );
    let AuthoredValue::Map(values) = results[1].0.as_ref().expect("header values") else {
        panic!("header values must be a map");
    };
    assert_eq!(
        values
            .iter()
            .map(|(key, _)| key.as_str())
            .collect::<Vec<_>>(),
        vec!["materialized"]
    );
    assert_eq!(
        results[2].2.as_deref(),
        Some("unterminated block comment at position 19")
    );
    true
}

pub(crate) fn nested_and_root_columns_return_only_root_offsets() -> bool {
    let headers = vec![
        "config (columns (nested (type INTEGER))), columns (top (type INTEGER))".to_owned(),
        "config (columns (nested (type INTEGER)))".to_owned(),
    ];

    let results = parse_batch(&headers).expect("worker pool builds");

    assert_eq!(
        results[0].1.as_ref().expect("column offsets"),
        &vec![("top".to_owned(), 51, 3)]
    );
    assert_eq!(
        results[1].1.as_ref().expect("column offsets"),
        &Vec::<(String, usize, usize)>::new()
    );
    true
}

pub(crate) fn batch_sizes_bound_workers_by_contract() -> bool {
    for (header_count, expected_workers) in [(0, 1), (1, 1), (3, 3), (5, MAX_TOKENIZER_WORKERS)] {
        let pool = build_tokenizer_pool(header_count).expect("worker pool builds");
        assert_eq!(pool.current_num_threads(), expected_workers);
    }
    assert_eq!(TOKENIZER_WORKER_STACK_BYTES, 16 * 1024 * 1024);
    true
}
