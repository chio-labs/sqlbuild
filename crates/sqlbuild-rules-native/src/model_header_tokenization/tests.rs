use super::main::{
    END_TOKEN, MAX_TOKENIZER_WORKERS, STRING_TOKEN, SYMBOL_TOKEN, TOKENIZER_WORKER_STACK_BYTES,
    WORD_TOKEN, build_tokenizer_pool, tokenize_batch,
};

#[test]
fn given_nested_authored_headers_when_tokenizing_batch_then_values_and_positions_are_preserved() {
    let headers = vec![
        " columns (café (type DECIMAL(10,2))), enabled true".to_owned(),
        "description \"Order \\\"total\\\"\", schema dev_${user}".to_owned(),
    ];

    let results = tokenize_batch(&headers).expect("worker pool builds");

    assert_eq!(results[0].1, None);
    assert_eq!(
        results[0].0.as_ref().expect("valid tokens"),
        &vec![
            (WORD_TOKEN, "columns".to_owned(), 1),
            (SYMBOL_TOKEN, "(".to_owned(), 9),
            (WORD_TOKEN, "café".to_owned(), 10),
            (SYMBOL_TOKEN, "(".to_owned(), 15),
            (WORD_TOKEN, "type".to_owned(), 16),
            (WORD_TOKEN, "DECIMAL".to_owned(), 21),
            (SYMBOL_TOKEN, "(".to_owned(), 28),
            (WORD_TOKEN, "10".to_owned(), 29),
            (SYMBOL_TOKEN, ",".to_owned(), 31),
            (WORD_TOKEN, "2".to_owned(), 32),
            (SYMBOL_TOKEN, ")".to_owned(), 33),
            (SYMBOL_TOKEN, ")".to_owned(), 34),
            (SYMBOL_TOKEN, ")".to_owned(), 35),
            (SYMBOL_TOKEN, ",".to_owned(), 36),
            (WORD_TOKEN, "enabled".to_owned(), 38),
            (WORD_TOKEN, "true".to_owned(), 46),
            (END_TOKEN, String::new(), 50),
        ]
    );
    let second = results[1].0.as_ref().expect("valid tokens");
    assert_eq!(second[1], (STRING_TOKEN, "Order \"total\"".to_owned(), 12));
    assert_eq!(second[4], (WORD_TOKEN, "dev_${user}".to_owned(), 38));
}

#[test]
fn given_invalid_headers_when_tokenizing_batch_then_each_exact_error_is_returned_in_order() {
    let headers = vec![
        "schema \"analytics".to_owned(),
        "schema analytics\"mart".to_owned(),
        "schema ${ENV".to_owned(),
    ];

    let results = tokenize_batch(&headers).expect("worker pool builds");

    assert_eq!(
        results
            .iter()
            .map(|result| result.1.as_deref())
            .collect::<Vec<_>>(),
        vec![
            Some("unterminated double-quoted string at position 7"),
            Some("unexpected double quote inside bare value at position 16; quote the whole value"),
            Some("unterminated template value at position 7"),
        ]
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
