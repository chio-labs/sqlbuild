use tempfile::TempDir;

use crate::engine::_helpers::evaluation::STRIPPED_ROW_MISSED;
use crate::engine::main::evaluate_rows::evaluate_rows;
use crate::engine::tests::helpers::{evaluation_summary, orders_models, speculative_rows_request};
use crate::errors::RowsError;
use crate::models::{EvaluateRequest, RetainedRows, RowsRequest};

/// The retained request with each row's digest restored, as a delta compile rebuilds it.
fn restored(retained: &RetainedRows) -> Result<EvaluateRequest, String> {
    let mut request: EvaluateRequest = serde_json::from_slice(&retained.request_json)
        .map_err(|error| format!("the retained request does not decode: {error}"))?;
    for (model, digest) in request.models.iter_mut().zip(&retained.digests) {
        model.payload_digest = Some(digest.clone());
        model.stripped = true;
    }
    Ok(request)
}

#[test]
fn given_retained_rows_when_evaluating_without_sql_then_only_cached_findings_stand_in()
-> Result<(), String> {
    let project_dir = TempDir::new().map_err(|error| error.to_string())?;
    let mut request: RowsRequest =
        speculative_rows_request(project_dir.path(), true, &orders_models())?;
    request.memo = None;
    request.retain = true;
    let first = evaluate_rows(request).map_err(|_| "first evaluation failed".to_owned())?;
    let retained: RetainedRows = first.retained.clone().ok_or("nothing was retained")?;
    let kept: EvaluateRequest = serde_json::from_slice(&retained.request_json)
        .map_err(|error| format!("the retained request does not decode: {error}"))?;
    assert_eq!(retained.digests.len(), kept.models.len());
    assert!(
        kept.models
            .iter()
            .all(|model| model.query_sql.is_empty() && model.authored_sql.is_empty())
    );

    let cached = evaluate_rows(RowsRequest {
        request: restored(&retained)?,
        memo: None,
        retain: false,
    })
    .map_err(|_| "cached evaluation failed".to_owned())?;
    assert_eq!(evaluation_summary(&cached).0, evaluation_summary(&first).0);

    let uncached_dir = TempDir::new().map_err(|error| error.to_string())?;
    let mut uncached: EvaluateRequest = restored(&retained)?;
    uncached.project_dir = uncached_dir.path().to_string_lossy().into_owned();
    let missed = evaluate_rows(RowsRequest {
        request: uncached,
        memo: None,
        retain: false,
    });
    assert!(
        matches!(&missed, Err(RowsError::Rules(message)) if message == STRIPPED_ROW_MISSED),
        "a stripped row evaluated without its cached findings"
    );
    Ok(())
}
