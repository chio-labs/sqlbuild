//! Evaluate a natively built rules request, reusing the last identical request's response.

use std::cell::RefCell;
use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;

use serde_json::Value;

use crate::constants::{API_VERSION, NATIVE_ROWS_MEMO_VERSION};
use crate::engine::_helpers::cache::PendingBucketWrite;
use crate::engine::_helpers::evaluation::{EvaluationControl, evaluate_request_with};
use crate::errors::RowsError;
use crate::models::{EvaluateRequest, Model, RetainedRows, RowsEvaluation, RowsRequest};

/// A rows request whose models are digested, ready to evaluate once.
#[derive(Debug)]
pub(crate) struct PreparedRows {
    request: EvaluateRequest,
    /// The request's memo identity and memo path, when the rules cache is enabled.
    memo: Option<(String, PathBuf)>,
    /// The digest of every evaluation input the request carries, when it was asked for.
    pub(crate) key: Option<String>,
    /// The request kept for the project image, when it was asked for.
    pub(crate) retained: Option<RetainedRows>,
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
    let RowsRequest {
        mut request,
        memo,
        retain,
    } = rows;
    let digested_rows: Vec<(Model, Option<Vec<u8>>)> = std::mem::take(&mut request.models)
        .into_iter()
        .map(|model| digested(model, retain))
        .collect::<Result<_, _>>()?;
    let mut row_json: Vec<Vec<u8>> = Vec::new();
    let mut models: Vec<Model> = Vec::with_capacity(digested_rows.len());
    for (model, json) in digested_rows {
        models.push(model);
        row_json.extend(json);
    }
    let mut request_json: Option<Vec<u8>> = None;
    let memo: Option<(String, PathBuf)> = match memo {
        Some((code_identity, path)) => {
            let kept: Option<&mut Option<Vec<u8>>> = retain.then_some(&mut request_json);
            Some((identity(&request, &models, &code_identity, kept)?, path))
        }
        None => None,
    };
    let key: Option<String> = if keyed {
        Some(speculation_key(&request, &models, memo.as_ref())?)
    } else {
        None
    };
    let retained: Option<RetainedRows> = if retain {
        retained_rows(&request, &models, (request_json, row_json))
    } else {
        None
    };
    request.models = models;
    Ok(PreparedRows {
        request,
        memo,
        key,
        retained,
    })
}

const NO_SQL_KEYS: &str = "a retained model row has no SQL keys";
/// Where the model-free request's JSON holds its empty model list, which the rows fill.
const EMPTY_MODELS: &[u8] = b",\"models\":[],\"sql_tests\":";
const MODELS_KEY: &[u8] = b",\"models\":[";

/// `request` as JSON with each model's row as `prepare` serialized it for its digest, the SQL
/// text dropped; and each model's payload digest. `None` when it cannot be assembled.
fn retained_rows(
    request: &EvaluateRequest,
    models: &[Model],
    (request_json, row_json): (Option<Vec<u8>>, Vec<Vec<u8>>),
) -> Option<RetainedRows> {
    if row_json.len() != models.len() {
        return None;
    }
    let request_json: Vec<u8> = match request_json {
        Some(json) => json,
        None => serde_json::to_vec(request).ok()?,
    };
    let mut found = request_json
        .windows(EMPTY_MODELS.len())
        .enumerate()
        .filter(|(_, window)| *window == EMPTY_MODELS)
        .map(|(index, _)| index);
    let (Some(at), None) = (found.next(), found.next()) else {
        return None;
    };
    let rows: usize = row_json.iter().map(Vec::len).sum::<usize>() + row_json.len();
    let mut json: Vec<u8> = Vec::with_capacity(request_json.len() + rows);
    json.extend_from_slice(&request_json[..at]);
    json.extend_from_slice(MODELS_KEY);
    for (index, row) in row_json.iter().enumerate() {
        if index > 0 {
            json.push(b',');
        }
        json.extend_from_slice(row);
    }
    json.push(b']');
    json.extend_from_slice(&request_json[at + MODELS_KEY.len() + 1..]);
    Some(RetainedRows {
        request_json: without_derived_fields(json),
        digests: models
            .iter()
            .map(|model| model.payload_digest.clone().unwrap_or_default())
            .collect(),
    })
}

