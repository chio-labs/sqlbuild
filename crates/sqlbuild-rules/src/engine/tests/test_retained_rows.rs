use tempfile::TempDir;

use crate::engine::_helpers::evaluation::STRIPPED_ROW_MISSED;
use crate::engine::main::evaluate_rows::evaluate_rows;
use crate::engine::tests::helpers::{
    evaluation_summary, orders_models, restored_rows, speculative_rows_request,
};
use crate::engine::tests::test_types::RetainedRowsTestCase;
use crate::errors::RowsError;
use crate::models::{EvaluateRequest, Fault, RetainedRows, RowsEvaluation, RowsRequest};

#[test]
fn given_retained_rows_when_evaluating_without_sql_then_only_cached_findings_stand_in()
-> Result<(), String> {
    let test_cases = [
        RetainedRowsTestCase {
            description: "the findings cached by the retaining evaluation stand in",
            fresh_cache: false,
            expected_same_findings: true,
            expected_missed: None,
        },
        RetainedRowsTestCase {
            description: "without cached findings a stripped row is refused",
            fresh_cache: true,
            expected_same_findings: false,
            expected_missed: Some(STRIPPED_ROW_MISSED),
        },
    ];
    for test_case in test_cases {
        let project_dir = TempDir::new().map_err(|error| error.to_string())?;
        let mut request: RowsRequest =
            speculative_rows_request(project_dir.path(), true, &orders_models())?;
        request.memo = None;
        request.retain = true;
        let first = evaluate_rows(request).map_err(|_| "first evaluation failed".to_owned())?;
        let retained: RetainedRows = first.retained.clone().ok_or("nothing was retained")?;
        let kept: EvaluateRequest = serde_json::from_slice(&retained.request_json)
            .map_err(|error| format!("the retained request does not decode: {error}"))?;
        let other_dir = TempDir::new().map_err(|error| error.to_string())?;
        let mut stripped: EvaluateRequest = restored_rows(&retained)?;
        stripped.project_dir = [project_dir.path(), other_dir.path()]
            [usize::from(test_case.fresh_cache)]
        .to_string_lossy()
        .into_owned();

        let evaluated: Result<RowsEvaluation, RowsError> = evaluate_rows(RowsRequest {
            request: stripped,
            memo: None,
            retain: false,
        });

        assert_eq!(
            retained.digests.len(),
            kept.models.len(),
            "{}",
            test_case.description
        );
        assert!(
            kept.models
                .iter()
                .all(|model| model.query_sql.is_empty() && model.authored_sql.is_empty()),
            "{}",
            test_case.description
        );
        let findings: Option<Vec<Fault>> = match &evaluated {
            Ok(evaluation) => Some(evaluation_summary(evaluation).0),
            Err(_refused) => None,
        };
        assert_eq!(
            findings == Some(evaluation_summary(&first).0),
            test_case.expected_same_findings,
            "{}",
            test_case.description
        );
        let missed: Option<&str> = match &evaluated {
            Err(RowsError::Rules(message)) => Some(message.as_str()),
            _ => None,
        };
        assert_eq!(
            missed, test_case.expected_missed,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
