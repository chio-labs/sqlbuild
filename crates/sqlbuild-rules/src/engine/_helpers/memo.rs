//! Evaluate a natively built rules request, reusing the last identical request's response.

use std::cell::RefCell;
use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;

use serde_json::Value;

use crate::constants::{API_VERSION, NATIVE_ROWS_MEMO_VERSION};
use crate::engine::_helpers::cache::PendingBucketWrite;
use crate::engine::_helpers::evaluation::{EvaluationControl, evaluate_request_with};
use crate::errors::RowsError;
use crate::models::{EvaluateRequest, Model, RowsEvaluation, RowsRequest};

/// A rows request whose models are digested, ready to evaluate once.
#[derive(Debug)]
pub(crate) struct PreparedRows {
    request: EvaluateRequest,
    /// The request's memo identity and memo path, when the rules cache is enabled.
    memo: Option<(String, PathBuf)>,
    /// The digest of every evaluation input the request carries, when it was asked for.
    pub(crate) key: Option<String>,
}

/// What a speculative evaluation found, with every write it would have made still pending.
#[derive(Debug)]
pub(crate) enum SpeculativeOutcome {
    /// The memo answered the request, so the evaluation would have written nothing.
    Reused(String),
    /// The request was evaluated; its bucket write precedes its memo write.
    Evaluated {
        bucket: Option<PendingBucketWrite>,
        response: Result<String, String>,
        memo: Option<(String, PathBuf)>,
    },
}

pub(crate) fn evaluate_rows(rows: RowsRequest) -> Result<RowsEvaluation, RowsError> {
    evaluate_prepared(prepare(rows, false)?)
}

/// Digest `rows`' models and derive its memo identity and, when asked, its speculation key.
pub(crate) fn prepare(rows: RowsRequest, keyed: bool) -> Result<PreparedRows, RowsError> {
    let RowsRequest { mut request, memo } = rows;
    let models: Vec<Model> = std::mem::take(&mut request.models)
        .into_iter()
        .map(digested)
        .collect::<Result<_, _>>()?;
    let memo: Option<(String, PathBuf)> = match memo {
        Some((code_identity, path)) => Some((identity(&request, &models, &code_identity)?, path)),
        None => None,
    };
    let key: Option<String> = if keyed {
        Some(speculation_key(&request, &models, memo.as_ref())?)
    } else {
        None
    };
    request.models = models;
    Ok(PreparedRows { request, memo, key })
}

/// Answer a prepared request from the memo or evaluate it, writing the cache and memo at once.
pub(crate) fn evaluate_prepared(prepared: PreparedRows) -> Result<RowsEvaluation, RowsError> {
    let PreparedRows { request, memo, .. } = prepared;
    let reused: Option<String> = memo
        .as_ref()
        .and_then(|(identity, path)| read_response(path, identity));
    let (response, was_reused): (String, bool) = match reused {
        Some(response) => (response, true),
        None => {
            let response: String = evaluate_request_with(request, &EvaluationControl::immediate())
                .map_err(RowsError::Rules)?;
            if let Some((identity, path)) = &memo {
                write_response(path, identity, &response).map_err(RowsError::Io)?;
            }
            (response, false)
        }
    };
    decode(&response, was_reused)
}

/// Evaluate a prepared request as `evaluate_prepared` does, holding every write it would make.
pub(crate) fn speculate(prepared: PreparedRows, cancel: &AtomicBool) -> SpeculativeOutcome {
    let PreparedRows { request, memo, .. } = prepared;
    if let Some(response) = memo
        .as_ref()
        .and_then(|(identity, path)| read_response(path, identity))
    {
        return SpeculativeOutcome::Reused(response);
    }
    let bucket: RefCell<Option<PendingBucketWrite>> = RefCell::new(None);
    let response: Result<String, String> = evaluate_request_with(
        request,
        &EvaluationControl {
            deferred_bucket: Some(&bucket),
            cancel: Some(cancel),
        },
    );
    let bucket: Option<PendingBucketWrite> = bucket.into_inner();
    SpeculativeOutcome::Evaluated {
        bucket,
        response,
        memo,
    }
}

/// Make a speculative evaluation's pending writes in order and answer as `evaluate_prepared` would.
impl SpeculativeOutcome {
    /// Whether the speculation produced a response, so a failure is retried by the real request.
    pub(crate) fn evaluated_cleanly(&self) -> bool {
        !matches!(
            self,
            Self::Evaluated {
                response: Err(_),
                ..
            }
        )
    }
}

