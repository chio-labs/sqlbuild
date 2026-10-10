use crate::assembly::analysis_session::models::{
    ColumnFact, ContractProof, ModelColumns, ModelColumnsInput, QueryColumns, SessionModelAnalysis,
};
use crate::assembly::analysis_session::tests::helpers::{
    column_view, contract_proof, fact_columns,
};
use crate::assembly::analysis_session::tests::test_types::ModelColumnsTestCase;

const ORDERS: &[(&str, &str)] = &[("id", "INTEGER"), ("amount", "DECIMAL")];
const PARSED: &[(&str, &str)] = &[("id", "BIGINT")];
const PIVOT: &[(&str, &str)] = &[("region", "VARCHAR"), ("north", "DECIMAL")];

#[test]
fn given_model_results_when_finalizing_columns_then_applies_python_order() {
    let test_cases = [
        ModelColumnsTestCase {
            description: "analysis disabled keeps no columns but still reports poisoned names",
            analysis_enabled: false,
            succeeded: false,
            session_columns: None,
            session_proof: None,
            fallback: None,
            standalone_proof: None,
            poisoned: &["id"],
            expected_columns: Ok((None, false)),
        },
        ModelColumnsTestCase {
            description: "a successful session keeps its columns and type recovery unsets poisoned types",
            analysis_enabled: true,
            succeeded: true,
            session_columns: Some(ORDERS),
            session_proof: None,
            fallback: None,
            standalone_proof: None,
            poisoned: &["amount"],
            expected_columns: Ok((Some(vec![("id", Some("INTEGER")), ("amount", None)]), false)),
        },
        ModelColumnsTestCase {
            description: "a failed session takes the parse fallback's columns",
            analysis_enabled: true,
            succeeded: false,
            session_columns: None,
            session_proof: None,
            fallback: Some(Some(PARSED)),
            standalone_proof: None,
            poisoned: &[],
            expected_columns: Ok((Some(vec![("id", Some("BIGINT"))]), false)),
        },
        ModelColumnsTestCase {
            description: "a failed session whose parse fallback infers nothing has no columns",
            analysis_enabled: true,
            succeeded: false,
            session_columns: None,
            session_proof: None,
            fallback: Some(None),
            standalone_proof: None,
            poisoned: &[],
            expected_columns: Ok((None, false)),
        },
        ModelColumnsTestCase {
            description: "a failed session without its parse fallback is an internal failure",
            analysis_enabled: true,
            succeeded: false,
            session_columns: None,
            session_proof: None,
            fallback: None,
            standalone_proof: None,
            poisoned: &[],
            expected_columns: Err("a failed session analysis without its parse fallback"),
        },
        ModelColumnsTestCase {
            description: "a proven session pivot replaces the parse fallback and forces a star",
            analysis_enabled: true,
            succeeded: false,
            session_columns: None,
            session_proof: Some((true, PIVOT)),
            fallback: Some(Some(PARSED)),
            standalone_proof: None,
            poisoned: &[],
            expected_columns: Ok((
                Some(vec![
                    ("region", Some("VARCHAR")),
                    ("north", Some("DECIMAL")),
                ]),
                true,
            )),
        },
        ModelColumnsTestCase {
            description: "an unproven session pivot keeps the analysed columns",
            analysis_enabled: true,
            succeeded: true,
            session_columns: Some(ORDERS),
            session_proof: Some((false, PIVOT)),
            fallback: None,
            standalone_proof: Some((true, PIVOT)),
            poisoned: &[],
            expected_columns: Ok((
                Some(vec![("id", Some("INTEGER")), ("amount", Some("DECIMAL"))]),
                false,
            )),
        },
        ModelColumnsTestCase {
            description: "a proven standalone pivot of an unanalysed model sets columns, then poisoning",
            analysis_enabled: false,
            succeeded: false,
            session_columns: None,
            session_proof: None,
            fallback: None,
            standalone_proof: Some((true, PIVOT)),
            poisoned: &["north"],
            expected_columns: Ok((
                Some(vec![("region", Some("VARCHAR")), ("north", None)]),
                true,
            )),
        },
    ];
    for test_case in test_cases {
        let session_columns: Option<Vec<ColumnFact>> = test_case.session_columns.map(fact_columns);
        let session_proof: Option<ContractProof> = test_case.session_proof.map(contract_proof);
        let fallback: Option<QueryColumns> = test_case.fallback.map(|parsed| QueryColumns {
            succeeded: parsed.is_some(),
            columns: parsed.map(fact_columns),
            has_star: false,
        });
        let standalone_proof: Option<ContractProof> =
            test_case.standalone_proof.map(contract_proof);
        let poisoned: Vec<String> = test_case
            .poisoned
            .iter()
            .map(|name| (*name).to_owned())
            .collect();
        let input = ModelColumnsInput {
            analysis_enabled: test_case.analysis_enabled,
            session: SessionModelAnalysis {
                succeeded: test_case.succeeded,
                columns: session_proof
                    .as_ref()
                    .filter(|proof| proof.output_proven)
                    .map(|proof| proof.fixed_columns.as_slice())
                    .or(session_columns.as_deref()),
                dynamic_proof: session_proof.as_ref(),
            },
            fallback: fallback.as_ref(),
            standalone_proof: standalone_proof.as_ref(),
            poisoned: &poisoned,
        };

        let finished: Result<ModelColumns, String> = input.model_columns();

        assert_eq!(
            finished.as_ref().map(column_view).map_err(String::as_str),
            test_case.expected_columns,
            "{}",
            test_case.description
        );
        assert!(
            finished.map_or(true, |finished| finished.unchecked == poisoned),
            "{}",
            test_case.description
        );
    }
}
