//! Evaluate a natively built rules request, reusing the last identical request's response.

use std::path::{Path, PathBuf};

use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::constants::{API_VERSION, NATIVE_ROWS_MEMO_VERSION};
use crate::engine::_helpers::evaluation::evaluate_request;
use crate::errors::RowsError;
use crate::models::{EvaluateRequest, Model, RowsEvaluation, RowsRequest};

pub(crate) fn evaluate_rows(rows: RowsRequest) -> Result<RowsEvaluation, RowsError> {
    let RowsRequest { mut request, memo } = rows;
    let models: Vec<Model> = std::mem::take(&mut request.models)
        .into_iter()
        .map(digested)
        .collect::<Result<_, _>>()?;
    let identity: Option<(String, PathBuf)> = match memo {
        Some((code_identity, path)) => Some((identity(&request, &models, &code_identity)?, path)),
        None => None,
    };
    let reused: Option<String> = identity
        .as_ref()
        .and_then(|(identity, path)| read_response(path, identity));
    let (response, was_reused): (String, bool) = match reused {
        Some(response) => (response, true),
        None => {
            request.models = models;
            let response: String = evaluate_request(request).map_err(RowsError::Rules)?;
            if let Some((identity, path)) = &identity {
                write_response(path, identity, &response).map_err(RowsError::Io)?;
            }
            (response, false)
        }
    };
    decode(&response, was_reused)
}

/// `model` with the digest of its exact facts, which keys its cached findings.
fn digested(mut model: Model) -> Result<Model, RowsError> {
    let bytes: Vec<u8> = serde_json::to_vec(&model).map_err(rules_error)?;
    model.payload_digest = Some(format!("{:x}", Sha256::digest(&bytes)));
    Ok(model)
}

/// The memo version, build, model-free request and every model's digest, in order.
fn identity(
    request: &EvaluateRequest,
    models: &[Model],
    code_identity: &str,
) -> Result<String, RowsError> {
    let mut hasher: Sha256 = Sha256::new();
    for part in [NATIVE_ROWS_MEMO_VERSION, code_identity] {
        hasher.update(part.as_bytes());
        hasher.update(b"\0");
    }
    hasher.update(serde_json::to_vec(request).map_err(rules_error)?);
    hasher.update(b"\0");
    hasher.update((models.len() as u64).to_le_bytes());
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
    Ok(format!("{:x}", hasher.finalize()))
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
