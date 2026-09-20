use super::main::{
    AuthoredValue, MAX_TOKENIZER_WORKERS, TOKENIZER_WORKER_STACK_BYTES, build_tokenizer_pool,
    parse_batch,
};

#[test]
fn given_nested_authored_headers_when_parsing_batch_then_values_and_offsets_are_preserved() {
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
}

#[test]
fn given_invalid_headers_when_parsing_batch_then_each_exact_error_is_returned_in_order() {
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
}

#[test]
fn given_nested_and_root_columns_when_parsing_then_only_root_offsets_are_returned() {
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
}

#[test]
fn given_batch_sizes_when_building_pool_then_workers_are_bounded_by_contract() {
    for (header_count, expected_workers) in [(0, 1), (1, 1), (3, 3), (5, MAX_TOKENIZER_WORKERS)] {
        let pool = build_tokenizer_pool(header_count).expect("worker pool builds");
        assert_eq!(pool.current_num_threads(), expected_workers);
    }
    assert_eq!(TOKENIZER_WORKER_STACK_BYTES, 16 * 1024 * 1024);
}
