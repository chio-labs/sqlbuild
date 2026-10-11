use crate::macro_calls::main::call_class_store_text::call_class_store_text;
use crate::macro_calls::tests::test_types::CallClassStoreTextTestCase;

#[test]
fn given_call_class_inputs_when_naming_it_then_python_json_text_is_returned() {
    let test_cases = [
        CallClassStoreTextTestCase {
            description: "macros only",
            context_token: None,
            prior_relations: None,
            expected_text: r#"[["cents"],null,null]"#,
        },
        CallClassStoreTextTestCase {
            description: "no relations passed yet differs from no typed reference text",
            context_token: None,
            prior_relations: Some(&[]),
            expected_text: r#"[["cents"],null,[]]"#,
        },
        CallClassStoreTextTestCase {
            description: "relations and a context token",
            context_token: Some("ctx"),
            prior_relations: Some(&[("model", "orders")]),
            expected_text: r#"[["cents"],"ctx",[["model","orders"]]]"#,
        },
        CallClassStoreTextTestCase {
            description: "non-ASCII text is kept and quotes and control characters are escaped",
            context_token: Some("ü\"\n\u{1f}"),
            prior_relations: Some(&[("source", "café")]),
            expected_text: "[[\"cents\"],\"ü\\\"\\n\\u001f\",[[\"source\",\"café\"]]]",
        },
    ];

    for test_case in test_cases {
        let relations: Option<Vec<(String, String)>> = test_case.prior_relations.map(|items| {
            items
                .iter()
                .map(|(kind, name)| ((*kind).to_owned(), (*name).to_owned()))
                .collect()
        });
        assert_eq!(
            call_class_store_text(
                &["cents".to_owned()],
                test_case.context_token,
                relations.as_deref()
            ),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
