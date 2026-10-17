//! Evaluate a built rules request speculatively and answer the real request from it when identical.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender, channel};
use std::sync::{Arc, Mutex, PoisonError};
use std::time::Duration;

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::engine::_helpers::memo::{
    PreparedRows, SpeculativeOutcome, commit, evaluate_prepared, prepare, speculate,
};
use crate::models::{RowsRequest, SpeculativeAnswer, SpeculativeRows};

const SPECULATION_THREAD: &str = "sqlbuild-early-rules";
/// How often a wait for the speculative thread checks its stop flag.
const WAIT_POLL: Duration = Duration::from_millis(5);

/// What the speculative thread finished with: its held outcome, or `None` when preparing failed.
type Speculated = Result<Option<SpeculativeOutcome>, String>;

pub(crate) fn start(rows: RowsRequest) -> std::io::Result<SpeculativeRows> {
    let cancel: Arc<AtomicBool> = Arc::new(AtomicBool::new(false));
    let (sender, key): (Sender<Option<String>>, Receiver<Option<String>>) = channel();
    let stop: Arc<AtomicBool> = Arc::clone(&cancel);
    let thread = std::thread::Builder::new()
        .name(SPECULATION_THREAD.to_owned())
        .spawn(move || -> Speculated {
            catch_compiler_panic(|| {
                let Ok(prepared) = prepare(rows, true) else {
                    let _ = sender.send(None);
                    return Ok(None);
                };
                let _ = sender.send(prepared.key.clone());
                Ok(Some(speculate(prepared, &stop)))
            })
        })?;
    Ok(SpeculativeRows {
        key: Mutex::new(key),
        thread: Some(thread),
        cancel,
    })
}

pub(crate) fn answer(
    mut speculative: SpeculativeRows,
    rows: RowsRequest,
    stop: &AtomicBool,
) -> SpeculativeAnswer {
    let prepared: PreparedRows = match prepare(rows, true) {
        Ok(prepared) => prepared,
        Err(error) => {
            drop(speculative);
            return SpeculativeAnswer::Answered {
                evaluation: Err(error),
                used: false,
            };
        }
    };
    let Some(speculated) = speculated_key(&speculative, stop) else {
        drop(speculative);
        return SpeculativeAnswer::Stopped;
    };
    let outcome: Option<SpeculativeOutcome> =
        if prepared.key.is_some() && speculated == prepared.key {
            if !finished(&speculative, stop) {
                drop(speculative);
                return SpeculativeAnswer::Stopped;
            }
            match speculative.thread.take().map(std::thread::JoinHandle::join) {
                Some(Ok(Ok(outcome))) => outcome.filter(SpeculativeOutcome::evaluated_cleanly),
                _ => None,
            }
        } else {
            drop(speculative);
            None
        };
    match outcome {
        Some(outcome) => SpeculativeAnswer::Answered {
            evaluation: commit(outcome),
            used: true,
        },
        None => SpeculativeAnswer::Answered {
            evaluation: evaluate_prepared(prepared),
            used: false,
        },
    }
}

/// The speculation's key once known (`Some(None)` when it has none), or `None` once `stop` is set.
fn speculated_key(speculative: &SpeculativeRows, stop: &AtomicBool) -> Option<Option<String>> {
    let receiver = speculative
        .key
        .lock()
        .unwrap_or_else(PoisonError::into_inner);
    loop {
        if stop.load(Ordering::Acquire) {
            return None;
        }
        match receiver.recv_timeout(WAIT_POLL) {
            Ok(key) => return Some(key),
            Err(RecvTimeoutError::Disconnected) => return Some(None),
            Err(RecvTimeoutError::Timeout) => {}
        }
    }
}

/// Whether the speculative thread finished before `stop` was set.
fn finished(speculative: &SpeculativeRows, stop: &AtomicBool) -> bool {
    loop {
        if stop.load(Ordering::Acquire) {
            return false;
        }
        if speculative
            .thread
            .as_ref()
            .is_none_or(std::thread::JoinHandle::is_finished)
        {
            return true;
        }
        std::thread::sleep(WAIT_POLL);
    }
}

pub(crate) fn discard(speculative: SpeculativeRows) {
    drop(speculative);
}

impl Drop for SpeculativeRows {
    /// Cancel the speculation and wait for its thread.
    fn drop(&mut self) {
        self.cancel.store(true, Ordering::Release);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}
