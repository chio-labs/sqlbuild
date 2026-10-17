use crate::assembly::analysis_session::main::contract_proof_json::contract_proof_json;
use crate::assembly::analysis_session::tests::test_types::ContractProofJsonTestCase;

use crate::assembly::analysis_session::models::{ColumnFact, ContractProof};

#[test]
fn given_contract_proof_when_encoding_then_matches_python_sorted_compact_json() {
    let test_cases = [
        ContractProofJsonTestCase {
            description: "a proven pivot escapes non-ASCII text as Python does",
            proof: ContractProof {
                output_proven: true,
                fixed_columns: vec![ColumnFact {
                    name: "a\u{e9}\"".to_owned(),
                    data_type: None,
                    nullability: "non_null".to_owned(),
                }],
                families: vec![("f".to_owned(), Some("INT".to_owned()))],
                input_relations: vec!["x".to_owned()],
                failure_reason: None,
                bare_dynamic_pivot: false,
            },
            expected_json: concat!(
                r#"{"bare_dynamic_pivot":false,"failure_reason":null,"#,
                r#""families":[{"inferred_type":"INT","name":"f"}],"#,
                r#""fixed_columns":[{"name":"a\u00e9\"","nullability":"non_null","type":null}],"#,
                r#""input_relations":["x"],"output_proven":true}"#
            ),
        },
        ContractProofJsonTestCase {
            description: "a failed proof keeps its reason and empty collections",
            proof: ContractProof {
                output_proven: false,
                fixed_columns: Vec::new(),
                families: vec![("g".to_owned(), None)],
                input_relations: Vec::new(),
                failure_reason: Some("no schema".to_owned()),
                bare_dynamic_pivot: true,
            },
            expected_json: concat!(
                r#"{"bare_dynamic_pivot":true,"failure_reason":"no schema","#,
                r#""families":[{"inferred_type":null,"name":"g"}],"fixed_columns":[],"#,
                r#""input_relations":[],"output_proven":false}"#
            ),
        },
    ];

    for test_case in test_cases {
        let json: String = contract_proof_json(&test_case.proof);

        assert_eq!(json, test_case.expected_json, "{}", test_case.description);
    }
}