pub(crate) fn commit(speculative: SpeculativeOutcome) -> Result<RowsEvaluation, RowsError> {
    match speculative {
        SpeculativeOutcome::Reused(response) => decode(&response, true),
        SpeculativeOutcome::Evaluated {
            bucket,
            response,
            memo,
        } => {
            if let Some(bucket) = &bucket {
                bucket.publish().map_err(RowsError::Rules)?;
            }
            let response: String = response.map_err(RowsError::Rules)?;
            if let Some((identity, path)) = &memo {
                write_response(path, identity, &response).map_err(RowsError::Io)?;
            }
            decode(&response, false)
        }
    }
}

/// Every evaluation input a request carries: its memo identity inputs and memo location.
fn speculation_key(
    request: &EvaluateRequest,
    models: &[Model],
    memo: Option<&(String, PathBuf)>,
) -> Result<String, RowsError> {
    let mut hasher: blake3::Hasher = blake3::Hasher::new();
    match memo {
        Some((identity, path)) => {
            hasher.update(b"memo\0");
            hasher.update(identity.as_bytes());
            hasher.update(b"\0");
            hasher.update(path.as_os_str().as_encoded_bytes());
        }
        None => {
            hasher.update(b"unmemoized\0");
            hasher.update(identity(request, models, "")?.as_bytes());
        }
    }
    Ok(hasher.finalize().to_hex().to_string())
}

/// `model` with the BLAKE3 digest of its exact facts, which keys its cached findings.
fn digested(mut model: Model) -> Result<Model, RowsError> {
    let mut hasher: blake3::Hasher = blake3::Hasher::new();
    serde_json::to_writer(&mut hasher, &model).map_err(rules_error)?;
    model.payload_digest = Some(hasher.finalize().to_hex().to_string());
    Ok(model)
}

/// The memo version, build, model-free request and every model's digest, in order.
fn identity(
    request: &EvaluateRequest,
    models: &[Model],
    code_identity: &str,
) -> Result<String, RowsError> {
    let mut hasher: blake3::Hasher = blake3::Hasher::new();
    for part in [NATIVE_ROWS_MEMO_VERSION, code_identity] {
        hasher.update(part.as_bytes());
        hasher.update(b"\0");
    }
    serde_json::to_writer(&mut hasher, request).map_err(rules_error)?;
    hasher.update(b"\0");
    hasher.update(&(models.len() as u64).to_le_bytes());
    for model in models {
        hasher.update(
            model
                .payload_digest
                .as_deref()
                .unwrap_or_default()
                .as_bytes(),
        );
        hasher.update(b"\0");
    }
    Ok(hasher.finalize().to_hex().to_string())
}

/// The stored response for exactly `identity`; an unreadable or foreign memo answers nothing.
fn read_response(path: &Path, identity: &str) -> Option<String> {
    let Ok(bytes) = std::fs::read(path) else {
        return None;
    };
    let Ok(stored) = serde_json::from_slice::<Value>(&bytes) else {
        return None;
    };
    if stored.get("identity")?.as_str()? != identity {
        return None;
    }
    stored.get("response")?.as_str().map(str::to_owned)
}

/// Atomically replace the memo with the latest evaluated request's response.
fn write_response(path: &Path, identity: &str, response: &str) -> Result<(), std::io::Error> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let temporary: PathBuf = path.with_extension(format!(
        "tmp-{}-{:?}",
        std::process::id(),
        std::thread::current().id()
    ));
    std::fs::write(
        &temporary,
        serde_json::to_vec(&serde_json::json!({"identity": identity, "response": response}))?,
    )?;
    std::fs::rename(&temporary, path)
}

fn decode(response: &str, reused: bool) -> Result<RowsEvaluation, RowsError> {
    let value: Value = serde_json::from_str(response).map_err(rules_error)?;
    if value.get("version").and_then(Value::as_u64) != Some(u64::from(API_VERSION)) {
        return Err(RowsError::Rules(
            "native rules engine returned an unsupported response version".to_owned(),
        ));
    }
    let mut evaluation: RowsEvaluation = serde_json::from_value(value).map_err(|_| {
        RowsError::Rules("native rules engine returned invalid findings".to_owned())
    })?;
    evaluation.reused = reused;
    Ok(evaluation)
}

fn rules_error(error: serde_json::Error) -> RowsError {
    RowsError::Rules(error.to_string())
}