/// A model row's JSON with its `query_sql` and `authored_sql` text emptied.
///
/// They are the first string-valued keys after `name` and `relative_path`, and compact JSON
/// escapes every quote inside strings, so the first match of each key is that key.
fn without_sql(json: &[u8]) -> Option<Vec<u8>> {
    let mut kept: Vec<u8> = Vec::with_capacity(json.len());
    let mut copied: usize = 0;
    for key in [&b"\"query_sql\":\""[..], &b"\"authored_sql\":\""[..]] {
        let start: usize = copied + find(&json[copied..], key)? + key.len();
        let end: usize = start + string_end(&json[start..])?;
        kept.extend_from_slice(&json[copied..start]);
        copied = end;
    }
    kept.extend_from_slice(&json[copied..]);
    Some(kept)
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

/// The offset of the quote closing the JSON string whose text `bytes` starts with.
fn string_end(bytes: &[u8]) -> Option<usize> {
    let mut index: usize = 0;
    while index < bytes.len() {
        match bytes[index] {
            b'\\' => index += 2,
            b'"' => return Some(index),
            _ => index += 1,
        }
    }
    None
}

/// The prefix the keys of fields a request serializes but never reads back share; evaluation
/// derives them again.
const DERIVED_FIELD_PREFIX: &str = ",\"empty_input_only";
const DERIVED_FIELDS: [&str; 2] = ["_test_count\":", "\":"];

/// `json` without the derived fields, each a bare number or boolean after its key.
///
/// Compact JSON escapes every quote inside strings, so these keys only match as keys.
fn without_derived_fields(json: Vec<u8>) -> Vec<u8> {
    let Ok(text) = std::str::from_utf8(&json) else {
        return json;
    };
    let mut kept: Vec<u8> = Vec::with_capacity(json.len());
    let mut copied: usize = 0;
    for (start, _) in text.match_indices(DERIVED_FIELD_PREFIX) {
        if start < copied {
            continue;
        }
        let rest: &str = &text[start + DERIVED_FIELD_PREFIX.len()..];
        let Some(field) = DERIVED_FIELDS
            .iter()
            .find(|field| rest.starts_with(**field))
        else {
            continue;
        };
        let value: &str = &rest[field.len()..];
        let length: usize = value.find([',', '}']).unwrap_or(value.len());
        kept.extend_from_slice(&json[copied..start]);
        copied = start + DERIVED_FIELD_PREFIX.len() + field.len() + length;
    }
    kept.extend_from_slice(&json[copied..]);
    kept
}

/// Answer a prepared request from the memo or evaluate it, writing the cache and memo at once.
pub(crate) fn evaluate_prepared(prepared: PreparedRows) -> Result<RowsEvaluation, RowsError> {
    let PreparedRows {
        request,
        memo,
        retained,
        ..
    } = prepared;
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
    let mut evaluation: RowsEvaluation = decode(&response, was_reused)?;
    evaluation.retained = retained;
    Ok(evaluation)
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
            hasher.update(identity(request, models, "", None)?.as_bytes());
        }
    }
    Ok(hasher.finalize().to_hex().to_string())
}

/// `model` with the BLAKE3 digest of its exact facts, which keys its cached findings; with
/// `retain`, also its row as JSON without its SQL text.
fn digested(mut model: Model, retain: bool) -> Result<(Model, Option<Vec<u8>>), RowsError> {
    if model.payload_digest.is_some() {
        let json: Option<Vec<u8>> = if retain {
            let json: Vec<u8> = serde_json::to_vec(&model).map_err(rules_error)?;
            Some(without_sql(&json).ok_or_else(|| RowsError::Rules(NO_SQL_KEYS.to_owned()))?)
        } else {
            None
        };
        return Ok((model, json));
    }
    if !retain {
        let mut hasher: blake3::Hasher = blake3::Hasher::new();
        serde_json::to_writer(&mut hasher, &model).map_err(rules_error)?;
        model.payload_digest = Some(hasher.finalize().to_hex().to_string());
        return Ok((model, None));
    }
    let json: Vec<u8> = serde_json::to_vec(&model).map_err(rules_error)?;
    model.payload_digest = Some(blake3::hash(&json).to_hex().to_string());
    let stripped: Vec<u8> =
        without_sql(&json).ok_or_else(|| RowsError::Rules(NO_SQL_KEYS.to_owned()))?;
    Ok((model, Some(stripped)))
}

/// The memo version, build, model-free request and every model's digest, in order.
///
/// With `kept`, the model-free request's JSON is kept there as well.
fn identity(
    request: &EvaluateRequest,
    models: &[Model],
    code_identity: &str,
    kept: Option<&mut Option<Vec<u8>>>,
) -> Result<String, RowsError> {
    let mut hasher: blake3::Hasher = blake3::Hasher::new();
    for part in [NATIVE_ROWS_MEMO_VERSION, code_identity] {
        hasher.update(part.as_bytes());
        hasher.update(b"\0");
    }
    match kept {
        Some(kept) => {
            let json: Vec<u8> = serde_json::to_vec(request).map_err(rules_error)?;
            hasher.update(&json);
            *kept = Some(json);
        }
        None => serde_json::to_writer(&mut hasher, request).map_err(rules_error)?,
    }
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
